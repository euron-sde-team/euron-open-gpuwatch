#!/usr/bin/env bash
# Stitch the tour frames written by screenshots.mjs into docs/assets/tour.gif.
# Each frame is held for 2.5 s; a generated palette keeps the GIF sharp and small.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRAMES="$ROOT/scripts/qa/output/tour"
OUT="$ROOT/docs/assets/tour.gif"
command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 1; }
ls "$FRAMES"/*.png >/dev/null 2>&1 || { echo "no frames in $FRAMES: run screenshots.mjs first" >&2; exit 1; }
# 1. Frames to a lossless intermediate: read at 1 fps, hold each 2.5 s, resample to a steady
#    2 fps (GIF frame differencing makes repeats nearly free). Going through a video file also
#    sidesteps a palettegen crash some ffmpeg builds hit on PNG-sequence input.
TMP="$FRAMES/tour.mkv"
ffmpeg -y -loglevel error -framerate 1 -pattern_type glob -i "$FRAMES/*.png" \
  -vf "setpts=2.5*PTS,fps=2,scale=1200:-1:flags=lanczos" -c:v ffv1 "$TMP"
# 2. Palette, then encode.
ffmpeg -y -loglevel error -i "$TMP" -vf "palettegen=max_colors=192" "$FRAMES/palette.png"
ffmpeg -y -loglevel error -i "$TMP" -i "$FRAMES/palette.png" \
  -lavfi "paletteuse=dither=sierra2_4a" -loop 0 "$OUT"
rm -f "$FRAMES/palette.png" "$TMP"
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
