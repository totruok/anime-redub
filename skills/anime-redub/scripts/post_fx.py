"""Scene post-processing that sits each dubbed voice into the original soundtrack.

Per character: a linear-phase EQ pulling the dub's long-term spectrum toward that
character's own Japanese lines in this scene. Boosts are capped low, because the
original's strong 250-500 Hz would otherwise make the dub boxy. Then one shared
acoustic per scene. Timing does not move: the filter delay is compensated.
"""
import numpy as np
import librosa
from scipy import signal

PROBE = [125, 250, 500, 1000, 2000, 4000, 8000, 12000]


def ltas(x, sr, n_fft=4096):
    S = np.abs(librosa.stft(x, n_fft=n_fft, hop_length=n_fft // 4)) ** 2
    e = S.sum(axis=0)
    S = S[:, e > e.max() * 0.03]
    p = S.mean(axis=1)
    f = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    cum = np.concatenate([[0.0], np.cumsum(p)])
    lo = np.searchsorted(f, f / 2 ** (1 / 6))
    hi = np.maximum(np.searchsorted(f, f * 2 ** (1 / 6)), lo + 1)
    smooth = (cum[hi] - cum[lo]) / (hi - lo)
    return f, 10 * np.log10(smooth + 1e-14)


def curve(ref_db, src_db, f, strength, max_cut, max_boost):
    d = ref_db - src_db
    band = (f >= 800) & (f <= 2500)
    d = (d - d[band].mean()) * strength
    d = np.clip(d, -max_cut, max_boost)
    d = np.where(f < 120, d * np.clip((f - 60) / 60, 0, 1), d)  # leave the rumble region alone
    top = f >= 14000
    if top.any():
        d[top] = min(d[np.searchsorted(f, 14000)], 0.0)
    return d


def apply_curve(x, f, d_db, sr, taps=2049):
    freq = np.clip(f / (sr / 2), 0, 1)
    h = signal.firwin2(taps, freq, 10 ** (d_db / 20))
    y = signal.fftconvolve(x, h, mode="full")
    delay = (taps - 1) // 2
    return y[delay : delay + len(x)].astype(np.float32)


def active_rms(x, sr):
    n = int(0.02 * sr)
    frames = len(x) // n
    rms = np.sqrt(np.mean(x[: frames * n].reshape(frames, n) ** 2, axis=1) + 1e-14)
    return float(np.sqrt(np.mean(rms[rms > rms.max() * 0.1] ** 2)))


def acoustic(x, sr, env):
    """A faint distant reflection plus a soft delayed tail, both dull, so no small-room sound."""
    wet = np.zeros_like(x)
    sos = signal.butter(2, env.get("wet_lowpass", 5000) / (sr / 2), output="sos")
    if env.get("slap_db") is not None:
        k = int(env["slap_ms"] / 1000 * sr)
        wet[k:] += x[: len(x) - k] * 10 ** (env["slap_db"] / 20)
    if env.get("diffuse_db") is not None:
        n = int(env["rt"] * sr)
        rng = np.random.default_rng(11)
        ir = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
        ir = np.concatenate([np.zeros(int(env["predelay_ms"] / 1000 * sr)), ir])
        ir = ir / np.sqrt(np.sum(ir**2)) * 10 ** (env["diffuse_db"] / 20)
        wet += signal.fftconvolve(x, ir, mode="full")[: len(x)].astype(np.float32)
    return (x + signal.sosfilt(sos, wet)).astype(np.float32)


def process(by_who, refs, sr, post):
    eq = post.get("eq_match", {})
    totals = {}
    chars = {}
    for group in by_who:
        chars.setdefault(group.split("|")[0], []).append(group)
    print(f"character          EQ gain dB at {PROBE} | mismatch to original 200-8000 Hz, dB: before -> after", flush=True)
    for who, groups in chars.items():
        # One curve per character across scenes, so a voice does not change colour between them.
        ref = np.concatenate([s for g in groups for s in refs[g]]).astype(np.float32)
        x = sum(by_who[g] for g in groups)
        f, ref_db = ltas(ref, sr)
        _, src_db = ltas(x, sr)
        ref_seconds = len(ref) / sr
        strength = eq.get("strength", 0.7) * min(1.0, ref_seconds / eq.get("full_strength_seconds", 3.0))
        d = curve(ref_db, src_db, f, strength, eq.get("max_cut", 8.0), eq.get("max_boost", 3.0))
        y = apply_curve(x, f, d, sr)
        level = active_rms(x, sr) / (active_rms(y, sr) + 1e-12)
        _, out_db = ltas(y * level, sr)
        band = (f >= 200) & (f <= 8000)
        mis = lambda a: float(np.sqrt(np.mean(((ref_db - a) - (ref_db - a)[band].mean())[band] ** 2)))  # noqa: E731
        gains = " ".join(f"{d[np.searchsorted(f, p)]:+5.1f}" for p in PROBE)
        print(f"{who:<18} {gains} | {mis(src_db):4.1f} -> {mis(out_db):4.1f}  ref {ref_seconds:4.1f}s", flush=True)
        for g in groups:
            name = g.split("|")[1]
            totals[name] = totals.get(name, 0) + apply_curve(by_who[g], f, d, sr) * level
    hp = signal.butter(2, post.get("highpass", 90) / (sr / 2), btype="highpass", output="sos")
    mixed = None
    for name, x in totals.items():
        x = signal.sosfiltfilt(hp, x).astype(np.float32)
        env = post.get("envs", {}).get(name, post.get("env"))
        if env:
            x = acoustic(x, sr, env)
        mixed = x if mixed is None else mixed + x
    return mixed
