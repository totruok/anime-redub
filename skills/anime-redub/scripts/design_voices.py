"""Generate Voice Design previews for each character. Nothing is saved to the account.

usage: design_voices.py CHARACTERS.json OUT_DIR --language CODE

--language is the language the voices will speak, a code from languages.py. Voice Design
has no language setting of its own, so the language goes into the voice description, and
the preview text must be written in it too. Each character is one billed generation that
returns several previews. A finished character is skipped on rerun, so nothing is paid
for twice.
"""
import argparse
import base64
import json
import os
import time

import requests

import budget
import el
import languages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("characters")
    ap.add_argument("out")
    ap.add_argument("--language", required=True, help="the language of the voices, a code from languages.py")
    ap.add_argument("--model", default="eleven_ttv_v3")
    a = ap.parse_args()
    language_name = languages.check(a.language)
    cfg = json.load(open(a.characters, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)

    total = len(cfg["characters"])
    billed = 0
    for i, c in enumerate(cfg["characters"], 1):
        meta_path = os.path.join(a.out, f"{c['key']}.json")
        sent = {"voice_description": f"{c['description']} Native {language_name} speaker. {cfg['common']}", "text": c["text"]}
        if os.path.exists(meta_path):
            made = json.load(open(meta_path, encoding="utf-8"))
            if made.get("language") != a.language:
                raise SystemExit(f"{meta_path} was made for language {made.get('language')}, not {a.language}: use another folder")
            if made.get("sent") != sent:
                print(f"WARNING: {c['key']}: the description or text changed, but these previews were kept. To pay for new ones, delete {meta_path} and run again.", flush=True)
            print(f"[{i}/{total}] {c['key']} already generated", flush=True)
            continue
        if not 100 <= len(c["text"]) <= 1000:
            raise SystemExit(f"{c['key']}: preview text must be 100-1000 chars, has {len(c['text'])}")
        cost = budget.text_cost(len(c["text"]))
        budget.charge(cost, f"voice previews for {c['key']}")
        t = time.time()
        r = requests.post(
            f"{el.API}/v1/text-to-voice/design",
            headers=el.headers(),
            params={"output_format": "mp3_44100_192"},
            json={**sent, "model_id": a.model},
            timeout=240,
        )
        if not r.ok:
            budget.refund(cost)
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
        json.dump({"key": c["key"], "language": a.language, "sent": sent, "text": data.get("text"), "previews": previews}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, meta_path)
        other = sorted({p["language"] for p in previews if p["language"] not in (None, a.language)})
        if other:
            print(f"WARNING: {c['key']}: previews came back in {other}, not {a.language}. Fix the description or the preview text, delete {meta_path} and run again.", flush=True)
        header = r.headers.get("character-cost")
        billed += int(header or 0)
        print(
            f"[{i}/{total}] {c['key']}: {len(previews)} previews in {time.time() - t:.0f}s, "
            f"text {len(c['text'])} chars, server-reported cost {header or 'not given, the budget holds an estimate'}, "
            f"languages {[p['language'] for p in previews]}, durations {[p['duration_secs'] for p in previews]}",
            flush=True,
        )
    if billed:
        print(f"server-reported cost this run: {billed} characters", flush=True)


if __name__ == "__main__":
    main()
