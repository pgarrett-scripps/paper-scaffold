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
cp -r paper-scaffold /path/to/your-project/paper
cd /path/to/your-project/paper

just assets        # regenerate the example figure + SI table via analysis/
just paper         # -> paper.pdf, plus word count and readability
just docx          # -> paper.docx
```

Then:

1. Edit `config.typ` (title, authors, abstract, keywords, bibliography style).
2. Replace the placeholder prose in `paper.typ` and `si-body.typ`.
3. Replace `references.bib`.
4. Put your analysis in `analysis/`, keeping `just assets` as its front door. Or
   delete `analysis/` entirely if the paper has no generated assets.

Nothing else should need editing.

## What to run

| Command | Does |
|---|---|
| `just paper` | Compile `paper.pdf`, then print word counts and readability |
| `just watch` | Live preview, recompiling on save |
| `just fmt` | Reflow the hand-written Typst sources (typstyle, 80 cols) |
| `just docx` | Export `paper.docx` for journals and co-authors |
| `just wordcount` | Journal-style counts without rebuilding |
| `just readability` | Flesch-Kincaid / reading ease / fog without rebuilding |
| `just assets` | Regenerate every generated figure and table (delegates to `analysis/`) |
| `just check` | Report every artifact that has fallen behind its source |
| `just test` | Assert the prose extractors handle every construct, before and after a reflow |
| `just prose-check` | Check the prose against the mechanical rules in STYLE.md |
| `just density` | Numerals, parentheticals, acronyms, passives per 1,000 words, and section outliers |
| `just setup` | Build the Python environment (uv, locked) |
| `just audio-setup` | One-time: fetch Piper, the voice model, and the ffmpeg venv |
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
may take hours. `just check-assets` guards that by comparing commit dates, so
editing a generator and forgetting to re-run it is reported rather than shipped.

### `just check` is a submission gate

It exits non-zero if anything is stale, and covers the three failure modes that
actually happen:

- A tracked `paper.pdf` committed before a source fix. This is checked by comparing
  *commit dates*, not mtimes, because a fresh clone rewrites every mtime and would
  report a false alarm.
- `paper.docx` or an `.m4b` older than the text it renders or narrates. Each
  artifact is compared against its own inputs, so a regenerated SI table does not
  wrongly mark the audiobooks stale (they never read `si/`).
- `figures/` and `si/` committed before the `analysis/` code that generates them.

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
structural checks. A figure or table that no text ever references is an error,
since most journals require every one to be cited and a reader who is never sent
to a figure will not look at it. Two more are warnings: figures cited out of
numerical order (a copy-editing return at many journals, but a conventions
paragraph legitimately forward-references, so it does not gate), and an acronym
used repeatedly but never expanded (what counts as common knowledge is
field-specific).

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

The engine, voice model, venv, and every audio file are gitignored, so a fresh
clone needs `just audio-setup` once (~60 MB download).

## Requirements

- `typst`, `just`, `uv`
- `typstyle` for `just fmt` (`cargo install typstyle`)
- `curl` and a network connection for `just audio-setup` only

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

## Provenance

Extracted from the `dnoise` manuscript pipeline. The design decisions encoded
here (commit-date PDF checking, byte-compared figure copies, generated SI tables,
the docx-mode template bypass) each came from a specific way that manuscript went
wrong.
