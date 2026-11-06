#!/bin/bash
# Put the finished mix under the picture at a fixed loudness, so versions can be compared by switching between them.
# usage: render.sh SOURCE START DURATION DUB_MIX.wav OUT.mp4 [ORIGINAL_TRACK] [CRF]
# With ORIGINAL_TRACK (the N of -map 0:a:N) it also writes OUT_timing.mp4: the original
# in the left ear and the dub in the right, for checking timing with headphones.
set -euo pipefail
SRC="$1"; S="$2"; D="$3"; DUB="$4"; OUT="$5"; TRACK="${6:-}"; CRF="${7:-24}"
TARGET=-18
V=(-c:v libx264 -crf "$CRF" -preset fast -pix_fmt yuv420p)
A=(-c:a aac -b:a 192k -movflags +faststart)
LIM="alimiter=limit=0.97:level=false"

lufs() { ffmpeg -nostdin -hide_banner "$@" -af ebur128=framelog=quiet -f null - 2>&1 | grep -E '^ +I:' | tail -1 | awk '{print $2}'; }
gain() { awk -v t="$TARGET" -v l="$1" 'BEGIN{printf "%.1f", t-l}'; }

G_DUB=$(gain "$(lufs -i "$DUB")")
echo "dub gain to $TARGET LUFS: $G_DUB dB"
ffmpeg -nostdin -v error -y -ss "$S" -t "$D" -i "$SRC" -i "$DUB" -map 0:v:0 -map 1:a:0 \
  -af "volume=${G_DUB}dB,$LIM" "${V[@]}" "${A[@]}" "$OUT"
ls -la "$OUT"
if [ -n "$TRACK" ]; then
  G_ORIG=$(gain "$(lufs -ss "$S" -t "$D" -i "$SRC" -map "0:a:$TRACK")")
  CHECK="${OUT%.*}_timing.mp4"
  ffmpeg -nostdin -v error -y -ss "$S" -t "$D" -i "$SRC" -i "$DUB" -filter_complex \
    "[0:a:$TRACK]aformat=sample_rates=48000:channel_layouts=mono,volume=${G_ORIG}dB[l];[1:a:0]aformat=sample_rates=48000:channel_layouts=mono,volume=${G_DUB}dB[r];[l][r]join=inputs=2:channel_layout=stereo,$LIM[a]" \
    -map 0:v:0 -map "[a]" "${V[@]}" "${A[@]}" "$CHECK"
  ls -la "$CHECK"
fi
