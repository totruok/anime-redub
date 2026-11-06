"""How a voice-over dub keeps the original under it: measured from a finished dub track.

usage: underlay_measure.py SOURCE.mkv VOICEOVER_TRACK START DURATION VOCALS.wav INSTRUMENTAL.wav [OUR_DUB.wav]

The dub track is modelled as a*original_voice + b*original_music + new_voice. a and b
come from least squares, so they survive the new voice being far louder. Single short
windows are noisy under a loud voice, so levels are fitted per stretch of new speech
and the on/off shapes are fitted across all transitions together.
"""
import subprocess
import sys

import numpy as np
from scipy import signal

SR = 16000
HOP = int(0.05 * SR)


def decode(args):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", *args, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.float32).copy()


def solve(z, v, i):
    """Least squares of z on v and i, with a small ridge so silence stays stable."""
    A = np.array([[v @ v, v @ i], [v @ i, i @ i]], dtype=np.float64)
    y = np.array([v @ z, i @ z], dtype=np.float64)
    return np.linalg.solve(A + np.eye(2) * (1e-6 * (np.trace(A) + 1e-9)), y)


def db(x):
    return 20 * np.log10(np.maximum(np.abs(x), 1e-6))


def frame_rms(x, n=HOP):
    k = len(x) // n
    return np.sqrt(np.mean(x[: k * n].reshape(k, n) ** 2, axis=1) + 1e-12)


def otsu(values):
    hist, edges = np.histogram(values, bins=80)
    mid = (edges[:-1] + edges[1:]) / 2
    w = hist.cumsum().astype(np.float64)
    m = (hist * mid).cumsum()
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (m[-1] * w - m * w[-1]) ** 2 / (w * (w[-1] - w))
    return float(mid[int(np.nanargmax(between))])


def segments(active, min_gap, min_len):
    """Runs of True in a frame mask, with short gaps bridged and short islands dropped."""
    runs, on = [], None
    for k, a in enumerate(active):
        if a and on is None:
            on = k
        if not a and on is not None:
            runs.append([on, k])
            on = None
    if on is not None:
        runs.append([on, len(active)])
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] >= min_len]


def main():
    src, track, start, dur, voc_path, inst_path = sys.argv[1:7]
    start, dur = float(start), float(dur)
    z = decode(["-ss", str(start), "-t", str(dur), "-i", src, "-map", f"0:a:{track}"])
    v = decode(["-t", str(dur), "-i", voc_path])
    i = decode(["-t", str(dur), "-i", inst_path])
    n = min(len(z), len(v), len(i))
    z, v, i = z[:n], v[:n], i[:n]

    # Align the dub track to the stems first: a few milliseconds off would hide the original in the fit.
    mix = v + i
    size = 2 ** int(np.ceil(np.log2(2 * n)))
    corr = np.fft.irfft(np.fft.rfft(z, size) * np.conj(np.fft.rfft(mix, size)), size)
    reach = int(2 * SR)
    lags = np.concatenate([corr[:reach], corr[-reach:]])
    lag = int(np.argmax(np.abs(lags)))
    lag = lag if lag < reach else lag - 2 * reach
    z = np.roll(z, -lag)
    print(f"dub track lag behind stems: {lag / SR * 1000:+.1f} ms", flush=True)

    # Rough fit in short windows, only to find where the new voice speaks.
    win = int(0.4 * SR)
    residual = np.zeros(n, dtype=np.float32)
    for k in range(0, n - win, win):
        a, b = solve(z[k : k + win], v[k : k + win], i[k : k + win])
        residual[k : k + win] = z[k : k + win] - a * v[k : k + win] - b * i[k : k + win]
    level = db(frame_rms(residual))
    level = np.convolve(level, np.ones(3) / 3, mode="same")
    threshold = otsu(level[level > -70])
    speech = segments(level > threshold, min_gap=5, min_len=4)
    silence = []
    prev = 0
    for a, b in speech:
        if a - prev >= 6:
            silence.append([prev, a])
        prev = b
    active_share = sum(b - a for a, b in speech) * HOP / n
    print(f"new voice: threshold {threshold:.1f} dB, {len(speech)} stretches, {active_share * 100:.0f}% of the time", flush=True)

    voice_rms = frame_rms(v)
    voiced = voice_rms > voice_rms.max() * 0.1

    def fit(seg):
        x, y = seg[0] * HOP, seg[1] * HOP
        return solve(z[x:y], v[x:y], i[x:y])

    def has_voice(seg):
        return voiced[seg[0] : seg[1]].mean() > 0.4

    on = np.array([fit(s) for s in speech if has_voice(s)])
    off = np.array([fit(s) for s in silence if has_voice(s)])
    music_on = np.array([fit(s)[1] for s in speech])
    music_off = np.array([fit(s)[1] for s in silence])
    print(f"original voice gain, stretches with original speech: under new voice n={len(on)} median {np.median(db(on[:, 0])):.1f} dB (quartiles {np.percentile(db(on[:, 0]), 25):.1f}..{np.percentile(db(on[:, 0]), 75):.1f}); between lines n={len(off)} median {np.median(db(off[:, 0])) if len(off) else float('nan'):.1f} dB", flush=True)
    print(f"original music gain: under new voice median {np.median(db(music_on)):.1f} dB; between lines median {np.median(db(music_off)):.1f} dB", flush=True)

    # Shapes: all transitions fitted together, in 100 ms bins around the moment the new voice starts or stops.
    bin_len = int(0.1 * SR)
    def shape(moments, label):
        print(label, flush=True)
        out = []
        for b in range(-12, 16):
            A, y = np.zeros((2, 2)), np.zeros(2)
            for t in moments:
                x = t + b * bin_len
                if x < 0 or x + bin_len > n:
                    continue
                vv, ii, zz = v[x : x + bin_len], i[x : x + bin_len], z[x : x + bin_len]
                A += np.array([[vv @ vv, vv @ ii], [vv @ ii, ii @ ii]])
                y += np.array([vv @ zz, ii @ zz])
            a, c = np.linalg.solve(A + np.eye(2) * 1e-6 * np.trace(A), y)
            out.append((b / 10, db(a), db(c)))
            print(f"  {b / 10:+.1f}s voice {db(a):6.1f} dB  music {db(c):6.1f} dB", flush=True)
        return out

    starts = [s[0] * HOP for k, s in enumerate(speech) if k == 0 or s[0] - speech[k - 1][1] >= 14]
    ends = [s[1] * HOP for k, s in enumerate(speech) if k + 1 == len(speech) or speech[k + 1][0] - s[1] >= 14]
    shape(starts, f"new voice STARTS at 0 ({len(starts)} moments with 0.7 s of quiet before)")
    shape(ends, f"new voice STOPS at 0 ({len(ends)} moments with 0.7 s of quiet after)")

    # The ratio that decides how audible the original is: new voice against the original voice left under it.
    sos = signal.butter(4, [300 / (SR / 2), 3400 / (SR / 2)], btype="band", output="sos")
    gaps, band_gaps = [], []
    for s in speech:
        if not has_voice(s):
            continue
        a, b = fit(s)
        x, y = s[0] * HOP, s[1] * HOP
        new = z[x:y] - a * v[x:y] - b * i[x:y]
        keep = voiced[s[0] : s[1]]
        m = min(len(keep), len(frame_rms(new)))
        keep = keep[:m]
        if keep.sum() < 4:
            continue
        gaps.append(float(db(np.sqrt(np.mean(frame_rms(new)[:m][keep] ** 2))) - db(abs(a) * np.sqrt(np.mean(voice_rms[s[0] : s[1]][:m][keep] ** 2)))))
        new_band = frame_rms(signal.sosfilt(sos, new))[:m][keep]
        old_band = frame_rms(signal.sosfilt(sos, v[x:y]))[:m][keep]
        band_gaps.append(float(db(np.sqrt(np.mean(new_band**2))) - db(abs(a) * np.sqrt(np.mean(old_band**2)))))
    print(f"new voice above the original voice under it: median {np.median(gaps):.1f} dB (quartiles {np.percentile(gaps, 25):.1f}..{np.percentile(gaps, 75):.1f}), n={len(gaps)}", flush=True)
    print(f"same, 300-3400 Hz only: median {np.median(band_gaps):.1f} dB (quartiles {np.percentile(band_gaps, 25):.1f}..{np.percentile(band_gaps, 75):.1f})", flush=True)

    if len(sys.argv) > 7:
        ours = decode(["-t", str(dur), "-i", sys.argv[7]])[:n]
        ours_rms = frame_rms(ours)
        m = min(len(ours_rms), len(voice_rms))
        both = (ours_rms[:m] > ours_rms.max() * 0.1) & voiced[:m]
        delta = float(db(np.sqrt(np.mean(ours_rms[:m][both] ** 2))) - db(np.sqrt(np.mean(voice_rms[:m][both] ** 2))))
        print(f"our dub against the untouched original voice: {delta:+.1f} dB", flush=True)
        print(f"to match, the original voice under our dub goes to {delta - np.median(gaps):+.1f} dB", flush=True)


if __name__ == "__main__":
    main()
