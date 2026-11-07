"""Fit each dub take onto the original's phrases and report what does not fit.

usage: autofit.py SCENE.json MEASURE.json TAKES_DIR OUT_FIT.json

A take is cut at its own pauses where the original pauses too, and each part starts
on the original phrase's onset. Parts are sped up only as much as needed, within a
limit. Lines still running into the next line are marked OVER: those need shorter text.
"""
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure import latest_take, speech_bounds  # noqa: E402
from mix_window import decode  # noqa: E402

SR = 44100
MAX_TEMPO = 1.22
HARD_TEMPO = 1.30
MIN_ORIG_PAUSE = 0.22
ALLOW_TAIL = 0.35
GAP_TO_NEXT = 0.06


def take_gaps(x):
    n = int(0.01 * SR)
    frames = len(x) // n
    db = 20 * np.log10(np.sqrt(np.mean(x[: frames * n].reshape(frames, n) ** 2, axis=1)) + 1e-9)
    quiet = db < db.max() - 30
    gaps, a = [], None
    for k, v in enumerate(quiet):
        if v and a is None:
            a = k
        if not v and a is not None:
            if k - a >= 7:
                gaps.append((a * 0.01, k * 0.01))
            a = None
    return gaps


def match_pauses(groups, gaps, length, window=0.25):
    """Best in-order pairing of original pauses with take gaps, by relative position in the line."""
    total = sum(b - a for a, b in groups)
    pauses, cum = [], 0.0
    for a, b in groups[:-1]:
        cum += b - a
        pauses.append(cum / total)
    centers = [((ga + gb) / 2) / length for ga, gb in gaps]
    np_, ng = len(pauses), len(gaps)
    best = [[0.0] * (ng + 1) for _ in range(np_ + 1)]
    for i in range(1, np_ + 1):
        for j in range(1, ng + 1):
            best[i][j] = max(best[i - 1][j], best[i][j - 1])
            delta = abs(pauses[i - 1] - centers[j - 1])
            if delta < window:
                reward = 1 - delta / window + min(0.5, gaps[j - 1][1] - gaps[j - 1][0])
                best[i][j] = max(best[i][j], best[i - 1][j - 1] + reward)
    out, i, j = [], np_, ng
    while i and j:
        if best[i][j] == best[i - 1][j]:
            i -= 1
        elif best[i][j] == best[i][j - 1]:
            j -= 1
        else:
            out.append((i - 1, j - 1))
            i, j = i - 1, j - 1
    return out[::-1]


def real_length(gaps, length):
    """Drop a tail of mostly silence with a tiny blip after it."""
    if gaps and length - gaps[-1][1] < 0.06:
        return gaps[-1][0], gaps[:-1]
    return length, gaps


def main():
    scene = json.load(open(sys.argv[1], encoding="utf-8"))
    meas = json.load(open(sys.argv[2]))
    takes = sys.argv[3]
    lines = scene["lines"]
    fit, over = {}, []
    prev_end = None
    print("id who      orig on-off      | parts: start+len@tempo               | end   tail  next  flag")
    for idx, l in enumerate(lines):
        path = latest_take(takes, l["id"])
        x = decode(path, SR)
        s, e = speech_bounds(x, sr=SR)
        x = x[s:e]
        # A sound before the first word, such as a gasp, goes before the original's onset, so the word stays on it.
        lead = 0.0
        side = os.path.splitext(path)[0] + ".json"
        if "lead" in l and os.path.exists(side):
            lead = max(0.0, json.load(open(side))["first_word"] - 0.06 - s / SR)
            x = x[int(lead * SR) :]
        gaps = take_gaps(x)
        length, gaps = real_length(gaps, len(x) / SR)
        ph = meas[l["id"]]["phrases"]
        # group original phrases separated by real pauses
        groups = [list(ph[0])]
        for a, b in ph[1:]:
            if a - groups[-1][1] >= MIN_ORIG_PAUSE:
                groups.append([a, b])
            else:
                groups[-1][1] = b
        orig_on, orig_off = ph[0][0], ph[-1][1]
        next_on = meas[lines[idx + 1]["id"]]["phrases"][0][0] if idx + 1 < len(lines) else l.get("next_on", orig_off + 3)
        limit = next_on - GAP_TO_NEXT

        # match original pauses to take gaps in order, over the whole line
        min_part = 0.1 if re.match(r"^(\[[^\]]*\]\s*)*(\w-|(\w{2,3})-\3)", l["text"], re.I) else 0.3  # stammers may be tiny
        matches = match_pauses(groups, gaps, length)
        starts, cuts, begin = [groups[0][0]], [], 0.0
        for pause_i, gap_i in matches:
            ga, gb = gaps[gap_i]
            if ga - begin < min_part or length - gb < 0.3:
                continue
            cuts.append((ga, gb))
            starts.append(groups[pause_i + 1][0])
            begin = gb
        bounds = []
        begin = 0.0
        for ga, gb in cuts:
            bounds.append((begin, ga + 0.02))
            begin = gb - 0.04
        bounds.append((begin, length + 0.04))

        hold = bool(l.get("hold"))
        parts, cursor = [], prev_end  # a line that ran over pushes the next one instead of overlapping it
        for i, ((frm, to), st) in enumerate(zip(bounds, starts)):
            ln = to - frm
            is_last = i == len(bounds) - 1
            st = max(st, cursor + 0.02) if cursor is not None else st
            if is_last:
                avail = min(limit - st, (orig_off - st) + ALLOW_TAIL)
            else:
                avail = starts[i + 1] - st - 0.03
            tempo = ln / max(avail, 0.05)
            if hold and tempo < 1.0:
                tempo = max(tempo, l.get("hold_min", 0.75))
            else:
                tempo = float(np.clip(tempo, 1.0, MAX_TEMPO))
            if is_last and st + ln / tempo > limit:
                tempo = min(HARD_TEMPO, ln / max(limit - st, 0.05))
            parts.append({"from": round(frm + lead, 3), "to": round(to + lead, 3), "start": round(st, 3), "tempo": round(tempo, 3)})
            cursor = st + ln / tempo
        if lead:
            room = parts[0]["start"] - (prev_end if prev_end is not None else 0.0) - GAP_TO_NEXT
            keep = min(lead, max(room, 0.0))
            late = min(lead - keep, max(0.0, orig_off - cursor))  # no room before: the word may wait inside the original's own span
            if late > 0:
                for p in parts:
                    p["start"] = round(p["start"] + late, 3)
                cursor += late
                keep += late
            if keep > 0.05:
                parts.insert(0, {"from": round(lead - keep, 3), "to": round(lead, 3), "start": round(parts[0]["start"] - keep, 3), "tempo": 1.0})
        end = prev_end = cursor
        flag = ""
        if end > limit + 0.005:
            flag = f"OVER {end - limit:.2f}s"
            over.append(l["id"])
        elif end - orig_off > 0.6:
            flag = "long tail"
        fit[l["id"]] = {"orig_on": ph[0][0], "orig_off": ph[-1][1], "tempo": max(p["tempo"] for p in parts), "parts": parts}
        pretty = " ".join(f"{p['start']:.2f}+{p['to'] - p['from']:.2f}@{p['tempo']:.2f}" for p in parts)
        print(f"{l['id']} {l['who']:<8} {orig_on:7.2f}-{orig_off:7.2f} | {pretty:<38} | {end:7.2f} {end - orig_off:+5.2f} {next_on:7.2f} {flag}", flush=True)
    json.dump(fit, open(sys.argv[4], "w"), ensure_ascii=False, indent=1)
    print(f"lines over limit: {over or 'none'}")


if __name__ == "__main__":
    main()
