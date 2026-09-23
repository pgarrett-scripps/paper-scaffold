# Commands

Every `just` recipe a manuscript uses, in one table.

## What to run

| Command | Does |
|---|---|
| `just verify` | **The gate.** Formatting, extractors, prose rules and staleness, in one pass |
| `just preflight` | **The submission gate.** Fresh builds and upload set + `verify` + deep stats + DOI audit |
| `just doctor` | Are the external tools installed and new enough? |
| `just paper` | Build `paper.pdf`, `paper.docx`, and `paper.review.txt`, with word counts and readability |
| `just pdf` | Build only `paper.pdf`, with word counts and readability |
| `just draft` | Compile `paper-draft.pdf` with unresolved `#s()` numbers shown as `?id?` |
| `just watch` | Live preview, recompiling on save |
| `just fmt` | Reflow the hand-written Typst sources (typstyle, 80 cols) |
| `just docx` | Export `paper.docx` for journals and co-authors |
| `just submission` | The journal upload set in `submission/`: main text and SI apart (PDF and Word), graphical abstract, cover letter, `manifest.json` |
| `just main-pdf` / `si-pdf` / `main-docx` / `si-docx` | One half of the manuscript, cut from the last `just paper` build |
| `just toc-graphic` / `cover-letter` | The graphical abstract in the profile's format and box; `cover-letter.typ` as a PDF |
| `just check-submission` | Fail if a file in `submission/` is behind its source. Not in `verify`; in `preflight` |
| `just slides [name]` | Build a slide deck from `slides/` -> `slides/<name>.pdf` (all decks with no name) |
| `just slides-handout [name]` | Build the handout form, with every `#pause` reveal flattened |
| `just slides-check [name]` | Deck staleness plus the four slide-only prose rules. Not in `verify` |
| `just slides-notes <name>` | Export `#speaker-note` text to `slides/<name>.pdfpc` for a presenter tool |
| `just slides-list` | What decks exist, and whether each is current |
| `just review-text [target]` | Export a compact `.review.txt` with prose, equations and numbered captions for AI review |
| `just wordcount` | Journal-style counts and configured section checks without rebuilding |
| `just journal` | Everything the selected journal profile says, against the manuscript |
| `just check-journal` | Keyword count, figure and table counts, graphical abstract size. In `verify` |
| `just journals` | The profiles under `journals/` and which one `journal.toml` selects |
| `just wordcount --sections` | List exact section paths available for word-count checks |
| `just check-words` | Enforce configured minimum/maximum word counts; also runs in `verify` |
| `just readability` | Flesch-Kincaid / reading ease / fog without rebuilding |
| `just assets` | Regenerate every generated figure, table and prose number (delegates to `analysis/`) |
| `just check` | Report every artifact that has fallen behind its source |
| `just trace <id> --json` | Inspect a statistic or asset, its uses, provenance, and checks as structured data |
| `just check-actions [--open\|--init]` | Validate `reviews/ACTIONS.md` and count open review actions; `--open` lists them, `--init` creates it. In `verify` |
| `just pin` | Record hashes for the files listed under `pinned` in `stats.json` |
| `just text-baseline` / `text-diff` | Snapshot the PDF's words; word-level diff after a structural refactor |
| `just review-baseline <name>` | Save a resolved manuscript version, including its figures and bibliography |
| `just review <name> [new-name]` | Highlight changes against the current manuscript or another saved version |
| `just edit-baseline` / `edit-check` | Check that wording edits preserve retained numbers, helper IDs, citations, declarations, and structure |
| `just test` | Assert the prose extractors handle every construct, before and after a reflow |
| `just prose-check` | Check the prose, plus figure resolution and table shape, against STYLE.md |
| `just word-audit` | Count flagged words across the manuscript without rebuilding |
| `just prose-check --list-rules` | Every rule, its severity, and how to configure it |
| `just bib-audit` | Check DOI metadata, retractions and dead links against Crossref/DataCite (network) |
| `just viz` | Diagnostics about the draft -> `viz/`: nine plots plus `report.json` for tools |
| `just density` | Numerals, parentheticals, acronyms, passives per 1,000 words, and section outliers |
| `just setup` | Build the Python environment (uv, locked) |
| `just version` | Which scaffold version this manuscript is built on |
| `just upgrade-plan [vX.Y.Z]` | Upgrade: lines since this version, and each scaffold file classed pristine or customized; read-only unless `--apply-pristine` |
| `just audio-setup` | One-time: install the audio deps and download the voice model |
| `just audiobook` | Chaptered `.m4b` of the main text |
| `just all` | PDF + Word + both audiobooks + the upload set, then `just check` |
