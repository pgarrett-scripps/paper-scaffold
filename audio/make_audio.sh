#!/usr/bin/env bash
# Regenerate the flat (unchaptered) spoken-audio version of the manuscript.
# Usage: ./make_audio.sh    -- re-extracts prose from ../paper.typ, synthesizes
#                              paper.wav, then compresses to MP3 and Opus.
# For the chaptered .m4b, use make_audiobook.py instead.
set -euo pipefail
cd "$(dirname "$0")"

# One environment, shared with the manuscript toolchain (../pyproject.toml).
PY="uv run --quiet --group audio python"

# Titles, author, description, voice, and year all come from config.py, which in
# turn reads the manuscript's identity out of ../config.typ. Nothing about the
# paper is spelled out in this script.
eval "$($PY - <<'PY'
import shlex
import config
for k in ("TITLE", "AUTHOR", "MAIN_DESC", "YEAR", "VOICE_NAME"):
    print(f"{k}={shlex.quote(str(getattr(config, k)))}")
PY
)"

VOICE="models/${VOICE_NAME}.onnx"

# 1. extract clean prose from the Typst source
$PY extract_prose.py

# 2. synthesize to WAV with Piper (offline)
export LD_LIBRARY_PATH="./piper:${LD_LIBRARY_PATH:-}"
./piper/piper --model "$VOICE" --output_file paper.wav < paper_prose.txt

# 3. compress: a self-contained ffmpeg comes from imageio-ffmpeg in the audio group.
#    MP3 (plays everywhere) + Opus (smallest, modern players).
FF=$($PY -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null || true)
[ -z "$FF" ] && command -v ffmpeg >/dev/null 2>&1 && FF=ffmpeg

[ -f cover_main.png ] || $PY make_cover.py 2>/dev/null || true

if [ -n "$FF" ]; then
  # MP3 with cover art + ID3 tags (falls back to no cover if the png is absent)
  if [ -f cover_main.png ]; then
    "$FF" -y -loglevel error -i paper.wav -i cover_main.png -map 0:a -map 1:v \
      -codec:a libmp3lame -b:a 64k -c:v mjpeg -id3v2_version 3 -disposition:v:0 attached_pic \
      -metadata title="$TITLE" -metadata artist="$AUTHOR" -metadata album_artist="$AUTHOR" \
      -metadata album="$TITLE" -metadata genre="Audiobook" -metadata date="$YEAR" \
      -metadata comment="$MAIN_DESC" paper.mp3
  else
    "$FF" -y -loglevel error -i paper.wav -codec:a libmp3lame -b:a 64k paper.mp3
  fi
  "$FF" -y -loglevel error -i paper.wav -codec:a libopus -b:a 24k \
    -metadata title="$TITLE" -metadata artist="$AUTHOR" -metadata album="$TITLE" \
    -metadata genre="Audiobook" -metadata date="$YEAR" paper.opus
  echo "wrote paper.wav, paper.mp3 (cover+tags), paper.opus"
else
  echo "wrote paper.wav  (no ffmpeg found; run: just audio-setup)"
fi
