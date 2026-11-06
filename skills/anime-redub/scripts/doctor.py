"""Check that everything the pipeline needs is installed. Spends nothing and never prints the key.

usage: doctor.py
"""
import importlib
import os
import shutil
import subprocess
import sys


def main():
    bad = 0
    for tool in ("ffmpeg", "ffprobe", "rubberband"):
        found = shutil.which(tool)
        print(f"{'ok ' if found else 'NO '} {tool} {found or ''}")
        bad += not found
    for mod in ("numpy", "scipy", "soundfile", "librosa", "requests"):
        try:
            importlib.import_module(mod)
            print(f"ok  python module {mod}")
        except ImportError:
            print(f"NO  python module {mod}")
            bad += 1
    separator = shutil.which("audio-separator") or os.path.join(os.path.dirname(sys.executable), "audio-separator")
    has_sep = os.path.exists(separator)
    print(f"{'ok ' if has_sep else 'NO '} audio-separator {separator if has_sep else '(needed for separate.py unless you already have clean stems)'}")
    has_key = bool(os.environ.get("ELEVENLABS_API_KEY"))
    if not has_key and os.path.exists(".env"):
        has_key = any(l.strip().removeprefix("export ").upper().startswith("ELEVENLABS_API_KEY=") for l in open(".env"))
    print(f"{'ok ' if has_key else 'NO '} ELEVENLABS_API_KEY {'is set' if has_key else 'is not set in the environment or ./.env'}")
    if shutil.which("ffmpeg"):
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        for f in ("ebur128", "alimiter"):
            print(f"{'ok ' if f in filters else 'NO '} ffmpeg filter {f}")
            bad += f not in filters
    print("everything needed is here" if not bad and has_key and has_sep else "fix the NO lines above")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
