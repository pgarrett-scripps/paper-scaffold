# paper-scaffold

A reusable Typst manuscript directory: PDF, Word export, journal word counts,
readability metrics, auto-generated Supporting Information tables, figure
staleness checking, and offline audiobook narration.

Clone it and `just paper` produces a compiling three-page skeleton before you
have written anything. `paper.typ` and `si-body.typ` are placeholders meant to be
deleted, so they stay short.

Coverage of the constructs the tooling handles specially does **not** live in the
placeholder prose, because that prose is gone the moment real writing starts. It
lives in `tests/fixture.typ`, which is never part of the manuscript, and
`just test` asserts the extractors still handle every case and still do so after
a reflow. That check survives for the life of the project.

## Quick start

```bash
git clone https://github.com/YOURNAME/paper-scaffold
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

**Do not start a paper with `cp -r`.** It copies `.git` too, and the new
manuscript then carries the scaffold's history: `just check-pdf` compares the
paper against the *scaffold's* commits, and `just version` reports the
scaffold's last commit as the manuscript's state. Both keep reporting
confidently while answering the wrong question.

Then, in the new directory:

1. Replace the abstract in `config.typ`. Title, authors and keywords are already
   filled in; the abstract is prose and is left for you.
2. Replace the placeholder prose in `paper.typ` and `si-body.typ`.
3. Replace `references.bib`.
4. Put your analysis in `analysis/`, keeping `just assets` as its front door. Or
   delete `analysis/` entirely if the paper has no generated assets.

Nothing else should need editing. `just verify` is the gate that says whether the
directory is in a shippable state.

Three parts are optional and can simply be deleted: `analysis/` (no generated
assets), `audio/` (no narration), and `stats.typ` + `si/stats.json` +
`analysis/scripts/gen_stats.py` (no numbers stated in prose). Every recipe and
check adapts rather than failing.

## What to run

| Command | Does |
|---|---|
| `just verify` | **The gate.** Formatting, extractors, prose rules and staleness, in one pass |
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
| `just test` | Assert the prose extractors handle every construct, before and after a reflow |
| `just prose-check` | Check the prose, plus figure resolution and table shape, against STYLE.md |
| `just prose-check --list-rules` | Every rule, its severity, and how to configure it |
| `just bib-audit` | Check every DOI against Crossref for retractions and dead links (network) |
| `just viz` | Diagnostics about the draft -> `viz/`: sentence length, word use, citation ages |
| `just density` | Numerals, parentheticals, acronyms, passives per 1,000 words, and section outliers |
| `just setup` | Build the Python environment (uv, locked) |
| `just version` | Which scaffold version this manuscript is built on |
| `just audio-setup` | One-time: install the audio deps and download the voice model |
| `just audiobook` | Chaptered `.m4b` of the main text |
| `just all` | PDF + Word + both audiobooks, then `just check` |

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
`just assets` runs every `gen_*_table.py`, so a new table needs no wiring beyond
matching the filename pattern.

The point is that a number in the manuscript should be traceable to the analysis
that produced it. Re-run the analysis and the manuscript updates.

### Numbers in prose: `#s("id")`, not a typed numeral

A table tracks the analysis because a script writes it. A number in a *sentence*
is typed by hand, and that is where drift lives: a unit error, a percentage
stale after a re-run, a value fixed in the table but not in the paragraph beside
it.

`analysis/scripts/gen_stats.py` declares every number the prose states and writes
`si/stats.json`. The manuscript reads it back:

```typst
the treated group scored #s("effect.treated_over_control") over control
```

Three things make it hold:

- **An unknown id fails the build.** `#s(...)` panics at compile time, so a
  number that stops existing is loud rather than blank. `readability.py` and the
  narrator resolve the same call, because they read the source, not the PDF.
- **Guards run when the file is generated.** A value can be declared `sign="-"`
  or `between=(0, 100)`. If a sentence says "fell" and a re-run turns the value
  positive, `just assets` fails and names the assumption, instead of the paper
  shipping "fell by -3.1%". A plausibility band catches the unit error.
- **`just prose-check` flags a typed numeral** that matches a declared value, so
  the rule is enforced rather than merely intended.

Rounding is set once per value with `fmt`, next to the analysis, so every mention
is punctuated identically.

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

To drop the mechanism from a project that states no computed numbers, delete
`stats.typ`, `si/stats.json` and `gen_stats.py`, **and the
`#import "stats.typ": n, s` line from all three files that carry it**:
`paper.typ`, `si-body.typ` and `wordcount.typ`. Each import is commented to say
so. Nothing beyond those three refers to it.

### `analysis/` lives inside the manuscript, and writes to it directly

The analysis that produces the numbers is a subdirectory, not a sibling
repository. It writes its figures into `figures/` and its tables into `si/` with
no staging copy in between.

That last part is the point. A copy is the single most reliable way for a
manuscript to go quietly wrong: a re-analysis updates the plot upstream, the copy
in `figures/` is untouched, and the PDF keeps rendering a figure that no longer
matches the numbers in its own caption. Writing to the destination removes the
failure rather than adding a guard for it.

**The contract is one recipe.** `analysis/justfile` exposes `assets`, which
regenerates everything the manuscript includes. `just assets` at the top level
delegates to it and knows nothing else. Whatever is inside `analysis/` is that
project's business: sixty numbered scripts, one notebook, a Snakemake pipeline.
Keep `assets` as the front door and the manuscript never has to care.

A paper with no computed results simply has no `analysis/` directory, and the
recipes say so instead of failing.

`figures/` and `si/` are generated but **tracked**, for the same reason
`paper.pdf` is: a fresh clone must compile without re-running an analysis that
may take hours. `just check-assets` guards that with a content stamp of the
analysis source, recorded in `.assets-stamp` when `just assets` runs, so editing
a generator and forgetting to re-run it is reported rather than shipped.

It stamps rather than comparing commit dates because the generators are
deterministic on purpose. Re-running them after an edit that does not move the
output produces no new commit, and a date-based check would then nag with no way
to satisfy it.

### `just check` is a submission gate

It exits non-zero if anything is stale, and covers the three failure modes that
actually happen:

- A tracked `paper.pdf` committed before a source fix. This is checked by comparing
  *commit dates*, not mtimes, because a fresh clone rewrites every mtime and would
  report a false alarm.
- `paper.docx` or an `.m4b` older than the text it renders or narrates. Each
  artifact is compared against its own inputs, so a regenerated SI table does not
  wrongly mark the audiobooks stale (they never read `si/`).
- `figures/` and `si/` older than the `analysis/` code that generates them.

`paper.pdf` is deliberately tracked in git, so a reader can get the manuscript
without installing Typst. `check-pdf` is what keeps that honest.

### The Word export is more delicate than it looks

`just docx` goes Typst → HTML → pandoc, and three things make it work:

1. `--input docx=true` bypasses the arkheion template, whose front matter and
   heading styling are layout-only primitives that Typst's HTML export silently
   discards. Without the bypass you lose every section heading and the abstract.
2. `paper.typ` wraps equations in `html.frame()` under that same flag, because
   HTML export drops math outright. `typst2docx.py` rasterizes them back inline
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
the balanced-paren stripper) live in `typst_prose.py`, imported by both
`readability.py` and `audio/extract_prose.py`. They are shared because keeping
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
- `git` for `just check-pdf`, which skips itself outside a repository
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
