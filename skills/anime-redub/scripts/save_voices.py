"""Save chosen Voice Design previews to the account and write a cast file.

usage: save_voices.py CHARACTERS.json PREVIEWS_DIR CAST_OUT.json hero=A rival=C ...

Each saved voice takes one slot. Voices already in the cast file are not saved twice.
"""
import json
import os
import sys

import requests

import el


def main():
    chars_path, previews, cast_path, picks = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    cfg = json.load(open(chars_path))
    by_key = {c["key"]: c for c in cfg["characters"]}
    cast = json.load(open(cast_path)) if os.path.exists(cast_path) else {}
    for pick in picks:
        key, letter = pick.split("=")
        if key in cast and cast[key].get("letter") == letter:
            print(f"{key}: already saved", flush=True)
            continue
        meta = json.load(open(os.path.join(previews, f"{key}.json")))
        preview = next(p for p in meta["previews"] if p["letter"] == letter)
        c = by_key[key]
        r = requests.post(
            f"{el.API}/v1/text-to-voice",
            headers=el.headers(),
            json={
                "voice_name": f"{cfg.get('project', 'Dub')} {c['name']}",
                "voice_description": f"{c['description']} {cfg['common']}",
                "generated_voice_id": preview["generated_voice_id"],
            },
            timeout=120,
        )
        el.check(r)
        cast[key] = {"voice_id": r.json()["voice_id"], "name": f"{cfg.get('project', 'Dub')} {c['name']}", "letter": letter}
        tmp = cast_path + ".tmp"
        json.dump(cast, open(tmp, "w"), ensure_ascii=False, indent=2)
        os.replace(tmp, cast_path)
        print(f"{key}: saved {letter} as {cast[key]['name']}", flush=True)


if __name__ == "__main__":
    main()
