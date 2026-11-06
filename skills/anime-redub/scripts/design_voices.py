"""Generate Voice Design previews for each character. Nothing is saved to the account.

usage: design_voices.py CHARACTERS.json OUT_DIR

Each character is one billed generation that returns several previews. A finished
character is skipped on rerun, so nothing is paid for twice.
"""
import argparse
import base64
import json
import os
import time

import requests

import el


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("characters")
    ap.add_argument("out")
    ap.add_argument("--model", default="eleven_ttv_v3")
    a = ap.parse_args()
    cfg = json.load(open(a.characters))
    os.makedirs(a.out, exist_ok=True)

    total = len(cfg["characters"])
    billed = 0
    for i, c in enumerate(cfg["characters"], 1):
        meta_path = os.path.join(a.out, f"{c['key']}.json")
        if os.path.exists(meta_path):
            print(f"[{i}/{total}] {c['key']} already generated", flush=True)
            continue
        if not 100 <= len(c["text"]) <= 1000:
            raise SystemExit(f"{c['key']}: preview text must be 100-1000 chars, has {len(c['text'])}")
        t = time.time()
        r = requests.post(
            f"{el.API}/v1/text-to-voice/design",
            headers=el.headers(),
            params={"output_format": "mp3_44100_192"},
            json={
                "voice_description": f"{c['description']} {cfg['common']}",
                "model_id": a.model,
                "text": c["text"],
            },
            timeout=240,
        )
        el.check(r)
        data = r.json()
        previews = []
        for n, p in enumerate(data["previews"]):
            letter = "ABCDEFG"[n]
            path = os.path.join(a.out, f"{c['key']}_{letter}.mp3")
            with open(path, "wb") as f:
                f.write(base64.b64decode(p["audio_base_64"]))
            previews.append({
                "letter": letter,
                "file": os.path.basename(path),
                "generated_voice_id": p["generated_voice_id"],
                "duration_secs": p.get("duration_secs"),
                "language": p.get("language"),
            })
        tmp = meta_path + ".tmp"
        json.dump({"key": c["key"], "text": data.get("text"), "previews": previews}, open(tmp, "w"), ensure_ascii=False, indent=1)
        os.replace(tmp, meta_path)
        cost = r.headers.get("character-cost")
        billed += int(cost or 0)
        print(
            f"[{i}/{total}] {c['key']}: {len(previews)} previews in {time.time() - t:.0f}s, "
            f"text {len(c['text'])} chars, cost header {cost}, "
            f"languages {[p['language'] for p in previews]}, durations {[p['duration_secs'] for p in previews]}",
            flush=True,
        )
    print(f"cost header total this run: {billed}", flush=True)


if __name__ == "__main__":
    main()
