"""Generate a block of lines as one dialogue request, then cut it into one take per line.

usage: dialogue.py BLOCK.json CAST.json OUT_DIR [--model eleven_v4] [--stability 0] [--seed 17] [--similarity 0.75] [--collect TAKES_DIR]

One request means one generation: every voice hears the scene it is in. Scribe finds
where each line was really spoken, and each cut goes to the quietest moment between
two lines. Resumable: a finished request is keyed by its settings and text, so it is
never paid for twice; a rerun only cuts again. The key is never printed. A request
holds at most 2000 characters, tags included: make_blocks.py splits a longer scene.
"""
import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np
import requests
import soundfile as sf

import el
from make_blocks import check_lines

SR = 44100
LEAD = 0.10
MAX_CHARS = 2000


def decode(path):
    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def quietest(x, a, b):
    """Middle of the quietest 30 ms stretch between two times, in seconds."""
    i, j = int(a * SR), int(b * SR)
    n = int(0.01 * SR)
    if j - i < 3 * n:
        return (a + b) / 2
    frames = (j - i) // n
    e = np.mean(x[i : i + frames * n].reshape(frames, n) ** 2, axis=1)
    e3 = np.convolve(e, np.ones(3) / 3, mode="same")
    return a + (int(np.argmin(e3)) + 0.5) * 0.01


LATIN = str.maketrans("abcdefghijklmnopqrstuvwxyz", "абкдефгхийклмнопкрстуввкиз")


def letters(text):
    """Cyrillic letters only; a word the recogniser wrote in Latin is transliterated first."""
    return re.sub(r"[^а-я]", "", text.lower().replace("ё", "е").translate(LATIN))


def word_spans(lines, all_words):
    """Where each line was really spoken. Lines take consecutive recognised words, chosen for the best match
    over the whole block, so repeats like "Нет!" and "Не-е-ет!" keep their order. A line asking for a lead
    also takes the sound event just before its first word, such as a gasp. Returns (begin, end, first_word)."""
    words = [w for w in all_words if w.get("type") == "word" and letters(w["text"])]
    said = [letters(w["text"]) for w in words]
    want = [letters(re.sub(r"\[[^\]]*\]", "", l["ru"])) for l in lines]
    inf = float("inf")
    best = [[inf] * (len(words) + 1) for _ in range(len(lines) + 1)]
    back = [[0] * (len(words) + 1) for _ in range(len(lines) + 1)]
    best[0][0] = 0.0
    for i, target in enumerate(want):
        for j in range(len(words) + 1):
            if best[i][j] == inf:
                continue
            for k in range(j + 1, min(len(words), j + 16) + 1):
                ratio = difflib.SequenceMatcher(None, target, "".join(said[j:k]), autojunk=False).ratio()
                cost = best[i][j] + (1 - ratio) * max(len(target), 1)
                if cost < best[i + 1][k]:
                    best[i + 1][k], back[i + 1][k] = cost, j
    if best[len(lines)][len(words)] == inf:
        raise SystemExit("could not match the recognised words to the lines")
    groups, k = [], len(words)
    for i in range(len(lines), 0, -1):
        groups.append((back[i][k], k))
        k = back[i][k]
    groups.reverse()
    events = [w for w in all_words if w.get("type") == "audio_event"]
    spans = []
    for l, (j, k) in zip(lines, groups):
        first, end = words[j]["start"], words[k - 1]["end"]
        begin = first
        if "lead" in l:
            begin = min([e["start"] for e in events if e["end"] <= first + 0.05 and first - e["end"] < 0.4] + [first])
        spans.append((begin, end, first))
    return spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("cast")
    ap.add_argument("out")
    ap.add_argument("--model", default="eleven_v4")
    ap.add_argument("--stability", type=float, default=0.0)
    ap.add_argument("--similarity", type=float, default=0.75)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--collect", help="also copy the cut takes here, the one folder autofit.py and mix_window.py read")
    a = ap.parse_args()

    lines = json.load(open(a.scene))["lines"]
    cast = json.load(open(a.cast))
    check_lines(lines, cast)
    inputs = [{"text": l["ru"], "voice_id": cast[l["who"]]["voice_id"]} for l in lines]
    chars = sum(len(i["text"]) for i in inputs)
    print(f"{len(inputs)} lines, {chars} characters, model {a.model}, stability {a.stability}, similarity {a.similarity}, seed {a.seed}", flush=True)
    if chars > MAX_CHARS:
        raise SystemExit(f"{chars} characters do not fit one request (limit {MAX_CHARS}): split the scene with make_blocks.py")
    body = {
        "inputs": inputs, "model_id": a.model, "language_code": "ru", "seed": a.seed,
        "settings": {"stability": a.stability, "similarity": a.similarity},
    }
    h = hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
    rawdir = os.path.join(a.out, "raw")
    os.makedirs(rawdir, exist_ok=True)
    audio, meta = os.path.join(rawdir, f"{h}.mp3"), os.path.join(rawdir, f"{h}.json")
    if os.path.exists(audio) and os.path.exists(meta):
        print(f"cached {audio}", flush=True)
        res = json.load(open(meta))
    else:
        r = requests.post(
            f"{el.API}/v1/text-to-dialogue/with-timestamps",
            headers=el.headers(), params={"output_format": "mp3_44100_192"}, json=body, timeout=300,
        )
        el.check(r)
        res = r.json()
        tmp = audio + ".tmp"
        with open(tmp, "wb") as f:
            f.write(base64.b64decode(res.pop("audio_base64")))
        os.replace(tmp, audio)
        res["request"] = {k: v for k, v in body.items()}
        res["character_cost"] = r.headers.get("character-cost") or r.headers.get("x-character-count")
        with open(meta + ".tmp", "w") as f:
            json.dump(res, f, ensure_ascii=False)
        os.replace(meta + ".tmp", meta)
        print(f"generated {audio}, billed characters {res['character_cost']}", flush=True)

    for s in res["voice_segments"]:
        if s["voice_id"] != inputs[s["dialogue_input_index"]]["voice_id"]:
            print(f"WARNING: segment of input {s['dialogue_input_index']} reports another voice", flush=True)

    # The server's spans share time out over the tags too, so they miss the real speech by up to 0.3 s.
    heard = os.path.join(rawdir, f"{h}.scribe.json")
    if not os.path.exists(heard):
        speakers = len({l["who"] for l in lines})
        here = os.path.dirname(os.path.abspath(__file__))
        subprocess.run([sys.executable, os.path.join(here, "scribe.py"), audio, heard, "--lang", "rus", "--speakers", str(speakers)], check=True)
    spans = word_spans(lines, json.load(open(heard))["words"])

    x = decode(audio)
    total = len(x) / SR
    cuts = [0.0]
    for i in range(len(lines) - 1):
        end, nxt = spans[i][1], spans[i + 1][0]
        cuts.append(quietest(x, min(end, nxt) - 0.03, max(end, nxt) + 0.03))
    cuts.append(total)

    takes = os.path.join(a.out, f"takes_{h}")
    os.makedirs(takes, exist_ok=True)
    print(f"audio {total:.2f}s, takes in {takes}", flush=True)
    print("id who      words heard      take           len  pause_to_next | text", flush=True)
    for i, l in enumerate(lines):
        begin = max(cuts[i], spans[i][0] - LEAD)  # a long inhale would push the first word off the original's onset
        piece = x[int(begin * SR) : int(cuts[i + 1] * SR)]
        path = os.path.join(takes, f"{l['id']}_{l['who']}")
        sf.write(path + ".wav", piece, SR, subtype="FLOAT")
        with open(path + ".json", "w") as f:
            json.dump({"first_word": spans[i][2] - begin}, f)
        pause = spans[i + 1][0] - spans[i][1] if i + 1 < len(lines) else 0.0
        print(f"{l['id']} {l['who']:<8} {spans[i][0]:6.2f}-{spans[i][1]:6.2f}  {begin:6.2f}-{cuts[i + 1]:6.2f} {len(piece) / SR:5.2f} {pause:+6.2f} | {l['ru']}", flush=True)
    print(f"takes_dir={takes}", flush=True)
    if a.collect:
        os.makedirs(a.collect, exist_ok=True)
        for l in lines:
            for ext in ("wav", "json"):
                shutil.copy2(os.path.join(takes, f"{l['id']}_{l['who']}.{ext}"), a.collect)
        print(f"copied {len(lines)} takes to {a.collect}", flush=True)


if __name__ == "__main__":
    main()
