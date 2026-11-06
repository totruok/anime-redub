"""Transcribe with diarization through ElevenLabs Scribe.

usage: scribe.py AUDIO OUT.json [--model scribe_v2] [--lang jpn] [--speakers N]
Skips the call if OUT.json already exists, so a rerun never pays twice.
Also writes OUT.lines.tsv: start, end, speaker, text, one utterance per line.
"""
import argparse
import json
import os
import time

import requests

import el


def utterances(words, gap=0.7):
    out, cur = [], None
    for w in words:
        if w.get("type") == "spacing":
            continue
        sp = w.get("speaker_id") or "?"
        is_event = w.get("type") == "audio_event"
        if cur and cur["speaker"] == sp and w["start"] - cur["end"] <= gap:
            cur["text"] += w["text"]
            cur["end"] = w["end"]
        else:
            if cur:
                out.append(cur)
            cur = {"start": w["start"], "end": w["end"], "speaker": sp, "text": w["text"]}
        if is_event:
            cur["has_event"] = True
    if cur:
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("out")
    ap.add_argument("--model", default="scribe_v2")
    ap.add_argument("--lang", default="jpn")
    ap.add_argument("--speakers", type=int)
    a = ap.parse_args()

    if os.path.exists(a.out):
        print(f"exists, not calling the API again: {a.out}", flush=True)
        data = json.load(open(a.out))
    else:
        form = {
            "model_id": a.model,
            "language_code": a.lang,
            "diarize": "true",
            "tag_audio_events": "true",
            "timestamps_granularity": "word",
        }
        if a.speakers:
            form["num_speakers"] = str(a.speakers)
        size = os.path.getsize(a.audio) / 1e6
        print(f"uploading {a.audio} ({size:.0f} MB), model {a.model}", flush=True)
        t = time.time()
        with open(a.audio, "rb") as f:
            r = requests.post(
                f"{el.API}/v1/speech-to-text",
                headers=el.headers(),
                data=form,
                files={"file": (os.path.basename(a.audio), f)},
                timeout=1800,
            )
        el.check(r)
        data = r.json()
        tmp = a.out + ".tmp"
        json.dump(data, open(tmp, "w"), ensure_ascii=False)
        os.replace(tmp, a.out)
        print(f"done in {time.time() - t:.0f}s", flush=True)

    utts = utterances(data.get("words", []))
    tsv = os.path.splitext(a.out)[0] + ".lines.tsv"
    with open(tsv, "w") as f:
        for u in utts:
            f.write(f"{u['start']:.2f}\t{u['end']:.2f}\t{u['speaker']}\t{u['text']}\n")
    speakers = {}
    for u in utts:
        speakers.setdefault(u["speaker"], [0, 0.0])
        speakers[u["speaker"]][0] += 1
        speakers[u["speaker"]][1] += u["end"] - u["start"]
    print(f"language: {data.get('language_code')} p={data.get('language_probability')}")
    print(f"utterances: {len(utts)}, written to {tsv}")
    for s, (n, d) in sorted(speakers.items(), key=lambda kv: -kv[1][1]):
        print(f"  {s}: {n} utterances, {d:.0f}s")


if __name__ == "__main__":
    main()
