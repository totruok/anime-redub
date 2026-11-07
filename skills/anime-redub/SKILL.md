---
name: anime-redub
description: Re-dub a scene or episode of anime or other foreign-language video into a language the user chooses, with distinct AI voices, using ElevenLabs Text to Dialogue v4 and Scribe. Runs end to end on its own, from one launch to a finished video, within a spending limit. Covers the timing-fitted translation, emotion tags, voice casting, a voice-over mix with the original kept quietly underneath, and level checks. Use this whenever the user wants to dub, re-dub or voice over an anime or film scene, replace a bad fan dub, make their own voice-over, or asks how to place a quiet original voice under a dub, whatever language they ask in and even if they never say "skill".
---

# Anime re-dub

You make a voice-over: every character gets their own designed voice in the target language, each line starts where the original phrase starts, and the original stays quietly underneath.

**Status.** One 2:40 scene of dialogue and fighting was dubbed from Japanese into Russian with real voices chosen by ear, and judged by ear. The automatic run has gone through the real API once, on a 14-second scene from Japanese into English with two characters, and its one listener liked it. Other target languages are covered only by a local stand-in for the API and by automated tests, and any other source language should work because only Scribe reads it, but only Japanese has been run. A whole episode has not been run through. Say all this to the user in your report.

## Launch

The user launches once, in words or with flags in the arguments:

| What | Flag | Default |
|---|---|---|
| Source file | a path | required |
| Window | `7:05-9:45` | the whole file, from the first spoken line to the last |
| Target language | `--language es` | required |
| Spending limit | `--budget 5` | 5 US dollars |
| Choose voices by ear | `--pick-by-ear` | off: chosen automatically |

Find the language code with `python $S/languages.py`. Below, `LANG` stands for that code and `BUDGET` for the limit.

## Run on your own

Launching is the user's approval to spend up to the limit. Work from the source to the finished video without stopping for approval or a verdict.

Stop and say what you need only in these cases: the source file or the target language is missing, the budget ran out, or something failed and retrying did not fix it. Everything else has a rule:

- **Track:** the original-language audio, not a dub. Judge by the language tags, the titles and the language of the video stream. A title that is only a group's name usually marks a fan dub. If that settles nothing, take the first track that is not in the target language.
- **Subtitles:** a file the user named, then the ones in the file, then a file beside the source with the same name, then Scribe.
- **Window:** if the user named one, keep it, and widen it only as far as the end of a line it would cut. The margin in step 1 is for a window you choose yourself.
- **Style:** the most frequent dialogue style in the counts `subs_window.py` prints.
- **Who speaks:** decide from meaning, the subtitles and frames from the video. Extract a frame with `ffmpeg -ss T -i SOURCE -frames:v 1 frame.jpg` and look at it.
- **Voices:** a designed voice for every character with real lines. Walk-on characters with a line or two can share a few "extra" voices, to save slots and money. This is untested.
- **Lines that run over:** step 9 has the limit on how often to redo them.
- **Lines that barely match:** step 8 says what to do.

If the user asks to approve each payment, or to go in small steps, do that instead: 15 seconds, then a scene, then an episode, with their verdict after each. `--pick-by-ear` stops once, at step 6.

## How to work

- **You cannot hear the result.** Numbers only show where a person should listen. Do not call a mix good. If the user does listen and their ear disagrees with a measurement, believe the ear and ask what the measurement cannot see. In this project a test once "proved" a quiet original voice was absent, because the recogniser simply could not read a voice that faint.
- **Stay inside the budget.** Scribe, Voice Design and generation cost money, and each refuses a request that would pass the limit. Every paid step prints a `budget:` line. `NO LIMIT` there means you are not in the working folder: stop and go back to it. All paid scripts cache their results, so a finished request is never paid for twice. A request cut off on its way may be paid for again, and it is counted each time. Everything else, including every remix, is free.
- **Give each character a distinct voice.** One voice for everybody is the thing this project exists to beat. Use voices from Voice Design, and do not clone real people, the original actors included.
- **Overact.** A flat reading sounds worse in anime than a wrong one. Bright, exaggerated delivery is the goal.
- **Mind the rights.** The results are for personal viewing unless the user holds the rights. Keep source media, stems, subtitles and dubs out of any repository. Do not publish anything yourself.
- **Never print the API key.** Run long jobs in the background, where their line-by-line progress stays readable.

## Setup

Make one working folder per launch outside the repository, such as `redub/show_e01/`, and run every command from there, so one `budget.json` holds the limit and one `cast.json` keeps the voices. Below, `$S` stands for the full path of the `scripts` folder next to this file.

```bash
python $S/doctor.py
python $S/budget.py set BUDGET
```

The pipeline needs ffmpeg, rubberband and the Python packages numpy, scipy, soundfile, librosa and requests, plus `audio-separator[cpu]` for step 2. The key comes from `ELEVENLABS_API_KEY` or a `.env` file in the working folder. The limit lives in `budget.json`, and `python $S/budget.py` shows what has been spent. These are estimates from the documented prices, not the account's balance.

## The pipeline

### 1. Look at the source and choose the window

```bash
ffprobe -v error -show_entries stream=index,codec_type,codec_name,channels:stream_tags=language,title -of compact SOURCE.mkv
python $S/subs_window.py subs.ass 0 99999
```

`N` in `-map 0:a:N` counts audio tracks only, from zero. Take subtitles from the file with `ffmpeg -i SOURCE.mkv -map 0:s:0 subs.ass`. Subtitles that match this particular rip save a lot of work.

When you choose the window yourself, take `START` and `END` from the subtitles so that it ends in a pause, at least two seconds after its last line. A dub often runs longer than the subtitle, and a window ending too soon cuts the last line.

On a small-steps run, separate the whole scene you expect to dub anyway and take the pilot from inside it, because stems for a window cannot be extended afterwards. Then keep the two windows apart. `STEM_START` is `start` in `stems/stems.json`. A pilot's own `START` and `END` go only to `subs_window.py` and to `make_mix.py --start START --end END`, and its `scene.json` holds only the pilot's lines. On an ordinary run `STEM_START` is simply `START`.

### 2. Separate voice from music (free, slow)

```bash
python $S/separate.py SOURCE.mkv --track N --start START --end END --out stems
```

Allow about 5 minutes of computing per minute of audio. Run it in the background: it prints the time left, and a rerun with the same settings continues from the last finished chunk. To change the window, use a new `--out` folder. It writes `stems/vocals.wav`, `stems/instrumental.wav` and `stems/stems.json`.

### 3. Draft the scene

```bash
python $S/subs_window.py subs.ass START END --draft scene.json --style STYLE
```

The first line of the output counts the lines per subtitle style. Pass the dialogue style as `--style` so songs and on-screen signs stay out, and delete any that still get through. The script refuses to replace a draft that already has `who` or `text` filled in, unless you pass `--force`.

Without subtitles, transcribe the voice stem instead (paid, 0.22 USD per hour), then draft from the transcript. Scribe's times count from the start of the stem, so the offset is `STEM_START`:

```bash
python $S/scribe.py stems/vocals.wav source.json
python $S/subs_window.py source.lines.tsv START END --offset STEM_START --draft scene.json
```

Scribe detects the language itself. If it guesses wrong, delete `source.json` and run again with the source language set, for example `--language ja`. This is paid again. While the file exists the script reuses it and ignores `--language`.

Fill in `who` for each line by meaning, by the subtitles and by frames from the video. Do not rely on Scribe's speaker labels: on old mixes it merges characters. Set `env` for each line: `narration` for dry voice-over, `room` indoors, `outdoors` outside. Times in `scene.json` are seconds of the source file. See `references/formats.md` for every field.

### 4. Measure the original

```bash
python $S/scene_measure.py scene.json stems/vocals.wav STEM_START measure.json
```

For each line this gives the real spoken `phrases`, `talk` (seconds of actual speech), `level`, `f0` and `range`. These numbers drive the next steps. Pitch is the weak one: it can read far too high or too low, or be null, on a raspy or very short line, so ignore an `f0` that does not fit the character.

On a scene of 20 lines or more it also compares the subtitles with the voice. If it prints `WARNING: subtitles sit about X s from the voice`, add that amount to every `start` and `end` in `scene.json` and measure again. If the warning stays, go back to the Scribe route in step 3. Put the shift in your report. A shorter scene is not checked, and a jump partway through a scene is missed, so never say the timing was verified.

### 5. Write the lines

`original` holds whatever the subtitles or transcript gave you, which may already be a translation. Work from it, and aim for what the actor is doing with the line as well as what it says. Put the result in `text`, in the target language. Use the alphabet Scribe writes that language in, because `dialogue.py` compares the two.

- **Length:** for Russian, aim for about 11 letters per second of `talk`, counting letters only. That was the median on the tested scene, and about half of its lines still needed some speeding up. Above roughly 13, expect the line to run long. No other language has a dependable number yet. The one English scene had only five lines, and those of 9 to 12 letters per second needed at most 1.18 times speed-up. So start from about 11, and step 8 takes a better number from the first block. A line of `talk` under a second has room for a word or two.
- **Pauses:** put `…` where the original pauses. `autofit.py` cuts takes at their own pauses and starts each part on the matching original phrase, so a matching pause is what makes a long line land.
- **Silent lines:** a line needs something to say. `make_blocks.py` refuses one that holds only tags or punctuation, so take it out of the scene.

### 6. Cast the voices (paid, about 1 cent per story character)

Write `characters.json` (see `$S/../../../examples/characters.example.json` and `references/acting-and-voices.md`), with the preview `text` in the target language, then:

```bash
python $S/design_voices.py characters.json previews --language LANG
python $S/save_voices.py characters.json previews cast.json --auto
```

`--auto` takes a preview in the right language, as unlike the voices already chosen as possible. The first character has nothing to compare with, so it simply gets the first preview. That keeps the characters apart, but it cannot judge the acting, so tell the user which letters it took. Picking by acoustic numbers was tried on the tested scene and could not replace listening, which is why choosing by ear stays available.

With `--pick-by-ear`, build a page instead, give the user `voices.html`, and wait for their choice:

```bash
python $S/build_audition_page.py characters.json previews voices.html
python $S/save_voices.py characters.json previews cast.json hero=A rival=C
```

`design_voices.py` adds "Native <language> speaker" to each voice description, so leave the language out of `common`. If a character needs a regional accent, put it in their `description`, and move `Neutral standard accent.` out of `common` into the descriptions of the other characters, because `common` goes on every voice. It warns when a preview comes back in another language: fix the text, delete `previews/KEY.json` and run again, which is billed again. Each saved voice takes a slot on the account.

### 7. Add the tags

Read `references/acting-and-voices.md` before writing them. Tags come from what the original actor does, read from `level` and `range` in `measure.json` and from the scene, and they belong inside the line where the delivery changes: `[dramatic] From so far away… [weary] it was a long road.` Keep tags in English whatever the language of the line, as they were on the tested scene. Tags are billed like any other characters, and on the tested scene they made up about half of the bill.

### 8. Generate (paid)

```bash
python $S/cost.py scene.json --passes 1.5
python $S/make_blocks.py scene.json blocks
python $S/dialogue.py blocks/block_01.json cast.json gen --language LANG --collect takes
```

`cost.py` leaves out what the voices already cost, so compare its estimate with what `python $S/budget.py` shows is left. If it is over, stop and say so before generating. Otherwise generate block 1 first and run step 9 on it. On a scene of several blocks, step 9's command then stops at the first line of block 2 with `no take for line N` and writes no `fit.json`. That is expected: the table above the message is complete for block 1. For a language with no measured rate, take one from the lines of that table with a tempo of about 1.1 or less: the letters of the line without its tags, divided by its `talk` in `measure.json`. Rewrite the lines of the later blocks to that rate, then generate them one block at a time. `fit.json` comes from the run after the last block.

One request is one performance, so the voices stay consistent and react to each other, which is why lines are not generated one by one. Each block goes through Scribe to find where every line was really said, since the server's own segment times can miss by 0.3 s.

Read what `dialogue.py` prints. `heard:` shows a line that Scribe wrote differently. If its first or last word looks like it belongs to the neighbouring line, the cut may be in the wrong place, so list that line in your report. `WARNING: line ... barely matches` means the cut cannot be trusted. If most lines of the block warn, the cause is the alphabet or the language: fix the text and regenerate. If only a line or two warn, the performance may have lost or added a line, and a neighbouring take may be missing a word too. Regenerate the whole block once by rerunning `dialogue.py` with `--seed 18`, then accept the result and keep any line that still warns for your report.

### 9. Fit the takes to the original

```bash
python $S/autofit.py scene.json measure.json takes fit.json
```

Read the table it prints. Parts are sped up to at most 1.22 times, or 1.30 for a last part that would otherwise run into the next line.

- **`OVER`** means the line still runs into the next one. Shorten the text, or add a tempo tag such as `[speedy]`, `[snappy]` or `[rushed]`, and regenerate. Do this at most twice per block, then accept what is left and put it in your report. A small overrun can stay.
- **`long tail`** means the line ends well after the original. List it in your report as a place to listen.

Changing any text in a block regenerates the whole block, and every line in it comes back as a new performance. Moving a line into its own small block costs almost nothing, but its voice may differ a little from its neighbours. Prefer the small block when only one or two lines of a block run over.

`dialogue.py` reads only the block file it is given, never `scene.json`. To change a line, edit its `text` in both `scene.json` and the block file that holds it, then rerun `dialogue.py` on that block. Do not rerun `make_blocks.py` once a block has been paid for, because it can move the boundaries. For a small block, write a new file such as `blocks/small_05.json` with just that line, in the same form. Keep the line in its old block file so that block's cache still holds, and do not rerun the old block afterwards, because that copies the old take back.

`references/formats.md` has two fields for special cases: `hold` lets a take slow down to fill a long drawn-out line, and `next_on` tells the last line of a scene where the next speech begins. Set `next_on` when another line follows just outside the window.

### 10. Mix (free)

```bash
python $S/make_mix.py scene.json fit.json takes mix.json --stems stems
python $S/mix_window.py mix.json
```

The defaults keep the original voice at -14 dB inside lines and the music at -5 dB, so the dub sits about 14 dB above the voice under it. Between lines the original voice stays at -5 dB, which keeps breaths and grunts. Change these with `--voice-db`, `--music-db`, `--replace` or `--duck`, and give each trial its own `--out-dir` so earlier mixes survive for comparison. `references/mix-recipes.md` has the measurements behind these numbers and how they differ between dubs. A remix of a scene takes a couple of minutes and costs nothing.

Read the warnings `mix_window.py` prints. A line cut by the end of the window is worth fixing with a wider window.

### 11. Check by numbers

```bash
python $S/check_levels.py mix.json
```

This reports the balance the mix really has and the parts where the dub sinks into the music. It is a list of places to listen to, not a verdict: a whisper meant to be quiet will be on it too. Leave those parts as they are and list them in your report. To raise one quiet part, a person can add `"gain_db": 6` to that part in `mix.json` and remix.

If the user asks for a paid check that every line is understood, run Scribe on the mix: `python $S/scribe.py out/dub_mix.wav check.json --language LANG --speakers 1`. Scribe reads words a person would barely make out, so a passed line can still be too quiet. A rerun with the same output name reads the old result, so give each mix its own name.

### 12. Render and report

```bash
$S/render.sh SOURCE.mkv START DURATION out/dub_mix.wav dub.mp4 N
```

`START` is `start` and `DURATION` is `end` minus `start`, both from `mix.json`. The video is brought to -18 LUFS, so versions can be compared fairly by switching between them. With the track number `N`, it also writes `dub_timing.mp4` with the original in the left ear and the dub in the right, which is the quickest way to check timing on headphones. That check is for timing only, and it plays louder than the main video.

Then report: where the video is, what was spent, which voices were chosen automatically, any subtitle shift, lines still marked `OVER` or `long tail`, lines whose cut could not be trusted, the parts `check_levels.py` lists, and the status at the top of this file. Say that nobody has listened to it yet.

## When the user reports a problem

| They say | Likely cause and what to do |
|---|---|
| The same character sounds like different people | Lines were generated apart. Keep the character's lines in one request where possible. Keep one EQ per character, as `post_fx.py` does: per-scene EQ made this worse. |
| Voices sound flat or embarrassing | Stock voices or weak tags. Use Voice Design, stability 0 and stronger tags. Transfer what the original actor does instead of reading the text neutrally. If the automatic choice is the problem, run with `--pick-by-ear`. |
| A phrase sinks or the sound seems to die | The delivery fades inside one take, while the gain is one per line. Find it with `check_levels.py`. |
| The dub lags behind the picture | Open `dub_timing.mp4`. Shorten the text or add a tempo tag, then regenerate. |
| The original is too loud or too quiet | Change `--voice-db` and `--music-db`, then remix for free. |

## Scaling up to an episode

An episode held about 8 times the text of the tested scene, which is roughly 15,000 characters in Russian: about 1.50 USD for a clean pass, and 2 to 3 USD in practice. Another language will have a different number of characters. Use one window and one folder for the whole run: `make_blocks.py` splits the requests, and the result is one video. Start the window at the first spoken line and end it after the last. A window cannot skip a song in its middle, so an opening after a cold open stays in the video undubbed. Expect about two hours of separation. Say plainly that a whole episode has not been run through this pipeline yet, because problems that one scene cannot show may appear, such as many minor characters needing voices.
