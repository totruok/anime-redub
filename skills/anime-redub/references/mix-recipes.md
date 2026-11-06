# Mix recipes: how existing dubs keep the original underneath

The model behind every number here is:

```
dub_track = a * original_voice + b * original_music + new_voice
```

`a` and `b` are found by least squares against separated stems, stretch by stretch. They survive the new voice being far louder than either.

## What was measured

| Dub | Original voice | Dub above it, voice band | Music |
|---|---|---|---|
| Fan dub A, 2008 | 0 dB, not lowered | 4 to 6 dB | unchanged |
| Fan dub B, 2008 | -6.2 dB | about 17 dB | -6.2 dB, constant |
| Modern dub, Frieren S02E01 | -12.2 to -12.9 dB | 13.5 to 14.5 dB | -3.5 dB, constant, no ducking |
| Another modern dub | roughly -20 to -30 dB, indirect estimate | not measured | down about 17 dB under speech |

Each row comes from one episode of one dub, so recipes clearly vary by studio. There is no single standard. Fan dub A, with the original not lowered at all, was the one a listener liked least.

## The default here

`--voice-db -14 --music-db -5`. It comes from the Frieren row. On the tested scene, one listener liked it better than the trials before it.

The dub here is levelled to the original line, so it starts at about the original voice's natural level. Taking the original down 14 dB therefore gives the same 14 dB gap. Frieren's Russian sits about 5 dB above that natural balance, with the music 3.5 dB down, so the music goes to -5 dB here to keep the same relation.

Other starting points:

| Sound | Flags |
|---|---|
| Same relation as fan dub B: dub 17 dB above everything | `--voice-db -17.1 --music-db -17.1` |
| Heavy ducking, original voice barely there | `--voice-db -25 --music-db 0 --duck -17` |
| Clean dub with no original voice in the lines | `--replace --music-db 0` |

## Frieren in more detail

- The whole original drops by a constant 3.5 dB: in silence, 94% of frames were within 1 dB of that.
- Under speech the side channel stayed put: 88% of frames within 1 dB, and none below -6 dB when the background was loud.
- The centre channel drops within 0.1 to 0.2 s of the Russian voice starting.
- On a stretch of loud music, the music stayed at about -4 dB under the Russian while the Japanese voice sat at -12 dB. A voice dropping while the music holds suggests the voice was handled separately. That is an inference, not a direct observation.
- Unknown: whether the Japanese comes back up in pauses. The measured stretches had no pauses containing Japanese.

## Measuring a dub yourself

When a file has both the dub and the original track:

```bash
python $S/separate.py SOURCE.mkv --track ORIGINAL_N --start 360 --end 420 --out stems
python $S/underlay_measure.py SOURCE.mkv DUB_N 360 60 stems/vocals.wav stems/instrumental.wav
```

The third and fourth arguments are the window, which must match the stems. It prints the lag between the tracks, the gains under the new voice and between lines, and the new voice over the original.

Traps that were actually hit:

- **Choose a stretch with audible music.** On a stretch where the music is around -55 dB the fit is meaningless. Map the background level first.
- **A centred dub leaves the side channel (L-R) free of Russian,** so the side channel gives the background's gain without any separation. This only works on true stereo.
- **The separator makes false dips:** about 1.3 dB in a controlled test. Do not read small drops as mixing decisions.
- **Absence is hard to prove.** Scribe does not read a voice at -40 to -50 dB, and a pause test cannot see an original voice that only talks while the dub talks. Without the original track, say "could not detect", never "absent".
- **One stretch of a few transitions is not a recipe.** Say how much you measured when you report it.
