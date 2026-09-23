# History

What changed in the pipeline, and why. Read the "Decisions reversed" section
before proposing a change that looks obvious. Several obvious things were tried
here and were wrong.

Entries are deliberately short: what changed, the one-line reason, and the
upgrade step. The full arguments live as comments next to the mechanisms they
justify, where someone touching the code will actually read them.

## Versioning

The version lives in one place, `version` in `pyproject.toml`, and travels with
the scaffold when it is copied into a project. `just version` prints it.

What bumps what is judged from the manuscript's point of view, not the code's:

- **Major** breaks a manuscript. An existing `paper.typ`, `si-body.typ`, or
  `analysis/` has to be edited to keep working.
- **Minor** adds a capability without touching an existing manuscript. A new
  check, a new metric, a new recipe.
- **Patch** fixes something without changing the interface.

Tag every release: `git tag -a v1.2.3 -m "..."`.

### Upgrading a project built on an older version

From inside the project. The upstream clone is `--scaffold PATH`, else
`$PAPER_SCAFFOLD`, else found through `.agents/skills`, a sibling
`paper-scaffold` directory, or `~/Repos/paper-scaffold`:

```bash
just version                        # what the project is on
just upgrade-plan                   # plan to the latest tag, or: just upgrade-plan v3.23.0
just upgrade-plan --apply-pristine  # copy only the files the project never touched
```

The plan lists every "Upgrade:" line between the project's version and the
target, oldest first, folds a pure copy step that a later release repeats,
and names the customized files each line touches. It then classes every
scaffold-owned file: **pristine** (identical to upstream at the project's
current version, so replacing it loses nothing), **customized** (changed both
locally and upstream; lines on each side, and whether `git merge-file` would
conflict), **new-upstream**, **removed-upstream**, **project-only**,
**at-target**, and **unchanged**. `--apply-pristine` copies the pristine and
new files only, refuses when git shows any of them dirty, and leaves removals,
customized files and the `version` line to you. `--json` is the same plan for
an agent.

Then merge each customized file by hand, with
`git -C <scaffold> diff vOLD..vNEW -- <path>` beside it, set
`version` in `pyproject.toml`, and run `just paper` and `just verify`. There is
still deliberately no automatic merge: a manuscript diverges from the scaffold
the moment real writing starts, and a merge tool cannot tell your
customization from the placeholder it replaced. The tool takes over the
bookkeeping only; every file that would need merging, it leaves to you. Read
the major entries first, since those need an edit rather than a copy. For
moving an existing manuscript onto the scaffold, see docs/migrating.md.

(A project older than 3.23.0 has no `tools/upgrade_plan.py`: run the scaffold's
copy with `--project PATH`, or copy the tool and the recipe in first. Before
2.0.0 the toolchain sat in the root, so upgrading from 1.x is by hand:
`git -C <scaffold> diff vOLD..vNEW -- justfile *.py tests/`.)

---

## 4.1.0

Multi-document projects on the stock recipes, a paper-owned slide theme, and
`paper migrate` on mixed-release trees. Found migrating the dissertation,
which carried a `-dissertation` or `chapter-` variant of seven stock recipes.

- **The stock recipes read `manuscript.toml`.** `pdf`, `watch`, `clean`,
  `prose-check`, `bib-audit`, `check-build` and so `check` and `verify`
  dispatch on it: every document's PDF, a watch of the default document,
  each part prose-checked once with its own bibliography, the parts'
  bibliographies audited with their citation prefixes, every document's
  staleness plus the dissertation Word export. `verify` skips word limits
  and the journal profile with a note, and `fmt-check` passes with a note
  when there are no hand-written sources (typstyle given no file reads
  stdin). Without `manuscript.toml` nothing changes (docs/multi-document.md).
- **`[slides] theme` in `project.toml`** names the paper's own deck theme,
  the escape hatch 3.27.0 gave the Word template: `paper sync` then writes
  no `slides/theme.typ` (removing a pristine one), never touches the
  declared file, and locks it as an override; `just slides` does not build
  it as a deck (docs/hooks.md).
- **`paper migrate` classes a file against every tagged release**, not only
  the paper's base: a file identical to any release is pristine, and the
  report names the release under "stock in another release". A tree
  upgraded by hand file by file no longer refuses on files it never edited.
- **`paper migrate`'s `tools/` scan matches uses, not words.** 4.0.1 flagged
  any `"tools"` string: koth-paper's analysis got eleven false refusals (a
  dict key, an argparse name, `benchmark/tools/x.jar`). A literal now counts
  only when it resolves into the paper's `tools/` (a `.`/`..` or
  paper-directory prefix, then a `.py` file or a name that directory holds);
  a bare `"tools"` only when joined onto a directory.

Upgrade: `uv add` the v4.1.0 pin, `uv run paper sync`. A multi-document
project then drops its variant recipes from `project.just`
(`verify-dissertation`, `watch-dissertation`, `clean-dissertation`,
`chapter-bib-audit` if it only audited, and the like) and the `just
document-verify all` stage from `project.toml`'s `[stages] verify` (stock
`verify` now covers it); keep house checks with no stock counterpart as
stages. A paper with its own deck theme declares it as `[slides] theme`
and points its decks at it. `just verify`.

## 4.0.1

Three 4.0.0 roll-out bugs in `paper migrate` and `paper path`.

- **`migrate` refuses the paper's own files in `docs/`.** `docs/` is the
  package's (docs/package.md, "What a paper holds"): `migrate` removed the
  directory and `paper sync --check` fails on one, so a paper's study notes
  there were either deleted or left verify failing. `migrate` now names them
  and says to move them to `notes/`; `sync --check` stays strict (a
  leftover `docs/` cannot be told apart from an unfinished migration) and
  its message now says where notes go.
- **`migrate` refuses Python that reaches the paper's `tools/`** (a
  `sys.path` insert, an import, a glob) with each `file:line`, in the paper
  and, for a paper in a subdirectory, in the rest of the repository when the
  line names the paper directory. Replacement: `paper_scaffold.tools_dir()`
  (docs/package.md, "Code that used tools/"; docs/hooks.md).
- **`paths.locate()` normalizes the name**, so `paper path tools` (no
  trailing slash) and `./tools` give the package's directory, not a missing
  local `tools`.

Upgrade: a paper on 4.0.0: `uv add` the v4.0.1 pin, `uv run paper sync`
(it rewrites `analysis/scripts/_toolchain/paths.py`), then move any notes
of the paper's own out of `docs/` to `notes/` (`git mv`, fix links) and
replace any code that builds `PAPER / "tools"` with
`paper_scaffold.tools_dir()`; `just verify`. A paper still on 3.x: migrate
from a v4.0.1 clone, which refuses both cases up front.

## 4.0.0

The toolchain is a package. A paper holds what it owns plus a pin, and an
upgrade is: move the pin, run `paper sync`. Reference: docs/package.md.

- **`paper-scaffold` installs as a Python package** with a `paper` console
  script. `tools/`, `tests/`, `journals/`, `word/` and `docs/` are package
  data, read from the installed release; a paper no longer carries them.
  Recipes run tools as `uv run paper tool NAME`.
- **`paper sync`** writes the few files a paper must hold on disk (the
  justfile, the five Typst modules, the `analysis/scripts/_*.py` helpers and
  `_toolchain/`, the audio scripts, `slides/theme.typ`), each headed
  GENERATED, and records them in `.paper/scaffold.lock.json`. It refuses to
  overwrite an edit. `.paper/docs/` is a gitignored copy of the docs.
- **`paper sync --check`** is the first `just verify` stage: it fails on a
  missing or edited generated file, a lock from another release, or a leftover
  `tools/`, `tests/` or `docs/`.
- **Overrides.** A paper's own `word/reference.docx` (the multi-document
  reference) or `journals/*.toml` wins over the package's copy
  (`tools/paths.py` `locate()`), is never written or flagged, and is listed
  in the lock. The single paper's Word reference is not a shipped file
  (3.27.0): it is generated from `[word.style]`, or it is the paper's own
  `[word] reference`, so the package ships and syncs no docx for it.
- **Staleness** hashes the build tools and journal profiles by content
  wherever they resolve, and `uv.lock`, so a pin move marks outputs stale.
  `paper.docx` goes stale on `project.toml` (`[word.style]`, `[word]
  reference`), on the declared reference file, and on the generator; no
  longer on `word/paper-reference.docx`.
- **`just upgrade-plan`** is now `just upgrade-notes` (the old name is an
  alias): the upgrade instructions between the lock's release and the
  installed one.
  `--apply-pristine` is gone; there is nothing to copy.
- **`paper migrate`** moves a 3.26.x or 3.27.x paper once: pristine
  toolchain copies are removed, generated files replaced, customized journal
  profiles kept as overrides; a customized tool, test, generated file or
  `HISTORY.md` is refused and nothing changes. A leftover
  `word/paper-reference.docx` is settled by the 3.27.0 rules, compared as
  Word renders it: stock or only recoloured black, removed; other edits,
  removed and written into `project.toml` as the `[word.style]` block that
  reproduces them; edits no setting expresses, kept and declared as
  `[word] reference`.
- **`HISTORY.md` is the package's.** It is read from the installed release
  (`.paper/docs/HISTORY.md`); a paper's own notes go in
  `notes/PROJECT-HISTORY.md`.
- **In a paper, `just test` is the extractor fixture check**; the case suites
  test the toolchain and run in this repository.
- `scripts/new-paper.sh` writes the pinned `pyproject.toml` and runs
  `paper sync` instead of copying the toolchain (`--pin` to choose).

Upgrade: from 3.26.x or 3.27.x. First settle every customized scaffold file
into `project.toml`, `project.just` or `hooks/` (3.26.0; `just upgrade-plan`
lists them), and move any notes of the paper's own out of `HISTORY.md` into
`notes/PROJECT-HISTORY.md`, restoring `HISTORY.md` to its stock text; run
`just text-baseline`; commit. Then from a scaffold clone at v4.0.0 run
`uv run paper migrate --project PAPER --dry-run`, read its REFUSED lines and
its "Word template" line, and rerun without `--dry-run`. It removes the
toolchain copies, rewrites `pyproject.toml` with the pin, handles
`word/paper-reference.docx` (removed; or removed with a `[word.style]` block
added to `project.toml`; or kept as `[word] reference`: check the block it
wrote), and runs `uv lock`, `uv sync` and `paper sync`. Then `just paper`,
`just text-diff`,
`just docx` (headings are black unless `heading_color` says otherwise),
`just verify`; commit with `git add -A`. A hook that ran `python tools/x.py`
now runs `uv run paper tool x`.

## 3.27.0

Word styling is declared, not a binary to edit. The Word export never
compiles the Typst preamble, so the paper's look reaches Word only through
the reference document, and each paper kept a hand-edited
`word/paper-reference.docx` that every upgrade had to diff by eye.

- **`[word.style]` in `project.toml`**: `font`, `font_size`,
  `line_spacing`, `margins`, `title_size`, `title_align`, `title_color`,
  `heading_color`, each optional and validated strictly.
  `tools/paper_word_reference.py` generates the reference document from
  them into `.build-state/word-reference/`, cached by a hash of the settings
  and the tool. A settings change makes `paper.docx` stale. docs/word-export.md.
- **The stock headings are black.** Title, Subtitle and Heading 1-9 were
  pandoc's blue, which three of the papers recoloured locally.
- **`[word] reference = "word/custom.docx"`** keeps a hand-made reference
  document, used as it is. It cannot be combined with `[word.style]`.
- **`word/paper-reference.docx` is no longer shipped or read.** A paper
  that still has one and does not declare it gets a build error that names
  the fix. `--translate` prints the `[word.style]` block that reproduces an
  old template, and `just upgrade-plan` states which case each paper is in.

Upgrade: copy `tools/`, `tests/` and `docs/` (`--apply-pristine`). Then handle
`word/paper-reference.docx` as `just upgrade-plan` classes it. The stock
file, or one only recoloured black: `git rm` it. One with other edits: put
the `[word.style]` block the plan prints into `project.toml` and `git rm`
the file. One with edits no setting expresses: keep it and declare
`[word] reference = "word/paper-reference.docx"`. For a paper whose own copy
of `upgrade_plan.py` predates this, run
`uv run python tools/paper_word_reference.py --translate word/paper-reference.docx`
after copying `tools/`. Rebuild with `just docx`: headings turn black unless
`heading_color` says otherwise.

## 3.26.1

- **The voice check wants both files.** `audio-setup` and `_audio-check` now
  require `<voice>.onnx.json` beside `<voice>.onnx`; an interrupted download
  left the model alone, `audio-setup` skipped it as present, and piper failed
  at synthesis. Brought up from spectrl-paper.

Upgrade: replace `justfile` (`--apply-pristine`). A paper whose audiobook
recipes depend on `audio-setup` instead of `_audio-check` returns them to
stock: the audiobook never downloads on its own.

## 3.26.0

Extension hooks: a paper extends the toolchain in files it owns, so an upgrade
replaces scaffold files instead of merging local edits into them. Nothing
changes for a paper that declares nothing. Reference: docs/hooks.md;
`just hooks` lists what a paper declares.

- **`project.toml`** (validated strictly; `schema_version = 1`):
  - `[[stages.verify]]`, `stages.check`, `stages.preflight` and
    `stages.submission` add named gate stages after the built-in ones. A
    stage extends a gate and never replaces one.
  - `[preflight] bib_audit_require_complete = false` drops the DOI
    completeness flag.
  - `[sources] typst` adds files to `fmt`, `fmt-check`, the prose rules and
    the todo check.
  - `[word]` adds Lua filters and Python steps before and after pagination.
    Those files and project.toml count toward staleness.
  - `[bibliography] single = true` declares one shared reference list: the
    SI cites `@key`, and a new `si-bibliography-mode` error flags a mismatch.
- **`project.just`** holds the paper's own recipes, imported by the justfile.
  A name clash with a scaffold recipe is an error, not an override.
- **CLAUDE.md** now says paper-specific toolchain changes go in these files,
  never in a scaffold file.

Upgrade: copy the justfile, `tools/`, `tests/`, `docs/` and CLAUDE.md's
"Paper scaffold" paragraph. Then move each local edit to a scaffold file into
`project.toml`, `project.just` or `hooks/` (docs/hooks.md), and restore the
scaffold file:
- justfile additions to `verify`/`check`/`preflight`/`all`/`submission`
  become stages;
- private recipes move to `project.just`;
- edits to the `typst_sources` line move to `[sources] typst`;
- `export_docx.py` table and style patches become `[word]` steps;
- deleted `@si-key` rules in CLAUDE.md/STYLE.md become
  `[bibliography] single = true`.

## 3.25.1

- **`just review-text` handles `#si-contents`.** The helper is a `context`
  block, which the review export refuses rather than risk dropping prose, so
  a manuscript using it had no review copy (koth-paper worked around it in
  its justfile). The export now writes in the same sentence the Word export
  builds, from `resolve_typst.substitute_si_contents`.

- **`just all`'s narration check is its own recipe, `_narrate-if-voice`.**
  Its test ran the whole `all`, so a project that added steps to `all`
  (koth-paper, cascade) had to patch the test. The test now runs only the
  condition.

Upgrade: copy `tools/export_text.py`, `tools/resolve_typst.py`,
`tests/test_export_text.py` and `tests/hardening.py`; in the justfile, add
`_narrate-if-voice` and call it from `all` in place of the inline voice
check. Delete any local `just review-text || echo` workaround in `paper` and
any local skip in the `all` test.

## 3.25.0

About twenty improvements the papers had each made on their own copy, moved
upstream so the next roll-out deletes local patches instead of merging them.
Every new rule or helper is opt-in or silent on an unchanged manuscript.

- **Prose checks.**
  - `list-in-prose` and `bold-in-prose` are house-style rules. They are off by
    default; turn them on with `enable = [...]` in `prose-check.toml`.
  - New warnings: `cross-reference-order` (a float cited before an earlier
    one) and `unreached-si-section` (an SI section the main text never cites).
- **Bibliography audit.**
  - Generational suffixes are no longer read as surnames.
  - Journal abbreviations are matched against the registered title.
  - Registry quirks are tolerated, and URL-only entries (GitHub, crates.io,
    web) are resolved.
  - A known registrar defect is waived with `[allow] doi-metadata =
    ["key:field"]` in `prose-check.toml`, each with a comment.
- **Export and resolver.**
  - `@fig:x[]` prints the number alone.
  - The source index follows `tbl()` ids into the generated `si/*.typ`.
  - An opt-in `#si-contents` sentence for the Word export.
  - `dfile("id")`, `dfile-short`, `dfile-number` and `dfile-count()` number
    supplementary data files from `paper-data-files` in `config.typ`.
- **Analysis helpers.**
  - `add(minimum=, maximum=)` seeds one-sided guards.
  - `write(keep_hand_ids=)` prunes unlisted hand entries.
  - `record(fig=, min_pt=)` stores print geometry.
  - An `assets.json` lock lets generators run in parallel.
  - `hashcache` skips files changed in the last 2 s.
- **Narration.**
  - It drops standalone code lines (`#counter`, `#context`, `#pagebreak`,
    `#v`, `#place` and the like) across lines.
  - It speaks inline math with no `MATH` entry as words ("T equals 84").
  - It speaks `±`, `×` and subscripts.
  - `MATH_WORDS` and `UNICODE_SPEAK` in `audio/config.py` extend it.
- **Recipes and documents.**
  - `just all` skips narration when the voice model is missing.
  - `just version` counts changes in the manuscript directory only.
  - A multi-document build compiles, counts and scores readability in
    parallel.
  - Its Word file updates page fields on open, and captions keep their lines
    together.

Upgrade: copy every file under `tools/`, `tests/`, `docs/`, `word/`, plus
`justfile`, `wordcount.typ`, `assets.typ`, `analysis/scripts/_assets.py`,
`analysis/scripts/_stats.py` and `audio/extract_prose.py`; merge
customizations by hand. Then delete what is now upstream:
- the paper's own list/bold rules (use `enable = [...]`);
- crossref-order, SI-reach, URL, CASSI, suffix, abbreviation and registry
  patches in `bib_audit.py`/`prose_check.py`;
- a `bib audit =` waiver (move it to `[allow] doi-metadata`);
- local `dfile` code (move the list to `#let paper-data-files = (...)`,
  write `#dfile-count()`);
- local `si-contents` resolver patches (use the block in docs/manuscript.md);
- local math speech (keep only paper terms in `audio/config.py`).

`audio/config.py` belongs to the paper; add the new optional `MATH_WORDS` and
`UNICODE_SPEAK` blocks by hand. Narration changes wherever inline math had no
`MATH` entry, so run `just audiobook-all` afterwards.

## 3.24.3

Audiobook fixes from the spectrl SI narration, plus one edit-check false alarm.

- **The SI audiobook no longer opens by reading code.** The narrator dropped
  only the first line of a directive, so 3.24.2's multi-line
  `#import (...)` and `#let bibliographyx(...) = {...}` in `si-body.typ`
  were narrated for twenty seconds. It now uses `typst_prose.strip_directives`,
  the bracket-following strip the word count already used.
- **Cross-references are spoken, not deleted.** "as seen in @tbl:roles" was
  narrated as "as seen in". The narrator now says "Table S1", numbered by the
  Word export's own count, which `resolve_typst.label_numbers` exposes.
- **`just edit-check` ignores numbers in code directives.** The `0` in the
  SI guard's `bib.references.len() > 0` read as an invented number. A `#let`
  bound to content (`#let paper-abstract = [...]`) is still checked.

Upgrade: copy `audio/extract_prose.py`, `audio/make_audiobook.py`,
`tools/resolve_typst.py`, `tools/typst_prose.py`, `tools/prose_edit_guard.py`,
`tests/narration_cases.py`, `tests/hardening.py`, `docs/slides-and-audio.md`,
and add `"narration_cases"` to `CASE_MODULES` in `tests/run.py`. Then
`just audiobook-all` if you want the audiobooks refreshed.

## 3.24.2

Two fixes from rolling out the SI's own reference list.

- **No empty SI "References".** Alexandria's `bibliographyx` prints its
  heading even when the SI cites nothing, which is why koth-paper and
  uno-lfq-paper backed the switch out. `si-body.typ` now imports
  `get-bibliography`, `load-bibliography` and `render-bibliography` and
  defines a local `bibliographyx` that renders only a non-empty list; the
  call at the foot is unchanged, so every parser still reads it. The resolver
  (and so the SI docx) drops the list when no `@si-` citation exists, unless
  the call says `full: true`.
- **`just edit-check` ignores import paths**, so
  `#import "@preview/alexandria:0.2.0"` is no longer read as a citation
  (`@preview`) and a number (`0.2.0`). A pure `@key` -> `@si-key` rename
  counts as a citation moved between lists, not one lost and one gained.

Bare main-text references ("Figure 3") in an SI on its own reference list
are intended: SI floats are numbered S1, S2, ..., so an unprefixed number
already means the main text, and `just submission` adds no "of the main
text" there.

Upgrade: copy `tools/resolve_typst.py`, `tools/manuscript_sources.py`,
`tools/prose_edit_guard.py`, `tests/bibliography_cases.py`,
`tests/hardening.py` and `docs/manuscript.md`. In `si-body.typ`, replace the
`#import "@preview/alexandria:0.2.0": bibliographyx` line with the template's
import and `#let bibliographyx(...)` block (above the `#bibliographyx` call;
leave the call as it is).

## 3.24.1

`tools/submission.py` used an atomic regex group, `(?>...)`, which Python
added in 3.11; on 3.10, the supported floor, importing it failed. It is now a
lookahead plus backreference with the same matches. Upgrade: copy
`tools/submission.py`.

## 3.24.0

A ledger that carries review findings from one agent to the next, and the
fixes the 3.23.0 roll-out to ten papers turned up.

### Review action ledger

An agent picking up after a review could not tell which findings were already
fixed. `reviews/ACTIONS.md` is now one markdown table of every review finding:
id, severity, status, source, summary, fix, closed. The rules sit in the
file's own header.

- Review skills read it first, skip findings already recorded, reopen one
  that has come back, and append the rest. `review-all` merges into it once,
  at the end, instead of writing a separate ranked list, and keeps its ship
  verdict. `story-review` adds only the items the author accepts.
- Editing skills (`copy-edit`, `fix-verify`, `declare-number`, `new-figure`)
  list the open rows for their task and close the ones they fix with the
  commit hash.
- `just check-actions`, now in `verify`, fails only on a malformed ledger and
  warns while a blocker is open. `--open` lists open rows; `--init` creates
  the file from `tools/actions-template.md`. New papers get one.

Upgrade: copy `tools/check_actions.py`, `tools/actions-template.md` and
`tests/actions_cases.py`; merge the `check-actions` recipe and its `verify`
stage into the justfile and `actions_cases` into `tests/run.py`'s
`CASE_MODULES`; run `just check-actions --init` and seed it from the findings
files already in `reviews/`; run `paper-plugin-update`.

### Fixes

- `fmt` and `fmt-check` skip a `typst_sources` file that does not exist, so a
  project without `cover-letter.typ` no longer fails the format check.
- A scaffold version bump no longer marks declared inputs stale: recorded
  hashes of `pyproject.toml` and `uv.lock` ignore the scaffold's own version
  line.
- `just submission` handles three SI layouts: appended (unchanged); a
  separate `manuscript.toml` target, which becomes the SI PDF with no SI Word
  file; and no SI, which ships the main files only.
- An SI that cites the main reference list, with no bibliography of its own,
  now gets its own local list, numbered 1 to n in SI order, in both split
  files, and a bare "Figure 3" pointing into the main text reads "Figure 3 of
  the main text". The combined `paper.docx` still shows such SI citations as
  raw keys.

Upgrade: copy `tools/submission.py`, `tools/export_docx.py`,
`tools/hashcache.py`, `tools/check_stats.py`, `tools/check_assets.py` and
`analysis/scripts/_provenance.py`, and take the justfile's `fmt` recipes
(papers that dropped `cover-letter.typ` from `typst_sources` can restore it).
`_provenance.py` is imported by the generators, so run `just assets` once
after copying it; values do not change. Drop a local SI splitter.

## 3.23.0

Three things the paper projects kept building for themselves are now upstream.

### Word export

The Word-export fixes that paper projects made locally in
`tools/export_docx.py` and `tools/resolve_typst.py` are now upstream. General
fixes, on for every export:

- Pagination (`export_docx.paginate`): table rows never split, the first row
  repeats, tables of up to 20 rows stay on one page, captions keep their
  lines, table captions and figure images keep with what follows, and bold
  run-in labels and empty lines after headings keep with the next paragraph.
- `#pagebreak()` is a real page break, not a horizontal rule. The SI title
  and the "For Table of Contents Only" section start on a new page, as in the
  PDF.
- The manuscript title uses Word's Title style, not Heading 1.
- `image(..., width: 70%)` is sized against the text width instead of
  pandoc's fixed 420 pt.
- The empty paragraph left by a `<label>` after a heading or float is folded
  into the paragraph before it.
- `docProps/custom.xml` no longer records absolute `.bib` and `.csl` paths.
- `#bibliography(title: "...")` in string form is read.
- `@fig:x[]` gives the bare number and `@fig:x[Panel]` gives "Panel 1".
- The SI is appended only when `paper.typ` includes `si-body.typ`.
- Content after that include is kept.

Opt-in:

- `paper-running-title`, `paper-corresponding-email` and
  `paper-corresponding-phone` in `config.typ` add a running-title line, a
  star on the matching author (`email:` field) and a correspondence line.
- `uv run python tools/export_docx.py --main-only` writes `paper-main.docx`
  without the SI.
- `tools/paper_word_reference.py --black-headings` regenerates the template
  with black title and headings.

Per-table column widths stay project code: set them in the source with `fr`
columns (`columns: (2fr, 1fr, 1fr)`), which reach Word as proportional widths.

This covers local fixes in koth-paper, koth-lfq-paper, uno-paper,
uno-lfq-paper, spectrl-paper, cascade, DeNovoRust and d_noise-paper.

Upgrade: copy `tools/export_docx.py`, `tools/resolve_typst.py` and
`tools/paper_word_reference.py`, then delete each local patch this list now
covers. Keep patches it does not cover, such as fixed column widths,
table font sizes and caption sizes. To get black headings in an existing
template, recolour the styles in Word, or regenerate the template with
`--black-headings` (this discards other template edits). Then run
`just docx` and `just verify`.

### Submission outputs

The journal upload set is upstream. Four papers each built their own split
PDFs, split Word files and standalone graphic, three different ways. Now one
tool, `tools/submission.py`, writes them into `submission/` with a
`manifest.json`. The recipes are `just main-pdf`, `si-pdf`, `main-docx`,
`si-docx`, `toc-graphic`, `cover-letter`, and `just submission` for all of
them. Every split file is cut from the manuscript that `just paper` captured,
never from a second compile. It refuses to build while the source differs from
that capture, so its page, figure and reference numbers always match
`paper.pdf`.

- **PDFs.** They are page ranges of one compile, split at a new `<si-start>`
  probe in `paper.typ`.
- **Word files.** They are split at the SI heading of the Word projection.
- **Graphical abstract.** It follows the profile's new
  `[graphical-abstract] file-format` (TIF for the four ACS profiles, as the
  ACS guideline says). It is flattened onto white, and its resolution is set
  so it fits the journal's box. It fails if that resolution is under
  `min-dpi`.
- **Cover letter.** `cover-letter.typ` is a new, optional template. It reads
  `config.typ` and `#s()`, and takes the journal name from the profile. If the
  file is absent, the step is skipped.
- **Graphic placement.** `journal.toml [placement]` gains `submission`, which
  defaults to `journal`.

Each output is recorded in `.build-state/submission.json`. The set stays
outside `verify`, for the same reason as the audiobooks. `just check` prints a
note, not a failure. `just check-submission` is the strict version, and
`preflight` now builds the set and runs that check. Project-specific packaging
stays downstream: figure QC for one journal, source-data archives and delivery
bundles.

Upgrade: copy `tools/submission.py`, the new justfile recipes and the
`all`/`preflight`/`check`/`clean` changes, `submission/` in `.gitignore`, and
the `file-format` lines in `journals/*.toml`. Add
`#context [#metadata(here().page()) <si-start>]` to `paper.typ` directly after
the `#pagebreak()` that opens the SI. Do this after the journal-layout graphic,
so the main text ends with that page. Copy `cover-letter.typ` only if you want
a letter. If the project has its own main-pdf, si-pdf, main-docx or si-docx
recipes or a tool behind them, delete those. Keep project extras such as
figure QC and source-data packaging, and point them at `submission/`, which is
where the outputs now land, not the root.

### Upgrade planning

`just upgrade-plan [target]` (`tools/upgrade_plan.py`) plans a scaffold
upgrade from inside a derived project. Ten papers made about 105 upgrade
commits in 60 days, most of them copying files the project had never touched,
one release at a time. The plan reads old releases with `git show` from a
local clone, never the network: the "Upgrade:" lines for every release in
(current, target], and a class per scaffold-owned file, where owned means
what `scripts/new-paper.sh` copies minus what CLAUDE.md says the project owns.
Pristine files can be replaced with `--apply-pristine`; customized ones still
get a hand merge, with a three-way summary to size it. `--json` serves agents,
and `--from` overrides a `version` line that is wrong. Upgrade: copy
`tools/upgrade_plan.py` and `tests/upgrade_plan_cases.py`, add
`upgrade_plan_cases` to `CASE_MODULES` in `tests/run.py`, add the
`upgrade-plan` recipe after `version` in the justfile, and replace the "no
upgrade script" sentence in CLAUDE.md's "Paper scaffold" paragraph.

### Documentation

DOCUMENTATION.md grew past 1,100 lines and CLAUDE.md past 3,500 words, and
an agent reads the whole of CLAUDE.md on every session. The long form is now
`docs/`, one page per subsystem indexed by `docs/README.md`; DOCUMENTATION.md
is a stub mapping each former section to its page. MIGRATING.md and
MULTI-DOCUMENT.md moved to `docs/migrating.md` and `docs/multi-document.md`.
Release notes older than 3.20.0 moved to `docs/history-archive.md`, which
`just upgrade-plan` reads alongside HISTORY.md. CLAUDE.md keeps every rule
in about 1,400 words; the reasons behind them moved to
`docs/working-with-ai.md`. `new-paper.sh` copies `docs/` because CLAUDE.md
links into it, but not `docs/migrating.md` or `docs/history-archive.md`:
a new paper is neither migrating nor older than any release. Upgrade: copy
`docs/` without those two files, replace DOCUMENTATION.md with the stub, and
copy `tools/upgrade_plan.py` and `tests/upgrade_plan_cases.py`; optional:
replace CLAUDE.md's generic sections with the trimmed template, keeping
project additions.

## Unreleased

Seven read-only review skills join the four editing skills in
`.claude/skills/`: `claim-audit` walks every quantitative claim to the code
that computes it through `just trace`; `methods-vs-code` compares the methods
section with the analysis parameter by parameter; `figure-review` checks each
figure and table against its caption, citing sentences, and statistics;
`prose-review` flags vague, decorative, or machine-sounding wording and
proposes only replacements the evidence supports; `literature-check`
reads each cited work against the sentence citing it, searches for missing
foundational or competing work, and may only propose a reference it
resolved online in the same pass; `story-review` is the developmental
pass, proposing message, structure, float, and analysis changes ranked by
cost against acceptance with the stated aim of a defensible paper that gets
published rather than a perfect one; `peer-review` convenes a small panel of reviewer personas and an editor, with
loose parameters, and depends on no external review pipeline. Each writes a
dated findings file under `reviews/` and routes every fix to the editing
skill that owns it, so a review never edits the manuscript. `review-all`
runs the fix-list reviews concurrently, the literature check on request
and the story review never, as forked agents, with an optional model per run,
and merges the findings into one ranked list with a ship verdict. The review
skills carry `context: fork` and `model: opus`, so they run as their own
agents on Opus and hand back only the report. Upgrade: copy the eight new directories under
`.claude/skills/`.

CLAUDE.md carries a short "Paper scaffold" paragraph -- what the scaffold owns,
what the project owns, how numbers reach the prose, the build and gate
commands, and how an upgrade is done -- with a `SCAFFOLD_VERSION` placeholder
that `scripts/new-paper.sh` fills with the release the copy came from. Every
derived manuscript on this machine now carries the same paragraph at 3.20.3.
Upgrade: optional; copy the paragraph into CLAUDE.md with the version written
in.

## 3.22.0

`/paper:review-all` now splits the model by the kind of review. The four
checklist reviews (`claim-audit`, `methods-vs-code`, `figure-review`,
`prose-review`) compare the manuscript against a fixed standard and run on
Sonnet; `peer-review` and `literature-check` are judgment calls and stay on
Opus. Opus draws down the plan's rate-limit window several times faster than
Sonnet, and the checklists do not lose findings on Sonnet. "all on opus"
restores the old behaviour for one run. No manuscript-side change. Each repo pins its plugin version, so run
`claude plugin update paper@paper-scaffold --scope project` in each paper
(`paper-plugin-update` on this machine does all of them).

## 3.21.0

Skills moved out of `.claude/skills/` into a Claude Code plugin, `paper`, served
from this repository as the `paper-scaffold` marketplace. Eleven repos carried
byte-identical copies and every skill fix meant twelve files times eleven
commits. Now a paper enables `paper@paper-scaffold` in `.claude/settings.json`
and gets the current skills. Slash names gain the plugin prefix:
`/review-all` is `/paper:review-all`. The review skills also share one
`paper.review.txt` generated once by `/paper:review-all`, instead of each
agent re-reading the Typst sources.

Upgrade: `git rm -r .claude/skills`, add `{"enabledPlugins": {"paper@paper-scaffold": true}}`
to `.claude/settings.json`, `claude plugin marketplace add pgarrett-scripps/paper-scaffold`
once per machine, and repoint `.agents/skills` at `<scaffold>/plugins/paper/skills`.

## 3.20.3

Three fixes the 3.20 roll-out across ten manuscripts found. `just paper`,
`just docx` and `just docx-check` chose the dissertation Word adapter on the
mere presence of `manuscript.toml`, then failed a manifest that names only
PDF targets; they now require `lib/template.typ` as well and otherwise keep
the paper's route. The standalone-directive strip in the Word resolver and
the prose cleaner was line-based, so a `#show` rule typstyle had broken
across lines left its continuation lines behind as prose; it now follows
the brackets to the line that closes the statement. And author names and
affiliations are emitted escaped, so a corresponding-author `*` no longer
opens emphasis and an email address no longer reads as a citation pandoc
fails the export over. Upgrade: copy `tools/typst_prose.py`,
`tools/resolve_typst.py`, `tools/readability.py`, `tests/export_cases.py`,
and the three `manuscript.toml` conditions in the justfile.

## 3.20.2

`tests/slide_cases.py` failed four cases in a manuscript with no `slides/`
directory, which made `just test` and therefore `just verify` fail in exactly
the projects the 3.20.0 note said were unaffected. The three cases that read
the shipped deck now skip when it is absent, as `tests/new_paper_cases.py`
already does for `scripts/new-paper.sh`. Upgrade: copy
`tests/slide_cases.py`.

## 3.20.1

The Word resolver honoured `toc-graphic = none` by emitting a literal `#none`
and the caption. It now treats `none` as no graphic, as `just check-journal`
already did. Upgrade: copy `tools/resolve_typst.py`; only a manuscript that
sets the binding to `none` is affected.

## 3.20.0

Journal profiles. `journals/<name>.toml` carries one venue's limits for one
manuscript type -- word limits and what they exclude, abstract and keyword
caps, figure and table counts, the figure resolution floor, and the graphical
abstract's box -- together with the URL they were read from, the date the
journal printed on its guidelines, and the date they were read. A profile
without that provenance does not load. `journal.toml` selects one and maps the
roles it names (the experimental section JPR leaves out of its count) onto
this manuscript's section paths. Four ship, read from the ACS guidelines
dated 2026-08-27: JPR Article and Technical Note, JASMS Article and Technical
Note.

Nothing is a second checker: the profile's word limits join `just
check-words`, its resolution floor joins `just prose-check` beneath the
project's own `min-figure-dpi`, and `just check-journal` (in `verify`) covers
keywords, main-text float counts, and the graphical abstract measured against
the journal's box. `just journal` prints the whole card with the journal's own
wording; `just journals` lists the profiles. A limit that covers the reference
list (JASMS's Technical Note) selects a `references` region: the main text's
list as citeproc sets it for the Word file, rendered through pandoc and
counted; `just wordcount` shows it as its own row.

The graphical abstract is declared once in `paper.typ` (`toc-graphic`,
`toc-caption`) and placed per output by `journal.toml`'s `[placement]`: under
the abstract for a preprint, on the last page of the main manuscript under
"For Table of Contents Only" for the journal, or nowhere. The PDF defaults to
the preprint layout and the Word file to the journal's, the build passes each
its choice, and a placement change marks both outputs stale. A shipped
generator draws a placeholder at exactly the ACS box (975 x 525 px); a drawn
graphic is adopted with `just adopt` and referenced the same way.

Also fixed on the way: `just prose-check`'s figure resolution check only ever
measured `image("literal")` calls, so a figure placed through `fig("id")` --
every figure in this scaffold -- was never measured, while the generator's
comment said it was. It now resolves ids through `assets.json` and reads
absolute widths (`width: 3.25in`) as well as percentages.

Upgrade: copy `journals/`, `journal.toml`, `tools/journal.py`,
`tests/journal_cases.py`, the `journal*` recipes and the `verify` stage, and
the updated `tools/wordcount.py`, `tools/prose_rules.py`,
`tools/prose_check.py`, `tools/resolve_typst.py`, `tools/manuscript_snapshot.py`
and `tools/build_state.py`. Add the `toc-graphic` block to `paper.typ` (the
scaffold's shows where) or set `toc-graphic = none`. A project with no
`journal.toml` behaves as before, except that its `fig()` figures are now
measured.

The HTML Word route is gone. `just docx-html`, `tools/typst2docx.py`, the
`docx-mode` conditionals in `paper.typ` and the `paper-author-line` binding
they read from `config.typ` are removed; `just docx` through pandoc's Typst
reader is the only export, and has been the default since 3.18. The route
could not carry the SI's own reference list, which was the last reason to keep
it. The PDF renders identically and `paper.docx` is byte-identical. The typst
floor stays at 0.14, now as the oldest version the pandoc route has been run
under.

Upgrade: delete `tools/typst2docx.py`, drop the `docx-html` recipe, and remove
every `docx-mode` branch from `paper.typ`, keeping the `else` content. A
project that still carries `paper-author-line` in `config.typ` may keep or
drop it.

`tests/run.py` is a fixture harness and a registry again. It had grown to 2,271
lines: the golden-file extractor check it documents, plus fourteen unrelated
suites that ran as a side effect of `structural_cases()`, which chained thirteen
of them at its end. A failure in the Word export was reported under "structural
cases", and adding a suite meant editing a function about prose rules. Those
suites are now one case module per subject under `tests/` -- `prose_cases.py`,
`bibliography_cases.py`, `asset_cases.py`, `stats_cases.py`,
`stats_ownership_cases.py`, `resolver_cases.py`, `export_cases.py`,
`adoption_cases.py`, `new_paper_cases.py`, joining the five that already lived
this way -- listed in `CASE_MODULES`, which names whichever one fails. Every
module now also runs on its own (`uv run python tests/stats_cases.py`); three
that could not before, because they read `sys.path` as `run.py` had left it, set
it themselves. No case changed. The split found one real coupling: the adoption
cases imported `_assets` off a path `stats_cases()` happened to add first.

Upgrade: copy `tests/` wholesale. Nothing outside it changed.

Slide decks are part of the pipeline. A deck lives in `slides/`, is built by
name with `just slides <name>`, and reuses the manuscript's own declarations:
`#s("id")` from `stats.json`, `#fig("id")` / `#tbl("id")` from `assets.json`,
and `references.bib`. The talks' own identity -- title, author line,
institution, date, aspect ratio -- is `slides/config.typ`, separate from the
manuscript's `config.typ` because a talk title is usually not the paper title,
and because a `manuscript.toml` project has no root `config.typ` to read.
Touying supplies
the slides (metropolis theme, speaker notes, handout mode, appendix); all of it
is configured in `slides/theme.typ`. `just slides-handout`, `just slides-notes`
(a `.pdfpc` sidecar for presenter tools), `just slides-draft`, `just
slides-list` and `just slides-fmt` round it out.

Decks are outside the gate: `just verify`, `just check` and `just fmt` say
nothing about them, and `just slides-check` answers staleness plus four prose
rules on demand. Two things in `verify` DO change, because the id index now
includes decks: a number or figure used only in a talk is no longer reported as
declared-but-unread, and `just trace <id>` lists the deck among its use sites.
An id a deck references but nothing declares is a warning, not an error -- a
half-written talk must not fail the manuscript's gate.

Upgrade: nothing to do; a project with no `slides/` directory behaves exactly as
before. To adopt, copy `slides/`, `tools/slides.py`, `tests/slide_cases.py` and
the `slides*` recipes, then replace the example deck.

The Supporting Information carries its own reference list, for journals that
take the SI as a separate file. Typst allows one native `#bibliography` per
document, so the SI's is set by Alexandria: `#show: alexandria(prefix: "si-",
read: p => read(p))` in `paper.typ`, `#bibliographyx(..., prefix: "si-")` at
the foot of `si-body.typ`, and every SI citation written `@si-key`. Both lists
number from 1 and each prints only the works its own half cites. The Word
export converts each list with its own citeproc run and joins the trees.
`just prose-check`
reports a bare `@key` in the SI, which compiles and quietly joins the MAIN
list, and prefixes that disagree between the two files.

CI's figure-survival check now counts images embedded in `paper.docx`
against `fig()` call sites, which is exact on the pandoc route because
equations are native Word math.

Upgrade: nothing to do. A manuscript with one bibliography behaves exactly as
before, down to the bytes of its Word export. To adopt the second list, copy
the Alexandria show rule into `paper.typ` and the `#bibliographyx` call into
`si-body.typ` from the scaffold, then prefix the SI's citation keys.

Word generation now carries the dissertation pipeline's reusable reference
styles, full-caption front lists, page-number caching, independent chapter
bibliographies, proportional table columns and OOXML property-order fixes.
`examples/dissertation/` supplies the supported template contract and a small
working example. `just paper` selects the document pipeline when a manifest is
present. Single papers use `word/paper-reference.docx`; custom styles survive
builds and template edits invalidate freshness.

Upgrade: copy the new `tools/document_docx.py`, `tools/word_*.py`,
`tools/paper_word_reference.py`, updated exporter/build-state tools, `word/`, ACS
CSL, tests and justfile recipes together. Existing dissertation templates need
the documented capture contract; arbitrary multi-document layouts are not
silently adapted. Full Word contents pagination also needs LibreOffice and
Poppler. Existing local template edits should be merged rather than replaced.

Optional `word-limits.toml` defines independent word-count checks with section
inclusions, exclusions, and inclusive minimum/maximum bounds. `just wordcount
--sections` lists paths from evaluated Typst content, including nested headings
and includes. Overlaps count once; unknown or ambiguous selections fail.
Standard journal totals and content exemptions are unchanged.

`just check-words` enforces the configured limits inside `verify` and
`preflight`; draft builds report length violations without refusing to build.
The shipped configuration leaves all bounds unset. This applies to the
single-paper workflow; named document part scopes are unchanged.

Upgrade: copy `wordcount.typ`, `wordcount-sections.typ`, `tools/wordcount.py`,
`tools/wordcount.sh`, and the updated build-state tool, tests, and justfile
recipes together. Add `word-limits.toml` to enable checks in an existing paper.

Entries for 3.19.0 and older are in
[docs/history-archive.md](docs/history-archive.md).

---

## Decisions reversed

Each of these was built, shipped, and then undone. They are recorded because all
of them look reasonable in the abstract, and the reasons they failed are only
visible from use.

### Construct coverage in the placeholder prose

The first skeleton put one of every special-cased Typst construct into
`paper.typ`, so `just all` on a fresh clone was a smoke test. Placeholder prose
is deleted the moment real writing starts, so the test ran exactly once and
then the constructs went untested for the life of the project. Coverage now
lives in `tests/fixture.typ`, which is never part of the manuscript.

### A general "-ise to -ize" spelling rule

The regex for the whole `-ise` family flagged the project's own software name,
`dnoise`/`denoise`, on every mention. A checker that cries wolf on the
project's vocabulary gets switched off within a week. The British list is
explicit and grown by hand.

### Spell-checking inline code

`readability.clean` unwraps inline code into a bare word (journals count it),
and spell-checking that output flagged the column name `Ms1.Normalised` as a
British spelling. The spelling pass runs on a code-removed variant instead.

### Commit dates for generated-asset staleness

Comparing commit dates of `figures/` against `analysis/` cannot handle
deterministic generators: re-running after a no-op edit produces nothing to
commit, so the check nagged forever with no way to satisfy it. Content hashes,
no git.

### `figures.map` and an external analysis tree

The analysis was a sibling directory figures were copied out of. The copy was
the whole problem: a re-analysis updated the plot upstream, the copy stayed
put, and the PDF kept rendering a figure that no longer matched its own
caption. The analysis moved inside and writes to the destination.

### `fmt-verify`, and five other recipes

`just --list` reached 30 entries. `fmt-verify` was superseded, compared a
no-op, and restored via `git checkout --`, the most dangerous line in the
repo. The `.m4b` staleness checks went too: every prose edit marked the
audiobooks stale, clearing that cost minutes of narration, and a warning
almost always present and almost never acted on erodes trust in the rest.

### The HTML Word route as a fallback

Word export first went Typst → HTML → pandoc, with a `docx-mode` flag that
bypassed the PDF template and `html.frame()` plus a rasterizer to bring the
equations Typst's HTML export drops back as images. When the pandoc route
arrived it was kept as a fallback "while the new one earns trust". It never
paid its way: it doubled the preamble with conditionals every editor had to
read past, it set the typst floor for a reason no longer relevant, and when the
SI got its own reference list it could not carry it, since the HTML export
drops the grid that list is set in. A fallback that refuses the scaffold's own
manuscript is not a fallback. Removed.

### Re-deriving every value in `just verify` (3.0.0 → 3.2.0)

The strongest possible stats check, run on every verify — affordable only
because the scaffold's own generator reads a four-row CSV. On a real analysis
the gate costs the analysis. The general lesson: the scaffold cannot surface a
cost that scales with project size, so anything whose cost depends on scale
needs a deliberate "what does this look like at 1000×" pass, not a green gate
on the example.

---

## Bugs worth remembering

**A reflow can break the prose extractors.** typstyle breaks long lines inside a
call or an emphasis pair, so `#refn(<sec:x>)`, `_Saccharomyces cerevisiae_`, and
`#link(` all became multi-line forms. Patterns written for the one-line version
then leaked a bare `#refn(` into the word count and the narration, or left
literal underscores for the voice to pronounce. The PDF looked correct
throughout. The recognition patterns now live in `typst_prose.py`, shared by both
extractors, because each of those three fixes otherwise had to be made twice.

**Typst line continuations.** A method chain broken across lines after `#let x =`
or inside `[...]` ends at the first newline, and the continuation is parsed as
literal text. The error points at a closure parameter and reads
`unknown variable: a`. Wrap the chain in a code block.

**matplotlib stamps a creation date into PNG metadata.** Every regeneration then
looks like real drift. Pass `metadata={"Software": None}` and seed any RNG.

**A check can die silently when the thing it counts moves.** The CI
figure-survival check counted `image(` calls; the assets manifest reduced that
count to zero, and a comparison against zero passes forever. A counting check
must also fail when it counts nothing.
