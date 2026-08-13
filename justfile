# Manuscript build (Typst). See README.md for the tour.
#
# CONVENTION: `just --list` shows the LAST comment line before each recipe as
# its description. Every comment block here therefore ENDS with the one-line
# description; the rationale goes above it. An edit that appends prose after
# that line puts a sentence fragment in the list, which has happened ten
# recipes' worth of times.
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

[private]
default:
  @just --list

# Which paper-scaffold version this manuscript is built on, and the state of the
# working tree. The version comes from pyproject.toml, which is copied along with
# the scaffold, so it answers the question in a derived project too.
# See HISTORY.md for the versioning policy and how to upgrade.
# Print which paper-scaffold version this manuscript is built on
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
# One-time: build the locked Python environment (runs doctor first)
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
# python3 is in the required list because the justfile's own inline recipes
# (_stamp-manuscript, _audio-check) shell out to it directly, before uv is
# involved.
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
  report python3  python3  required "the justfile inline recipes"                   python3 --version
  report git      git      optional "just text-diff word compare; version reporting" git --version
  report typstyle typstyle optional "just fmt and just fmt-check"    typstyle --version
  report pdftotext pdftotext optional "just text-baseline and just text-diff" pdftotext -v
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
# Density metrics per 1,000 words, and the sections that depart from the paper's norms
density:
  @uv run --quiet python tools/density.py

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
  # One stage, because both answer the same question -- are the declarations
  # still consistent with what produced them -- and splitting them made verify
  # six blocks of output for a manuscript with one figure and five numbers.
  stage "declarations (stats + assets)"  "" just check-declared
  stage "staleness (just check)"         "" just check

  echo ""
  if [ $rc -eq 0 ]; then
    echo "VERIFY OK -- formatting, extractors, prose rules and staleness all pass."
  else
    echo "VERIFY FAILED -- see the stages above. Nothing was rebuilt."
  fi
  exit $rc

# The day-of-submission gate. `verify` answers "is this done" cheaply and
# constantly; this answers "is this safe to SUBMIT", and pays for it. The
# expensive checks were each documented as "run before submitting" -- three
# commands in three places, which is a conditional ritual, and conditional
# rituals get skipped (the same reasoning that created `verify`).
#
# What it runs, in order: fresh builds of both outputs (as dependencies), the
# whole verify gate, the deep stats check (re-runs the analysis behind the
# numbers and diffs -- as slow as your gen_stats.py), and the bibliography audit
# (network: every DOI checked against Crossref for retractions). Every stage
# runs even after one fails, same as verify: the full list beats four rounds of
# fix-and-rerun on submission day.
#
# NOT here: `just assets`. Regenerating every figure may take hours and is a
# rebuild, not a check -- `check-assets` (inside verify) already reports if the
# analysis moved out from under the committed figures, and names what to re-run.
# Everything to run before submitting: fresh builds, verify, deep stats, DOI audit
preflight: paper docx
  #!/usr/bin/env bash
  set -uo pipefail
  rc=0
  just verify || rc=1
  echo ""
  echo "=== deep stats (just check-stats-deep) ==="
  just check-stats-deep || rc=1
  echo ""
  echo "=== bibliography (just bib-audit) ==="
  just bib-audit || rc=1
  echo ""
  if [ $rc -eq 0 ]; then
    echo "PREFLIGHT OK -- fresh builds, the full gate, re-derived numbers and the"
    echo "bibliography all pass. Remaining judgement calls: read the prose-check"
    echo "warnings above, and \`just viz\` for the shape of the draft."
  else
    echo "PREFLIGHT FAILED -- see the stages above."
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

  # One mechanism for both outputs now: a content stamp written at build time.
  # This replaced a git commit-date check for paper.pdf and an mtime check for
  # paper.docx, which disagreed with each other and each missed something -- the
  # mtime list globbed si/*.typ, so a changed number never marked the Word export
  # stale.
  #
  # The audiobooks are deliberately NOT checked. Every prose edit would mark them
  # stale, and clearing that costs minutes of narration, so the warning was almost
  # always present and almost never acted on. A nag with an expensive fix is a nag
  # people learn to scroll past, and it was eroding trust in the rest of this
  # output. Rebuild them with `just audiobook-all` when you actually want them.
  just check-build || rc=1

  [ $rc -eq 0 ] && echo "everything is current with the source"
  exit $rc

# stats.json stores the VALUE and the FORMAT, never the rendered string: a
# derived field sitting in a source file can drift from the value beside it, and
# needed its own check to notice. This renders one from the other into
# stats-rendered.json, which is what stats.typ reads.
#
# Python's formatter, because Typst has none: no thousands separator, no `+.2f`,
# and a str() that rounds floats where Python's does not. The extractors call the
# same function (typst_prose.display_of), so the PDF, the word count and the
# narration cannot disagree about what a number looks like.
#
# Gitignored, and regenerated by every recipe that compiles, so it is never stale.
# Render stats.json into the stats-rendered.json that Typst reads
[private]
render-stats:
  @uv run --quiet python tools/render_stats.py

# Both declaration checks, which is how `just verify` runs them. Kept as separate
# recipes underneath so either can be run alone while working on one of them.
# Check stats.json and assets.json against what produced them
[private]
check-declared:
  #!/usr/bin/env bash
  set -uo pipefail
  rc=0
  just check-stats  || rc=1
  just check-assets || rc=1
  exit $rc

# Reads files only -- guards, provenance, checksums, and a hash comparison of the
# code and data behind the numbers. Deliberately does NOT re-run the analysis:
# `just verify` is the command you run constantly and it must rebuild nothing.
# The first version of this re-derived every time, which on the scaffold cost
# 0.02s and looked free, and on a real analysis would make the gate cost the
# analysis.
# Check stats.json: guards, provenance, checksums, and the hashes behind them
check-stats:
  @uv run --quiet python tools/check_stats.py

# The strong check, and the expensive one: re-runs gen_stats.py and diffs every
# value it owns against what the analysis produces now. Run it before submitting,
# or when `just check-stats` reports the sources moved and you want to know which
# numbers actually change. Not part of `just verify`.
# Re-run the analysis and diff every generated number against it
check-stats-deep:
  @uv run --quiet python tools/check_stats.py --deep

# Files the author declares worth watching, beyond what any generator knows it
# read: a raw export, a protocol document, an upstream config. Declared by hand
# in stats.json under `pinned` (path: null), hashed by this, and watched by
# `just check-stats` from then on. Re-run it to accept a deliberate change.
# Record hashes for the files listed under `pinned` in stats.json
pin:
  @uv run --quiet python tools/pin.py

# For a manuscript migrating onto this scaffold with figures whose analysis is
# gone or unrunnable: every unclaimed file under figures/ and si/ is declared
# with origin.by = "adopted" and your note as its provenance. The hash and
# reference checks still apply; what is honestly absent is regeneration --
# nothing can rebuild an adopted file, and the checks say so rather than
# pretend. A generator that later calls record() with the same id takes it
# over. Re-run with a new note to accept a deliberate change to an adopted file.
# Adopt committed figures/tables no generator can rebuild (migration aid)
adopt note="":
  @uv run --quiet python tools/adopt_assets.py --note="{{note}}"

# assets.json is the same contract for figures and tables: declared by the script
# that writes them, referenced from the prose by id. Because the compile resolves
# those ids, the manifest cannot rot into a file nobody reads -- which is what
# makes these checks worth running. This replaced a pair of whole-tree hashes in
# .assets-stamp, which fired on the same two failures and could only say
# "analysis/ has changed" -- and which also fired on a new file no generator
# imports, a change that by definition altered no output.
#
# What went with them: an input a generator READS without declaring or importing
# is now invisible. record() warns when a generator declares no inputs at all,
# which is the nudge that replaces it.
# Check assets.json: output hashes, generators, declared inputs, and references
check-assets:
  @uv run --quiet python tools/check_assets.py

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
draft: render-stats
  typst compile --input draft=true paper.typ paper-draft.pdf
  @echo 'wrote paper-draft.pdf -- unresolved numbers appear as ?id?; `just paper` is the real build'

# The source stamp is taken BEFORE the compile, in both build recipes: a source
# edit saved while typst runs is then not claimed as built, and the next
# `just check` reports stale -- wrong in the safe direction. Stamping afterwards
# claimed the edited sources as rendered when they were not.
# Compile paper.typ -> paper.pdf, then print word counts and readability.
#
# The density report is NOT printed here any more. It is a diagnosis tool --
# CLAUDE.md has always described it as "worth running by hand, not part of the
# gate" -- and on a real manuscript its nine-column table plus the per-section
# outlier list tripled the build output into a wall nobody read. The two
# numbers a build should surface (how long, how readable) fit on nine lines.
# Compile paper.typ -> paper.pdf, then print word counts and readability
paper: render-stats
  #!/usr/bin/env bash
  set -euo pipefail
  stamp=$(just _stamp-manuscript)
  typst compile paper.typ
  just _record-build paper.pdf "$stamp"
  bash tools/wordcount.sh
  echo ""
  uv run --quiet python tools/readability.py
  echo "  density and per-section outliers: just density"

# See wordcount.typ for exactly what is excluded (refs, figures/tables, captions,
# math, code) vs. included (headings, inline code).
# Journal-style word counts (main text / SI / total), without rebuilding the PDF
wordcount: render-stats
  @bash tools/wordcount.sh

# Computed from the Typst source with the same exemptions as the word count. Uses
# `textstat` if installed, else a built-in estimate. No PDF rebuild.
# Readability metrics (Flesch-Kincaid grade, reading ease, words/sentence, fog)
readability:
  @uv run --quiet python tools/readability.py

# ---------------------------------------------------------------------------
# Text-invariance, for structural refactors: preamble changes, docx-mode edits,
# a typstyle upgrade, a migration. The property being protected is "the words
# in the PDF did not move", which no other check watches -- verify guards the
# machinery, not the rendered text. Snapshot before the refactor, rebuild
# after, diff. Word-level, because a reflow rewraps every line and a line diff
# would report the whole paper changed.
#
# The baseline is local state like .build-stamp: untracked, disposable, and
# meaningful only against the paper.pdf on this machine.
# ---------------------------------------------------------------------------

# The copy-edit twin of text-diff. text-diff proves the WORDS did not move
# through a machinery refactor; this proves everything BUT the words survived
# an editing pass -- every number, label, reference, figure and heading.
# STYLE.md permits dropping a number during a rewrite and never permits
# editing one; these are mechanical properties, so they are checked
# mechanically instead of eyeballed. Snapshot before handing the prose to a
# co-author or an agent, check after. Numbers may be dropped (a note), never
# invented (fatal); references, floats and headings must survive exactly.
# The manuscript as plain Typst, with every project helper resolved: #s() and
# #lit() become their values, fig()/tbl() become real image()/table content,
# @fig:x becomes #ref(<fig:x>). Pandoc can read Typst but not our helpers, so
# this is the one step between the manuscript and any pandoc-based export --
# a Word file with NATIVE equations, or LaTeX for a journal that wants source.
#
# A build artifact, like stats-rendered.json: gitignored, rewritten on demand,
# never edited. Read it when an export looks wrong; it is what pandoc was fed.
# Resolve the manuscript into plain Typst -> paper.resolved.typ (for pandoc)
resolve: render-stats
  @uv run --quiet python tools/resolve_typst.py

# Snapshot the manuscript's numbers/refs/floats/headings before an editing pass
edit-baseline tag="default":
  @uv run --quiet python tools/prose_edit_guard.py snapshot {{tag}}

# Prove an editing pass changed only wording: nothing invented, nothing lost
edit-check tag="default":
  @uv run --quiet python tools/prose_edit_guard.py check {{tag}}

# Snapshot the current paper.pdf's extracted text as the baseline for text-diff
text-baseline:
  #!/usr/bin/env bash
  set -euo pipefail
  command -v pdftotext >/dev/null 2>&1 || {
    echo "pdftotext is not installed (package: poppler-utils). See: just doctor"; exit 1; }
  [ -f paper.pdf ] || { echo "no paper.pdf -- build it first: just paper"; exit 1; }
  pdftotext -layout paper.pdf .text-baseline
  echo "baseline recorded from paper.pdf ($(wc -w < .text-baseline) words)."
  echo "After the refactor: just paper && just text-diff"

# Word-level diff of the current paper.pdf's text against the recorded baseline
text-diff:
  #!/usr/bin/env bash
  set -euo pipefail
  command -v pdftotext >/dev/null 2>&1 || {
    echo "pdftotext is not installed (package: poppler-utils). See: just doctor"; exit 1; }
  [ -f .text-baseline ] || {
    echo "no baseline -- record one BEFORE the refactor: just text-baseline"; exit 1; }
  [ -f paper.pdf ] || { echo "no paper.pdf -- build it first: just paper"; exit 1; }
  current=$(mktemp)
  trap 'rm -f "$current"' EXIT
  pdftotext -layout paper.pdf "$current"
  # --word-diff, because the failure mode of a line diff here is a false alarm
  # on every rewrap; --no-index because neither file is tracked.
  if git diff --no-index --word-diff=color -- .text-baseline "$current"; then
    echo "extracted text is unchanged from the baseline."
  else
    echo ""
    echo "the words above moved. If every change is one you chose, accept the"
    echo "new state as the baseline: just text-baseline"
    exit 1
  fi

# Live preview, recompiling on save.
#
# render-stats runs once here, not per recompile: typst watch owns the loop and
# cannot call out to it. Editing stats.json (or re-running the analysis) during a
# watch means restarting it.
# Live preview, recompiling on save (restart it after editing stats.json)
watch: render-stats
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
# Add --strict to treat warnings as failures.
# Check the prose against the mechanical rules in STYLE.md and prose-check.toml
prose-check:
  @uv run --quiet python tools/prose_check.py

# Pictures OF the manuscript, for revising it -- not pictures in it. Sentence
# length, words per section, most-used words, a word cloud, and the age of the
# bibliography.
#
# Writes to viz/, NOT figures/. figures/ holds the manuscript's own figures and
# is checked for orphans, so a diagnostic written there would be reported as a
# generated asset nothing cites. viz/ is gitignored and disposable.
#
# Not part of any gate: nothing here can fail, it only shows you the shape of
# what you have written.
# Diagnostics about the draft -> viz/ (sentence length, word use, citation ages)
viz:
  @uv run --quiet python tools/viz.py

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
  @uv run --quiet python tools/bib_audit.py

# Assert the prose extractors still handle every construct, and still do so after
# a reflow. Runs against tests/fixture.typ, which is NOT part of the manuscript --
# placeholder prose in paper.typ gets deleted the moment real writing starts, so
# anything relying on it for coverage would be tested once and never again.
# Assert the prose extractors handle every construct, before and after a reflow
test:
  @uv run --quiet python tests/run.py

# Rewrite tests/expected/ from the current extractor behaviour. Review the diff:
# this is how a regression gets blessed into the baseline by accident.
# Rewrite the golden files from current behavior -- review the diff before committing
test-update:
  @uv run --quiet python tests/run.py --update

# Reflow the hand-written Typst sources to `fmt_width` columns
#
# The message below is single-quoted, NOT backquoted. just evaluates a backquoted
# string as a shell command, so a `just paper` written inside that message ran a
# full PDF rebuild as a side effect of formatting and printed a word count nobody
# asked for. Recipe-body `#` comments are echoed too, hence this sits out here.
# Reflow the hand-written Typst sources to fmt_width columns
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
#      export drops math outright; tools/typst2docx.py rasterizes them back inline.
#   3. pandoc comes from uv (pypandoc-binary), so no system install is needed.
# Figures embed as images, tables stay real Word tables, and `=` sections map onto
# Word's Heading 1. Typst's HTML export is experimental and prints "ignored during
# HTML export" warnings for layout-only constructs; those are expected and cost
# nothing in the prose. The PDF build is entirely unaffected by the docx flag.
# Compile paper.typ -> paper.docx (Word), for journals/co-authors that want .docx
docx: render-stats
  #!/usr/bin/env bash
  set -euo pipefail
  stamp=$(just _stamp-manuscript)
  typst compile --features html --input docx=true -f html paper.typ paper.docx.html
  uv run --quiet python tools/typst2docx.py paper.docx.html paper.docx
  rm -f paper.docx.html
  just _record-build paper.docx "$stamp"

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
  # No stamp is written any more. assets.json records a hash per generated file
  # and per input its generator declared, so "has the analysis moved on since
  # these were made" is answered per entry by `just check-assets`, with the file
  # and the script named -- which a whole-tree hash could not do.

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

# paper.pdf and paper.docx are UNTRACKED build artifacts (see .gitignore). Large
# binaries do not belong in git: every version is kept forever, a clone pays for
# all of them, and getting one back out means rewriting history.
#
# So staleness is answered by a CONTENT STAMP rather than by git. `just paper` and
# `just docx` record the hash of the sources they rendered AND of the output they
# produced; this recompares both. No git, no mtimes -- mtimes are rewritten by a
# clone or a checkout, which is why the git version existed in the first place.
#
# .build-stamp is itself untracked, and has to be: it describes local build output.
# Tracking it would mean a rebuild on one machine reports every other checkout
# stale, for a file those checkouts do not have.
#
# The trade this accepts: a reader can no longer get the PDF from the repository
# without a Typst install. Attach it to a release or a CI artifact instead.
# Fail if paper.pdf or paper.docx no longer matches the source it was built from
[private]
check-build:
  #!/usr/bin/env bash
  set -uo pipefail
  rc=0
  now=$(just _stamp-manuscript)
  for out in paper.pdf paper.docx; do
    recipe=$([ "$out" = "paper.pdf" ] && echo "just paper" || echo "just docx")
    was=$(grep -m1 "^$out " .build-stamp 2>/dev/null | cut -d" " -f2)
    outwas=$(grep -m1 "^$out " .build-stamp 2>/dev/null | cut -d" " -f3)
    if [ ! -f "$out" ]; then
      echo "MISSING:  $out -- rebuild: $recipe"
      rc=1
    elif [ -z "$was" ]; then
      # Built before this check existed, or written by something other than the
      # recipe. Reported rather than guessed at: assuming current would hide the
      # exact case the stamp is for.
      echo "UNKNOWN:  $out has no entry in .build-stamp -- rebuild: $recipe"
      rc=1
    elif [ "$now" != "$was" ]; then
      echo "STALE:    $out was built from different sources -- rebuild: $recipe"
      rc=1
    elif [ -z "$outwas" ]; then
      # A stamp from before output hashes were recorded. One rebuild upgrades it.
      echo "UNKNOWN:  $out predates output hashing in .build-stamp -- rebuild: $recipe"
      rc=1
    elif [ "$(sha256sum "$out" | cut -d" " -f1)" != "$outwas" ]; then
      # The sources match, but the FILE is not what that build produced: it was
      # overwritten, truncated, or restored from somewhere else after the build.
      # Without this line, a paper.pdf copied in from Downloads passes as
      # current -- the source stamp only proves a build happened, not that this
      # file is its output.
      echo "REPLACED: $out is not the file that build produced -- rebuild: $recipe"
      rc=1
    fi
  done
  [ $rc -eq 0 ] && echo "paper.pdf and paper.docx are current with the source"
  exit $rc

# Hash of everything the manuscript renders: the hand-written sources and the
# generated assets they pull in. stats.typ and wordcount.typ are included here and
# were missing from the git-based check they replace, so editing either one used
# to leave the PDF looking current.
#
# The three tools that SHAPE the output are in the list too: render_stats.py and
# typst_prose.py decide what every number looks like, typst2docx.py builds the
# Word file. A change to any of them changes what a build produces, which is the
# definition of stale this stamp exists to catch. The rest of tools/ only
# measures or checks, so it stays out.
#
# stats.json is hashed WITHOUT its `pinned` block, through python3 rather than
# find. The pins are bookkeeping about external files; nothing a build renders
# reads them, and hashing them whole meant `just pin` -- a pure record-keeping
# command -- marked both outputs STALE and demanded a rebuild that would change
# nothing.
_stamp-manuscript:
  #!/usr/bin/env bash
  set -uo pipefail
  { find paper.typ config.typ si-body.typ stats.typ assets.typ \
      assets.json wordcount.typ references.bib si figures \
      tools/render_stats.py tools/typst_prose.py tools/typst2docx.py \
      -type f -not -name '*.pyc' \
      -print0 2>/dev/null | sort -z | xargs -0 -r sha256sum
    python3 - 2>/dev/null <<'PY' || true
  import hashlib, json
  d = json.load(open("stats.json"))
  d.pop("pinned", None)
  h = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()
  print(f"{h}  stats.json(sans pinned)")
  PY
  } | sha256sum | cut -d" " -f1

# Record that <name> was just built from the sources hashed in <srchash>, which
# the build recipe captured BEFORE compiling. Rewrites only its own line, so
# building the PDF does not claim the Word export is current too. The line also
# records the hash of the output itself, so check-build can tell "this file is
# that build's product" from "a build happened once".
_record-build name srchash:
  #!/usr/bin/env bash
  set -euo pipefail
  touch .build-stamp
  { grep -v "^{{name}} " .build-stamp || true; } > .build-stamp.tmp
  echo "{{name}} {{srchash}} $(sha256sum "{{name}}" | cut -d" " -f1)" >> .build-stamp.tmp
  mv .build-stamp.tmp .build-stamp

# Remove the built PDF and Word export
clean:
  rm -f paper.pdf paper-draft.pdf paper.docx paper.docx.html
