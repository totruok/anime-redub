---
name: anime-redub
description: Re-dub a scene or episode of anime or other foreign-language video into Russian with distinct AI voices, using ElevenLabs Text to Dialogue v4 and Scribe. Covers the timing-fitted translation, emotion tags, voice casting, a voice-over mix with the original kept quietly underneath, and level checks. Use this whenever the user wants to dub, re-dub or voice over an anime or film scene, replace a bad fan dub, make their own voice-over, or asks how to place a quiet original voice under a dub, even if they never say "skill". Also triggers in Russian - переозвучить аниме, сделать озвучку, дубляж, закадровая озвучка, многоголоска, заменить пиратскую озвучку.
---

# Anime re-dub

You make a voice-over: every character gets their own designed Russian voice, each line starts where the original phrase starts, and the original stays quietly underneath.

**Status.** Tested end to end on one 2:40 scene of dialogue and fighting. A whole episode has not been run through yet. The target language is Russian only, because `dialogue.py` matches recognised Cyrillic words to the script. The source can be any language.

## How to work

- **You cannot hear the result.** The user's ear is the final judge, and numbers only show where to listen. Do not call a mix good. When the user's ear and a measurement disagree, believe the ear and ask what the measurement cannot see. In this project a test once "proved" a quiet original voice was absent, because the recogniser simply could not read a voice that faint.
- **Ask before every paid step.** Scribe, Voice Design and generation cost money. State the sum and wait for a clear yes. All paid scripts cache their results, so a rerun never pays twice. Everything else, including every remix, is free.
- **Go in small steps: 15 seconds, then a scene, then an episode.** Timing and voice problems show up in the first 15 seconds, and each step up costs several times more. Stop for the user's verdict after each.
- **Give each character a distinct voice.** One voice for everybody is the thing this project exists to beat. Use voices from Voice Design, and do not clone real people, the original actors included.
- **Overact.** A flat reading sounds worse in anime than a wrong one. Bright, exaggerated delivery is the goal.
- **Mind the rights.** The results are for personal viewing unless the user holds the rights. Keep source media, stems, subtitles and dubs out of any repository. If the user wants to publish a dubbed clip, say it is a rights question and that the decision is theirs.
- **Never print the API key.** Run long jobs in the background, where their line-by-line progress stays readable.

## Setup

Make one working folder per scene outside the repository, such as `redub/show_e01/`, and run every command from there. Below, `$S` stands for the full path of the `scripts` folder next to this file.

```bash
python $S/doctor.py
```

The pipeline needs ffmpeg, rubberband and the Python packages numpy, scipy, soundfile, librosa and requests, plus `audio-separator[cpu]` for step 2. The key comes from `ELEVENLABS_API_KEY` or a `.env` file in the working folder.

## The pipeline

### 1. Look at the source and choose the window

```bash
ffprobe -v error -show_entries stream=index,codec_type,codec_name,channels:stream_tags=language,title -of compact SOURCE.mkv
python $S/subs_window.py subs.ass 0 99999
```

Find the original-language audio track. `N` in `-map 0:a:N` counts audio tracks only, from zero. Take subtitles from the file (`ffmpeg -i SOURCE.mkv -map 0:s:0 subs.ass`) or ask the user for them. Subtitles that match this particular rip save a lot of work.

Choose `START` and `END` from the subtitles so that the window ends in a pause, at least two seconds after its last line. A dub often runs longer than the subtitle, and a window ending too soon cuts the last line.

For a pilot, separate the whole scene you expect to dub anyway, and take the pilot from inside it. The stems can then be reused, and the pilot's lines can stay a block of their own later. Stems for a window cannot be extended afterwards.

### 2. Separate voice from music (free, slow)

```bash
python $S/separate.py SOURCE.mkv --track N --start START --end END --out stems
```

Allow about 5 minutes of computing per minute of audio. Run it in the background: it prints the time left, and a rerun with the same settings continues from the last finished chunk. To change the window, use a new `--out` folder. It writes `stems/vocals.wav`, `stems/instrumental.wav` and `stems/stems.json`.

### 3. Draft the scene

```bash
python $S/subs_window.py subs.ass START END --draft scene.json --style STYLE
```

The first line of the output counts the lines per subtitle style. Pass the dialogue style as `--style` so songs and on-screen signs stay out, and delete any that still get through.

Without subtitles, transcribe the voice stem instead (paid, $0.22 per hour), then draft from the transcript. Scribe's times count from the start of the stem, so the offset is `START`:

```bash
python $S/scribe.py stems/vocals.wav jp.json --lang jpn
python $S/subs_window.py jp.lines.tsv START END --offset START --draft scene.json
```

Fill in `who` for each line by meaning, by the subtitles and by frames from the video. Do not rely on Scribe's speaker labels: on old mixes it merges characters. Set `env` for each line: `narration` for dry voice-over, `room` indoors, `outdoors` outside. Times in `scene.json` are seconds of the source file. See `references/formats.md` for every field.

### 4. Measure the original

```bash
python $S/scene_measure.py scene.json stems/vocals.wav START measure.json
```

For each line this gives the real spoken `phrases`, `talk` (seconds of actual speech), `level`, `f0` and `range`. These numbers drive the next steps. Pitch is the weak one: it can read far too high or too low, or be null, on a raspy or very short line, so ignore an `f0` that does not fit the character.

### 5. Write the Russian lines

`original` holds whatever the subtitles or transcript gave you, which may already be a translation. Work from it, and aim for what the actor is doing with the line as well as what it says. Put the result in `ru`.

- **Length:** aim for about 11 Russian letters per second of `talk`, counting letters only. That was the median on the tested scene, and about half of its lines still needed some speeding up. Above roughly 13, expect the line to run long. A line of `talk` under a second has room for a word or two.
- **Pauses:** put `…` where the original pauses. `autofit.py` cuts takes at their own pauses and starts each part on the matching original phrase, so a matching pause is what makes a long line land.

### 6. Cast the voices (paid, about 1 cent per character)

Write `characters.json` (see `examples/characters.example.json` in the repository and `references/acting-and-voices.md`), then:

```bash
python $S/design_voices.py characters.json previews
python $S/build_audition_page.py characters.json previews voices.html
```

Each character returns three previews with the same text. Give the user `voices.html` to choose from by ear, because you cannot judge this. Then save only the chosen ones, since each saved voice takes a slot on the account:

```bash
python $S/save_voices.py characters.json previews cast.json hero=A rival=C
```

### 7. Add the tags

Read `references/acting-and-voices.md` before writing them. Tags come from what the original actor does, read from `level` and `range` in `measure.json` and from the scene, and they belong inside the line where the delivery changes: `[dramatic] Издалека… [weary] дорога была долгой.` Tags are billed like any other characters, and on the tested scene they made up about half of the bill.

### 8. Generate (paid)

```bash
python $S/cost.py scene.json --passes 1.5
python $S/make_blocks.py scene.json blocks
python $S/dialogue.py blocks/block_01.json cast.json gen --collect takes
```

Run `dialogue.py` once per block. Show the cost first and wait for a yes. One request is one performance, so the voices stay consistent and react to each other, which is why lines are not generated one by one. Each block goes through Scribe to find where every line was really said, since the server's own segment times can miss by 0.3 s.

### 9. Fit the takes to the original

```bash
python $S/autofit.py scene.json measure.json takes fit.json
```

Read the table it prints. Parts are sped up to at most 1.22 times, or 1.30 for a last part that would otherwise run into the next line.

- **`OVER`** means the line still runs into the next one. Shorten the text, or add a tempo tag such as `[speedy]`, `[snappy]` or `[rushed]`. A small overrun on a line the user likes can stay.
- **`long tail`** means the line ends well after the original. Check it by ear.

Changing any text in a block regenerates the whole block, and every line in it comes back as a new performance. Moving a line into its own small block costs almost nothing, but its voice may differ a little from its neighbours. Tell the user which trade-off they are choosing.

### 10. Mix (free)

```bash
python $S/make_mix.py scene.json fit.json takes mix.json --stems stems
python $S/mix_window.py mix.json
```

The defaults keep the original voice at -14 dB inside lines and the music at -5 dB, so the dub sits about 14 dB above the voice under it. Between lines the original voice stays at -5 dB, which keeps breaths and grunts. Change these with `--voice-db`, `--music-db`, `--replace` or `--duck`, and give each trial its own `--out-dir` so earlier mixes survive for comparison. `references/mix-recipes.md` has the measurements behind these numbers and how they differ between dubs. A remix takes a couple of minutes and costs nothing, so try things freely.

Read the warnings `mix_window.py` prints. A line cut by the end of the window is worth fixing with a wider window.

### 11. Check by numbers

```bash
python $S/check_levels.py mix.json
```

This reports the balance the mix really has and the parts where the dub sinks into the music. It is a list of places to listen to, not a verdict: a whisper meant to be quiet will be on it too. To raise one quiet part, add `"gain_db": 6` to that part in `mix.json` and remix, but only if the user wants it. They may prefer the performance as it is.

For a paid check that every line is understood, run Scribe on the mix: `python $S/scribe.py out/dub_mix.wav check.json --lang rus --speakers 1`. Scribe reads words a person would barely make out, so a passed line can still be too quiet.

### 12. Render and ask

```bash
$S/render.sh SOURCE.mkv START DURATION out/dub_mix.wav dub.mp4 N
```

`DURATION` is `end` minus `start` from `mix.json`. The video is brought to -18 LUFS, so versions can be compared fairly by switching between them. With the track number `N`, it also writes `dub_timing.mp4` with the original in the left ear and the dub in the right, which is the quickest way to check timing on headphones. That check is for timing only, and it plays louder than the main video. Give the user the video and ask what they hear.

## When the user reports a problem

| They say | Likely cause and what to do |
|---|---|
| The same character sounds like different people | Lines were generated apart. Keep the character's lines in one request where possible. Keep one EQ per character, as `post_fx.py` does: per-scene EQ made this worse. |
| Voices sound flat or embarrassing | Stock voices or weak tags. Use Voice Design, stability 0 and stronger tags. Transfer what the original actor does instead of reading the text neutrally. |
| A phrase sinks or the sound seems to die | The delivery fades inside one take, while the gain is one per line. Find it with `check_levels.py`. |
| The Russian lags behind the picture | Open `dub_timing.mp4`. Shorten the text or add a tempo tag, then regenerate. |
| The original is too loud or too quiet | Change `--voice-db` and `--music-db`, then remix for free. |

## Scaling up to an episode

An episode held about 8 times the text of the tested scene, which is roughly 15,000 characters: about $1.50 for a clean pass, and $2 to $3 in practice. Work scene by scene, leave out the opening and ending songs, and expect about two hours of separation. Say plainly that a whole episode has not been run through this pipeline yet, because problems that one scene cannot show may appear, such as many minor characters needing voices.
