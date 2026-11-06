"""Check a finished mix by numbers: the balance it really has, and where the dub sinks into the music.

usage: check_levels.py MIX.json [--warn 6]

Spends nothing. It cannot say how a mix sounds, only where to listen. A whisper meant to be
quiet will be listed too, so a low margin is a place to check by ear, not a verdict.
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mix_window import duck_envelope  # noqa: E402


def rms_db(x):
    return float(20 * np.log10(np.sqrt(np.mean(x**2)) + 1e-9))


def top_db(x, sr):
    """Level of the loud part of a stretch, so the pauses inside a phrase do not count."""
    k = int(0.02 * sr)
    if len(x) < k:
        return rms_db(x)
    f = np.sqrt(np.mean(x[: (len(x) // k) * k].reshape(-1, k) ** 2, axis=1) + 1e-12)
    return float(20 * np.log10(np.sqrt(np.mean(f[f > f.max() * 0.25] ** 2))))


def margins(placement, dub, music, sr, w0):
    """Dub above what is left of the music, per placed part, in the voice band."""
    sos = signal.butter(4, [300 / (sr / 2), 3400 / (sr / 2)], btype="band", output="sos")
    d, m = signal.sosfilt(sos, dub), signal.sosfilt(sos, music)
    rows = []
    for p in placement:
        a, b = max(0, int((p["start"] - w0) * sr)), min(len(d), int((p["end"] - w0) * sr))
        if b - a < int(0.15 * sr):
            continue
        level, under = top_db(d[a:b], sr), rms_db(m[a:b])
        rows.append(dict(p, margin=level - under, dub=level, music=under))
    return rows


def clock(t):
    return f"{int(t) // 60}:{t % 60:05.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mix")
    ap.add_argument("--warn", type=float, default=6.0)
    a = ap.parse_args()
    cfg = json.load(open(a.mix, encoding="utf-8"))
    root = os.path.dirname(os.path.abspath(a.mix))
    path = lambda k: os.path.join(root, cfg[k])  # noqa: E731
    out = os.path.join(root, cfg["out_dir"])
    mix, sr = sf.read(os.path.join(out, "dub_mix.wav"), always_2d=True, dtype="float64")
    dub, _ = sf.read(os.path.join(out, "dub_only.wav"), dtype="float64")
    dub = dub if dub.ndim == 1 else dub.mean(axis=1)
    placement = json.load(open(os.path.join(out, "placement.json"), encoding="utf-8"))
    inst, _ = sf.read(path("instrumental"), always_2d=True, dtype="float64")
    voc, _ = sf.read(path("vocals"), always_2d=True, dtype="float64")
    w0, i0 = cfg["start"], int((cfg["start"] - cfg["stem_start"]) * sr)
    n = min(len(mix), len(dub), len(inst) - i0, len(voc) - i0)
    mix, dub, inst, voc = mix[:n], dub[:n], inst[i0 : i0 + n], voc[i0 : i0 + n]

    # 1. The balance: fit what is left without the dub onto the two stems, inside each original line.
    jp, mu = [], []
    for f in cfg["lines"].values():
        x, y = int((f["orig_on"] - w0 + 0.05) * sr), int((f["orig_off"] - w0 - 0.05) * sr)
        y = min(y, n)
        if y - x < int(0.1 * sr) or np.sum(voc[x:y] ** 2) < 1e-6:
            continue
        g = np.linalg.lstsq(np.array([voc[x:y].ravel(), inst[x:y].ravel()]).T, (mix[x:y] - dub[x:y, None]).ravel(), rcond=None)[0]
        jp.append(g[0])
        mu.append(g[1])
    if jp:
        to_db = lambda v: 20 * np.log10(np.abs(np.array(v)) + 1e-9)  # noqa: E731
        print(f"balance inside lines: original voice {np.median(to_db(jp)):.1f} dB, music {np.median(to_db(mu)):.1f} dB (n={len(jp)})")

    # 2. The dub above the music actually left under it.
    music = inst.mean(axis=1) * 10 ** (cfg.get("original_gain_db", 0.0) / 20)
    if cfg.get("duck"):
        music = music * duck_envelope([(p["id"], p["start"], p["end"]) for p in placement], w0, n, sr, cfg["duck"])[:n]
    rows = margins(placement, dub, music, sr, w0)
    print(f"{len(rows)} dub parts; dub above the music, voice band: median {np.median([r['margin'] for r in rows]):.1f} dB")
    low = sorted((r for r in rows if r["margin"] < a.warn), key=lambda r: r["margin"])
    print(f"parts under {a.warn:.0f} dB, listen to these: {len(low)}")
    print("margin  dub  music  time in the mix  who  text")
    for r in low:
        t = r["start"] - w0
        print(f"{r['margin']:5.1f} {r['dub']:6.1f} {r['music']:6.1f}  {clock(t)}-{clock(r['end'] - w0)}  {r['who']}  {r['text'][:70]}")


if __name__ == "__main__":
    main()
