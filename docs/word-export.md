# Word export

How `just docx` turns the Typst source into an editable Word file.

## The Word export is more delicate than it looks

Every Word style in `paper.docx` comes from a reference document. The export
never compiles the Typst preamble, so the paper's look reaches Word only
through that file. `tools/paper_word_reference.py` generates it: pandoc's
default, then the stock adjustments (black title and headings, single-spaced
figures and references, code in DejaVu Sans Mono, concrete fonts and colours
winning over theme settings), then the settings in `project.toml`:

```toml
[word.style]
font = "Times New Roman"   # every text style but code; replaces the theme fonts
font_size = 12             # body text, pt (6-36, half-points)
line_spacing = 2.0         # body line spacing, a multiple (1-3)
margins = "1in"            # all four sides: in, cm, mm or pt, up to 3in
title_size = 20            # the Title style, pt
title_align = "left"       # the Title style: "left" or "center"
title_color = "000000"     # Title and Subtitle, six hex digits
heading_color = "000000"   # Heading 1-9
title_bold = true          # the Title style in bold (false: regular)
page_numbers = true        # a centred page number in every footer
```

Every key is optional; one left out keeps the stock value. Headings keep
their own sizes when `font_size` changes. With `line_spacing` set, table
cells and tight lists (the Compact style) stay single-spaced, like figures
and references. `margins` also sets a US Letter page when none is set, and
figure widths follow the text width it leaves.

The generated file is cached in `.build-state/word-reference/`, keyed by the
settings, the tool and the pandoc version. `project.toml` is a build input,
so changing a setting makes `paper.docx` stale. To look at the file:
`uv run python tools/paper_word_reference.py` prints its path.

### Tables

pandoc writes every table auto-fit, in the reference document's Table style
at body size, so Word and LibreOffice choose different column widths and a
dense SI table can wrap an identifier mid-word. The `table_*` keys restyle
every table in the written file (`tools/word_tables.py`, after the
pagination pass); `[word.tables]` adjusts one table, named by its label:

```toml
[word.style]
table_font_size = 9            # pt, every table cell (5-14)
table_header_bold = true       # header rows in bold
table_header_shading = "F2F2F2"  # header-row fill
table_borders = "booktabs"     # "booktabs", "grid" or "none"
table_layout = "fixed"         # full text width, fixed columns; "auto" = pandoc's
table_cell_margin = "0.04in"   # left and right cell padding, up to 0.5in
table_compact = true           # single-spaced cells, no space around, kept whole
table_valign = "center"        # "top", "center" or "bottom"
table_unnest = true            # a figure of several tables: one table after another

[word.tables."tbl:runtime"]    # the label, or the assets.json id tbl.runtime
widths = [3, 1, 1, 1]          # relative; implies the fixed layout for this table
font_size = 8
header_rows = 2                # rows that repeat and take the header styling
```

Header rows are the rows of the source's `table.header` (pandoc repeats
them) plus the first row, which the pagination pass always repeats; set
`header_rows` where that is wrong, `0` for a table with no header. With no
`widths`, the fixed layout keeps pandoc's column proportions, which follow
the source's `columns:`. A widths list whose length differs from the table's
columns stops the export; a `[word.tables]` label no table carries prints a
note. None of these keys touch the reference document, so they also work
beside a hand-made `reference`, and a paper that sets none converts to the
same bytes as before.

What stays a paper's own Word step: content rewrites (a glyph Word's fonts
lack), stacking a code listing's lines inside a table cell, and widths
chosen by matching header text, which `[word.tables]` replaces with the
label.

A paper that needs more than these settings keeps its own reference
document, made in Word, and declares it instead:

```toml
[word]
reference = "word/custom.docx"   # exclusive with [word.style], table_* keys aside
```

That file is used as it is, with no stock adjustments. It is a build input
too. Before 3.27.0 the scaffold shipped `word/paper-reference.docx` for
papers to edit. That file is no longer read, and a build stops if one is
left undeclared. `uv run python tools/paper_word_reference.py --translate
word/paper-reference.docx` prints the `[word.style]` block that reproduces
it, or lists what no setting can express. Add
`--baseline <the release's copy>` to count only the paper's own edits.

After pandoc writes the file, `export_docx.paginate` sets the keep rules the
PDF follows without being told: a table row never splits, a short table stays
on one page, a caption stays with its figure or table, and a page break
starts the next paragraph instead of standing alone as an empty one. Column
widths come from the source: `columns: (2fr, 1fr, 1fr)` reaches Word as
proportional widths, while `columns: 3` is left for Word to size.
`uv run python tools/export_docx.py --main-only` (after `just docx`) writes
`paper-main.docx` without the SI, for journals that take the SI as a separate
upload. Optional `paper-running-title`, `paper-corresponding-email` and
`paper-corresponding-phone` bindings in `config.typ` add those lines to the
Word front matter. The author whose `email:` matches the corresponding email
gets a star.
For multi-chapter Word exports, see [multi-document.md](multi-document.md).


`just docx` goes `just resolve` → pandoc's native Typst reader. The resolver
replaces every project helper (`#s()`, `fig()`, cross-references, the
bibliography's style variable) with plain Typst in `paper.resolved.typ`, and
pandoc — a real evaluator, from `uv` (`pypandoc-binary`), no system install —
turns that into **native, editable Word equations**, real tables, and a
reference list set by citeproc from `references.bib`. A manuscript whose SI
carries its own list gets both: citeproc sets one list per run, so each
stretch of the projection is converted separately and the Pandoc trees are
joined, with the second list's anchors renamed so a work cited in both halves
is not two Word bookmarks with one id. Citations follow
`<style>.csl` in the manuscript root when present (the scaffold ships
`american-chemical-society.csl`, matching the default `paper-bib-style`);
otherwise pandoc's default applies, with a printed note. Every citation key is
checked against the `.bib` before converting, because citeproc renders a
missing one as bold prose and still exits 0. When the output looks wrong, read
`paper.resolved.typ` — it is exactly what pandoc was fed.

This is the only Word route. The one it replaced went Typst → HTML → pandoc,
and is recorded under "Decisions reversed" in HISTORY.md. The PDF path is
entirely unaffected by the export.
