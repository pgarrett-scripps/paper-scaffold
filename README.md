# paper-scaffold

[![CI](https://github.com/pgarrett-scripps/paper-scaffold/actions/workflows/ci.yml/badge.svg)](https://github.com/pgarrett-scripps/paper-scaffold/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Typst 0.14+](https://img.shields.io/badge/Typst-0.14%2B-239dad)

A reusable Typst manuscript directory where every number, figure and table is
**traced to the analysis that produced it** and checked for staleness: your
scripts write them, the prose references them by id, and a typed or drifted
value fails a check instead of shipping. Around that: PDF and Word export,
word counts, readability and style checks, and offline audiobook narration.

New paper: quick start below. Existing manuscript: [MIGRATING.md](MIGRATING.md).

## Quick start

```bash
git clone https://github.com/pgarrett-scripps/paper-scaffold
cd paper-scaffold
just doctor                          # is the toolchain present and new enough?

./scripts/new-paper.sh ~/papers/my-paper
```

The script asks for the title, author, and the rest of the identity, copies the
working files, fills in `config.typ`, builds the first PDF, and starts a git
history that belongs to the new paper. Every field also has a flag, so a
scripted run needs no terminal:

```bash
./scripts/new-paper.sh --yes --title "My Paper" --author "Ada Lovelace" ~/papers/mine
./scripts/new-paper.sh --help
```

**Do not start a paper with `cp -r`.** It copies `.git` too, so `just version`
reports the *scaffold's* last commit as the manuscript's state — confidently, and
wrongly. It also drags along `.build-stamp`, which then claims the new paper's
outputs were built from sources it has never seen.

Then, in the new directory:

1. Replace the abstract in `config.typ`. Title, authors and keywords are already
   filled in; the abstract is prose and is left for you.
2. Replace the placeholder prose in `paper.typ` and `si-body.typ`.
3. Replace `references.bib`.
4. Put your analysis in `analysis/`, keeping `just assets` as its front door. Or
   delete `analysis/` entirely if the paper has no generated assets.

Nothing else should need editing. `just verify` is the gate that says whether the
directory is in a shippable state.

Three parts are optional. `analysis/` (no generated assets) and `audio/` (no
narration) can simply be deleted: every recipe and check adapts rather than
failing. The generated-numbers mechanism (`stats.typ` + `stats.json` +
`analysis/scripts/gen_stats.py`) and the generated-asset one (`assets.typ` +
`assets.json`) also come out, but not by deleting alone —
Typst cannot conditionally import a file that is not there, so three `.typ` files
have to drop their import. The exact edits are under
[Numbers in prose](#numbers-in-prose-sid-not-a-typed-numeral).

## What to run

| Command | Does |
|---|---|
| `just verify` | **The gate.** Formatting, extractors, prose rules and staleness, in one pass |
| `just preflight` | **The submission gate.** Fresh builds + `verify` + deep stats + DOI audit |
| `just doctor` | Are the external tools installed and new enough? |
| `just paper` | Compile `paper.pdf`, then print word counts and readability |
| `just draft` | Compile `paper-draft.pdf` with unresolved `#s()` numbers shown as `?id?` |
| `just watch` | Live preview, recompiling on save |
| `just fmt` | Reflow the hand-written Typst sources (typstyle, 80 cols) |
| `just docx` | Export `paper.docx` for journals and co-authors |
| `just wordcount` | Journal-style counts without rebuilding |
| `just readability` | Flesch-Kincaid / reading ease / fog without rebuilding |
| `just assets` | Regenerate every generated figure, table and prose number (delegates to `analysis/`) |
| `just check` | Report every artifact that has fallen behind its source |
| `just pin` | Record hashes for the files listed under `pinned` in `stats.json` |
| `just text-baseline` / `text-diff` | Snapshot the PDF's words; word-level diff after a structural refactor |
| `just edit-baseline` / `edit-check` | Prove a copy-edit pass changed only wording: numbers, refs, floats, headings survive |
| `just test` | Assert the prose extractors handle every construct, before and after a reflow |
| `just prose-check` | Check the prose, plus figure resolution and table shape, against STYLE.md |
| `just prose-check --list-rules` | Every rule, its severity, and how to configure it |
| `just bib-audit` | Check every DOI against Crossref for retractions and dead links (network) |
| `just viz` | Diagnostics about the draft -> `viz/`: nine plots plus `report.json` for tools |
| `just density` | Numerals, parentheticals, acronyms, passives per 1,000 words, and section outliers |
| `just setup` | Build the Python environment (uv, locked) |
| `just version` | Which scaffold version this manuscript is built on |
| `just audio-setup` | One-time: install the audio deps and download the voice model |
| `just audiobook` | Chaptered `.m4b` of the main text |
| `just all` | PDF + Word + both audiobooks, then `just check` |

## Working with an AI

CLAUDE.md is the standing brief for any agent editing the manuscript, and the
gates are what make delegation safe: `edit-check` makes an invented numeral
fatal, `#lit()`/`#s()` make numbers tamper-evident, `verify` makes "done"
machine-checkable. On top of that, four packaged workflows ship as skills in
`.claude/skills/` and travel with `new-paper.sh` into every derived paper:

| Skill | Does |
|---|---|
| `/copy-edit` | Wording-only pass (grammar, tighten, de-hedge), bracketed by `edit-baseline`/`edit-check` |
| `/fix-verify` | Clear a failing gate with the intended fix per finding class — never by weakening a check |
| `/declare-number` | Route a typed numeral through the four tiers, prove nothing rendered differently |
| `/new-figure` | Generator, `record()`, id reference, wordcount scope — all four steps, proven by the gate |

Each ends by running the check that proves it behaved, so an agent cannot
report success without the pipeline agreeing.

## The ideas

```
A number worth stating is worth tracing.
Declared and read back beats typed and remembered.
A copy is the thing that goes stale.
A manifest nothing reads is already wrong.
The value is the analysis's; how it reads is the author's.
What cannot be discovered must be declared,
    and an honest partial answer beats one that looks total.
A check that never fails is not a check.
The gate you run constantly must cost nothing;
    the gate that costs something must be one command.
A ritual with conditions is a ritual skipped.
A warning with an expensive fix is a warning ignored.
Silence is not success -- fail where the mistake was made.
Hashes, not dates; content, not history.
"It changed" means it changed, not that the script ran.
Every guarantee was proven by breaking it first.
```

Each line is a decision this repository actually made, usually after the
opposite failed; HISTORY.md records which failure produced which line. The
rest of this README is the long form — skim the section heads and read the
ones you are about to touch.

## Layout

```
paper.typ  config.typ  si-body.typ    the manuscript
stats.typ  assets.typ  wordcount.typ  Typst helpers it imports
stats.json  assets.json               what the analysis declared: numbers, figures
references.bib                        the bibliography
justfile  pyproject.toml              how to build it, and what with
prose-check.toml                      this project's prose exceptions

tools/       the Python and shell toolchain. Nothing here is imported by the
             manuscript; every one of them READS it. Run through `just`.
analysis/    your analysis. Writes into figures/ and si/. Own environment.
figures/ si/ generated, and tracked, so a fresh clone compiles
audio/       narration. Optional, deletable.
tests/       the extractor fixture and its golden files
scripts/     new-paper.sh, which makes a manuscript out of this directory
```

The root holds what a person edits and what a build produces. Everything that
processes the manuscript lives in `tools/`, and each of those resolves paths
against the repository root (`.parent.parent`, since they sit one level down),
so they still run from anywhere via `just`.

## The parts worth understanding

### `config.typ` is the only place the paper's identity lives

Title, authors, affiliations, abstract, keywords, date, institution, and
bibliography style. The PDF template reads it, the Word front matter is derived
from it (including the numbered affiliation superscripts, so they cannot drift),
the word counter counts the abstract out of it, and `audio/config.py` parses the
title out of it so the narration can never announce a title the paper no longer
has.

### The BODY START / BODY END markers

`paper.typ` carries two marker comments:

```typst
// >>> BODY START
= Introduction
...
// <<< BODY END
```

Three tools slice the prose out at those markers, because "what counts as the
paper's prose" is not the whole file: the front matter, the back matter, the
acknowledgments, and the bibliography all have to be excluded from a journal word
count, a reading-level score, and a narration. Each tool fails loudly if the
markers go missing rather than guessing. Do not delete them.

### The `si/` contract: generated tables, never hand-typed numbers

Tables whose numbers come from an analysis are written by a script into
`si/*.typ` as a bare `#table(...)`, and `si-body.typ` wraps them in a `#figure`
that supplies the caption and label. Every generated file opens with a
"do not edit by hand" header.

`analysis/scripts/gen_example_table.py` is the template. Copy it per table.
`just assets` runs every `gen_*_table.py`, so the *discovery* needs no wiring
beyond matching the filename pattern.

**It does need wiring beyond that, and it is worth knowing before you start.**
Adding a figure or table is four steps, not one:

1. Copy the example generator, keep the `gen_*_figure.py` / `gen_*_table.py`
   name, and write into `figures/` or `si/`.
2. Call `record("fig.yourname", …, kind="figure", inputs=[…])` at the end of it.
   That declares the id; `inputs` is the data it read.
3. Reference it in the prose by id, not by filename:
   `#figure(fig("fig.yourname"), caption: [...]) <fig:yourname>`.
4. If this is the project's first one, add `fig`/`tbl` to `wordcount.typ`'s eval
   scope. Missing this leaves `just paper` working and only `just wordcount`
   failing, which is the least obvious way for it to break.

Step 2 is what buys the per-file staleness checking, and step 3 is what stops the
manifest rotting into a ledger nobody reads. Neither is free, and the trade is
deliberate.

The point is that a number in the manuscript should be traceable to the analysis
that produced it. Re-run the analysis and the manuscript updates.

### Numbers in prose: `#s("id")`, not a typed numeral

A table tracks the analysis because a script writes it. A number in a *sentence*
is typed by hand, and that is where drift lives: a unit error, a percentage
stale after a re-run, a value fixed in the table but not in the paragraph beside
it.

`analysis/scripts/gen_stats.py` declares the numbers the prose states and writes
them into `stats.json`. The manuscript reads them back:

```typst
the treated group scored #s("effect.treated_over_control") over control
```

Three things make it hold:

- **An unknown id fails the build.** `#s(...)` panics at compile time, so a
  number that stops existing is loud rather than blank. `tools/readability.py` and the
  narrator resolve the same call, because they read the source, not the PDF.
- **Guards run when the file is generated.** Each entry's `expect` block can
  assert a sign or a plausibility band. If a sentence says "fell" and a re-run
  turns the value positive, `just assets` fails and names the assumption,
  instead of the paper shipping "fell by -3.1%". A band catches the unit error.
  The fresh value is judged against the guard *as it stands in `stats.json`* —
  the author's — not against whatever the script happened to pass.
- **`just prose-check` flags a typed numeral** — one that matches a declared
  value (use `#s()` instead), and one that matches *nothing* declared, which is
  worse: mistyped, stale from an earlier draft, or from a source nobody
  recorded. Four ways out, each leaving a trail: compute it (`#s()`), declare
  it by hand with a note, vouch for it in place with `#lit("40")` when it is
  genuinely just prose, or suppress the value in `prose-check.toml` with a
  written reason. `lit()` deliberately does not silence the first rule — a
  computed value wrapped in it is still flagged. Years and short counts are
  skipped, and prose-check reports how many literals are vouched inline, so
  the count cannot grow silently.
- **`just check-stats` re-checks the committed file, without running anything.**
  Every guard is re-run against the values as they sit in `stats.json`; each
  generated value is compared to the checksum its generator recorded, so a
  hand-edit is caught; and the `sources` block hashes the code and data behind
  the numbers, so "the analysis moved" is answered in milliseconds. The guards
  above only fire while the generator runs, which does nothing for a value edited
  afterwards.
- **`just check-stats-deep` re-runs the generator and diffs.** Stronger — it
  recomputes from the data rather than comparing fingerprints — and it costs
  whatever your analysis costs, so it is deliberately not part of `just verify`.
  `verify` must rebuild nothing; run this before submitting.

### stats.json is yours, not just the analysis's

The split is by field, and it follows what each field *is*. The script owns the
`value` — a fact about the data, which nobody else can honestly write — plus
the `checksum` that catches a hand-edit to it and the `origin` that says who
wrote it and when it last changed. Everything else in an entry is the author's,
edited in `stats.json` directly:

- `fmt` and `unit` — how the number is shown. An editorial choice, not an
  analysis result.
- `desc` — what the number is, for whoever audits the file later.
- `expect` — what the *prose* assumes ("fell", "roughly 80–90%"). That
  assumption lives next to the sentence, so the author maintains it. A
  one-sided bound (`min` with no `max`) is fine.

The arguments to `st.add(...)` beyond the value are seeds: they fill in a new
entry so the file is never born empty, and are ignored once the entry exists —
with a note when they differ from the file, so a stale script argument is
visible rather than silently dead.

Every entry also records `origin.by`: the script that generated it, or
`"hand"`. A generator rewrites only its own entries, so a number you add by
hand survives `just assets` instead of being silently overwritten by it.
`origin.at` is when the value last *changed* — a re-run that reproduces the
same number leaves it alone, so the date means something.

```json
"cohort.sites": {
  "value": 4, "fmt": "",
  "expect": {"sign": "+"},
  "origin": {"by": "hand", "note": "study protocol v3, Table 1"}
}
```

A hand entry must carry `origin.note` saying where the number came from, and it
is guarded exactly as tightly as a derived one. What it cannot get is
re-derivation: `check-stats-deep` recomputes generated values from the data and
compares, and nothing can do that for a number that came off a printout. The
note is the audit trail instead.

That is also why `stats.json` sits at the manuscript root rather than under
`si/`: a file you are invited to edit is not generated output, and cannot be
guarded by "did anything change".

### Pinned files: watching what no script reads

Provenance the pipeline records automatically stops at what a generator
imported or declared. Plenty of files matter without any script reading them —
a raw instrument export, a protocol document, an upstream config. Declare those
by hand in `stats.json`:

```json
"pinned": {
  "analysis/data/raw_export_2026-06.csv": null
}
```

`just pin` records the sha256, and from then on `just check-stats` (so `just
verify`) reports when the file changes. The fix it names is deliberate: check
the numbers that depend on it, then `just pin` again to accept the new state.
Generators carry the block through untouched — declaring what is worth watching
is the author's call, made in the file.

**`stats.json` stores no rendered string.** It holds the `value` and the `fmt`;
`tools/render_stats.py` turns them into `stats-rendered.json`, which is what
`stats.typ` reads. Every recipe that compiles regenerates it first, and it is
gitignored, so it can never be stale and never disagrees with its source.

That step exists because Typst has no format spec — no thousands separator, no
`+.2f` — and its `str()` rounds floats where Python's does not
(`1.0899999999999999` is `1.09` there, the full expansion here). Doing the
formatting in the document would mean reimplementing Python's spec in a language
that cannot express it, and storing the result beside the value would put a
derived field in a source file, free to drift.

One formatter, `typst_prose.display_of`, is used by the renderer *and* by the
word count and the narrator, so the PDF and the extractors cannot disagree about
what a number looks like.

While ids are still in flux, `just draft` renders an unresolved one as a loud
`?id?` placeholder instead of stopping the compile, and writes `paper-draft.pdf`
so a placeholder can never reach the real PDF. `n("id")` fails even there: no
placeholder can stand in for a number inside an expression without making the
arithmetic that reads it silently wrong.

Available in the SI as well as the main text. `si-body.typ` imports the helpers
itself rather than inheriting them, because Typst's `include` gives the included
file its own scope: without that import an `#s("id")` in the SI fails with
`unknown variable: s` even though `paper.typ` imports it one line above the
include. The SI is the data-heavy half, so it is where generated numbers belong
most.

To drop the mechanism from a project that states no computed numbers, four steps.
Typst has no conditional import and no way to ask whether a file exists, so the
references have to come out by hand; each one is commented to say so.

```bash
rm stats.typ stats.json analysis/scripts/gen_stats.py
```

1. Delete the `#import "stats.typ": n, s` line from **`paper.typ`,
   `si-body.typ` and `wordcount.typ`**. All three carry it.
2. In `wordcount.typ`, also drop the helpers from the eval scope:
   `scope: (refn: refn, s: s, n: n, fig: asset-fig, tbl: asset-tbl)` becomes
   `scope: (refn: refn, fig: asset-fig, tbl: asset-tbl)`. The import alone is not
   enough — this line names them again, and missing it is the one that bites,
   because `just paper` still works and only `just wordcount` fails.
3. Remove any `#s()` / `#n()` calls left in the prose.

The generated-**assets** mechanism comes out the same way and separately:

```bash
rm assets.typ assets.json
```

Delete the `#import "assets.typ": fig, tbl` line from `paper.typ` and
`si-body.typ`, drop `fig: asset-fig, tbl: asset-tbl` (and the import above it)
from `wordcount.typ`, remove the `record(...)` calls from the generators in
`analysis/scripts/`, and go back to naming files directly:
`#figure(image("figures/x.png"), ...)`.

Verified by doing exactly this to a copy and confirming `just paper`,
`just wordcount`, `just readability` and the narration all still work.

### Figures and tables by id: `fig("fig.x")`, not a filename

The same contract as numbers, for files. Each generator calls `record(...)` to
declare what it wrote, into `assets.json`:

```json
"fig.example": {
  "path": "figures/example_figure.png",
  "kind": "figure",
  "hash": "sha256:b100e70d…",
  "origin": {"by": "analysis/scripts/gen_example_figure.py",
             "at": "2026-08-06T18:20:00Z"},
  "inputs": {
    "analysis/scripts/gen_example_figure.py": "sha256:1b2fcdf2…",
    "analysis/scripts/example_data.csv":      "sha256:c19c8377…"
  }
}
```

and the manuscript references the id rather than the path:

```typst
#figure(fig("fig.example", width: 70%), caption: [...]) <fig:example>
```

**Referencing by id is what makes the manifest worth having.** A manifest that
merely sits beside the files it describes rots, because nothing reads it. This
one is on the path the compile takes, so an undeclared id stops the build the
same way an undeclared `#s("id")` does — it cannot quietly stop being true.
`just prose-check` reports naming a declared asset directly as an error, which is
what keeps the bypass closed.

`just check-assets` then checks per entry: the output still hashes to
what was recorded (so a hand-edit to a generated file is caught and *attributed*),
the generator still exists, and the declared inputs are unchanged. `origin.at`
is when the output last *changed*: a regeneration that produces byte-identical
output (seeded RNG, no embedded timestamps) keeps the old date, so the
timestamp carries information.

Inputs are part automatic, part declared. The generator and every module it
imports from `analysis/` are recorded by walking `sys.modules`, which is exact
because imports are always Python-level. **Data files are declared by hand**
(`inputs=[...]`), because the automatic version is not exact: an audit hook on
`open` cannot see reads that HDF5, parquet and most binary readers do from C, and
would record an empty input set for precisely the formats that matter. A missed
input means a stale figure reported as current, so that half stays explicit.

An input that is not present — the normal state of a fresh clone, since
`analysis/data/` is untracked — is reported as unverified, never as stale.

This replaced `.assets-stamp`, a pair of whole-tree hashes that fired on the same
failures and could only report "analysis/ has changed" without naming the figure
it ruined — and that also fired on a new file no generator imports, a change
which by definition altered no output.

What went with it: **an input a generator reads without declaring or importing is
now invisible.** Nothing checks it — and nothing meaningfully did before. The
stamp excluded `analysis/data/`, so whether it caught an undeclared read depended
on where the file sat, not on whether it mattered.

There is no automatic answer that is actually right: an audit hook cannot see
C-level reads, a directory hash misses anything outside it and fires on changes
that altered nothing. So the scaffold no longer pretends to have one. **Which
files are worth tracking is the author's call**, declared in `inputs=[...]`, and
`record()` prints a note when a generator declares none — the omission is visible
where it is made rather than discovered from a wrong figure.

### `analysis/` lives inside the manuscript, and writes to it directly

The analysis that produces the numbers is a subdirectory, not a sibling
repository. It writes its figures into `figures/` and its tables into `si/` with
no staging copy in between.

That last part is the point. A copy is the single most reliable way for a
manuscript to go quietly wrong: a re-analysis updates the plot upstream, the copy
in `figures/` is untouched, and the PDF keeps rendering a figure that no longer
matches the numbers in its own caption. Writing to the destination removes the
failure rather than adding a guard for it.

**The location is load-bearing, not a taste.** The provenance machinery
resolves the manuscript root as `analysis/scripts/../..`, and the
`sys.modules` walk keeps exactly the modules whose paths start with
`analysis/`. An analysis kept as a sibling repository means forking those
tools, not just re-pointing a path — if you are migrating an existing paper,
moving the analysis under the manuscript is what lets the scaffold work
unmodified. (And if the repository publishes a package or crate, check its
include/exclude list afterwards: a newly nested analysis tree can quietly ship
to a registry.)

**The contract is one recipe.** `analysis/justfile` exposes `assets`, which
regenerates everything the manuscript includes. `just assets` at the top level
delegates to it and knows nothing else. Whatever is inside `analysis/` is that
project's business: sixty numbered scripts, one notebook, a Snakemake pipeline.
Keep `assets` as the front door and the manuscript never has to care.

A paper with no computed results simply has no `analysis/` directory, and the
recipes say so instead of failing.

`figures/` and `si/` are generated but **tracked**, so a fresh clone compiles
without re-running an analysis that may take hours. (`paper.pdf` is not tracked —
see below.) `just check-assets` guards them per file through `assets.json`: each
entry records a hash of the output and of every input its generator declared, so
editing a generator and forgetting to re-run it is reported — with the figure and
the script named.

Hashes rather than commit dates, because the generators are deterministic on
purpose. Re-running one after an edit that does not move the output produces no
new commit, and a date-based check would then nag with no way to satisfy it.

### `just check` reports staleness; `just preflight` gates a submission

`just check` exits non-zero if anything is stale, and covers the failure modes
that actually happen:

- `paper.pdf` or `paper.docx` built from sources that have since changed. `just
  paper` and `just docx` record the hash of what they rendered in `.build-stamp`;
  `just check-build` recompares it. The source hash is captured *before* the
  compile, so an edit saved mid-build errs toward stale rather than current.
- An output that is **not the file that build produced** — overwritten,
  truncated, or restored from somewhere else. The stamp records the output's own
  hash too; without it, a `paper.pdf` copied in from Downloads passes as
  current, because the source stamp only proves a build happened.
- `figures/` and `si/` older than the `analysis/` code that generates them.

`just preflight` is the day-of-submission command: fresh builds of both
outputs, the whole `verify` gate, `check-stats-deep` (re-derives every
generated number from the analysis and diffs), and `bib-audit` (every DOI
against Crossref for retractions and dead links). Those last two are too slow
and too network-bound for `verify`, and "run them before submitting" scattered
across the docs is a ritual — this is the ritual as one command.

**Neither output is tracked in git**, and neither is `.build-stamp`. Git keeps
every version of a binary forever, a clone pays for all of them, and removing one
means rewriting history. Ship the PDF as a release asset or a CI artifact.

That is also why staleness is a content hash rather than a commit date: nothing
here reads git history any more, so the checks work in an exported tree, a shallow
clone, or no repository at all. `.build-stamp` stays untracked because it
describes *local* build output — tracking it would let a rebuild on one machine
report every other checkout stale.

The audiobooks are deliberately not checked. Every prose edit would mark them
stale and clearing that costs minutes of narration, so the warning was almost
always present and almost never acted on.

### The Word export is more delicate than it looks

`just docx` goes Typst → HTML → pandoc, and three things make it work:

1. `--input docx=true` bypasses the arkheion template, whose front matter and
   heading styling are layout-only primitives that Typst's HTML export silently
   discards. Without the bypass you lose every section heading and the abstract.
2. `paper.typ` wraps equations in `html.frame()` under that same flag, because
   HTML export drops math outright. `tools/typst2docx.py` rasterizes them back inline
   and stitches the paragraphs Typst split around them.
3. pandoc comes from `uv` (`pypandoc-binary`), so no system install is needed.

Typst's HTML export prints "ignored during HTML export" warnings for layout-only
constructs. Those are expected. The PDF path is entirely unaffected by the flag.

### Formatting: the editor and the CLI must agree

`just fmt` runs [typstyle](https://github.com/Enter-tainer/typstyle), which is the
same engine the [tinymist](https://marketplace.visualstudio.com/items?itemName=myriad-dreamin.tinymist)
editor extension uses as its formatter backend. So format-on-save and `just fmt`
can produce byte-identical output, but only if they are configured identically,
and by default they are not:

| | tinymist default | `just fmt` |
|---|---|---|
| Line width | 120 | `fmt_width` (80) |
| Prose wrapping | off | on (`--wrap-text`) |

Left alone, every save reflows the manuscript one way and every `just fmt`
reflows it back, producing a churning diff that neither tool owns. The committed
`.vscode/settings.json` pins `tinymist.formatterPrintWidth` and
`tinymist.formatterProseWrap` to match the justfile. If you change `fmt_width`,
change both.

`--wrap-text` is the flag that matters for a manuscript: without it typstyle
formats code and leaves markup lines however long they already were, and in a
paper the long lines are the prose.

| Command | Does |
|---|---|
| `just fmt` | Reflow the hand-written sources in place |
| `just fmt-check` | Exit non-zero if reformatting is needed (CI / pre-commit gate) |

`typst_sources` deliberately excludes `si/*.typ`, which the generator scripts own
and would rewrite unformatted on the next run. `.vscode/settings.json` marks them
read-only in the editor for the same reason.

**Reformatting can break the prose extractors.** typstyle will break a long line
*inside* a function call or an emphasis pair, turning `#refn(<sec:methods>)` and
`_Saccharomyces cerevisiae_` into three-line forms. Any stripper regex written for
the one-line version then leaks a bare `#refn(` into the word count and the
narration, or leaves the literal underscores for the voice to pronounce. Both
happened in the manuscript this scaffold came from, and the PDF looked fine
throughout.

`tests/fixture.typ` carries a case for each, and `just test` asserts the extracted
prose is unchanged by a reflow. Add a case there when you add a construct.

The recognition patterns those checks protect (`#refn(`, `#link(`, emphasis, and
the balanced-paren stripper) live in `tools/typst_prose.py`, imported by both
`tools/readability.py` and `audio/extract_prose.py`. They are shared because keeping
them in two files meant fixing each of those three bugs twice.

### Reading the prose metrics

Three commands look at the writing rather than the build.

`just readability` is Flesch-Kincaid and friends. Useful, but it only knows word
length and sentence length.

`just density` counts what FK is blind to and what actually makes a Results
section unreadable: numerals, parentheticals (and what fraction of the words sit
inside them), acronyms, nominalizations, passives, and hedges, all per 1,000
words. **Read it relatively, not absolutely.** There is no published limit for any
of these and anyone quoting one is guessing, so the second table flags sections
that depart from *this paper's own median* by 1.6x. A Methods section running at
three times your own parenthetical rate is a real signal you can act on.

`just prose-check` enforces the mechanical rules in STYLE.md and adds two
structural checks. Anything this project has earned an exception to goes in
`prose-check.toml` (see below). A figure or table that no text ever references is an error,
since most journals require every one to be cited and a reader who is never sent
to a figure will not look at it. Two more are warnings: figures cited out of
numerical order (a copy-editing return at many journals, but a conventions
paragraph legitimately forward-references, so it does not gate), and an acronym
used repeatedly but never expanded (what counts as common knowledge is
field-specific).

### Suppressing a finding: `prose-check.toml`

Every finding carries a stable rule id and, where the rule is about a particular
value, the value that triggered it. A project silences one by naming both:

```toml
disable = ["semicolon-count"]        # a whole rule, off

[allow]                              # or just these values
unexpanded-acronym = ["TOF", "DIA-NN"]
british-spelling   = ["Grey"]        # a surname, not a colour
reference-order    = ["fig:si-lowab-retention"]

[limits]
max-sentence-words = 40
```

Three things keep it from becoming a place problems go to hide:

- **Every finding prints its own silencer**, once per rule, so the file is
  discoverable without reading the docs.
- **Suppressions are counted, never silent.** The footer says how many are
  hidden, and `--show-suppressed` lists them.
- **A typo is an error.** `acronym` instead of `unexpanded-acronym` fails with the
  list of valid rules rather than quietly suppressing nothing.

`just prose-check --list-rules` prints every rule, its severity, and what a
suppression matches on. Errors are suppressible too, since a surname or a figure
cited only from elsewhere is a real exception.

### `tests/` is the permanent smoke test

`tests/fixture.typ` is a deliberately dense pile of every construct any extractor
special-cases: citations, both reference forms, emphasis across a line break,
things that only look like markup (`smooth_*`, `"K*,R*"`, `analysis.tdf_bin`),
links, inline and display math, symbol tokens, block code, and figure captions.

`just test` checks three properties: the extracted prose matches
`tests/expected/`, a typstyle reflow changes neither output, and no forbidden
token (a leaked caption, citation key, or call name) appears in the result. `just
test-update` rewrites the golden files, which is also how a regression gets
blessed into the baseline by accident, so read the diff.

This is separate from the manuscript on purpose. Anything relying on placeholder
prose for coverage would be tested once, at clone time, and never again.

### Audio

Offline Piper TTS. `audio/extract_prose.py` rewrites the Typst source into
speakable text (citations, cross-references, math, `#sym.*` tokens, figure blocks
and code blocks all removed or verbalized), Piper narrates it, and ffmpeg muxes
chapters and cover art into an `.m4b` with one chapter per section.

Everything project-specific is in `audio/config.py`: the voice, the metadata
blurbs, a `PRONUNCIATION` map for words the voice mangles, and a `MATH` map from
inline equations to spoken English. Add every inline equation that appears in
running prose; anything unmapped falls back to reading the raw Typst, which is
usually wrong. Display equations are dropped rather than read.

One inherent trait: stripped cross-references leave sentences like "resolves to
and the bare-number kind" in the narration. Write around it in prose you care
about hearing, or accept it.

The engine is `piper-tts`, a uv dependency in the `audio` group, exactly like
pandoc and ffmpeg elsewhere in this directory: nothing is installed system-wide
and there is no binary to download by hand. **This runs on Linux, both Intel and
Apple Silicon Macs, and Windows.** It previously fetched a piper release tarball
by curl, pinned to a build that shipped x86_64 Linux only, which made the
audiobooks the one part of the scaffold that could not run on a Mac.

The voice model (~60 MB) and every generated audio file are gitignored, so a
fresh clone needs `just audio-setup` once. Change `VOICE_NAME` in
`audio/config.py` and re-run it to switch voices; the name is resolved against
piper's own index, so nothing else has to be kept in step with it.

## Requirements

Run `just doctor` and it will tell you which of these you are missing, and
whether the ones you have are new enough.

- `typst` **0.14 or newer**, `just`, `uv`, `python3`
- `typstyle` for `just fmt` and `just fmt-check` (`cargo install typstyle`)
- `git` is **not** required by any check; the staleness checks are content hashes
- a network connection for `just audio-setup` (the voice model) and the first
  PDF build (the `arkheion` template)

The Typst floor is 0.14, and it is not where you would guess. `--features html`
and `html.frame()`, which `just docx` is built on, both arrived in 0.13 — but on
0.13 the Word export runs, exits 0, and silently contains **no figures**: that
version's HTML export emits no `<img>` for an `image()` call, while tables and
rasterized math survive. The result is a .docx that looks finished and has lost
every plot. 0.14 emits them. All three of 0.13.1, 0.14.2 and 0.15.1 were run
through `just docx` to establish this, and CI holds the floor with a matrix.

`just setup` builds the Python environment from `pyproject.toml` and commits the
resolution to `uv.lock`, so every machine gets the same versions. There are two
environments on purpose: the manuscript toolchain at the root (pandoc, cairosvg,
textstat, small and stable, locked and shipped with the scaffold) and the
analysis in `analysis/pyproject.toml` (whatever the science needs, rewritten per
project). Keeping them apart means a project's churning analysis dependencies do
not invalidate the toolchain lock. The audiobook extras are a `--group audio` so a
clone that never builds audio stays light.

The first PDF build fetches the `arkheion` template from Typst Universe and
caches it.

## Things that will bite you

**Typst line continuations.** A method chain broken across lines after `#let x =`
or inside `[...]` ends at the first newline, and the continuation is read as
literal text. The error is confusing (`unknown variable: a` pointing at a closure
parameter). Wrap multi-line chains in a code block `{ ... }`. `config.typ` has a
worked example.

**Regenerated figures churning bytes.** matplotlib stamps a creation date into
PNG metadata by default, which makes every regeneration look like real drift to
`just check`. The bundled generator passes `metadata={"Software": None}`; do the
same in yours, and seed any RNG.

**The SI is not compiled on its own.** `si-body.typ` is body-only. Its title page,
S-prefixed numbering, and counter resets are applied by `paper.typ` at the include
site, so the whole manuscript is one compilation with one label namespace and
cross-references resolve in both directions.

## Versioning

The scaffold version lives in `pyproject.toml` and is copied into every project
built from it, so `just version` answers "what am I on" from inside a derived
manuscript. [HISTORY.md](HISTORY.md) records what each release contains, what
bumps major/minor/patch, and how to pull a later version's changes into an
existing project.

Read HISTORY.md's "Decisions reversed" section before changing something that
looks obviously improvable. Several obvious improvements were tried here and were
wrong for reasons only visible from use.

## Notes for agents

The working rules for editing a manuscript built on this scaffold are in
[CLAUDE.md](CLAUDE.md): what never to hand-edit, what to run before calling the
work done, and the Typst and Python conventions.

`AGENTS.md` is a **symlink** to that same file, so tools following either
convention read one document. It is a symlink rather than a copy on purpose: two
files of instructions drift, and the one that drifts is always the one the agent
happened to read. Preserve it as a symlink if you move the directory around by
hand (`scripts/new-paper.sh` uses `tar` rather than `cp -r` for exactly this
reason).

## Provenance

Extracted from the `dnoise` manuscript pipeline. The design decisions encoded
here (commit-date PDF checking, byte-compared figure copies, generated SI tables,
the docx-mode template bypass) each came from a specific way that manuscript went
wrong.

## License

MIT, see [LICENSE](LICENSE). It covers the scaffold and its tooling, not any
manuscript you write with it. `scripts/new-paper.sh` carries the notice into a
new project as `LICENSE.scaffold`, renamed so that a `LICENSE` at the root of a
manuscript directory does not read as a claim about the paper, which is a
different question and yours to answer.
