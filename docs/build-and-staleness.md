# Builds, staleness and the gates

What `just verify`, `just check` and `just preflight` check, and how builds are recorded.

## `just check` reports staleness; `just preflight` gates a submission

`just check` exits non-zero if anything is stale, and covers the failure modes
that actually happen:

- `paper.pdf` or `paper.docx` built from sources that have since changed. `just
  paper` and `just docx` record the hash of what they rendered in `.build-state/`;
  `just check-build` recompares it. Hashes are captured before rendering stats
  or resolving exports, and checked again before replacing the deliverable.
  A source edit during the build preserves the last good output and fails.
  Compiler dependencies, included chapters, CSL files, and the Word filter
  participate in the check. Concurrent manuscript builds are refused.
- An output that is **not the file that build produced** — overwritten,
  truncated, or restored from somewhere else. The stamp records the output's own
  hash too; without it, a `paper.pdf` copied in from Downloads passes as
  current, because the source stamp only proves a build happened.

The declaration checks in `just verify` also compare generated figures, tables,
and statistics against their recorded code, data, and analysis environment.

`just preflight` is the day-of-submission command: fresh builds of both
outputs, the whole `verify` gate, `check-stats-deep` (re-derives every
generated number from the analysis and diffs), and `bib-audit` (every DOI's
title, authors and publication details against Crossref or DataCite, plus
retractions and dead links). Those last two are too slow and too network-bound
for `verify`, and "run them before submitting" scattered across the docs is a
ritual — this is the ritual as one command.

Preflight requires a completed DOI audit (`bib-audit --require-complete`).
Network failures cannot produce a successful submission gate. The standalone
audit remains tolerant of an offline connection. A deep statistics check that
cannot run or obtain a fresh writer receipt also exits nonzero; it never treats
a copy of the old values as proof of regeneration.

The DOI audit does not mistake a resolving link for a verified citation. It
compares each entry with the metadata registered by the publisher: title,
author order, and year mismatches fail; venue, volume, issue, and page
differences are printed for review because online-first and print records often
differ there. Comparisons ignore capitalization, punctuation, markup, initials
versus full given names, and the different dashes used for BibTeX page ranges.
If a registrar omitted a field, the audit says nothing about that field rather
than pretending it verified information it never received.

Sometimes the registrar is the side that is wrong: a surname fused with a
footnote marker, or a record that never picked up a published correction. Do
not edit the bibliography to match. Name the entry in `prose-check.toml` as
`[allow] doi-metadata = ["key"]`, or `"key:author"` to excuse one field only,
with the reason in a comment beside it. The mismatch is still printed but no
longer fails, and an allowance that stops excusing anything is listed for
deletion.

An entry with no DOI but a `url` is fetched instead. GitHub and crates.io
URLs go through their APIs, which name the repository's owner and follow a
rename; anything else is fetched as a page and its title read. Nothing
registers a title or author list for a URL, so a live one prints what the page
says about itself under the bibliography's title and authors for a person to
compare. A URL that returns 404 or 410 fails the audit; one that now redirects
elsewhere is listed to update; one that cannot be reached is reported as a
network fact and does not fail, even under `--require-complete`, because many
sites refuse scripts.

**Neither output is tracked in git**, and neither is `.build-state/`. Git keeps
every version of a binary forever, a clone pays for all of them, and removing one
means rewriting history. Ship the PDF as a release asset or a CI artifact.

That is also why staleness is a content hash rather than a commit date: nothing
here reads git history any more, so the checks work in an exported tree, a shallow
clone, or no repository at all. `.build-state/` stays untracked because it
describes *local* build output — tracking it would let a rebuild on one machine
report every other checkout stale.

The audiobooks are deliberately not checked. Every prose edit would mark them
stale and clearing that costs minutes of narration, so the warning was almost
always present and almost never acted on.

## What `verify` runs


- **`just fmt-check`** -- the hand-written sources are reflowed to 80 columns.
  Skipped with a note if typstyle is not installed.
- **`just test`** -- the prose extractors still handle every construct, before
  and after a reflow. This is the one that matters when you touch inline markup,
  math, links, or cross-references: those are recognized by regexes in
  `tools/typst_prose.py` that a reflow can break silently, which has happened three
  times (see that file for the cases).
- **`just prose-check`** -- fails on em dashes, British spellings, doubled words,
  and uncited figures; reports long sentences, verbosity, repetition,
  unexpanded acronyms, and distinctive numerals that match nothing in
  `stats.json` as warnings you should read rather than silence.
- **`just check-words`** -- checks the scopes and inclusive word limits in
  `word-limits.toml`. Use `just wordcount --sections` to find section paths.
  Excluding a section affects this count only, not other prose checks or exports.
  Do not change limits or exclusions merely to clear a failure; follow the
  author's requested scope and journal requirements.
- **`just check-stats`** -- re-runs every guard in `stats.json` against the
  committed values, checks each generated value against the checksum its
  generator recorded, compares the hashes of the code and data behind them --
  and of every `pinned` file -- insists a hand-entered number carries a note,
  and reports ids nothing reads. Reads files only; it does **not** re-run the
  analysis.
- **`just check-stats-deep`** -- the same plus re-running `gen_stats.py` and
  diffing every value it owns. Stronger and as slow as your analysis, so it is
  NOT in `verify`. Run it before submitting.
- **`just check-assets`** -- per generated file: does it still hash to
  what was recorded, does its generator still exist, have its declared inputs
  changed, and does anything reference it.
- **`just check`** -- a `paper.pdf` or `paper.docx` built from sources that have
  since changed, and `figures/` and `si/` older than the `analysis/` code behind
  them. Neither output is tracked in git; `just paper` and `just docx` record what
  they rendered in `.build-state/` and `just check-build` recompares it. No check
  reads git history, so they all work outside a repository.
- **`just check-actions`** -- the review action ledger `reviews/ACTIONS.md`
  still parses: one table with the fixed columns, unique `A-NNNN` ids, allowed
  severity and status values, and a `closed` value on every done or wontfix
  row. Prints open counts by severity. Open blockers are a WARNING, not a
  failure; a missing ledger passes silently. See
  [working-with-ai.md](working-with-ai.md#the-review-action-ledger).

`just check` deliberately does not check the audiobooks, and there is no upstream
figure copy to compare against any more. See HISTORY.md's "Decisions reversed"
before adding either back.

## Reviewing changes between versions

Save the version you have finished reviewing, then compare after editing:

```bash
just review-baseline reviewed
# Edit prose or regenerate analysis outputs.
just review reviewed
```

Open `.review/review.html`. It shows the previous and current passages side by
side, highlights added and removed words, and includes tables, equations,
captions, figures, and the reference list. The section navigator shows where each edit belongs; **Next** / **Previous**
(or **J** / **K**) move between edits. **Content edits** hides automatic citation
renumbering; choose **All changes** to include it or **Full paper** for context.
Changed numbers are highlighted as complete values. Unchanged passages appear
once in Full paper mode. A changed number is
visible even when its `#s("id")` call did not change. Figures are stored with
each version, so overwriting a plot does not change what the old version shows.
Soft line wrapping does not count as a writing edit. Citation renumbering is
distinguished from changing the cited work. Moved passages may appear as a
removal and an addition; formatting rules and page layout are not compared.

`just review-versions` lists saved names without rebuilding.

Names are permanent: a command refuses to overwrite an existing version. To
compare two saved versions, use `just review reviewed revised`. Saved versions
live in `.review/versions/`, outside the disposable `.build-state/` cache.
They are local and gitignored; back up `.review/` if you want to retain this
review history. New papers do not inherit it. Neither review command reruns
analysis. Saving or comparing against current work makes a fresh strict build,
so unresolved notes and missing inputs fail visibly.

PDF, Word, and review now share a captured intermediate manuscript under
`.build-state/manuscripts/<id>/`. Its `paper.typ` contains resolved literal
statistic calls and asset paths while retaining Typst imports, include scopes,
labels, equations, and layout rules. It includes copies of the input files.
Typst supplies the actual heading and float numbers for the Word adaptation.
`paper.word.typ` is that adaptation; the root `paper.resolved.typ` remains a
convenient preview of it. Both are generated and must not be hand-edited.
`just resolve` refreshes this intermediate and its PDF.

`just paper` overlaps PDF compilation with the independent Word/review
preparation, then runs word count and readability together. Reports still
appear in order. Word front matter and numbering share one fresh Typst query.
Every invocation builds fresh, and both preparation paths
must succeed before the PDF is published; source-change and concurrent-build
checks remain in place.

The snapshot manifest records input and output hashes and the Typst version.
The HTML report embeds images and works offline. Recompiling a saved source tree
still requires the external toolchain, fonts, and Typst packages; a snapshot
does not vendor those. Custom Typst constructs must be supported by the Word
adapter as well as Typst. A mismatch in exported figures or heading numbering
fails the shared build rather than silently omitting content.
