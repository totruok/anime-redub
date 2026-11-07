"""Save chosen Voice Design previews to the account and write a cast file.

usage: save_voices.py CHARACTERS.json PREVIEWS_DIR CAST_OUT.json --auto
       save_voices.py CHARACTERS.json PREVIEWS_DIR CAST_OUT.json hero=A rival=C ...

--auto chooses without a listener: a preview in the requested language, as unlike the
voices already chosen as possible. It keeps the characters apart, but it cannot judge the
acting, and a character already in the cast keeps their voice. Each saved voice takes one
slot. Voices already in the cast file are not saved twice.
"""
import argparse
import json
import os

import numpy as np
import requests

import el


def voice_print(path):
    """The average timbre of a preview, without the coefficient that only follows loudness."""
    import librosa

    y, sr = librosa.load(path, sr=22050, mono=True)
    return librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)[1:].mean(axis=1)


def auto_picks(cfg, previews, cast=None):
    picks, chosen, todo = [], [], []
    for c in cfg["characters"]:
        entry = (cast or {}).get(c["key"])
        if entry and "generated_voice_id" not in entry:
            continue  # a voice written into the cast by hand
        meta = json.load(open(os.path.join(previews, f"{c['key']}.json"), encoding="utf-8"))
        kept = next((p for p in meta["previews"] if entry and p["generated_voice_id"] == entry["generated_voice_id"]), None)
        if kept:
            chosen.append(voice_print(os.path.join(previews, kept["file"])))
            picks.append(f"{c['key']}={kept['letter']}")
        else:
            todo.append((c, meta))
    for c, meta in todo:
        options = [p for p in meta["previews"] if p.get("language") in (None, meta.get("language"))]
        if not options:
            print(f"WARNING: {c['key']}: no preview came back in {meta.get('language')}, choosing among the others", flush=True)
            options = meta["previews"]
        prints = {p["letter"]: voice_print(os.path.join(previews, p["file"])) for p in options}
        letter = options[0]["letter"]
        if chosen:
            letter = max(prints, key=lambda k: min(np.linalg.norm(prints[k] - v) for v in chosen))
        chosen.append(prints[letter])
        picks.append(f"{c['key']}={letter}")
    print("chosen automatically: " + " ".join(picks), flush=True)
    return picks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("characters")
    ap.add_argument("previews")
    ap.add_argument("cast")
    ap.add_argument("picks", nargs="*", help="character=letter, as chosen by ear")
    ap.add_argument("--auto", action="store_true", help="choose one preview per character without a listener")
    a = ap.parse_args()
    if a.auto == bool(a.picks):
        raise SystemExit("give either --auto or the picks, such as hero=A rival=C")
    cfg = json.load(open(a.characters, encoding="utf-8"))
    by_key = {c["key"]: c for c in cfg["characters"]}
    cast = json.load(open(a.cast, encoding="utf-8")) if os.path.exists(a.cast) else {}
    for pick in auto_picks(cfg, a.previews, cast) if a.auto else a.picks:
        key, letter = pick.split("=")
        meta = json.load(open(os.path.join(a.previews, f"{key}.json"), encoding="utf-8"))
        preview = next(p for p in meta["previews"] if p["letter"] == letter)
        if key in cast and cast[key].get("generated_voice_id") == preview["generated_voice_id"]:
            print(f"{key}: already saved", flush=True)
            continue
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
        cast[key] = {"voice_id": r.json()["voice_id"], "name": f"{cfg.get('project', 'Dub')} {c['name']}", "letter": letter, "generated_voice_id": preview["generated_voice_id"]}
        tmp = a.cast + ".tmp"
        json.dump(cast, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, a.cast)
        print(f"{key}: saved {letter} as {cast[key]['name']}", flush=True)


if __name__ == "__main__":
    main()
