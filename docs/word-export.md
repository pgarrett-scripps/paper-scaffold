# Word export

How `just docx` turns the Typst source into an editable Word file.

## The Word export is more delicate than it looks

The native paper exporter now uses `word/paper-reference.docx` for reusable Word
styles. Edit that file in Word to change headings, body text, captions or code;
builds preserve those changes. The template has single-spaced image paragraphs
and references, and removes conflicting theme settings where concrete fonts or
colors are specified. Template edits invalidate the build fingerprint.
`uv run python tools/paper_word_reference.py` explicitly resets this template;
normal builds never regenerate it. Older projects without the file retain the
existing code-style fallback. The legacy HTML exporter does not use this template.
`--black-headings` sets the title and headings in black instead of blue.

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
