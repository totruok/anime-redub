"""Split a scene into Text to Dialogue requests, each under the character limit.

usage: make_blocks.py SCENE.json OUT_DIR [--max-chars 1900]

Lines keep their order. Every cut goes to the longest pause between lines that is
reachable, because the voices of one request are the ones that sound most alike, and a
long pause hides the join. Writes OUT_DIR/block_01.json and so on. Look the cuts over:
a change of scene is often a better place than the longest pause.
"""
import argparse
import glob
import json
import os
import re


def check_lines(lines, cast=None):
    """Refuse an unfinished script, because a paid request must not carry an empty line or an unknown voice."""
    empty = [l["id"] for l in lines if not any(c.isalnum() for c in re.sub(r"\[[^\]]*\]", "", l.get("text", "")))]
    if empty:
        raise SystemExit(f"lines with no text to speak: {empty}")
    nobody = [l["id"] for l in lines if l.get("who") in (None, "", "?")]
    if nobody:
        raise SystemExit(f"lines with no character in who: {nobody}")
    if cast is not None:
        unknown = sorted({l["who"] for l in lines} - set(cast))
        if unknown:
            raise SystemExit(f"characters missing from the cast file: {unknown}")


def split(lines, limit):
    blocks, i = [], 0
    while i < len(lines):
        total, j, fits = 0, i, []
        while j < len(lines) and total + len(lines[j]["text"]) <= limit:
            total += len(lines[j]["text"])
            fits.append(total)
            j += 1
        if j == i:
            raise SystemExit(f"line {lines[i]['id']} alone is longer than {limit} characters")
        if j == len(lines):
            blocks.append(lines[i:])
            break
        # A cut too early would waste a request, so the block must be at least a quarter full.
        candidates = [k for k in range(i + 1, j + 1) if fits[k - i - 1] >= limit / 4] or [j]
        cut = max(candidates, key=lambda k: lines[k]["start"] - lines[k - 1]["end"])
        blocks.append(lines[i:cut])
        i = cut
    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("out")
    ap.add_argument("--max-chars", type=int, default=1900)
    a = ap.parse_args()
    lines = json.load(open(a.scene, encoding="utf-8"))["lines"]
    check_lines(lines)
    os.makedirs(a.out, exist_ok=True)
    for old in glob.glob(os.path.join(a.out, "block_[0-9][0-9].json")):
        os.remove(old)
    for n, block in enumerate(split(lines, a.max_chars), 1):
        path = os.path.join(a.out, f"block_{n:02d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"lines": block}, f, ensure_ascii=False, indent=1)
        print(f"{path}: lines {block[0]['id']}-{block[-1]['id']}, {sum(len(l['text']) for l in block)} characters, ends at {block[-1]['end']:.1f} s", flush=True)


if __name__ == "__main__":
    main()
