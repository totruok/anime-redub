"""Generate a block of lines as one dialogue request, then cut it into one take per line.

usage: dialogue.py BLOCK.json CAST.json OUT_DIR --language CODE [--model eleven_v4] [--stability 0] [--seed 17] [--similarity 0.75] [--collect TAKES_DIR]

--language is the language the lines are written in, a code from languages.py. One
request means one generation: every voice hears the scene it is in. Scribe finds where
each line was really spoken, and each cut goes to the quietest moment between two
lines. Resumable: a finished request is keyed by its settings and text, so it is never
paid for twice; a rerun only cuts again. The key is never printed. A request holds at
most 2000 characters, tags included: make_blocks.py splits a longer scene.
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
import unicodedata
from collections import Counter
from itertools import accumulate

import numpy as np
import requests
import soundfile as sf

import budget
import el
import languages
from make_blocks import check_lines

SR = 44100
LEAD = 0.10
MAX_CHARS = 2000
MIN_PAUSE = 0.2
SEAM_COST = 3.0
BAND = 120
MIN_MATCH = 0.5  # the worst of 37 lines on the tested Russian scene was 0.75


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


# Scribe now and then writes a word of a Russian line in Latin letters, so those are mapped back.
LATIN_TO_RUSSIAN = str.maketrans("abcdefghijklmnopqrstuvwxyz", "абкдефгхийклмнопкрстуввкиз")


def letters(text, language=None):
    """Letters and digits of any script, lower-cased and without accents, for comparing recognised words with a line."""
    text = unicodedata.normalize("NFKD", text.lower())
    if language == "ru":
        text = text.translate(LATIN_TO_RUSSIAN)
    return "".join(c for c in text if unicodedata.category(c)[0] in "LN" or unicodedata.category(c) == "Mc")


def seam(words, k, lines, i):
    """The cost of ending line i before word k. Lines end on a pause or a change of voice,
    so a misheard word at the edge of a line cannot slide across to its neighbour for free."""
    if not 0 < k < len(words) or i + 1 >= len(lines):
        return 0.0
    same_speaker = words[k].get("speaker_id") == words[k - 1].get("speaker_id")
    voices_differ = lines[i].get("who") != lines[i + 1].get("who")
    return SEAM_COST if same_speaker and (voices_differ or words[k]["start"] - words[k - 1]["end"] < MIN_PAUSE) else 0.0


def word_spans(lines, all_words, language=None):
    """Where each line was really spoken. Lines take consecutive recognised words, chosen for the best match
    over the whole block, so repeats like "No!" and "No-o-o!" keep their order. A line asking for a lead
    also takes the sound event just before its first word, such as a gasp. Returns (begin, end, first_word, heard)."""
    words = [w for w in all_words if w.get("type") == "word" and letters(w["text"], language)]
    said = [letters(w["text"], language) for w in words]
    want = [letters(re.sub(r"\[[^\]]*\]", "", l["text"]), language) for l in lines]
    # When the totals disagree a line was lost or added, and a band would force every later line off its words.
    trust_band = abs(sum(map(len, said)) - sum(map(len, want))) <= BAND / 2
    back = (trust_band and align(lines, words, said, want, BAND)) or align(lines, words, said, want, None)
    if back is None:
        raise SystemExit("could not match the recognised words to the lines")
    groups, k = [], len(words)
    for i in range(len(lines), 0, -1):
        groups.append((back[i][k], k))
        k = back[i][k]
    groups.reverse()
    events = [w for w in all_words if w.get("type") == "audio_event"]
    spans = []
    for l, target, (j, k) in zip(lines, want, groups):
        first, end = words[j]["start"], words[k - 1]["end"]
        begin = first
        if "lead" in l:
            begin = min([e["start"] for e in events if e["end"] <= first + 0.05 and first - e["end"] < 0.4] + [first])
        heard = "".join(said[j:k])
        match = difflib.SequenceMatcher(None, target, heard, autojunk=False).ratio()
        if match < MIN_MATCH:
            print(f"WARNING: line {l.get('id', '?')} barely matches what Scribe heard ({match:.2f}), so its cut cannot be trusted. Check the alphabet and the language, or whether a line was lost or added.", flush=True)
        spans.append((begin, end, first, "" if heard == target else " ".join(w["text"] for w in words[j:k])))
    return spans


def align(lines, words, said, want, band):
    """The best assignment of consecutive words to lines. With a band, a line may start only within that
    many letters of where it would start if every word were heard as written, which is much faster."""
    inf = float("inf")
    best = [[inf] * (len(words) + 1) for _ in range(len(lines) + 1)]
    back = [[0] * (len(words) + 1) for _ in range(len(lines) + 1)]
    best[0][0] = 0.0
    heard_at = list(accumulate(map(len, said), initial=0))
    want_at = list(accumulate(map(len, want), initial=0))
    for i, target in enumerate(want):
        for j in range(len(words) + 1):
            if best[i][j] == inf or (band and abs(heard_at[j] - want_at[i]) > band):
                continue
            left, common, length = Counter(target), 0, 0
            for k in range(j + 1, len(words) + 1):
                for c in said[k - 1]:
                    if left[c] > 0:
                        left[c] -= 1
                        common += 1
                length += len(said[k - 1])
                # Up to 16 words are always tried. Past that a line grows only to twice its own length,
                # which makes room for languages of short words or of one-character tokens.
                if k - j > 16 and length > 2 * len(target):
                    break
                edge = seam(words, k, lines, i)
                # Shared letters cap how good the match can be, which skips most of the slow comparisons.
                if best[i][j] + (1 - 2 * common / (len(target) + length)) * max(len(target), 1) + edge >= best[i + 1][k]:
                    continue
                ratio = difflib.SequenceMatcher(None, target, "".join(said[j:k]), autojunk=False).ratio()
                cost = best[i][j] + (1 - ratio) * max(len(target), 1) + edge
                if cost < best[i + 1][k]:
                    best[i + 1][k], back[i + 1][k] = cost, j
    return back if best[len(lines)][len(words)] < inf else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("cast")
    ap.add_argument("out")
    ap.add_argument("--language", required=True, help="the language of the lines, a code from languages.py")
    ap.add_argument("--model", default="eleven_v4")
    ap.add_argument("--stability", type=float, default=0.0)
    ap.add_argument("--similarity", type=float, default=0.75)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--collect", help="also copy the cut takes here, the one folder autofit.py and mix_window.py read")
    a = ap.parse_args()

    language_name = languages.check(a.language)
    lines = json.load(open(a.scene, encoding="utf-8"))["lines"]
    cast = json.load(open(a.cast, encoding="utf-8"))
    check_lines(lines, cast)
    inputs = [{"text": l["text"], "voice_id": cast[l["who"]]["voice_id"]} for l in lines]
    chars = sum(len(i["text"]) for i in inputs)
    print(f"{len(inputs)} lines, {chars} characters, language {language_name}, model {a.model}, stability {a.stability}, similarity {a.similarity}, seed {a.seed}", flush=True)
    if chars > MAX_CHARS:
        raise SystemExit(f"{chars} characters do not fit one request (limit {MAX_CHARS}): split the scene with make_blocks.py")
    body = {
        "inputs": inputs, "model_id": a.model, "language_code": a.language, "seed": a.seed,
        "settings": {"stability": a.stability, "similarity": a.similarity},
    }
    h = hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
    rawdir = os.path.join(a.out, "raw")
    os.makedirs(rawdir, exist_ok=True)
    audio, meta = os.path.join(rawdir, f"{h}.mp3"), os.path.join(rawdir, f"{h}.json")
    if os.path.exists(audio) and os.path.exists(meta):
        print(f"cached {audio}", flush=True)
        res = json.load(open(meta, encoding="utf-8"))
    else:
        cost = budget.text_cost(chars)
        budget.charge(cost, f"a dialogue request of {chars} characters")
        r = requests.post(
            f"{el.API}/v1/text-to-dialogue/with-timestamps",
            headers=el.headers(), params={"output_format": "mp3_44100_192"}, json=body, timeout=300,
        )
        if not r.ok:
            budget.refund(cost)
        el.check(r)
        res = r.json()
        tmp = audio + ".tmp"
        with open(tmp, "wb") as f:
            f.write(base64.b64decode(res.pop("audio_base64")))
        os.replace(tmp, audio)
        res["request"] = {k: v for k, v in body.items()}
        res["character_cost"] = r.headers.get("character-cost") or r.headers.get("x-character-count")
        with open(meta + ".tmp", "w", encoding="utf-8") as f:
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
        done = subprocess.run([sys.executable, os.path.join(here, "scribe.py"), audio, heard, "--language", a.language, "--speakers", str(speakers)])
        if done.returncode:
            raise SystemExit(done.returncode)
    words = json.load(open(heard, encoding="utf-8"))["words"]
    print(f"matching {len(lines)} lines to {len(words)} recognised tokens; a long block of one-character tokens can take minutes", flush=True)
    spans = word_spans(lines, words, a.language)

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
        print(f"{l['id']} {l['who']:<8} {spans[i][0]:6.2f}-{spans[i][1]:6.2f}  {begin:6.2f}-{cuts[i + 1]:6.2f} {len(piece) / SR:5.2f} {pause:+6.2f} | {l['text']}" + (f" | heard: {spans[i][3]}" if spans[i][3] else ""), flush=True)
    print(f"takes_dir={takes}", flush=True)
    if a.collect:
        os.makedirs(a.collect, exist_ok=True)
        for l in lines:
            for ext in ("wav", "json"):
                shutil.copy2(os.path.join(takes, f"{l['id']}_{l['who']}.{ext}"), a.collect)
        print(f"copied {len(lines)} takes to {a.collect}", flush=True)


if __name__ == "__main__":
    main()
