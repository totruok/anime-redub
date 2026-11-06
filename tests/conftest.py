"""No test may reach the network: a paid call from a test run would be a real bill."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "anime-redub", "scripts")
sys.path.insert(0, SCRIPTS)
SR = 44100


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import requests

    def refuse(*a, **k):
        raise AssertionError("a test tried to reach the network")

    monkeypatch.setattr(requests, "post", refuse)
    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")


def run_script(name, *args, cwd=None):
    """Run a pipeline script in its own process, with a dead key and no route to the real key."""
    env = dict(os.environ, ELEVENLABS_API_KEY="test-key")
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, name), *map(str, args)], capture_output=True, text=True, cwd=cwd, env=env)


def tone(freq, seconds, level=0.2, sr=SR):
    t = np.arange(int(seconds * sr)) / sr
    return (np.sin(2 * np.pi * freq * t) * level).astype(np.float32)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def write_wav(path, x, sr=SR):
    sf.write(path, x, sr, subtype="FLOAT")
