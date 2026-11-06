"""Shared ElevenLabs helpers. The key comes from ELEVENLABS_API_KEY or a .env file in the current folder, and is never printed."""
import os
import sys

import requests

API = "https://api.elevenlabs.io"
KEY_FILE = ".env"


def key() -> str:
    env_val = os.environ.get("ELEVENLABS_API_KEY")
    if env_val:
        return env_val
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):]
                if line.upper().startswith("ELEVENLABS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("ELEVENLABS_API_KEY is not set: export it, or put it in a .env file in the current folder")


def headers() -> dict:
    return {"xi-api-key": key()}


def check(r: requests.Response) -> requests.Response:
    if not r.ok:
        sys.exit(f"HTTP {r.status_code} {r.url}: {r.text[:800]}")
    return r
