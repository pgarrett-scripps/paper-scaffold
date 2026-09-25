# v5-word: Word, layout, upstreamed local features, the dissertation track

## What changed

- Word tables: `[word.style]` `table_font_size`, `table_header_bold`, `table_header_shading`, `table_borders` (booktabs/grid/none), `table_layout` (fixed/auto), `table_cell_margin`, `table_compact`, `table_valign`, `table_unnest` (tools/word_tables.py); per-table `[word.tables."tbl:x"]` `widths`, `font_size`, `header_rows`. Replaces the table hooks four papers wrote. Off unless set; a paper without the keys converts to the same bytes.
- Word page setup: `[word.style]` `page_numbers` (a PAGE footer) and `title_bold`.
- `just check-layout` (tools/layout_check.py): text past the margins or page edge in the built PDF, and figures against the journal profile's `[figures]`: resolution as placed, width (single/double column), height, smallest type (assets.json `print.min_pt`), colour mode. Warn only (`--strict` fails); runs on paper.pdf and, from `check-submission`/`preflight`, on `submission/*.pdf`.
- Journal profiles: new `[figures]` keys `single-column-in`, `double-column-min-in`, `double-column-max-in`, `max-height-in`, `min-type-pt`, `color-modes`; the JASMS profiles set the widths and minimum type size from their quoted guidelines.
- `#si-contents` ships in `assets.typ` (from koth-paper); `#import "assets.typ": fig, tbl, si-contents`. The prose rules `cross-reference-order` and `unreached-si-section` were already upstream (3.25.0, warn).
- Ported parts: `[parts.X.upstream] repo, commit, figures` in manuscript.toml; `just port-check` (a `verify` stage in multi-document projects) warns when the upstream HEAD moved, a copied figure's sha256 matches a since-regenerated upstream assets.json entry, or a chapter-directory Typst file sets the page (the CeTZ rule); `just port-diff PART` / `paper port-diff PART` prints the upstream stats.json diff. Skips quietly when the repo is absent.

## Upgrade:

- Nothing is required. Every new key is opt-in; every new check warns.
- `just check-submission` and `just preflight` now print layout warnings; they do not fail. spectrl-paper will see one (fig.spectral_similarity 7.255 in, over JASMS's 7.0 in double column).
- A paper with its own `#let si-contents` (koth-paper) keeps it, or deletes it and adds `si-contents` to its `assets.typ` import; do not do both.
- A local Word table hook can be replaced by the `[word.style]` table keys; `reference` may now sit beside the table keys.
- Multi-document projects: `verify` gains the `port-check` stage (warn only). Add `upstream` to ported parts to use it. Document PDFs rebuild once after the upgrade, as after any change to the document tools.
