# Working in this directory

Rules for an agent editing this manuscript, each stated once. The reasons and
full recipe descriptions are in [docs/](docs/README.md) (in a paper, read
them under `.paper/docs/`, the copy `paper sync` writes); prose conventions
are in [STYLE.md](STYLE.md). To move an existing manuscript onto the scaffold,
follow the scaffold's `docs/migrating.md` instead of improvising the order.

## Paper scaffold

Built on [paper-scaffold](https://github.com/pgarrett-scripps/paper-scaffold)
SCAFFOLD_VERSION, installed as the `paper-scaffold` package that
`pyproject.toml` pins (`just version`). The package owns the toolchain:
`tools/`, `tests/`, `journals/`, `word/` and `docs/` are read from it, and
`paper sync` writes the few files a paper must hold on disk (`justfile`,
`stats.typ`, `assets.typ`, `code.typ`, the wordcount modules, the
`analysis/scripts/_*.py` helpers, the audio scripts, `slides/theme.typ`),
each headed GENERATED, recorded in `.paper/scaffold.lock.json`. Never edit a
generated file: `just verify` runs `paper sync --check`, which fails on the
edit. This project owns the manuscript: `paper.typ`, `config.typ`,
`si-body.typ`, `analysis/`, and the declarations in `stats.json` and
`assets.json`. A paper-specific gate stage, recipe, Word step or extra source
goes in `project.toml`, `project.just` or `hooks/` (see
[docs/hooks.md](docs/hooks.md)). A local `word/*.docx` or `journals/*.toml`
overrides the package's copy and is the project's. To move to a newer
scaffold, change the pin (`uv add "paper-scaffold @ git+...@vX.Y.Z"`), then
`uv run paper sync`: it prints the "Upgrade:" lines to act on
(`just upgrade-notes` reprints them). See
[docs/package.md](docs/package.md).

## Read the text first

- For prose, terminology and argument work, read the Typst sources with shell
  reads and searches: `paper.typ`, `config.typ` (abstract), `si-body.typ` or
  the included file. Do not invoke PDF, image or document-rendering skills
  just because the manuscript produces a PDF or Word file.
- `paper.resolved.typ` is the last build's text with numbers, tables and
  reference numbers filled in; the captured sources are under the path in
  `.build-state/manuscript.json`. Both are generated: never edit them. They
  describe the last build, so check `just check-build` before relying on
  them; while editing, read the source with `stats.json` or
  `just trace <id> --json`. Do not rebuild to read a sentence (`just resolve`
  compiles a PDF too). In trace output, `status: incomplete` means a check
  could not be established; trace never re-runs the analysis.
- Build once after the edits, then run the gate. Inspect pages or images only
  when the user asks, when changing layout, figures or typesetting, or when
  diagnosing a specific rendering defect; stop when that issue is resolved.

## Preserve scientific meaning

Follow STYLE.md, especially "Scientific terms and concrete claims". Before
replacing a technical term, search its uses and check the quantity's
definition, units and analysis; repeat the established name, never a synonym
for variety. Mass spectrometry intensity must not become "height",
"brightness" or "abundance" unless the manuscript defines that relationship
and the evidence supports it. For each edited claim, know what was measured,
what it was compared with, and what supports it. Remove decorative jargon and
undefined labels. If the meaning cannot be established from the source, keep
the supported wording and flag the ambiguity; do not invent a plausible
explanation. A clean prose check does not make a sentence clear or correct.

## Numbers, figures and tables

Details: [docs/numbers.md](docs/numbers.md), [docs/assets.md](docs/assets.md).

- **Never type a result into the prose.** Declare it in
  `analysis/scripts/gen_stats.py` and read it as `#s("id")`. Guard what the
  sentence assumes in the entry's `expect` (prose says "fell": `"sign": "-"`);
  seed the guard in `gen_stats.py` for a new value, edit `expect` in
  `stats.json` for an existing one.
- **Four tiers**, weakest claim to strongest: a computed number is
  `#s("id")`; one no script can compute but worth an audit trail is a hand
  entry in `stats.json` with a note; a deliberate prose literal ("40 °C") is
  vouched in place with `#lit("40")`; a global value-level exception goes in
  `prose-check.toml` with a written reason. `lit()` never silences
  `derivable-number`.
- **`stats.json` you MAY edit, by field.** The script owns `value`,
  `checksum` and `origin`; `fmt`, `unit`, `desc` and `expect` are yours and
  survive `just assets` (`gen_stats.py` arguments only seed a NEW entry). To
  change a number, change the analysis; never edit a generated `value`. A
  hand entry has `origin.by = "hand"`, an `origin.note`, an `origin.source`
  a reader can re-open (repo path, URL, DOI, commit or `evidence:SET`), a
  `value` and a `fmt`. Files no generator declares can be watched under a
  top-level `"pinned"` block, recorded with `just pin`.
- **Never edit or commit `stats-rendered.json`** (a build artifact).
- **Never hand-edit `si/*.typ` or `figures/`.** Change the generator
  (`analysis/scripts/gen_*_table.py`, the plotting script) or its data, then
  `just assets`.
- **Never name a generated figure or table by filename.** Reference the id
  declared in `assets.json`: `#figure(fig("fig.x"), caption: [...])`.
- **Adding one:** copy `analysis/scripts/gen_example_table.py` or
  `gen_example_figure.py`, keeping the `gen_*_table.py` / `gen_*_figure.py`
  name. A table writes a bare `#table(...)` into `si/` and gets its
  `#figure(tbl("tbl.x"), caption: [...]) <tbl:x>` in `si-body.typ`. A figure
  sets `metadata={"Software": None}` and seeds any RNG. End the generator
  with `record(id, path, kind=..., inputs=[data it read], desc=...)`, paths
  relative to the manuscript root. Data named in `evidence.toml` is opened
  as `evidence("set")`, never a typed path ([docs/evidence.md](docs/evidence.md)).
  A result still running is a `pending` block, never a stale value. Then
  `just assets && git add figures si assets.json stats.json`.
  `/paper:new-figure` does every step.

## Manuscript rules

- **Cite in `si-body.typ` as `@si-key`, never `@key`.** A bare key in the SI
  silently joins the main reference list (`misrouted-citation`). Exception:
  `project.toml` sets `[bibliography] single = true` (one list; the SI cites
  `@key`). See docs/hooks.md.
- **Never delete the `// >>> BODY START` / `// <<< BODY END` markers** in
  `paper.typ`; moving them changes what the word count means.
- **Notes to self are `#todo("...")`, never a comment.** `just paper` refuses
  to build with one open; `just prose-check` lists them.
- **Journal limits come from `journals/<profile>.toml`, never from memory.**
  `journal.toml` selects the profile. To change a limit, re-read its
  `source`, change the number, move `checked`. The graphical abstract is
  `toc-graphic` in `paper.typ`; `[placement]` decides where it lands, so do
  not move the block. See [docs/journals.md](docs/journals.md).
- **A stale slide deck is not a `verify` failure.** Do not fix decks during a
  verify pass or add `slides/*.typ` to `typst_sources`; check one on request
  with `just slides-check`. Decks use `#s()`/`#fig()` too, never typed
  numbers. A talk's identity is `slides/config.typ`, not `config.typ`.
- **Typst gotchas.** A method chain broken across lines after `#let x =` or
  inside `[...]` ends at the newline (`unknown variable: a`): wrap it in
  `{ ... }`. `#include` gives the file its own scope, so a new `.typ` file
  using `s()`, `n()`, `fig()` or `tbl()` needs its own
  `#import "stats.typ": s, n` and `#import "assets.typ": fig, tbl`.
- **Word export never compiles the preamble.** If you change the preamble or
  the resolver, run `just docx` and confirm the headings, abstract and
  equations survive, not just the exit code. Word fonts, spacing,
  margins and heading colours are `[word.style]` in `project.toml`
  (docs/word-export.md).

## Done means `just verify` is clean

```bash
just paper      # rebuild; prints word count and readability
just verify     # the gate: formatting, extractors, prose rules, staleness
```

- Quote the word count and readability `just paper` prints; never estimate.
  Read the edited passages in the refreshed `paper.resolved.typ` for meaning.
- A wording-only pass is bracketed by `just edit-baseline` and
  `just edit-check` (numbers may be dropped, never invented; references,
  floats and headings survive). Still read the edited sentences.
- `verify` rebuilds nothing and names the recipe that clears each stale
  item. What each stage checks:
  [docs/build-and-staleness.md](docs/build-and-staleness.md).
- A concurrent build or a source edit during compilation is a failed build,
  not permission to weaken the check.
- Do not change word limits or exclusions just to clear `check-words`. Do not
  silence a prose-check finding by editing `tools/prose_check.py`: add it to
  `prose-check.toml` with a comment saying why.
- `just check` ignores the audiobooks on purpose, and there is no upstream
  figure copy to compare; read HISTORY.md's "Decisions reversed" before
  adding either back.
- Before submission: `just preflight` (fresh builds, the `just submission`
  upload set, `verify`, `check-submission`, `check-stats-deep`, `bib-audit`).
  The upload set lands in `submission/`; single parts are `just main-pdf`,
  `si-pdf`, `main-docx`, `si-docx`, `toc-graphic`, `cover-letter`. See
  [docs/submission.md](docs/submission.md).

## Skills

Thirteen workflows ship as the `paper` plugin (from the scaffold's
`plugins/paper/skills/`, enabled by `.claude/settings.json`; Codex reads the
same files through the `.agents/skills` symlink as `$copy-edit` and so on).
Prefer a skill over improvising its steps.

- Edit: `/paper:copy-edit`, `/paper:fix-verify`, `/paper:declare-number`,
  `/paper:new-figure`, `/paper:cover-letter`.
- Review, read-only, findings under `reviews/`: `/paper:claim-audit`,
  `/paper:methods-vs-code`, `/paper:figure-review`, `/paper:prose-review`,
  `/paper:literature-check` (network), `/paper:story-review`,
  `/paper:peer-review`. `/paper:review-all` runs them and merges the findings
  (literature check only on request, story review never). A review skill
  never edits the manuscript.
- `reviews/ACTIONS.md` is the action ledger: reviews read it first and append
  new findings, editing skills close the rows they fix with the commit hash;
  `just check-actions --open` lists what is open.

What each does: [docs/working-with-ai.md](docs/working-with-ai.md).

## Toolchain

- **Python goes through uv.** Root `pyproject.toml` pins the toolchain
  package, `analysis/pyproject.toml` is the analysis. Use `uv run`, never a
  bare `python3`, never `uv run --with X`: add the dependency to the right
  pyproject.
- **The toolchain is the pinned package, not files in the paper.** Recipes
  run tools as `uv run paper tool NAME`; a hook does the same, never
  `python tools/NAME.py`. A toolchain change is made in the scaffold
  repository and released; a paper gets it by moving its pin and running
  `uv run paper sync`. `paper path NAME` shows which file (the package's or a
  local override) a name resolves to.
- **Toolchain development (the scaffold repository only).** Every tool lives
  in `tools/` with a `just` recipe and finds the manuscript through
  `tools/paths.py` (`ROOT`, `locate()`), never `Path(__file__).parent.parent`.
  A new extractor construct gets a case in `tests/fixture.typ`, then
  `just test-update` (read the diff); anything else goes in the per-subject
  case module listed in `tests/run.py`'s `CASE_MODULES`. Never add coverage
  through `paper.typ`: that prose is placeholder. In a paper, `just test` is
  the fixture check alone.
- **Draft metrics:** read `viz/report.json` from `just viz` rather than
  re-deriving section metrics, long sentences or float citations.
  `just density` and `just doctor` are useful, outside the gate.
- **Scope:** do not restructure the pipeline to fix a one-off problem. Ask
  before removing a staleness check, the generated-table contract or the
  docx bypass.
