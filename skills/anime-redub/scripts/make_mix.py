"""Write the config for mix_window.py from the fit and the balance you want.

usage: make_mix.py SCENE.json FIT.json TAKES_DIR OUT_MIX.json (--stems DIR | --vocals V --instrumental I --stem-start S)
                   [--start S] [--end E] [--voice-db -14] [--music-db -5] [--replace] [--duck DEPTH_DB] [--out-dir out]

The dub is levelled to the original line, so --voice-db -14 leaves the dub about 14 dB
above the original voice under it. That level holds inside lines; between lines the
original voice stays at --music-db, so breaths and grunts survive. The defaults are the
balance measured from a modern voice-over: see references/mix-recipes.md. --replace takes
the original line out completely. --duck also lowers the music by DEPTH_DB while the dub
speaks. Give each trial its own --out-dir to keep earlier mixes for comparison.
"""
import argparse
import json
import os

import soundfile as sf

POST = {
    "highpass": 90,
    "eq_match": {"strength": 0.7, "max_cut": 5.0, "max_boost": 3.0, "full_strength_seconds": 3.0},
    # Acoustics per scene, chosen by the "env" field of a line. null means dry, as narration should be.
    "envs": {
        "default": None,
        "narration": None,
        "room": {"slap_db": None, "diffuse_db": -31, "rt": 0.45, "predelay_ms": 20, "wet_lowpass": 4000},
        "outdoors": {"slap_ms": 110, "slap_db": -32, "diffuse_db": -30, "rt": 0.3, "predelay_ms": 30, "wet_lowpass": 5000},
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("fit")
    ap.add_argument("takes")
    ap.add_argument("out")
    ap.add_argument("--stems", help="folder written by separate.py")
    ap.add_argument("--vocals")
    ap.add_argument("--instrumental")
    ap.add_argument("--stem-start", type=float)
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--voice-db", type=float, default=-14.0, help="the original voice inside lines")
    ap.add_argument("--music-db", type=float, default=-5.0)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--duck", type=float, help="depth in dB, for example -17")
    ap.add_argument("--out-dir", default="out")
    a = ap.parse_args()

    if a.stems:
        meta = json.load(open(os.path.join(a.stems, "stems.json")))
        vocals, instrumental = os.path.join(a.stems, meta["vocals"]), os.path.join(a.stems, meta["instrumental"])
        stem_start = meta["start"]
    elif a.vocals and a.instrumental and a.stem_start is not None:
        vocals, instrumental, stem_start = a.vocals, a.instrumental, a.stem_start
    else:
        raise SystemExit("give --stems, or all of --vocals, --instrumental and --stem-start")
    info = sf.info(vocals)
    stem_end = stem_start + info.frames / info.samplerate
    end = a.end if a.end is not None else stem_end
    if end > stem_end:
        print(f"WARNING: the stems end at {stem_end:.2f} s, so the mix stops there and not at {end:.2f} s")
        end = stem_end
    root = os.path.dirname(os.path.abspath(a.out))
    rel = lambda p: os.path.relpath(os.path.abspath(p), root)  # noqa: E731
    cfg = {
        "scene": rel(a.scene),
        "takes": rel(a.takes),
        "instrumental": rel(instrumental),
        "vocals": rel(vocals),
        "stem_start": stem_start,
        "start": a.start if a.start is not None else stem_start,
        "end": end,
        "out_dir": a.out_dir,
        "residual_gain": 1.0,
        "lines": json.load(open(a.fit, encoding="utf-8")),
        "post": POST,
    }
    if a.music_db:
        cfg["original_gain_db"] = a.music_db
    if not a.replace:
        # original_gain_db lowers everything from the original, so the line itself only needs the difference.
        cfg["voice_under_db"] = a.voice_db - a.music_db
    if a.duck:
        cfg["duck"] = {"depth_db": a.duck, "attack": 0.35, "release": 0.6, "lookahead": 0.1}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    what = "original line removed" if a.replace else f"original voice {a.voice_db:+.1f} dB inside lines"
    print(f"{a.out}: {what}, music {a.music_db:+.1f} dB, {len(cfg['lines'])} lines, {cfg['start']:.2f}-{cfg['end']:.2f} s")


if __name__ == "__main__":
    main()
