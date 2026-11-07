"""Measure real speech length of each take, with file-edge silence removed.

usage: measure.py SCENE.json TAKES_DIR FIRST_ID LAST_ID [--stem VOCALS.wav --stem-start SEC]

With a vocal stem it also reports where speech actually starts and ends in the
original around each line, because subtitle times are only approximate.
"""
import argparse
import glob
import json
import os
import subprocess

import numpy as np
import soundfile as sf

SR = 44100


def load_mono(path):
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32)


def speech_bounds(x, sr=SR, floor_db=-38.0, win=0.02):
    """First and last sample whose short-window level is within floor_db of the peak level."""
    n = int(win * sr)
    if len(x) < n:
        return 0, len(x)
    frames = len(x) // n
    rms = np.sqrt(np.mean(x[: frames * n].reshape(frames, n) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    on = np.where(db > max(db.max() + floor_db, -60))[0]
    if not len(on):
        return 0, 0
    return on[0] * n, min((on[-1] + 1) * n, len(x))


def latest_take(takes, line_id):
    found = [p for ext in ("mp3", "wav") for p in glob.glob(os.path.join(takes, f"{line_id}_*.{ext}"))]
    if not found:
        raise SystemExit(f"no take for line {line_id} in {takes}: run dialogue.py with --collect {takes} for the block that holds it, or take the line out of the scene")
    return max(found, key=os.path.getmtime)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("takes")
    ap.add_argument("first")
    ap.add_argument("last")
    ap.add_argument("--stem")
    ap.add_argument("--stem-start", type=float, default=0.0)
    a = ap.parse_args()

    stem = None
    if a.stem:
        y, sr = sf.read(a.stem, always_2d=True)
        stem, stem_sr = y.mean(axis=1), sr

    lines = [l for l in json.load(open(a.scene))["lines"] if int(a.first) <= int(l["id"]) <= int(a.last)]
    print("id  who       window  speech  ratio  next_gap  orig_on  orig_off  text")
    for i, l in enumerate(lines):
        x = load_mono(latest_take(a.takes, l["id"]))
        s, e = speech_bounds(x)
        speech = (e - s) / SR
        win = l["end"] - l["start"]
        gap = (lines[i + 1]["start"] - l["end"]) if i + 1 < len(lines) else float("nan")
        on, off = "", ""
        if stem is not None:
            lo = max(0, int((l["start"] - 0.4 - a.stem_start) * stem_sr))
            hi = int((l["end"] + 0.4 - a.stem_start) * stem_sr)
            ss, ee = speech_bounds(stem[lo:hi].astype(np.float32), sr=stem_sr, floor_db=-30.0)
            on = f"{(lo + ss) / stem_sr + a.stem_start:.2f}"
            off = f"{(lo + ee) / stem_sr + a.stem_start:.2f}"
        print(f"{l['id']}  {l['who']:<8} {win:5.2f}  {speech:5.2f}  {speech / win:5.2f}  {gap:7.2f}  {on:>7}  {off:>8}  {l['text']}", flush=True)


if __name__ == "__main__":
    main()
