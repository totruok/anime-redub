"""Separate voice from music and effects in chunks, so a stop never loses finished work.

usage: separate.py SOURCE --track N --start S --end E --out DIR [--chunk 30] [--overlap 1]
                   [--model model_bs_roformer_ep_317_sdr_12.9755.ckpt] [--model-dir DIR]

The original-language track is decoded once, cut into overlapping chunks and each chunk
goes through audio-separator. A finished chunk is skipped on rerun; progress and the time
left are printed one line per chunk. The chunks are then joined with a short crossfade
into DIR/vocals.wav and DIR/instrumental.wav, and DIR/stems.json records the window.
A folder belongs to one set of settings: to change the window or the chunking, use a new one.

Roughly 5 minutes of computing per minute of audio on a laptop: run it in the
background. Runs locally, so it costs nothing.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

SR = 44100
DEFAULT_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"


def plan_chunks(n, sr, chunk, overlap):
    """Sample ranges to separate. Neighbours share 2*overlap seconds around each boundary."""
    step, lap = int(chunk * sr), int(overlap * sr)
    out, a = [], 0
    while a < n:
        b = a + step
        if n - b < step / 2:  # the separator does much worse on a very short chunk, so the last one takes the rest
            b = n
        out.append((max(0, a - lap), min(n, b + lap)))
        a = b
    return out


def stitch(parts, ranges, sr, overlap, n):
    """Join separated chunks. Inside each shared stretch the left chunk fades out as the right one fades in."""
    channels = parts[0].shape[1]
    y = np.zeros((n, channels), dtype=np.float32)
    lap = int(overlap * sr)
    for k, (part, (a, b)) in enumerate(zip(parts, ranges)):
        part = part[: b - a]
        gain = np.ones(len(part), dtype=np.float32)
        if k > 0:
            m = min(2 * lap, len(part))
            gain[:m] = np.linspace(0, 1, m, dtype=np.float32)
        if k < len(parts) - 1:
            m = min(2 * lap, len(part))
            gain[len(part) - m :] *= np.linspace(1, 0, m, dtype=np.float32)
        y[a : a + len(part)] += part * gain[:, None]
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--track", type=int, required=True, help="audio track number of the original language, as in -map 0:a:N")
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=float, default=30.0)
    ap.add_argument("--overlap", type=float, default=1.0)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--model-dir", default=os.path.expanduser("~/.cache/anime-redub/models"))
    ap.add_argument("--separator", default=shutil.which("audio-separator") or os.path.join(os.path.dirname(sys.executable), "audio-separator"))
    a = ap.parse_args()

    chunks_dir = os.path.join(a.out, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    settings = dict(source=os.path.abspath(a.source), track=a.track, start=a.start, end=a.end, chunk=a.chunk, overlap=a.overlap, model=a.model)
    settings_path = os.path.join(a.out, "settings.json")
    if os.path.exists(settings_path) and json.load(open(settings_path)) != settings:
        raise SystemExit(f"{a.out} was made with other settings, and its chunks would not fit: use a new --out folder")
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=1)
    source_wav = os.path.join(a.out, "source.wav")
    if not os.path.exists(source_wav):
        tmp = source_wav + ".tmp.wav"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(a.start), "-t", str(a.end - a.start), "-i", a.source,
             "-map", f"0:a:{a.track}", "-ac", "2", "-ar", str(SR), "-c:a", "pcm_f32le", tmp],
            check=True,
        )
        os.replace(tmp, source_wav)
    info = sf.info(source_wav)
    ranges = plan_chunks(info.frames, SR, a.chunk, a.overlap)
    print(f"{info.frames / SR:.0f} s to separate, {len(ranges)} chunks", flush=True)

    def done(k, kind):
        return os.path.join(chunks_dir, f"{k:04d}_{kind}.wav")

    spent, fresh = 0.0, 0
    for k, (x, y) in enumerate(ranges):
        if os.path.exists(done(k, "vocals")) and os.path.exists(done(k, "instrumental")):
            print(f"chunk {k + 1} of {len(ranges)} already done", flush=True)
            continue
        t = time.time()
        work = os.path.join(chunks_dir, f"work_{k:04d}")
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        audio, _ = sf.read(source_wav, start=x, frames=y - x, dtype="float32", always_2d=True)
        sf.write(os.path.join(work, "c.wav"), audio, SR, subtype="FLOAT")
        with open(os.path.join(a.out, "separate.log"), "a") as log:
            subprocess.run(
                [a.separator, os.path.join(work, "c.wav"), "--model_file_dir", a.model_dir, "--output_dir", work, "--output_format", "WAV", "-m", a.model],
                stdout=log, stderr=log, check=True,
            )
        os.replace(glob.glob(os.path.join(work, "*(Vocals)*.wav"))[0], done(k, "vocals"))
        os.replace(glob.glob(os.path.join(work, "*(Instrumental)*.wav"))[0], done(k, "instrumental"))
        shutil.rmtree(work)
        spent += time.time() - t
        fresh += 1
        left = sum(1 for j in range(k + 1, len(ranges)) if not os.path.exists(done(j, "vocals")))
        print(f"chunk {k + 1} of {len(ranges)} done in {time.time() - t:.0f} s, about {left * spent / fresh / 60:.0f} min left", flush=True)

    for kind in ("vocals", "instrumental"):
        parts = [sf.read(done(k, kind), dtype="float32", always_2d=True)[0] for k in range(len(ranges))]
        tmp = os.path.join(a.out, f"{kind}.tmp.wav")
        sf.write(tmp, stitch(parts, ranges, SR, a.overlap, info.frames), SR, subtype="FLOAT")
        os.replace(tmp, os.path.join(a.out, f"{kind}.wav"))
    with open(os.path.join(a.out, "stems.json"), "w") as f:
        json.dump({"start": a.start, "end": a.end, "track": a.track, "model": a.model, "vocals": "vocals.wav", "instrumental": "instrumental.wav"}, f, indent=1)
    print(f"ALL_DONE {a.out}/vocals.wav and instrumental.wav", flush=True)


if __name__ == "__main__":
    main()
