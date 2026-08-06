# Manuscript build (Typst). See README.md for the tour.
#
# The analysis that produces the numbers lives in analysis/, inside this
# directory, and writes its figures and tables straight into figures/ and si/.
# The only thing this justfile knows about it is that `just assets` regenerates
# everything the manuscript includes. See analysis/justfile for that contract.
#
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

# Which paper-scaffold version this manuscript is built on, and the state of the
# working tree. The version comes from pyproject.toml, which is copied along with
# the scaffold, so it answers the question in a derived project too.
# See HISTORY.md for the versioning policy and how to upgrade.
version:
  #!/usr/bin/env bash
  set -uo pipefail
  v=$(grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)
  echo "paper-scaffold $v"
  if git rev-parse --git-dir >/dev/null 2>&1; then
    dirty=$(git status --porcelain | wc -l)
    echo "  commit  $(git log -1 --format='%h %ad %s' --date=short)"
    [ "$dirty" -gt 0 ] && echo "  tree    $dirty uncommitted change(s)" || echo "  tree    clean"
  fi

# One-time (and after any pyproject change): build the Python environment. uv
# resolves and locks it, so every machine gets the same versions. The analysis has
# its own separate environment; `just assets` builds it on demand.
#
# Runs `doctor` first, because uv sync succeeding proves nothing about whether
# the manuscript can be built: typst is the tool this directory actually needs
# and the one uv knows nothing about.
setup: doctor
  uv sync
  @echo "environment ready. For the audiobooks: just audio-setup"

# The minimum Typst this scaffold compiles under.
#
# 0.13 is where `--features html` and `html.frame()` arrived, so it is the
# obvious floor and it is the WRONG one. On 0.13 the Word export runs, exits 0,
# and silently contains no figures: its HTML export emits no <img> for an
# `image()` call, while tables and the rasterized math both survive. You get a
# .docx that looks finished and has lost every plot. 0.14 emits them.
#
# Measured, not assumed -- 0.13.1, 0.14.2 and 0.15.1 were each run through
# `just docx` and the output compared. CI holds the floor with a version matrix.
typst_min := "0.14"

# Reports which of the external tools are present and whether they are new
# enough, rather than leaving a missing one to surface as a "command not found"
# from inside whichever recipe happened to need it first. Required tools fail
# this; optional ones are reported and cost only the feature they serve.
#
# python3 is in the required list because wordcount.sh shells out to it directly
# for the JSON formatting, before uv is ever involved.
# Check that the external tools this directory needs are installed and new enough
doctor:
  #!/usr/bin/env bash
  set -uo pipefail
  rc=0

  # <label> <command> <required|optional> <what it is for> [version-args...]
  report() {
    local label="$1" cmd="$2" need="$3" why="$4"; shift 4
    if ! command -v "$cmd" >/dev/null 2>&1; then
      if [ "$need" = required ]; then
        printf '  %-9s MISSING   %s\n' "$label" "$why"; rc=1
      else
        printf '  %-9s absent    %s\n' "$label" "$why"
      fi
      return
    fi
    local v; v=$("$@" 2>&1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)
    printf '  %-9s %-9s %s\n' "$label" "${v:-ok}" "$why"
  }

  echo "paper-scaffold doctor"
  echo ""
  report typst    typst    required "PDF and Word builds"            typst --version
  report just     just     required "every recipe in this file"      just --version
  report uv       uv       required "the Python toolchain"           uv --version
  report python3  python3  required "wordcount.sh"                   python3 --version
  report git      git      optional "just check-pdf (skipped without it)" git --version
  report typstyle typstyle optional "just fmt and just fmt-check"    typstyle --version
  report curl     curl     optional "not required; handy for diagnosis" curl --version

  # Version floor. Compared on major.minor as a pair of integers, because a
  # string compare puts 0.9 above 0.14 and would pass a binary that cannot
  # build the Word export.
  if command -v typst >/dev/null 2>&1; then
    have=$(typst --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    hmaj=${have%%.*}; hmin=${have##*.}
    want="{{typst_min}}"; wmaj=${want%%.*}; wmin=${want##*.}
    if [ "$hmaj" -lt "$wmaj" ] || { [ "$hmaj" -eq "$wmaj" ] && [ "$hmin" -lt "$wmin" ]; }; then
      echo ""
      echo "TOO OLD: typst $have, but this scaffold needs {{typst_min}} or newer."
      echo "  Below {{typst_min}}, \`just docx\` still exits 0 and silently drops every"
      echo "  figure from the Word export. See typst_min in the justfile."
      rc=1
    fi
  fi

  echo ""
  if [ $rc -eq 0 ]; then
    echo "every required tool is present. Next: just setup, then just paper"
  else
    echo "install what is marked MISSING or TOO OLD, then run this again."
    echo "  typst   https://github.com/typst/typst        (or: cargo install typst-cli)"
    echo "  just    https://github.com/casey/just         (or: cargo install just)"
    echo "  uv      https://docs.astral.sh/uv/            (curl -LsSf https://astral.sh/uv/install.sh | sh)"
    echo "  typstyle                                       cargo install typstyle"
  fi
  exit $rc

# Density metrics: numerals, parentheticals, acronyms, nominalizations, passives
# and hedges per 1,000 words, plus the sections that depart from the paper's own
# norms. These are what make prose dense; a reading-level score cannot see them.
density:
  @uv run --quiet python density.py

# Rebuild everything this directory owns, from the current source, in the order
# that fails fastest: the PDF first (any Typst error surfaces in seconds), then
# Word, then the audiobooks, which dominate the runtime.
#
# SCOPE. This does NOT re-run the analysis. The figures and tables under
# figures/ and si/ come from `just assets`, which may take hours. `check` reports
# drift in those too, without rebuilding anything.
#
# audio/ is optional: a project that does not want narration deletes the
# directory, and this skips the audiobooks rather than failing. Making it a hard
# dependency meant `just all` broke on a manuscript that had removed a feature it
# never asked for.
# Rebuild every artifact this directory owns: PDF, Word, and the audiobooks if audio/ is present
all: paper docx
  #!/usr/bin/env bash
  set -euo pipefail
  if [ -d audio ]; then
    just audiobook-all
    echo ""
    echo "PDF, Word and both audiobooks rebuilt from the current source."
  else
    echo ""
    echo "PDF and Word rebuilt from the current source (no audio/, narration skipped)."
  fi
  just check

# The one command that answers "is this done". Everything under it already
# existed and was already documented; what did not exist was a single thing to
# run, so the instructions were a four-step ritual with two conditions in it
# ("if you changed prose...", "if you changed inline markup..."). Conditional
# rituals get skipped, and the conditions need a judgement about which files a
# change touched that is easy to get wrong from inside the edit.
#
# It REBUILDS NOTHING, deliberately, so it stays seconds rather than minutes and
# can be run as often as you like. `check` reports what needs rebuilding and
# names the recipe. Build first, verify second:
#
#     just paper && just verify
#
# Every stage runs even after one fails, because finding out about the formatting
# and the stale PDF in the same pass beats four rounds of fix-and-rerun. Ordered
# cheapest first anyway, so a fast failure prints early.
#
# fmt-check is skipped rather than failed when typstyle is absent: it is the one
# optional tool in the set, and a manuscript that never formats is not broken.
# Run every gate: formatting, extractor tests, prose rules, staleness
verify:
  #!/usr/bin/env bash
  set -uo pipefail
  rc=0
  # <label> <message-on-success> <command...>. The success message exists because
  # a passing gate that prints nothing (fmt-check) is indistinguishable from one
  # that did not run.
  stage() {
    local label="$1" ok="$2"; shift 2
    echo ""
    echo "=== $label ==="
    if "$@"; then
      [ -n "$ok" ] && echo "$ok"
    else
      rc=1
    fi
  }

  if command -v typstyle >/dev/null 2>&1; then
    stage "formatting (just fmt-check)" "the hand-written sources are formatted" \
      just fmt-check
  else
    echo ""
    echo "=== formatting (just fmt-check) ==="
    echo "note:    typstyle is not installed, skipped. See: just doctor"
  fi

  stage "extractors (just test)"         "" just test
  stage "prose rules (just prose-check)" "" just prose-check
  stage "staleness (just check)"         "" just check

  echo ""
  if [ $rc -eq 0 ]; then
    echo "VERIFY OK -- formatting, extractors, prose rules and staleness all pass."
  else
    echo "VERIFY FAILED -- see the stages above. Nothing was rebuilt."
  fi
  exit $rc

# Covers the three ways a manuscript directory actually goes stale: a tracked
# paper.pdf committed before a source fix, generated artifacts older than the
# text they narrate or render, and generated figures/tables older than the
# analysis code that produces them. Exits non-zero if anything is stale, so it
# can gate a submission.
# Report which artifacts have fallen behind the source, rebuilding nothing
check:
  #!/usr/bin/env bash
  set -uo pipefail
  rc=0

  just check-pdf || rc=1

  # paper.docx is gitignored, so mtime is the only signal here.
  #
  # The audiobooks are deliberately NOT checked. Every prose edit would mark them
  # stale, and clearing that costs minutes of narration, so the warning was almost
  # always present and almost never acted on. A nag with an expensive fix is a nag
  # people learn to scroll past, and it was eroding trust in the rest of this
  # output. Rebuild them with `just audiobook-all` when you actually want them.
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

  just check-assets || rc=1

  [ $rc -eq 0 ] && echo "everything is current with the source"
  exit $rc

# figures/ and si/ are generated by analysis/ but TRACKED, so a fresh clone
# compiles the PDF without re-running an analysis that may take hours. That makes
# them the second thing here that can silently disagree with its own source: edit
# a generator, forget to re-run it, and the manuscript keeps rendering the old
# numbers with nothing to flag it.
#
# Compares a CONTENT STAMP of the analysis source, not commit dates. Commit dates
# were the first attempt and were wrong in the one case that matters most: the
# generators are deterministic on purpose, so re-running them after an edit that
# does not change the output produces no new commit, and a date-based check then
# nags forever with no way to satisfy it. A stamp clears the moment `just assets`
# runs, whether or not the bytes moved. It also needs no git, so it works in an
# exported tree.
# TWO stamps, because there are two ways these files can stop matching the
# analysis and only one of them used to be caught.
#
#   source  the analysis code. Differs when a generator was edited and not re-run.
#   output  figures/ and si/ themselves. Differs when something edited the
#           GENERATED file instead of the generator.
#
# The second is the rule CLAUDE.md states most loudly -- never hand-edit si/*.typ
# or figures/ -- and until now nothing enforced it. The failure is quiet and
# total: the edit renders correctly, every staleness check reports current, and
# the next `just assets` silently overwrites it. An "AUTO-GENERATED" header is a
# request; this is a check.
# Fail if the generated figures/tables predate, or diverge from, the analysis
check-assets:
  #!/usr/bin/env bash
  set -uo pipefail
  if [ ! -d analysis ]; then
    echo "note:    no analysis/ directory, skipped the generated-asset check"
    exit 0
  fi
  if [ ! -s .assets-stamp ]; then
    echo "MISSING: .assets-stamp -- run: just assets"
    exit 1
  fi

  field() { grep -m1 "^$1 " .assets-stamp 2>/dev/null | cut -d" " -f2; }
  have_src=$(field source)
  have_out=$(field output)

  # A stamp written before this check existed is a single bare hash with no
  # field names. Treated as unreadable rather than guessed at, since guessing
  # wrong reports a hand-edit that did not happen.
  if [ -z "$have_src" ] || [ -z "$have_out" ]; then
    echo "STALE: .assets-stamp predates the output check -- run: just assets"
    exit 1
  fi

  rc=0
  if [ "$(just _stamp-source)" != "$have_src" ]; then
    echo "STALE: analysis/ has changed since figures/ and si/ were last generated"
    echo "  fix: just assets && git add figures si .assets-stamp"
    rc=1
  fi
  if [ "$(just _stamp-output)" != "$have_out" ]; then
    echo "MODIFIED: figures/ or si/ has changed without the analysis being re-run."
    echo "  Those files are generated. A hand-edit to one survives until the next"
    echo "  \`just assets\` and then vanishes. Change the generator that writes it."
    echo "  fix: just assets && git add figures si .assets-stamp"
    rc=1
  fi
  [ $rc -eq 0 ] && echo "figures/ and si/ are current with analysis/"
  exit $rc

# Hash of the analysis source: every tracked-ish file under analysis/, excluding
# the heavy inputs and intermediates that do not determine the output.
# Null-delimited throughout: a plain `find | xargs` splits on whitespace, so a
# single script named `gen one.py` made sha256sum miss both halves. Its errors go
# to stderr and the pipeline still exits 0 through cut, so the stamp stayed stable
# while being computed from the wrong input, which is worse than failing.
_stamp-source:
  @find analysis -type f \
      -not -path 'analysis/data/*' -not -path 'analysis/results/*' \
      -not -path 'analysis/.venv/*' -not -name '*.pyc' -not -name 'uv.lock' \
      -print0 | sort -z | xargs -0 -r sha256sum | sha256sum | cut -d" " -f1

# Hash of what the analysis produced. si/stats.json is included: it is generated
# by gen_stats.py exactly like the tables, and hand-editing a value there would
# otherwise change every number in the prose with nothing to notice.
_stamp-output:
  @find figures si -type f -not -name '*.pyc' \
      -print0 2>/dev/null | sort -z | xargs -0 -r sha256sum | sha256sum | cut -d" " -f1

# Both stamps, in the two-line form check-assets reads.
_assets-stamp:
  @echo "source $(just _stamp-source)"
  @echo "output $(just _stamp-output)"

# The SI is included from si-body.typ as an appendix, so this single PDF holds the
# whole manuscript; there is no separate supplementary.pdf. si-body.typ is
# body-only and is never compiled on its own.
# Compile while the numbers are still in flux -> paper-draft.pdf.
#
# `#s("id")` normally panics on an unknown id, which is right for a real build: a
# number that stopped existing must not render blank. While drafting it is the
# wrong trade. Renaming a value breaks every call site at once, and until the
# last one is fixed there is no PDF at all -- not even to read the paragraph you
# were in the middle of writing.
#
# Here an unresolved id becomes a loud `?id?` placeholder instead. It writes
# paper-draft.pdf, NEVER paper.pdf, so a placeholder cannot end up in a file
# anyone mistakes for the finished paper. That is also why `check` needs to know
# nothing about this mode.
#
# `n("id")` still fails, draft mode included: no placeholder can stand in for a
# number inside an expression without making the arithmetic quietly wrong.
# Compile with unresolved numbers shown as placeholders -> paper-draft.pdf
draft:
  typst compile --input draft=true paper.typ paper-draft.pdf
  @echo 'wrote paper-draft.pdf -- unresolved numbers appear as ?id?; `just paper` is the real build'

# Compile paper.typ -> paper.pdf, then print word counts and readability
paper:
  typst compile paper.typ
  @bash wordcount.sh
  @echo ""
  @uv run --quiet python readability.py
  @echo ""
  @uv run --quiet python density.py

# See wordcount.typ for exactly what is excluded (refs, figures/tables, captions,
# math, code) vs. included (headings, inline code).
# Journal-style word counts (main text / SI / total), without rebuilding the PDF
wordcount:
  @bash wordcount.sh

# Computed from the Typst source with the same exemptions as the word count. Uses
# `textstat` if installed, else a built-in estimate. No PDF rebuild.
# Readability metrics (Flesch-Kincaid grade, reading ease, words/sentence, fog)
readability:
  @uv run --quiet python readability.py

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
# SCOPE. `typst_sources` deliberately excludes si/*.typ. Those are written by
# analysis/, so formatting them would be undone on the next
# regeneration and show up as spurious diffs. .vscode/settings.json marks them
# read-only in the editor for the same reason.
#
# Reflowing markup is output-neutral in Typst, since a single newline is just a
# space. `just test` proves it, on a fixture built for the purpose.
# ---------------------------------------------------------------------------

# Check the prose against the mechanical rules in STYLE.md. Errors are rules with
# no legitimate exception here (em dash, British spelling, doubled word, an
# uncited figure) and exit non-zero. Warnings are judgement calls (long sentences,
# verbosity, repetition, citation order) and are reported without failing, because
# a checker that fails the build over the word "very" gets disabled within a week.
# Add --strict to treat warnings as failures: uv run python prose_check.py --strict
prose-check:
  @uv run --quiet python prose_check.py

# Every DOI in the bibliography, checked against Crossref: does it resolve, and
# has the work been retracted?
#
# NOT part of `just verify`, deliberately. It needs the network, and a gate that
# can fail because an API was slow is a gate people learn to skip. Run it before
# submission, and again late: a paper can be retracted years after you cite it,
# so the answer has a shelf life.
#
# Being offline is reported, not failed. That is a fact about your connection,
# not a defect in the bibliography.
# Check every DOI against Crossref for retractions and dead links (needs network)
bib-audit:
  @uv run --quiet python bib_audit.py

# Assert the prose extractors still handle every construct, and still do so after
# a reflow. Runs against tests/fixture.typ, which is NOT part of the manuscript --
# placeholder prose in paper.typ gets deleted the moment real writing starts, so
# anything relying on it for coverage would be tested once and never again.
test:
  @uv run --quiet python tests/run.py

# Rewrite tests/expected/ from the current extractor behaviour. Review the diff:
# this is how a regression gets blessed into the baseline by accident.
test-update:
  @uv run --quiet python tests/run.py --update

# Reflow the hand-written Typst sources to `fmt_width` columns
#
# The message below is single-quoted, NOT backquoted. just evaluates a backquoted
# string as a shell command, so a `just paper` written inside that message ran a
# full PDF rebuild as a side effect of formatting and printed a word count nobody
# asked for. Recipe-body `#` comments are echoed too, hence this sits out here.
fmt:
  typstyle --inplace --line-width {{fmt_width}} --wrap-text {{typst_sources}}
  @echo 'formatted. Rebuild with "just paper" and confirm nothing moved.'

# Exit non-zero if the hand-written sources need reformatting (gate for CI or a hook)
fmt-check:
  typstyle --check --line-width {{fmt_width}} --wrap-text {{typst_sources}}

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
  uv run --quiet python typst2docx.py paper.docx.html paper.docx
  @rm -f paper.docx.html

# ---------------------------------------------------------------------------
# Generated assets. The contract: numbers and plots in the manuscript are written
# by the analysis that produced them, never typed in by hand. Tables land in si/
# as bare #table() blocks that si-body.typ wraps in a #figure. Figures land in
# figures/. Both are written DIRECTLY by analysis/, with no staging copy, because
# a copy is the thing that goes stale.
#
# This is a single delegation on purpose. The manuscript knows one thing about
# the analysis, which is that `just assets` brings its outputs up to date. What
# that takes -- one script or sixty, minutes or hours -- is analysis/'s business.
# ---------------------------------------------------------------------------

# Regenerate every figure and table the manuscript includes (delegates to analysis/)
assets:
  #!/usr/bin/env bash
  set -euo pipefail
  if [ ! -d analysis ]; then
    echo "no analysis/ directory: this manuscript has no generated assets."
    exit 0
  fi
  (cd analysis && just assets)
  # Record what produced these, so check-assets can tell whether the analysis has
  # moved on since. Written here rather than in analysis/justfile so the contract
  # with the analysis stays "regenerate the assets" and nothing more.
  just _assets-stamp > .assets-stamp
  echo "stamped .assets-stamp"

# ---------------------------------------------------------------------------
# Audiobook (audio/). Offline Piper TTS narration of the prose:
# audio/extract_prose.py rewrites the Typst source into speakable text (citations,
# math, #sym.* tokens and figure/table blocks removed), then Piper synthesizes it
# and ffmpeg muxes chapters and cover art. Only the scripts in audio/ are tracked
# -- the voice model, and every generated audio file, are gitignored -- so a fresh
# clone needs `just audio-setup` once. Voice, titles, and pronunciations all come
# from audio/config.py.
#
# Piper is a uv dependency (`piper-tts`, the audio group), like pandoc and ffmpeg
# before it. It used to be a binary tarball fetched by curl, pinned to a release
# that shipped x86_64 Linux only, so the audiobooks were the one part of this
# directory that could not run on a Mac. The wheels are abi3 and cover Linux,
# both Macs and Windows.
# ---------------------------------------------------------------------------

# One-time: install the audio dependencies and download the voice model (~60 MB).
audio-setup:
  #!/usr/bin/env bash
  set -euo pipefail
  uv sync --quiet --group audio
  cd audio
  uv run --quiet --group audio python - <<'PY'
  from pathlib import Path
  import config
  from piper.download_voices import download_voice
  d = Path("models")
  d.mkdir(exist_ok=True)
  # Resolved by NAME against piper's own voice index. The old path
  # ("en/en_US/lessac/medium") was a hand-built URL into a HuggingFace repo, so a
  # renamed voice gave a 404 that looked like a network failure.
  if (d / f"{config.VOICE_NAME}.onnx").is_file():
      print(f"  voice {config.VOICE_NAME} already present")
  else:
      print(f"  downloading {config.VOICE_NAME} ...")
      download_voice(config.VOICE_NAME, d)
  PY
  echo "audio toolchain ready -- build with: just audiobook"

# Chaptered audiobook of the main text -> audio/paper.m4b (one chapter per section).
audiobook: _audio-check
  cd audio && uv run --quiet --group audio python make_audiobook.py

# Chaptered audiobook of the Supporting Information -> audio/paper_si.m4b.
audiobook-si: _audio-check
  cd audio && uv run --quiet --group audio python make_audiobook.py si

# Both chaptered audiobooks (main text, then SI).
audiobook-all: audiobook audiobook-si

# Fail early with a fix-it hint when the untracked toolchain is missing. Only the
# voice model is checked now: the engine is a uv dependency, so `uv run` installs
# it and there is nothing to look for on disk. The model is the part that is
# gitignored, 60 MB, and absent on a fresh clone.
_audio-check:
  #!/usr/bin/env bash
  set -euo pipefail
  cd audio
  name=$(python3 -c "import config; print(config.VOICE_NAME)")
  if [ ! -f "models/${name}.onnx" ]; then
    echo "no voice model for ${name} -- run: just audio-setup"
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
  rm -f paper.pdf paper-draft.pdf paper.docx paper.docx.html
