import json
import os
import stat
import subprocess

import numpy as np
import soundfile as sf

import separate
from conftest import run_script

SR = 1000


def test_chunks_cover_everything_with_no_short_tail():
    for seconds in (65, 95, 100, 121):
        ranges = separate.plan_chunks(seconds * SR, SR, 30, 1)
        assert ranges[0][0] == 0 and ranges[-1][1] == seconds * SR
        assert all(b - a >= 15 * SR for a, b in ranges), seconds
    assert all(ranges[k + 1][0] < ranges[k][1] for k in range(len(ranges) - 1))


def test_short_window_is_one_chunk():
    assert separate.plan_chunks(10 * SR, SR, 30, 1) == [(0, 10 * SR)]


def test_stitch_returns_the_signal_when_chunks_agree():
    n = 95 * SR
    x = np.random.default_rng(1).standard_normal((n, 2)).astype(np.float32)
    ranges = separate.plan_chunks(n, SR, 30, 1)
    y = separate.stitch([x[a:b] for a, b in ranges], ranges, SR, 1, n)
    assert np.abs(y - x).max() < 1e-5


def test_stitch_fades_between_chunks_that_differ():
    n = 65 * SR
    ranges = separate.plan_chunks(n, SR, 30, 1)
    parts = [np.full((b - a, 1), float(k), dtype=np.float32) for k, (a, b) in enumerate(ranges)]
    y = separate.stitch(parts, ranges, SR, 1, n)[:, 0]
    assert np.all(np.diff(y[29 * SR : 31 * SR]) >= -1e-5)  # a ramp from one chunk's value to the next, with no jump
    assert np.abs(np.diff(y[29 * SR : 31 * SR])).max() < 0.01


FAKE_SEPARATOR = """#!/bin/bash
# Stands in for audio-separator: quarter level as voice, the rest as music, and a count of how often it ran.
echo run >> "$(dirname "$(dirname "$(dirname "$5")")")/runs.txt"
ffmpeg -nostdin -v error -y -i "$1" -af volume=0.25 "$5/c_(Vocals)_m.wav"
ffmpeg -nostdin -v error -y -i "$1" -af volume=0.75 "$5/c_(Instrumental)_m.wav"
"""


def test_a_whole_run_resumes_and_refuses_other_settings(tmp_path):
    fake = tmp_path / "fake.sh"
    fake.write_text(FAKE_SEPARATOR)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    src = tmp_path / "src.mkv"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=70:a=0.2:c=white:r=44100", "-c:a", "flac", src], check=True)
    args = [src, "--track", 0, "--start", 2, "--end", 67, "--out", tmp_path / "s" / "stems", "--separator", fake, "--model-dir", tmp_path]
    (tmp_path / "s").mkdir()
    first = run_script("separate.py", *args)
    assert first.returncode == 0, first.stderr
    assert "chunk 2 of 2 done" in first.stdout and "ALL_DONE" in first.stdout
    runs = tmp_path / "s" / "runs.txt"
    assert len(runs.read_text().splitlines()) == 2

    stems = tmp_path / "s" / "stems"
    assert json.load(open(stems / "stems.json"))["start"] == 2
    voc, sr = sf.read(stems / "vocals.wav", always_2d=True)
    ins, _ = sf.read(stems / "instrumental.wav", always_2d=True)
    source, _ = sf.read(stems / "source.wav", always_2d=True)
    assert len(voc) == 65 * sr and not os.path.exists(stems / "chunks" / "work_0000")
    assert np.abs(voc + ins - source).max() < 2e-3  # the seam leaves no gap and no double level

    again = run_script("separate.py", *args)
    assert again.returncode == 0 and "chunk 1 of 2 already done" in again.stdout
    assert len(runs.read_text().splitlines()) == 2  # nothing separated twice

    other = run_script("separate.py", src, "--track", 0, "--start", 2, "--end", 40, "--out", stems, "--separator", fake, "--model-dir", tmp_path)
    assert other.returncode != 0 and "other settings" in other.stderr
