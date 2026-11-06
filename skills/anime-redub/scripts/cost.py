"""Estimate what a scene will cost before anything is paid for.

usage: cost.py SCENE.json [--passes 1.5] [--scale 1] [--source-minutes M]

Tags are billed like any other characters. --passes covers lines generated again,
--scale projects from this scene to a longer piece (an episode was about 8 times a
2:40 scene of dialogue), --source-minutes adds a Scribe pass over the original.
The prices were read from the ElevenLabs documentation in November 2026: check them.
"""
import argparse
import json
import re

from make_blocks import check_lines

DIALOGUE_PER_1K_CHARS = 0.08  # Text to Dialogue with eleven_v4
SCRIBE_PER_HOUR = 0.22
CHARS_PER_SECOND = 19.6  # measured: 1913 characters with tags came back as 97.5 s of speech


def estimate(lines, passes=1.0, scale=1.0, source_minutes=0.0):
    chars = sum(len(l["ru"]) for l in lines) * scale
    spoken = sum(len(re.sub(r"\[[^\]]*\]", "", l["ru"]).strip()) for l in lines) * scale
    generation = chars / 1000 * DIALOGUE_PER_1K_CHARS * passes
    seconds = chars / CHARS_PER_SECOND
    # Scribe hears each generated request once, the finished mix once (about twice the speech), and the source if asked.
    scribe = (seconds * passes + seconds * 2 + source_minutes * 60) / 3600 * SCRIBE_PER_HOUR
    return dict(chars=chars, spoken=spoken, requests=chars / 1900, generation=generation, scribe=scribe, total=generation + scribe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--passes", type=float, default=1.0)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--source-minutes", type=float, default=0.0)
    a = ap.parse_args()
    lines = json.load(open(a.scene, encoding="utf-8"))["lines"]
    check_lines(lines)
    e = estimate(lines, a.passes, a.scale, a.source_minutes)
    print(f"{e['chars']:.0f} characters with tags ({e['spoken']:.0f} without), about {e['requests']:.1f} requests")
    print(f"generation ${e['generation']:.2f}, Scribe ${e['scribe']:.2f}, total about ${e['total']:.2f} at {a.passes:g} passes")
    print("Not counted: Voice Design, about 1 cent per character tried (billed by preview text; saving a voice is free).")
    print("Prices come from the documentation, not from your plan.")


if __name__ == "__main__":
    main()
