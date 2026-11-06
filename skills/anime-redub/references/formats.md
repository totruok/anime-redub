# File formats

All times are seconds of the source file, except part `from` and `to`, which count from the first speech sample of a take.

## scene.json

```json
{"lines": [
  {"id": "01", "who": "hero", "start": 429.9, "end": 431.2, "original": "the line as the subtitles have it", "env": "room", "ru": "[softly] Отчего ты молчишь?"}
]}
```

| Field | Meaning |
|---|---|
| `id` | Unique, sortable text. Names the take files, so keep it stable. |
| `who` | Key into `cast.json`. |
| `start`, `end` | Anchors from the subtitles. `scene_measure.py` finds the real phrases around them. |
| `original` | The subtitle or transcript text, in whatever language it came in, for you to translate from. No script reads it. |
| `env` | Acoustics for this line, a key of `post.envs` in `mix.json`: `narration` and `default` are dry, `room` adds a soft indoor tail, `outdoors` a faint far echo. Add your own in `mix.json`. |
| `ru` | The text to speak, with tags. Billed in full, tags included. |
| `lead` | Optional, any value. A sound before the first word, such as a gasp, goes before the original's onset, so the word itself stays on it. |
| `hold` | Optional, true. The take may be slowed down to fill a long drawn-out original line, no slower than `hold_min` (default 0.75). |
| `next_on` | Optional, on the last line only. Where the next speech begins, when it lies outside this scene. |

## characters.json

```json
{"project": "Моя озвучка",
 "common": "Native Russian speaker with a neutral standard accent. Studio-quality voice-over recording: dry, close microphone, no room echo, no reverb, no background noise.",
 "characters": [
  {"key": "hero", "name": "Герой", "role": "наивный молодой герой",
   "description": "Young man, about 18. Light, bright tenor...",
   "text": "[confidently] Нет. Я обязательно вернусь. [nervous] Ч-что это было?..."}
]}
```

`text` must be 100 to 1000 characters. `project` prefixes the saved voice's name. `key` matches `who` in the scene.

## cast.json

Written by `save_voices.py`. To use a voice you already have, write it by hand.

```json
{"hero": {"voice_id": "...", "name": "Моя озвучка Герой", "letter": "A"}}
```

## measure.json

Written by `scene_measure.py`, keyed by line id: `who`, `phrases` (list of `[on, off]`), `level` (dB), `f0` (Hz, or null), `range` (semitones), `voiced` (share of voiced frames), `talk` (seconds of speech).

## fit.json

Written by `autofit.py`, keyed by line id: `orig_on`, `orig_off`, `tempo` (the highest of the parts), `parts`. Each part is `{"from", "to", "start", "tempo"}`: the piece of the take, where it goes in the source's time, and how much it is sped up.

## mix.json

Written by `make_mix.py`. Edit it freely and rerun `mix_window.py`, which is free.

| Field | Meaning |
|---|---|
| `scene`, `takes`, `vocals`, `instrumental` | Paths relative to `mix.json`. |
| `stem_start` | The source second where the stems begin. |
| `start`, `end` | The window to mix. |
| `out_dir` | Output folder: `dub_mix.wav`, `dub_only.wav`, `residual_voice.wav`, `placement.json`. |
| `lines` | The content of `fit.json`. A line takes `gain_db`, and so does a part. |
| `original_gain_db` | Lowers everything from the original, voice and music alike. |
| `voice_under_db` | Lowers the original voice further, inside lines only. Leave it out to remove the line entirely. |
| `residual_gain` | Scales the whole original voice stem. Normally 1. |
| `duck` | Optional music ducking: `depth_db`, `attack`, `release`, `lookahead`. |
| `post` | One EQ per character towards their original lines, plus acoustics per `env`. An `env` of null is dry. |

The original voice inside a line ends up at `original_gain_db + voice_under_db`. Between lines it stays at `original_gain_db`, which keeps breaths and grunts.

## blocks and takes

`make_blocks.py` writes `block_NN.json`, which has the same form as `scene.json`. `dialogue.py` writes into its output folder: `raw/HASH.mp3` with its `.json` and `.scribe.json`, then `takes_HASH/ID_WHO.wav` with a sidecar `.json` holding `first_word`, the seconds from the start of the take to its first word. `--collect` copies the takes into the one folder that `autofit.py` and `mix_window.py` read. The hash covers the text and all settings, so a changed line means a new paid request.
