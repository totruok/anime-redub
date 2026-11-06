import os
import re
import subprocess

import numpy as np

from conftest import SCRIPTS, tone, write_wav


def lufs(path):
    out = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-af", "ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1])


def test_render_reaches_the_target_loudness_and_writes_the_timing_check(tmp_path):
    src = tmp_path / "src.mkv"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=6:s=160x90:r=10", "-f", "lavfi", "-i", "sine=440:d=6",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", src],
        check=True,
    )
    dub = tmp_path / "dub.wav"
    write_wav(dub, np.stack([tone(300, 5.0, 0.05)] * 2, axis=1))
    out = tmp_path / "out.mp4"
    r = subprocess.run([os.path.join(SCRIPTS, "render.sh"), src, "0", "5", dub, out, "0"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert abs(lufs(out) + 18) < 1.0
    assert (tmp_path / "out_timing.mp4").exists()
