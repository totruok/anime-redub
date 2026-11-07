"""Mix dub takes over the clean music/effects stem for one time window.

usage: mix_window.py CONFIG.json

Each take is trimmed to its speech, sped up by the line's tempo from the config,
matched in level to the original line, and placed at the original start. Prints
a placement table and warns about any line that runs into the next one.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(__file__))
from measure import latest_take, speech_bounds  # noqa: E402


def decode(path, sr):
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def stretch(x, sr, tempo):
    if abs(tempo - 1.0) < 0.005:
        return x
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        sf.write(a, x, sr, subtype="FLOAT")
        subprocess.run(["rubberband", "-3", "-F", "-q", "-T", str(tempo), a, b], check=True, capture_output=True)
        y, _ = sf.read(b, dtype="float32")
    return y if y.ndim == 1 else y.mean(axis=1)


def active_rms(x, sr, floor_db=-30.0):
    s, e = speech_bounds(x.astype(np.float32), sr=sr, floor_db=floor_db)
    x = x[s:e]
    n = int(0.02 * sr)
    if len(x) < n:
        return 1e-6
    frames = len(x) // n
    rms = np.sqrt(np.mean(x[: frames * n].reshape(frames, n) ** 2, axis=1) + 1e-12)
    return float(np.sqrt(np.mean(rms[rms > rms.max() * 0.25] ** 2)))


def room(sr, seconds=0.22, wet_db=-24.0):
    rng = np.random.default_rng(7)
    n = int(seconds * sr)
    ir = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
    ir /= np.sqrt(np.sum(ir**2))
    return ir * 10 ** (wet_db / 20)


def duck_envelope(placed, w0, n, sr, duck):
    """Music gain that follows the dub: down while it speaks, back up in the pauses, moving at fixed speeds."""
    rate = 100
    k = int(n / sr * rate) + 2
    active = np.zeros(k, dtype=bool)
    for _, a, b in placed:
        active[max(0, int((a - w0 - duck.get("lookahead", 0.1)) * rate)) : int((b - w0) * rate) + 1] = True
    depth = duck["depth_db"]
    down, up = -depth / (duck["attack"] * rate), -depth / (duck["release"] * rate)
    gain = np.zeros(k)
    g = 0.0
    for i in range(k):
        target = depth if active[i] else 0.0
        g = max(target, g - down) if g > target else min(target, g + up)
        gain[i] = g
    return (10 ** (np.interp(np.arange(n) / sr * rate, np.arange(k), gain) / 20)).astype(np.float32)


def main():
    cfg = json.load(open(sys.argv[1]))
    root = os.path.dirname(os.path.abspath(sys.argv[1]))
    p = lambda k: os.path.join(root, cfg[k])  # noqa: E731
    inst, sr = sf.read(p("instrumental"), always_2d=True, dtype="float32")
    voc, sr2 = sf.read(p("vocals"), always_2d=True, dtype="float32")
    assert sr == sr2
    stem0, w0, w1 = cfg["stem_start"], cfg["start"], cfg["end"]
    stem_end = stem0 + min(len(inst), len(voc)) / sr
    if w1 > stem_end:
        print(f"WARNING: the stems end at {stem_end:.2f} s, so the mix stops there and not at {w1:.2f} s")
        w1 = stem_end
    scene = json.load(open(p("scene")))
    lines = [l for l in scene["lines"] if str(l["id"]) in cfg["lines"]]
    voc_mono = voc.mean(axis=1)

    n = int((w1 - w0) * sr)
    dub = np.zeros(n, dtype=np.float32)
    by_who, refs = {}, {}
    mask = np.ones(n, dtype=np.float32)
    idx = lambda t: int((t - w0) * sr)  # noqa: E731
    rows, placed = [], []
    for l in lines:
        f = cfg["lines"][str(l["id"])]
        full = decode(latest_take(p("takes"), l["id"]), sr)
        s, e = speech_bounds(full, sr=sr)
        x = full[max(0, s - int(0.01 * sr)) : min(len(full), e + int(0.04 * sr))]
        whole = stretch(x, sr, f.get("tempo", 1.0))
        orig_on, orig_off = f.get("orig_on", l["start"]), f.get("orig_off", l["end"])
        src = voc_mono[int((orig_on - stem0) * sr) : int((orig_off - stem0) * sr)]
        gain_db = 20 * np.log10(active_rms(src, sr) / active_rms(whole, sr)) + f.get("gain_db", 0.0)
        gain_db = float(np.clip(gain_db, -30, 12))
        # A line may be cut at its internal pauses, each part placed on the original's own onset.
        # Part "from"/"to" are seconds counted from the first speech sample of the take.
        parts = f.get("parts") or [{"whole": True, "start": f.get("start", orig_on), "tempo": f.get("tempo", 1.0)}]
        for part in parts:
            if part.get("whole"):
                y = whole.copy()
            else:
                piece = full[s + int(part["from"] * sr) : min(len(full), s + int(part["to"] * sr))].copy()
                y = stretch(piece, sr, part.get("tempo", 1.0)).copy()
            y = y * 10 ** ((gain_db + part.get("gain_db", 0.0)) / 20)  # a part may be raised on its own
            fade = min(int(0.008 * sr), len(y) // 4)
            y[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
            y[-fade * 3 :] *= np.linspace(1, 0, fade * 3, dtype=np.float32)
            start = part["start"]
            i = idx(start)
            j = min(n, i + len(y))
            if i < 0:
                print(f"WARNING: a part of line {l['id']} starts before the window and is left out")
            else:
                dub[i:j] += y[: j - i]
                group = f"{l['who']}|{l.get('env', 'default')}"
                by_who.setdefault(group, np.zeros(n, dtype=np.float32))[i:j] += y[: j - i]
            end = start + len(y) / sr
            if end > w1:
                print(f"WARNING: line {l['id']} runs {end - w1:.2f} s past the end of the window and is cut: end the window in a pause")
            placed.append((l["id"], start, end))
            rows.append((l["id"], l["who"], orig_on, orig_off, start, end, part.get("tempo", 1.0), gain_db, l["text"]))
        refs.setdefault(f"{l['who']}|{l.get('env', 'default')}", []).append(src)
        a, b = max(0, idx(orig_on - 0.12)), min(n, idx(orig_off + 0.12))
        # Without voice_under_db the original line is removed; with it the line stays, lowered, under the dub.
        under_db = cfg.get("voice_under_db")
        mask[a:b] = 0.0 if under_db is None else 10 ** (under_db / 20)

    print("id who      orig_on orig_off | dub_on  dub_off  tail   tempo  gain  text")
    for r in rows:
        print(f"{r[0]} {r[1]:<8} {r[2]:7.2f} {r[3]:8.2f} | {r[4]:7.2f} {r[5]:8.2f} {r[5] - r[3]:+5.2f}  {r[6]:4.2f} {r[7]:+5.1f}  {r[8]}")
    for (a_id, _, a_end), (b_id, b_start, _) in zip(placed, placed[1:]):
        if a_end > b_start:
            print(f"WARNING: {a_id} runs {a_end - b_start:.2f}s into {b_id}")

    wet_db = cfg.get("room_wet_db")
    dub_wet = dub if wet_db is None else dub + np.convolve(dub, room(sr, wet_db=wet_db), mode="full")[: n]

    # Original vocal stem survives only outside dialogue, for breaths and grunts.
    kernel = int(0.03 * sr)
    mask = np.convolve(mask, np.ones(kernel) / kernel, mode="same")
    i0 = int((w0 - stem0) * sr)
    residual = voc[i0 : i0 + n] * mask[:, None] * cfg.get("residual_gain", 1.0)
    music = inst[i0 : i0 + n]
    if cfg.get("duck"):
        music = music * duck_envelope(placed, w0, n, sr, cfg["duck"])[: len(music), None]

    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "dub.wav")
        eq = os.path.join(d, "dub_eq.wav")
        sf.write(raw, dub_wet, sr, subtype="FLOAT")
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", raw, "-af",
             "highpass=f=110,lowpass=f=13000,equalizer=f=3400:t=q:w=1.2:g=-1.5", "-c:a", "pcm_f32le", eq],
            check=True,
        )
        dub_eq, _ = sf.read(eq, dtype="float32")
    if dub_eq.ndim > 1:
        dub_eq = dub_eq.mean(axis=1)
    if cfg.get("post"):
        import post_fx

        dub_eq = post_fx.process(by_who, refs, sr, cfg["post"])
    m = min(len(dub_eq), len(music), len(residual))
    # A voice-over usually lowers the whole original, voice and music alike, by one constant.
    original = 10 ** (cfg.get("original_gain_db", 0.0) / 20)
    mix = (music[:m] + residual[:m]) * original + dub_eq[:m, None]
    edge = int(0.12 * sr)
    env = np.ones(m, dtype=np.float32)
    env[:edge] = np.linspace(0, 1, edge)
    env[-edge:] = np.linspace(1, 0, edge)
    mix = mix * env[:, None]
    peak = float(np.max(np.abs(mix)))
    if peak > 0.97:
        mix *= 0.97 / peak
    out = os.path.join(root, cfg["out_dir"])
    os.makedirs(out, exist_ok=True)
    sf.write(os.path.join(out, "dub_mix.wav"), mix, sr, subtype="PCM_16")
    sf.write(os.path.join(out, "dub_only.wav"), dub_eq[:m], sr, subtype="PCM_16")
    sf.write(os.path.join(out, "residual_voice.wav"), residual[:m], sr, subtype="PCM_16")
    with open(os.path.join(out, "placement.json"), "w") as f:
        json.dump([{"id": r[0], "who": r[1], "start": r[4], "end": r[5], "text": r[8]} for r in rows], f, ensure_ascii=False, indent=1)
    print(f"peak before limit {peak:.2f}; wrote {out}/dub_mix.wav, {m / sr:.2f}s")
    res_rms = float(np.sqrt(np.mean(residual[:m] ** 2)))
    print(f"residual original voice level: {20 * np.log10(res_rms + 1e-9):.1f} dBFS")


if __name__ == "__main__":
    main()
