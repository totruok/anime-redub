"""Find the real spoken phrases of every line in the isolated Japanese voice and measure them.

usage: scene_measure.py SCENE.json VOCALS.wav STEM_START OUT.json

Subtitle times are only anchors: the window around each line stops halfway to its
neighbours, and quiet bright bursts (armour, swords) are not treated as speech.
Results go to OUT.json and one line per dialogue line to stdout.
"""
import json
import sys

import librosa
import numpy as np
import soundfile as sf


MIN_LINES_FOR_LAG = 20  # shorter scenes gave false alarms


def phrases(x, sr, t0, a0, a1):
    n = int(0.02 * sr)
    frames = len(x) // n
    if frames < 3:
        return []
    fr = x[: frames * n].reshape(frames, n)
    db = 20 * np.log10(np.sqrt(np.mean(fr**2, axis=1)) + 1e-9)
    peak = db.max()
    on = db > max(peak - 28, -58)
    segs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            segs.append([s, i])
            s = None
    if s is not None:
        segs.append([s, frames])
    merged = []
    for a, b in segs:
        if merged and a - merged[-1][1] < 7:  # gaps under 140 ms are not phrase breaks
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        seg_peak = db[a:b].max()
        dur = (b - a) * 0.02
        t_on, t_off = t0 + a * 0.02, t0 + b * 0.02
        if dur < 0.06:
            continue
        # Inside the subtitle's span a quiet segment is speech: first words are often very soft.
        inside = t_on >= a0 - 0.20 and t_off <= a1 + 0.10
        if inside:
            if seg_peak < peak - 34:
                continue
        else:
            if seg_peak < peak - 22:
                continue
            chunk = x[a * n : b * n]
            centroid = float(np.mean(librosa.feature.spectral_centroid(y=chunk, sr=sr, n_fft=1024, hop_length=256)))
            if centroid > 3500 and seg_peak < peak - 8:  # bright and quiet: effect leaking into the stem
                continue
        if t_off < a0 - 0.35 or t_on > a1 + 0.35:
            continue
        out.append([round(t_on, 2), round(t_off, 2)])
    return out


def subtitle_lag(mono, sr, t0, lines, reach=15.0, step=0.05):
    """How far to move the subtitles so most of their time falls on speech: the shift in seconds, and the share gained."""
    n = int(step * sr)
    frames = len(mono) // n
    db = 20 * np.log10(np.sqrt(np.mean(mono[: frames * n].reshape(frames, n) ** 2, axis=1)) + 1e-9)
    voice = db > max(db.max() - 35, -60)
    subs = np.zeros(frames, dtype=bool)
    for l in lines:
        subs[max(0, int((l["start"] - t0) / step)) : max(0, int((l["end"] - t0) / step))] = True
    total = max(int(subs.sum()), 1)

    def overlap(shift):
        return int(np.sum(subs[max(-shift, 0) : frames - max(shift, 0)] & voice[max(shift, 0) : frames + min(shift, 0)]))

    reach_frames = min(int(reach / step), frames - 1)
    best = max(range(-reach_frames, reach_frames + 1), key=overlap)
    return best * step, (overlap(best) - overlap(0)) / total


def main():
    scene = json.load(open(sys.argv[1], encoding="utf-8"))
    voc, sr = sf.read(sys.argv[2], always_2d=True, dtype="float32")
    t0 = float(sys.argv[3])
    mono = voc.mean(axis=1)
    lines = scene["lines"]
    if len(lines) >= MIN_LINES_FOR_LAG:
        lag, gain = subtitle_lag(mono, sr, t0, lines)
        if abs(lag) >= 0.4 and gain >= 0.05:
            print(f"WARNING: subtitles sit about {lag:+.1f} s from the voice; they may not fit this rip. Add that to every start and end, and measure again.", flush=True)
    else:
        print(f"subtitle timing not checked: fewer than {MIN_LINES_FOR_LAG} lines", flush=True)
    res = {}
    for i, l in enumerate(lines):
        lo = l["start"] - 0.45 if i == 0 else max(l["start"] - 0.45, (lines[i - 1]["end"] + l["start"]) / 2)
        hi = l["end"] + 0.45 if i == len(lines) - 1 else min(l["end"] + 0.45, (l["end"] + lines[i + 1]["start"]) / 2)
        x = mono[int((lo - t0) * sr) : int((hi - t0) * sr)]
        ph = phrases(x, sr, lo, l["start"], l["end"])
        if ph:
            # noise before the anchor is not the onset, but never invert a short first phrase
            if l["start"] - 0.12 < ph[0][1] - 0.05:
                ph[0][0] = round(max(ph[0][0], l["start"] - 0.12), 2)
            if l["end"] + 0.25 > ph[-1][0] + 0.05:
                ph[-1][1] = round(min(ph[-1][1], l["end"] + 0.25), 2)
        else:
            ph = [[l["start"], l["end"]]]
        speech = np.concatenate([mono[int((a - t0) * sr) : int((b - t0) * sr)] for a, b in ph])
        rms = 20 * np.log10(np.sqrt(np.mean(speech**2)) + 1e-9)
        y = librosa.resample(speech, orig_sr=sr, target_sr=16000)
        f0, voiced, _ = librosa.pyin(y, fmin=70, fmax=700, sr=16000, frame_length=1024)
        f = f0[voiced & ~np.isnan(f0)]
        med = float(np.median(f)) if len(f) > 3 else None
        spread = float(12 * np.log2(np.percentile(f, 90) / np.percentile(f, 10))) if len(f) > 3 else None
        talk = sum(b - a for a, b in ph)
        res[l["id"]] = {
            "who": l["who"], "phrases": ph, "level": round(float(rms), 1),
            "f0": round(med) if med else None, "range": round(spread, 1) if spread is not None else None,
            "voiced": round(float(np.mean(voiced)), 2), "talk": round(talk, 2),
        }
        print(
            f"{l['id']} {l['who']:<8} lvl {rms:6.1f} f0 {str(res[l['id']]['f0']):>4} rng {str(res[l['id']]['range']):>5} "
            f"voiced {res[l['id']]['voiced']:4.2f} talk {talk:5.2f} {ph} | {l['text']}",
            flush=True,
        )
    json.dump(res, open(sys.argv[4], "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
