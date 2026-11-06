# Acting, tags and voices

Everything here was learned on one scene with `eleven_v4`, judged by one listener. Treat it as a good starting point, and check the current ElevenLabs documentation for tags, since v4 has many more than are listed here.

## Settings

- **Model:** `eleven_v4`. On the tested scene it gave much better emotional range than v3, and the listener's reaction to the switch was immediate. `eleven_v4_turbo` costs half as much but is built for real time. It has not been tried here.
- **Stability 0.** This is the least stable and most expressive setting, the opposite of what the name suggests. It is the default in `dialogue.py`.
- **One request per block,** so a character keeps one voice and the characters react to each other. Generating line by line made one character sound like different people.

## Where tags come from

Read what the original actor does:

| In `measure.json` or the scene | Try |
|---|---|
| Line much louder than the scene's median | `[shouts]`, `[screaming]`, `[powerful]` |
| Line much quieter | `[softly]`, `[quietly]`, `[whispers]` |
| Wide pitch `range` | a strong emotion tag, such as `[overjoyed]` or `[tearful, trembling]` |
| Emotion turns inside the line | one tag at each turn: `[dramatic] Издалека… [weary] дорога была долгой.` |
| Original is fast or short | `[speedy]`, `[snappy]`, `[rushed]` |
| Gasp before a word | `[gasps]`, plus `"lead": true` on the line |

Automatic emotion recognition from the audio was tried and dropped: on anime it returned "unknown" almost every time. Level and pitch measurements, plus reading the scene, worked better.

## What tags do beyond emotion

- **Tempo tags work.** `[speedy]`, `[snappy]` and `[rushed]` really do shorten a line, and that is often better than stretching it in the mix.
- **Slow directions cost time.** v4 already speaks slower than v3, and directions like `relishing every word` slow it further.
- **`[booming]`** stretched lines and did not match the original. Avoid it.
- **`[shouts]` can push a low voice upward,** away from how it normally sounds. Listen for this on deep characters.
- **Fading tags fade for real.** `[weary]` or `[softly, earnestly]` can drop the end of a line by 15 dB or more against its start, while the music stays where it is. `check_levels.py` finds these places.
- **The model may add sounds of its own,** such as a laugh after `[overjoyed]` that no tag asked for.

## Voices

Voice Design previews give three takes per character with the same text. You pay for the preview text only, which comes to about a cent per character tried at the usual rate. That is a calculation, since the API page lists no separate price. Saving a chosen voice is free. A description that worked has this shape: age, pitch and timbre in plain words, temperament, then the kind of role.

> Young man, about 18. Light, bright tenor, clearly higher than an average male voice. Sincere, slightly naive and awkward, stammers when nervous but can sound heroic. Animated adventure protagonist with good comic timing.

- Put the shared recording conditions in `common`: a native speaker, a dry, close microphone, no room echo. A roomy preview sounds like someone recording in a bathroom, and that follows the character into every scene.
- Make the preview `text` run through the character's real range, from calm to shouting, since that is what the voice has to survive.
- Let the user pick by ear from the audition page. Picking voices by acoustic numbers was tried and could not replace listening.
- Voices from the shared library join the account on first use and take up slots, so don't try them casually. Designed voices are saved only when chosen.
- Do not clone real people, and that includes the original actors. The ElevenLabs Dubbing product does clone the original cast, costs from $2.20 per minute (about $55 per episode) and did not allow editing the translation through the API below Enterprise, which is why this pipeline does not use it.
