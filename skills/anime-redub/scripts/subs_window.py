"""List subtitle lines in a time window, and optionally write them out as a draft scene.

usage: subs_window.py SUBS.(ass|srt|tsv) START END [--draft SCENE.json] [--style NAME] [--offset SECONDS]

Subtitle times are only anchors: scene_measure.py finds the real phrases later. The
draft has an empty "ru" and who="?" on every line, for you to fill in by meaning, by
the frames and by the subtitles themselves. Songs and on-screen signs often come along:
the style counts printed first show which style to keep with --style.

A .lines.tsv file written by scribe.py works too. Scribe's times count from the start of
the audio it heard, so pass --offset with the source second where that audio begins.
"""
import argparse
import json
import re


def seconds(s):
    h, m, rest = s.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def read_ass(text):
    rows = []
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        p = line.split(",", 9)
        body = re.sub(r"\{[^}]*\}", "", p[9]).replace("\\N", " ").replace("\\n", " ").strip()
        if body and "\\p1" not in p[9][:60]:  # \p1 is a drawn shape, not speech
            rows.append(dict(start=seconds(p[1]), end=seconds(p[2]), style=p[3].strip(), name=p[4].strip(), text=body))
    return rows


def read_srt(text):
    rows = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        i = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if i is None:
            continue
        a, b = [x.strip().split(" ")[0] for x in lines[i].split("-->")]
        body = re.sub(r"<[^>]*>", "", " ".join(lines[i + 1 :])).strip()
        if body:
            rows.append(dict(start=seconds(a), end=seconds(b), style="", name="", text=body))
    return rows


def read_tsv(text):
    rows = []
    for line in text.splitlines():
        p = line.split("\t")
        if len(p) >= 4 and p[3].strip():
            rows.append(dict(start=float(p[0]), end=float(p[1]), style=p[2], name="", text=p[3].strip()))
    return rows


def read_any(path):
    text = open(path, encoding="utf-8-sig", errors="replace").read()
    lower = path.lower()
    if lower.endswith((".ass", ".ssa")):
        return read_ass(text)
    return read_tsv(text) if lower.endswith(".tsv") else read_srt(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subs")
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("--draft")
    ap.add_argument("--style", help="keep only this style, to drop songs and signs")
    ap.add_argument("--offset", type=float, default=0.0, help="added to every time in the file")
    a = ap.parse_args()
    rows = sorted(read_any(a.subs), key=lambda r: r["start"])
    for r in rows:
        r["start"] = round(r["start"] + a.offset, 3)
        r["end"] = round(r["end"] + a.offset, 3)
    styles = {}
    for r in rows:
        styles[r["style"]] = styles.get(r["style"], 0) + 1
    print(f"{len(rows)} lines in the file, styles: {dict(sorted(styles.items(), key=lambda kv: -kv[1])[:12])}")
    picked = [r for r in rows if a.start <= r["start"] <= a.end and (not a.style or r["style"] == a.style)]
    for r in picked:
        print(f"{r['start']:8.2f} {r['end']:8.2f} [{r['style']}|{r['name']}] {r['text']}")
    if a.draft:
        lines = [{"id": f"{i:02d}", "who": "?", "start": r["start"], "end": r["end"], "original": r["text"], "env": "default", "ru": ""} for i, r in enumerate(picked, 1)]
        with open(a.draft, "w", encoding="utf-8") as f:
            json.dump({"lines": lines}, f, ensure_ascii=False, indent=1)
        print(f"wrote {len(lines)} draft lines to {a.draft}")


if __name__ == "__main__":
    main()
