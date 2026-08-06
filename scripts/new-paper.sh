#!/usr/bin/env bash
# Start a new manuscript from this scaffold.
#
# WHY THIS EXISTS. The documented way to start a paper used to be
#
#     cp -r paper-scaffold /path/to/your-project/paper
#
# which copies .git along with everything else. The new manuscript then carries
# the scaffold's entire history, and `just version` reports the scaffold's last
# commit as the manuscript's state, confidently and wrongly. It also drags along
# .build-stamp, which would claim the new paper's outputs were built from sources
# it has never seen. This script copies the working files,
# fills in the identity, and starts a fresh history that belongs to the paper.
#
# It does NOT touch the placeholder prose in paper.typ, si-body.typ, or the
# abstract in config.typ. Those say "replace me" and are meant to be deleted
# once, by hand, when real writing starts. Only the structured identity fields
# are filled in, because those are the ones that are read by five different
# tools and are tedious to find.
#
# Usage:
#   scripts/new-paper.sh [options] [DEST]
#
# With no options it asks. Every field also has a flag, so a scripted run needs
# no terminal:
#
#   scripts/new-paper.sh --yes --title "My Paper" --author "Ada Lovelace" ~/papers/mine
#
# Options:
#   --title TEXT          Paper title
#   --wordmark TEXT       Short form for the audiobook cover (a word or two)
#   --subtitle TEXT       Cover subtitle; use \n for a line break
#   --author NAME         First author (add the rest by hand in config.typ)
#   --email ADDR          First author's email
#   --affiliation TEXT    First author's affiliation
#   --institution TEXT    Shown on the audiobook cover
#   --keywords A,B,C      Comma-separated
#   --date TEXT           e.g. "January 2026"
#   --bib-style NAME      Typst CSL style name (default american-chemical-society)
#   -y, --yes             Never prompt; take defaults for anything not passed
#   --no-build            Skip the first `just paper`
#   --no-git              Do not run git init / the first commit
#   -h, --help            This text
set -euo pipefail

SCAFFOLD="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { sed -n '2,42p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

die() { echo "error: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
DEST=""
TITLE=""; WORDMARK=""; SUBTITLE=""; AUTHOR=""; EMAIL=""; AFFILIATION=""
INSTITUTION=""; KEYWORDS=""; PDATE=""; BIBSTYLE=""
ASSUME_YES=0; DO_BUILD=1; DO_GIT=1

while [ $# -gt 0 ]; do
  case "$1" in
    --title)       TITLE="${2:?--title needs a value}"; shift 2 ;;
    --wordmark)    WORDMARK="${2:?}"; shift 2 ;;
    --subtitle)    SUBTITLE="${2:?}"; shift 2 ;;
    --author)      AUTHOR="${2:?}"; shift 2 ;;
    --email)       EMAIL="${2:?}"; shift 2 ;;
    --affiliation) AFFILIATION="${2:?}"; shift 2 ;;
    --institution) INSTITUTION="${2:?}"; shift 2 ;;
    --keywords)    KEYWORDS="${2:?}"; shift 2 ;;
    --date)        PDATE="${2:?}"; shift 2 ;;
    --bib-style)   BIBSTYLE="${2:?}"; shift 2 ;;
    -y|--yes)      ASSUME_YES=1; shift ;;
    --no-build)    DO_BUILD=0; shift ;;
    --no-git)      DO_GIT=0; shift ;;
    -h|--help)     usage; exit 0 ;;
    -*)            die "unknown option: $1 (try --help)" ;;
    *)             [ -n "$DEST" ] && die "more than one destination given"
                   DEST="$1"; shift ;;
  esac
done

# Prompt for a value unless it was passed or we were told not to ask. The
# default is shown in brackets and taken on an empty answer.
ask() {                      # ask VAR "prompt" "default"
  local __var="$1" prompt="$2" default="$3" reply
  local current="${!__var}"
  if [ -n "$current" ]; then return; fi
  if [ "$ASSUME_YES" = 1 ] || [ ! -t 0 ]; then
    printf -v "$__var" '%s' "$default"; return
  fi
  read -r -p "$prompt [$default]: " reply || reply=""
  printf -v "$__var" '%s' "${reply:-$default}"
}

echo "paper-scaffold: new manuscript"
echo "  scaffold: $SCAFFOLD"
echo ""

ask DEST        "Destination directory"  "./my-paper"
ask TITLE       "Paper title"            "Untitled Manuscript"
ask AUTHOR      "First author"           "$(git config user.name  2>/dev/null || echo 'Your Name')"
ask EMAIL       "  their email"          "$(git config user.email 2>/dev/null || echo 'you@example.edu')"
ask AFFILIATION "  their affiliation"    "Your Department, Your University, City, Country"
ask INSTITUTION "Institution (cover art)" "Your University"
ask KEYWORDS    "Keywords (comma-separated)" "keyword one, keyword two"
ask PDATE       "Date"                   "$(date '+%B %Y')"
ask BIBSTYLE    "Bibliography style"     "american-chemical-society"
# Derived defaults, asked last so they can lean on the title.
ask WORDMARK    "Cover wordmark (a word or two)" "$(echo "$TITLE" | awk '{print tolower($1)}')"
ask SUBTITLE    "Cover subtitle"         "$TITLE"

[ -n "$DEST" ] || die "no destination given"
if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  die "$DEST exists and is not empty"
fi
mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"
[ "$DEST" != "$SCAFFOLD" ] || die "destination is the scaffold itself"

# ---------------------------------------------------------------------------
# Copy. tar rather than cp so the AGENTS.md -> CLAUDE.md symlink survives as a
# symlink; a plain `cp -r` turns it into a second copy of the file, which is
# then free to drift from the one agents actually read.
#
# What is left out: the scaffold's git history (the whole point), both
# virtualenvs and every cache (rebuilt by `just setup`), this scripts/ directory
# (it makes new papers, and a paper does not make papers), and the built
# artifacts, which describe the scaffold's demo paper and not yours. figures/,
# si/ and .assets-stamp DO come along, so the copy compiles and `just check` is
# clean before the analysis has ever run.
# ---------------------------------------------------------------------------
echo ""
echo "copying scaffold -> $DEST"
tar -C "$SCAFFOLD" -cf - \
    --exclude='./.git' \
    --exclude='./.github' \
    --exclude='./scripts' \
    --exclude='./.venv' \
    --exclude='./analysis/.venv' \
    --exclude='./audio/.venv' \
    --exclude='./analysis/data' \
    --exclude='./analysis/results' \
    --exclude='./audio/piper' \
    --exclude='./audio/models' \
    --exclude='./audio/chapters*' \
    --exclude='*__pycache__*' \
    --exclude='*.pyc' \
    --exclude='./paper.pdf' \
    --exclude='./paper-draft.pdf' \
    --exclude='./.build-stamp' \
    --exclude='./paper.docx' \
    --exclude='./paper.docx.html' \
    . | tar -C "$DEST" -xf -

# The scaffold's MIT terms cover the TOOLING, which the new directory is now
# carrying a full copy of, so the notice travels with it. Renamed, because a
# plain LICENSE at the root of a manuscript reads as the licence of the paper,
# which is a different question and the author's to answer.
[ -f "$DEST/LICENSE" ] && mv "$DEST/LICENSE" "$DEST/LICENSE.scaffold"

# ---------------------------------------------------------------------------
# Fill in config.typ. Done in Python rather than sed because a title is allowed
# to contain the characters that break a sed expression, and a silently mangled
# title is worse than a failure -- it renders, and it renders wrong.
# ---------------------------------------------------------------------------
echo "filling in config.typ"
TITLE="$TITLE" WORDMARK="$WORDMARK" SUBTITLE="$SUBTITLE" AUTHOR="$AUTHOR" \
EMAIL="$EMAIL" AFFILIATION="$AFFILIATION" INSTITUTION="$INSTITUTION" \
KEYWORDS="$KEYWORDS" PDATE="$PDATE" BIBSTYLE="$BIBSTYLE" \
python3 - "$DEST/config.typ" <<'PY'
import os, re, sys
from pathlib import Path

p = Path(sys.argv[1])
src = p.read_text()
env = os.environ


def tstr(s: str) -> str:
    """A Typst string literal. Only backslash and quote need escaping, but both
    absolutely do: an unescaped quote in a title ends the string early and the
    rest of the line becomes code."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def sub_let(name: str, value: str) -> None:
    """Replace the value of a single-line `#let name = ...` binding."""
    global src
    pat = re.compile(rf"^(#let {re.escape(name)} = ).*$", re.M)
    if not pat.search(src):
        sys.exit(f"error: {name} not found in config.typ")
    src = pat.sub(lambda m: m.group(1) + value, src, count=1)


def sub_block(name: str, value: str) -> None:
    """Replace a `#let name = ( ... )` binding, scanning to the matching paren
    rather than to the first one, since author entries are parenthesized too."""
    global src
    m = re.search(rf"^#let {re.escape(name)} = \(", src, re.M)
    if not m:
        sys.exit(f"error: {name} not found in config.typ")
    i = src.index("(", m.start())
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                src = src[:m.start()] + f"#let {name} = " + value + src[j + 1:]
                return
    sys.exit(f"error: {name} has no closing paren")


# The subtitle takes a literal \n from the command line and passes it through as
# a Typst escape, because that is what config.typ documents it as accepting.
subtitle = tstr(env["SUBTITLE"]).replace("\\\\n", "\\n")

sub_let("paper-title", tstr(env["TITLE"]))
sub_let("paper-wordmark", tstr(env["WORDMARK"]))
sub_let("paper-cover-subtitle", subtitle)
sub_let("paper-date", tstr(env["PDATE"]))
sub_let("paper-institution", tstr(env["INSTITUTION"]))
sub_let("paper-bib-style", tstr(env["BIBSTYLE"]))

kws = [k.strip() for k in env["KEYWORDS"].split(",") if k.strip()]
sub_block("paper-keywords", "(" + ", ".join(tstr(k) for k in kws) + ")")

# One author. A paper with more adds them here by hand, which is a two-line
# edit against a worked example; guessing a delimiter for a list of
# name/email/affiliation triples on a command line is worse than not offering it.
author = (
    "(\n"
    "  (\n"
    f"    name: {tstr(env['AUTHOR'])},\n"
    f"    email: {tstr(env['EMAIL'])},\n"
    f"    affiliation: {tstr(env['AFFILIATION'])},\n"
    "  ),\n"
    ")"
)
sub_block("paper-authors", author)

p.write_text(src)
PY

# pyproject's `name` is cosmetic here (package = false, nothing is built), but it
# shows up in uv's output, so a directory-shaped slug beats "paper" everywhere.
# `version` is deliberately left alone: it records which scaffold release this
# manuscript came from, which is what `just version` exists to answer.
slug="$(basename "$DEST" | tr '[:upper:] _' '[:lower:]--' | tr -cd 'a-z0-9-')"
[ -n "$slug" ] && python3 - "$DEST/pyproject.toml" "$slug" <<'PY'
import re, sys
from pathlib import Path
p = Path(sys.argv[1])
p.write_text(re.sub(r'^name = ".*"$', f'name = "{sys.argv[2]}"',
                    p.read_text(), count=1, flags=re.M))
PY

# ---------------------------------------------------------------------------
# Build before the first commit. Neither output is tracked any more, so the order
# no longer matters to a staleness check -- but both are still built here, and for
# the same reason as before: `just check` reports a missing paper.pdf or
# paper.docx as something to rebuild. Without this, the first thing a new
# manuscript does is fail its own gate over files the author never asked for,
# which teaches them on day one that the gate is noise.
#
# Building also writes .build-stamp, which is what makes that gate pass. The stamp
# is untracked, so a collaborator who clones the new repository builds their own.
#
# The build is best-effort. It needs the network the first time (the arkheion
# template is fetched from Typst Universe and cached), and a new manuscript
# started on a plane should still end up with a working directory.
# ---------------------------------------------------------------------------
built=0
if [ "$DO_BUILD" = 1 ]; then
  echo ""
  echo "building the first PDF"
  if (cd "$DEST" && just paper >/dev/null 2>&1); then
    built=1
    echo "  wrote paper.pdf"
    if (cd "$DEST" && just docx >/dev/null 2>&1); then
      echo "  wrote paper.docx"
    else
      echo "  note: the Word export did not build; run 'just docx' to see why"
    fi
  else
    echo "  could not build yet (typst, uv, or the network). Run: just doctor"
  fi
fi

if [ "$DO_GIT" = 1 ]; then
  if command -v git >/dev/null 2>&1; then
    # A machine with no configured identity (a fresh laptop, a CI runner) makes
    # `git commit` fail with "please tell me who you are". Falling back to a
    # placeholder keeps the FIRST commit from being the thing that stops someone
    # on a fresh laptop. A real identity is still preferred wherever one is set.
    ident=()
    if [ -z "$(git config user.email || true)" ]; then
      ident=(-c "user.name=paper-scaffold" -c "user.email=paper-scaffold@localhost")
      echo "note: git has no configured identity; using a placeholder for the"
      echo "      first commit. Set user.name/user.email and amend it if you care."
    fi
    (cd "$DEST"
     git init -q
     git add -A
     git "${ident[@]}" commit -q -m "New manuscript from paper-scaffold $(
       grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)")
    echo "initialized a git repository and made the first commit"
  else
    echo "note: git not found, skipped git init"
  fi
fi

echo ""
echo "done: $DEST"
echo ""
echo "next:"
echo "  cd $DEST"
echo "  just doctor      # confirm the toolchain"
echo "  just setup       # build the Python environment"
[ "$built" = 1 ] || echo "  just paper       # first PDF"
echo "  just verify      # the gate: formatting, extractors, prose rules, staleness"
echo ""
echo "then replace the placeholder prose in paper.typ and si-body.typ, the"
echo "abstract in config.typ, and references.bib. See README.md for the tour."
