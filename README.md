# paper-scaffold

A reusable Typst manuscript directory: PDF, Word export, journal word counts,
readability metrics, auto-generated Supporting Information tables, figure
staleness checking, and offline audiobook narration.

It ships as a working skeleton rather than a set of blank files. Clone it and
`just paper` produces a real (if nonsensical) three-page paper before you have
written anything. That matters more than it sounds, because every tool here
depends on a specific Typst construct being present, and a blank template
exercises none of them. The skeleton includes one figure, one display equation,
one inline equation, one table, one auto-generated SI table, two citations, and
one cross-reference for exactly that reason. If you delete them all before you
start writing, you lose the smoke test.

## Quick start

```bash
cp -r paper-scaffold /path/to/your-project/paper
cd /path/to/your-project/paper

just si-assets     # generate the example SI table + figure
just paper         # -> paper.pdf, plus word count and readability
just docx          # -> paper.docx
```

Then:

1. Edit `config.typ` (title, authors, abstract, keywords, bibliography style).
2. Replace the placeholder prose in `paper.typ` and `si-body.typ`.
3. Replace `references.bib`.
4. Point `analysis_root` at the top of the `justfile` at your analysis tree, and
   rewrite `figures.map` and `scripts/gen_*.py` for your own figures and tables.

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
| `just si-assets` | Regenerate SI tables and re-copy figures from the analysis tree |
| `just check` | Report every artifact that has fallen behind its source |
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

`scripts/gen_example_table.py` is the template. Copy it per table. `just
si-tables` runs every `scripts/gen_*.py`, so a new table needs no wiring beyond
matching the filename pattern.

The point is that a number in the manuscript should be traceable to the analysis
that produced it. Re-run the analysis and the manuscript updates.

### `figures.map` and the staleness trap this closes

Figures live in the analysis tree and are *copied* into `figures/`. That copy is
the single most reliable way for a manuscript to go quietly wrong: a re-analysis
updates the plot upstream, the copy in `figures/` is untouched, and the PDF keeps
rendering a figure that no longer matches the numbers in its own caption, with
nothing to flag it.

`figures.map` lists `dest <- source` pairs. `just figures` copies them, and `just
check` byte-compares them and reports drift. Set `analysis_root` at the top of
the `justfile` to wherever your analysis writes.

### `just check` is a submission gate

It exits non-zero if anything is stale, and covers the three failure modes that
actually happen:

- A tracked `paper.pdf` committed before a source fix. This is checked by comparing
  *commit dates*, not mtimes, because a fresh clone rewrites every mtime and would
  report a false alarm.
- `paper.docx` or an `.m4b` older than the text it renders or narrates. Each
  artifact is compared against its own inputs, so a regenerated SI table does not
  wrongly mark the audiobooks stale (they never read `si/`).
- Figures that differ byte-for-byte from their upstream copy.

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
| `just fmt-diff` | Show what would change, writing nothing |
| `just fmt-verify` | Prove formatting is output-neutral by diffing the PDF's extracted text before and after |

`typst_sources` deliberately excludes `si/*.typ`, which the generator scripts own
and would rewrite unformatted on the next run. `.vscode/settings.json` marks them
read-only in the editor for the same reason.

**Reformatting can break the prose extractors.** typstyle will break a long line
*inside* a function call, turning `#refn(<sec:methods>)` into

```typst
Section #refn(
  <sec:methods>
)
```

Any stripper regex written for the one-line form then leaks a bare `#refn(` and
`)` into the word count, the readability score, and the narration, where the
voice reads "refn" aloud. The patterns in `readability.py` and
`audio/extract_prose.py` allow the whitespace for this reason. If you add your own
inline helper, make its pattern whitespace-tolerant too, and run `just fmt-verify`
plus a quick look at `audio/paper_prose.txt` after the first reformat.

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

- `typst` and `just`
- `uv` (for the Word export and the generator scripts; no global installs)
- `python3`
- `curl` and a network connection for `just audio-setup` only

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
