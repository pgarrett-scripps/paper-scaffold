# Manuscript build (Typst). See README.md for the tour.
#
# Only one setting here is project-specific: `analysis_root`, the directory the
# figures in figures.map are copied from. Point it at the analysis tree that
# produces your plots -- typically something like "../benchmark/results" or a
# sibling repo. The bundled scripts/ write into ./analysis so the scaffold works
# out of the box.
analysis_root := "analysis"

# The hand-written Typst sources, for `just fmt`. Add files here as the
# manuscript grows (a reviewer-response letter, a cover letter, a shared macro
# file). Deliberately does NOT include si/*.typ -- see the `fmt` recipe.
typst_sources := "config.typ paper.typ si-body.typ"

# Line width for typstyle. Must stay in step with `tinymist.formatterPrintWidth`
# in .vscode/settings.json, or format-on-save and `just fmt` will fight.
fmt_width := "80"

# Default target
default:
  @just --list

# Rebuild everything this directory owns, from the current source, in the order
# that fails fastest: the PDF first (any Typst error surfaces in seconds), then
# Word, then the audiobooks, which dominate the runtime.
#
# SCOPE. This does NOT re-run the analysis. Generated tables in si/ and the
# figures listed in figures.map come from `just si-assets`, which needs the
# analysis tree. `check` reports drift in those too, without rebuilding anything.
# Rebuild every artifact this directory owns: PDF, Word, and both audiobooks
all: paper docx audiobook-all
  @echo ""
  @echo "PDF, Word and both audiobooks rebuilt from the current source."
  @just check

# Covers the three ways a manuscript directory actually goes stale: a tracked
# paper.pdf committed before a source fix, generated artifacts older than the
# text they narrate or render, and figures copied in from an analysis tree and
# then left behind by a re-analysis. Exits non-zero if anything is stale, so it
# can gate a submission.
# Report which artifacts have fallen behind the source, rebuilding nothing
check:
  #!/usr/bin/env bash
  set -uo pipefail
  rc=0

  just check-pdf || rc=1

  # paper.docx and the .m4b files are gitignored, so mtime is the only signal here.
  # Each artifact is compared against ITS OWN inputs: the Word export renders the
  # whole manuscript including the generated tables and figures, but the audiobooks
  # narrate prose only and never read si/ or figures/, so holding them against a
  # regenerated table would report drift that cannot exist.
  newest() { ls -t "$@" 2>/dev/null | head -1; }
  check_artifact() {   # <artifact> <label> <input>...
    local f="$1" label="$2"; shift 2
    local src; src=$(newest "$@")
    if [ ! -f "$f" ]; then
      echo "MISSING: $f -- rebuild: $label"
      rc=1
    elif [ -n "$src" ] && [ "$f" -ot "$src" ]; then
      echo "STALE:   $f is older than $src -- rebuild: $label"
      rc=1
    fi
  }
  check_artifact paper.docx "just docx" \
    paper.typ config.typ si-body.typ references.bib si/*.typ figures/*.png
  check_artifact audio/paper.m4b "just audiobook" paper.typ config.typ
  check_artifact audio/paper_si.m4b "just audiobook-si" si-body.typ config.typ

  # The documented trap: `just figures` copies these in from the analysis tree, so
  # a re-analysis leaves the copies behind with nothing to flag it. Compare bytes.
  if [ -d "{{analysis_root}}" ]; then
    while read -r dest src; do
      [ -z "${dest:-}" ] && continue
      case "$dest" in \#*) continue;; esac
      if [ ! -f "figures/$dest" ]; then
        echo "MISSING: figures/$dest -- rebuild: just figures"
        rc=1
      elif [ -f "{{analysis_root}}/$src" ] && ! cmp -s "figures/$dest" "{{analysis_root}}/$src"; then
        echo "STALE:   figures/$dest differs from {{analysis_root}}/$src -- rebuild: just figures"
        rc=1
      fi
    done < <(grep -v '^\s*\(#\|$\)' figures.map)
  else
    echo "note:    {{analysis_root}} not reachable, skipped the copied-figure check"
  fi

  [ $rc -eq 0 ] && echo "everything is current with the source"
  exit $rc

# Compile paper.pdf (main text + Supporting Information appended as one PDF)
pdf: paper

# The SI is included from si-body.typ as an appendix, so this single PDF holds the
# whole manuscript; there is no separate supplementary.pdf. si-body.typ is
# body-only and is never compiled on its own.
# Compile paper.typ -> paper.pdf, then print word counts and readability
paper:
  typst compile paper.typ
  @bash wordcount.sh
  @echo ""
  @python3 readability.py

# See wordcount.typ for exactly what is excluded (refs, figures/tables, captions,
# math, code) vs. included (headings, inline code).
# Journal-style word counts (main text / SI / total), without rebuilding the PDF
wordcount:
  @bash wordcount.sh

# Computed from the Typst source with the same exemptions as the word count. Uses
# `textstat` if installed, else a built-in estimate. No PDF rebuild.
# Readability metrics (Flesch-Kincaid grade, reading ease, words/sentence, fog)
readability:
  @python3 readability.py

# Live preview, recompiling on save
watch:
  typst watch paper.typ

# ---------------------------------------------------------------------------
# Formatting (typstyle). This is the same engine the tinymist editor extension
# uses as its formatter backend, so format-on-save and `just fmt` produce
# identical output -- PROVIDED .vscode/settings.json keeps tinymist's
# formatterPrintWidth and formatterProseWrap in step with `fmt_width` and
# --wrap-text above. tinymist's own defaults are 120 columns and prose wrapping
# OFF, which disagree with both, so without that file every save and every
# `just fmt` would reflow the source the other way.
#
# --wrap-text is the flag that matters for a manuscript. Without it typstyle
# formats code and leaves markup lines however long they already were, and in a
# paper the long lines are prose.
#
# SCOPE. `typst_sources` deliberately excludes si/*.typ. Those are written by the
# scripts in scripts/, so formatting them would be undone on the next
# regeneration and show up as spurious diffs. .vscode/settings.json marks them
# read-only in the editor for the same reason.
#
# Reflowing markup is output-neutral in Typst, since a single newline is just a
# space. Verify with `just fmt-verify` if you change the line width.
# ---------------------------------------------------------------------------

# Reflow the hand-written Typst sources to `fmt_width` columns
fmt:
  typstyle --inplace --line-width {{fmt_width}} --wrap-text {{typst_sources}}
  @echo "formatted. Rebuild with `just paper` and confirm nothing moved."

# Exit non-zero if the hand-written sources need reformatting (gate for CI or a hook)
fmt-check:
  typstyle --check --line-width {{fmt_width}} --wrap-text {{typst_sources}}

# Show what `just fmt` would change, without writing anything
fmt-diff:
  typstyle --diff --line-width {{fmt_width}} --wrap-text {{typst_sources}}

# Prove a reflow changes nothing that matters, on BOTH axes.
#
# The PDF is the obvious one. The other is the prose that readability.py and
# audio/extract_prose.py strip out of the source with regexes, several of which
# have to assume a construct sits on one line -- which is exactly what
# --wrap-text stops being true. In the manuscript this scaffold came from, a
# reflow silently split `#refn(<tab:x>)`, `_Saccharomyces cerevisiae_` and
# `#link(` across lines: the PDF was untouched, but the narration gained a
# spoken "and)." and a pair of literal underscores. So check both.
#
# Uses git to restore the sources, so they must be committed first.
fmt-verify:
  #!/usr/bin/env bash
  set -euo pipefail
  if ! git diff --quiet -- {{typst_sources}}; then
    echo "error: {{typst_sources}} have uncommitted changes; commit or stash first"
    exit 1
  fi
  command -v pdftotext >/dev/null || { echo "error: pdftotext not found (poppler-utils)"; exit 1; }
  work=$(mktemp -d); trap 'git checkout -- {{typst_sources}}; rm -rf "$work"' EXIT
  # One-liners on purpose: a line at column 0 inside a recipe body ends the
  # recipe, so neither a heredoc nor a multi-line `python -c` string works here.
  snap() {   # <tag> -- the rendered text, the counted prose, and the narration
    typst compile paper.typ "$work/$1.pdf" 2>/dev/null
    pdftotext "$work/$1.pdf" "$work/$1-pdf.txt"
    python3 -c "import readability as r; open('$work/$1-main.txt','w').write(r.clean(r.slice_body(open('paper.typ').read())))"
    python3 -c "import readability as r; open('$work/$1-si.txt','w').write(r.clean(open('si-body.typ').read()))"
    (cd audio && python3 extract_prose.py >/dev/null && mv paper_prose.txt "$work/$1-prose.txt")
  }
  snap before
  typstyle --inplace --line-width {{fmt_width}} --wrap-text {{typst_sources}}
  snap after
  rc=0
  for f in pdf main si prose; do
    if diff -q "$work/before-$f.txt" "$work/after-$f.txt" >/dev/null; then
      echo "  $f: unchanged by the reflow"
    else
      echo "  $f: CHANGED by the reflow --"
      diff "$work/before-$f.txt" "$work/after-$f.txt" | head -20
      rc=1
    fi
  done
  [ $rc -eq 0 ] && echo "reflow is neutral: PDF, word count, readability and narration all unaffected"
  exit $rc

# Route: Typst HTML export -> pandoc. Three things make it work:
#   1. --input docx=true bypasses the arkheion template. Its front matter and heading
#      styling are layout-only primitives that Typst's HTML export silently discards,
#      which would otherwise cost every section heading and the abstract.
#   2. paper.typ wraps equations in html.frame() under that same flag, because HTML
#      export drops math outright; typst2docx.py rasterizes them back inline.
#   3. pandoc comes from uv (pypandoc-binary), so no system install is needed.
# Figures embed as images, tables stay real Word tables, and `=` sections map onto
# Word's Heading 1. Typst's HTML export is experimental and prints "ignored during
# HTML export" warnings for layout-only constructs; those are expected and cost
# nothing in the prose. The PDF build is entirely unaffected by the docx flag.
# Compile paper.typ -> paper.docx (Word), for journals/co-authors that want .docx
docx:
  typst compile --features html --input docx=true -f html paper.typ paper.docx.html
  uv run --quiet --with pypandoc-binary --with cairosvg --with pillow python typst2docx.py paper.docx.html paper.docx
  @rm -f paper.docx.html

# ---------------------------------------------------------------------------
# Generated assets. The contract: numbers and plots in the manuscript are written
# by the scripts that produced them, never typed in by hand. Tables land in si/
# as bare #table() blocks that si-body.typ wraps in a #figure; figures are copied
# into figures/ according to figures.map.
# ---------------------------------------------------------------------------

# Everything generated: SI tables, then figures copied from the analysis tree
si-assets: si-tables figures
  @echo ""
  @echo "generated assets refreshed; rebuild the PDF with: just paper"

# Run every scripts/gen_*.py -- each one owns one si/*.typ table. A new table
# needs no wiring here beyond matching the filename pattern.
si-tables:
  #!/usr/bin/env bash
  set -euo pipefail
  shopt -s nullglob
  for s in scripts/gen_*.py; do
    echo "-> $s"
    uv run --quiet --with matplotlib "$s"
  done

# Copy each figure named in figures.map out of the analysis tree. Fails loudly on
# a missing source rather than leaving the old copy silently in place.
figures:
  #!/usr/bin/env bash
  set -euo pipefail
  if [ ! -d "{{analysis_root}}" ]; then
    echo "error: analysis_root '{{analysis_root}}' does not exist."
    echo "       Set it at the top of the justfile, or run: just si-tables"
    exit 1
  fi
  n=0
  while read -r dest src; do
    [ -z "${dest:-}" ] && continue
    case "$dest" in \#*) continue;; esac
    if [ ! -f "{{analysis_root}}/$src" ]; then
      echo "error: {{analysis_root}}/$src is missing (wanted for figures/$dest)"
      exit 1
    fi
    cp "{{analysis_root}}/$src" "figures/$dest"
    n=$((n+1))
  done < <(grep -v '^\s*\(#\|$\)' figures.map)
  echo "copied $n figure(s) from {{analysis_root}}/ per figures.map"

# ---------------------------------------------------------------------------
# Audiobook (audio/). Offline Piper TTS narration of the prose:
# audio/extract_prose.py rewrites the Typst source into speakable text (citations,
# math, #sym.* tokens and figure/table blocks removed), then Piper synthesizes it
# and ffmpeg muxes chapters and cover art. Only the scripts in audio/ are tracked
# -- the engine, the voice model, the ffmpeg venv, and every generated audio file
# are gitignored -- so a fresh clone needs `just audio-setup` once. Voice, titles,
# and pronunciations all come from audio/config.py.
# ---------------------------------------------------------------------------

# Piper 1.2.0, x86_64 Linux (the tarball unpacks to audio/piper/).
piper_url := "https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz"

# One-time: fetch the Piper engine and voice model, and build the ffmpeg venv.
audio-setup:
  #!/usr/bin/env bash
  set -euo pipefail
  cd audio
  test -x piper/piper || curl -sSL "{{piper_url}}" | tar -xz
  mkdir -p models
  # The voice name and its path under piper-voices both live in config.py.
  read -r name lang < <(python3 -c "import config; print(config.VOICE_NAME, config.VOICE_LANG)")
  base="https://huggingface.co/rhasspy/piper-voices/resolve/main/${lang}/${name}.onnx"
  test -f "models/${name}.onnx"      || curl -sSL -o "models/${name}.onnx" "$base"
  test -f "models/${name}.onnx.json" || curl -sSL -o "models/${name}.onnx.json" "${base}.json"
  test -x .venv/bin/python || uv venv .venv
  uv pip install -q --python .venv/bin/python imageio-ffmpeg pillow matplotlib
  echo "audio toolchain ready -- build with: just audiobook"

# Chaptered audiobook of the main text -> audio/paper.m4b (one chapter per section).
audiobook: _audio-check
  cd audio && .venv/bin/python make_audiobook.py

# Chaptered audiobook of the Supporting Information -> audio/paper_si.m4b.
audiobook-si: _audio-check
  cd audio && .venv/bin/python make_audiobook.py si

# Both chaptered audiobooks (main text, then SI).
audiobook-all: audiobook audiobook-si

# Flat narration of the main text, no chapters: paper.wav + paper.mp3 + paper.opus.
audio: _audio-check
  cd audio && ./make_audio.sh

# Cover art only (audio/cover_main.png, audio/cover_si.png).
audio-cover: _audio-check
  cd audio && .venv/bin/python make_cover.py

# Fail early with a fix-it hint when the untracked toolchain is missing.
_audio-check:
  #!/usr/bin/env bash
  set -euo pipefail
  cd audio
  name=$(python3 -c "import config; print(config.VOICE_NAME)")
  if [ ! -x piper/piper ] || [ ! -f "models/${name}.onnx" ] || [ ! -x .venv/bin/python ]; then
    echo "audio toolchain missing -- run: just audio-setup"
    exit 1
  fi

# Remove generated audio and intermediates, keeping the engine, voice, and venv.
audio-clean:
  rm -rf audio/chapters audio/chapters_si
  rm -f audio/paper.wav audio/paper.mp3 audio/paper.opus audio/paper.m4b audio/paper_si.m4b
  rm -f audio/paper_prose.txt audio/cover_main.png audio/cover_si.png

# paper.pdf is a TRACKED build artifact (see .gitignore) -- it is the reviewable
# output, so a reader can get it from the repo without a Typst install. That makes
# it the one thing here that can silently disagree with its own source. Compare
# commit dates, not mtimes, since a fresh clone or checkout rewrites every mtime
# and would report a false alarm.
# Fail if the committed paper.pdf is older than the manuscript source it was built from
check-pdf:
  #!/usr/bin/env bash
  set -uo pipefail
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "note:    not a git repository, skipped the paper.pdf staleness check"
    exit 0
  fi
  pdf_commit=$(git log -1 --format=%H -- paper.pdf)
  if [ -z "$pdf_commit" ]; then echo "paper.pdf is not committed yet"; exit 1; fi
  sources="paper.typ config.typ si-body.typ references.bib si figures"
  stale=$(git log --format=%ct "$pdf_commit"..HEAD -- $sources | head -1)
  if [ -n "$stale" ]; then
    echo "STALE: paper.pdf predates these source commits --"
    git log --oneline "$pdf_commit"..HEAD -- $sources | sed 's/^/  /'
    echo "  fix: just paper && git add paper.pdf"
    exit 1
  fi
  echo "paper.pdf is current with $sources"

# Remove the built PDF and Word export
clean:
  rm -f paper.pdf paper.docx paper.docx.html
