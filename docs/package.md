# The toolchain as a package (4.0.0)

Up to 3.26, every paper carried a full copy of the toolchain: the `justfile`,
`tools/`, `tests/`, `journals/`, `word/` and `docs/`. Each release was a
three-way merge in ten papers. From 4.0.0 the toolchain is an installed Python
package, `paper-scaffold`. A paper keeps only the files it owns plus a version
pin, and an upgrade is a changed pin followed by `paper sync`.

The extension hooks from 3.26.0 ([hooks.md](hooks.md)) remain where a paper
puts its own behaviour. The package never ships or replaces those files.

## What a paper holds

| Owned by the paper | Written by `paper sync` | Read from the package |
|---|---|---|
| `paper.typ`, `config.typ`, `si-body.typ`, `cover-letter.typ` | `justfile` | `tools/` (every tool) |
| `analysis/` (apart from the three helpers) | `stats.typ`, `assets.typ`, `code.typ` | `tests/` (fixture and cases) |
| `stats.json`, `assets.json`, `references.bib`, `*.csl` | `wordcount.typ`, `wordcount-sections.typ` | `journals/*.toml` |
| `journal.toml`, `project.toml`, `project.just`, `hooks/` | `analysis/scripts/_stats.py`, `_assets.py`, `_provenance.py` and `_toolchain/` (when `analysis/scripts/` exists) | `word/reference.docx` (the multi-document reference) |
| `prose-check.toml`, `word-limits.toml`, `word-watchlist.toml` | `audio/extract_prose.py`, `make_audiobook.py`, `make_cover.py` (when `audio/config.py` exists) | `docs/`, `HISTORY.md` |
| `pyproject.toml` (the pin), `uv.lock` | `slides/theme.typ` (when `slides/` exists) | |
| `CLAUDE.md`, `AGENTS.md`, `STYLE.md`, `README.md`, `.gitignore`, `.claude/`, `.vscode/` | `.paper/scaffold.lock.json` | |
| `audio/config.py`, `slides/config.typ`, `slides/*.typ` decks | `.paper/docs/` (a gitignored mirror, not locked) | |
| A local `word/*.docx` or `journals/*.toml` (an override, below) | | |
| The `[word] reference` document, if the paper declares one | | |

Why each generated file has to exist on disk:

- **`justfile`.** `just` reads a file, not a Python package. With just 1.21,
  recipes from an `import`ed file run in that file's own directory, so a thin
  `justfile` importing `.paper/scaffold.just` would run every recipe inside
  `.paper/`. The generated `justfile` therefore contains the recipes and ends
  its settings with `import? "project.just"` as before.
- **The Typst modules.** Typst resolves `#import "stats.typ"` inside the
  compile root and cannot read site-packages.
- **The analysis helpers.** `gen_*.py` scripts run in the analysis's own
  environment (`analysis/pyproject.toml`), which does not install the
  toolchain. They import `_stats`, `_assets` and `_provenance` from beside
  themselves, and those import four small toolchain modules (`atomic_io`,
  `manifest_validation`, `hashcache`, `paths`) from
  `analysis/scripts/_toolchain/`, also written by `paper sync`. In the
  scaffold checkout the helpers use `tools/` directly.
- **The audio scripts and the slide theme.** The audio recipes run inside
  `audio/` and import the paper's `config.py`; `extract_prose.py` takes the
  Typst primitives from the installed package's `tools/` (the audio group
  extends the root environment, which has it). Decks import `theme.typ` from
  `slides/`. Neither is written for a paper without the feature.

Everything else is read from the installed package: the tools, the journal
profiles, the Word reference documents, the test fixture and the docs.

### Overrides: a paper's own reference document or journal profile

A paper may keep its own `word/reference.docx` (the multi-document Word
reference) or `journals/<name>.toml`. A local file at one of those paths wins
over the package's copy, for the build, the Word export and the staleness
record. It belongs to the paper: `paper sync` never writes it and
`paper sync --check` does not flag it. The lock lists it under `overrides`
with its hash, and `paper sync` prints it, so a reader can see that the paper
does not use the stock file.

The single paper's Word reference document is not a shipped file (3.27.0):
the export generates it from the `[word.style]` settings in `project.toml`,
or uses the paper's own document named by `[word] reference = "..."`
(cascade and spectrl-style journal templates with edits no setting
expresses). The package ships no `paper-reference.docx` and `paper sync`
writes none; nothing vendors or syncs it. A declared file under `word/` is
still listed in the lock's `overrides`, so `paper sync` reports that the
paper does not use the generated reference. `export_docx.py` reads the
declared file from the manuscript directly (no `locate()`), and
`build_state.py` hashes `project.toml` and that file, not
`word/paper-reference.docx`.

The lookup is one function, `paths.locate(root, name)`: the manuscript's copy
if it exists, else the package's. It applies to `tools/`, `journals/` and
`word/`. A local `tools/` file is not an override; `paper sync --check` flags
it (see "Migration").

## The package

The repository stays the template and the development tree. `tools/`,
`tests/`, `journals/`, `word/`, `docs/` and the `justfile` stay at the
repository root, so every path in the docs and every `uv run python tools/x.py`
still works there. The Python package is small:

```
src/paper_scaffold/
  __init__.py     data_dir(): the repository root in a checkout,
                  paper_scaffold/data/ in an installed wheel
  cli.py          the `paper` console script
  sync.py         paper sync / paper sync --check
  migrate.py      paper migrate (3.26.x -> 4.0.0)
```

The wheel carries the rest as package data under `paper_scaffold/data/`
(hatchling `force-include`): `tools/`, `tests/`, `journals/`, `word/`,
`docs/`, `audio/` scripts, `analysis/scripts/_*.py`, `slides/theme.typ`, the
five Typst modules, `justfile`, `HISTORY.md`. The plugin skills are not
packaged: they already reach every paper through the `paper-scaffold` plugin
marketplace (`.claude/settings.json`), which a pin would only duplicate.

A paper's `pyproject.toml`:

```toml
[project]
name = "koth-lfq-paper"
version = "0.0.0"
requires-python = ">=3.10"
dependencies = [
  "paper-scaffold @ git+https://github.com/pgarrett-scripps/paper-scaffold@v4.0.0",
]

[dependency-groups]
audio = ["piper-tts>=1.6", "imageio-ffmpeg", "pillow", "matplotlib"]

[tool.uv]
package = false
```

The pin is the `dependencies` line; `uv.lock` records the commit it resolved
to. The toolchain's own dependencies (pandoc, textstat, bibtexparser and the
rest) come with it.

### Where a tool finds the manuscript

A tool used to find the manuscript as `Path(__file__).parent.parent`. Inside
site-packages that is the package, so every tool now imports `tools/paths.py`:

| Name | Meaning |
|---|---|
| `paths.ROOT` | The manuscript: `$PAPER_ROOT` if set, else the current directory (installed) or the directory above `tools/` (a checkout). The justfile exports `PAPER_ROOT := justfile_directory()` and `paper tool` sets it to the working directory when unset, so every recipe sees the manuscript root. `paper test` clears it, so a test's temporary manuscript is not mistaken for the caller's. |
| `paths.TOOLS` | The directory holding the tools. |
| `paths.DATA` | The toolchain's data root: the repository in a checkout, `paper_scaffold/data/` when installed. |
| `paths.locate(root, name)` | `root/name` if present, else `DATA/name` (for `tools/`, `journals/`, `word/`). |

Recipes call tools through the console script: `uv run --quiet paper tool
check_stats --deep` runs `tools/check_stats.py` from the installed package,
in-process, with its own directory first on `sys.path`, exactly as
`python tools/check_stats.py` did. In the scaffold checkout the same line runs
the checkout's file, because the package is installed editable.

## `paper sync`

```bash
paper sync            # write the generated files and the lock
paper sync --check    # fail on anything missing, edited or out of date
paper upgrade-notes   # HISTORY Upgrade: lines between the lock's version and the installed one
paper version         # installed version, the pin, the lock
```

`paper sync` writes each generated file with a header naming the release and
saying not to edit it, then records the hashes in `.paper/scaffold.lock.json`.
It refuses to overwrite a generated file whose content no longer matches the
lock, because that is someone's edit: move the change into `project.just`,
`project.toml` or `hooks/` and rerun, or pass `--force` to discard it. When
the lock's version differs from the installed one, sync prints the "Upgrade:"
lines between them first.

`paper sync --check` exits 1 when:

- the lock is missing, or was written by a different installed version (the
  pin moved and `paper sync` was not run);
- a generated file is missing, or its hash differs from the lock (edited);
- a generated file differs from what the installed package would write now;
- a toolchain directory that sync does not own (`tools/`, `tests/`, `docs/`)
  still exists in the paper, which means a half-finished migration.

`just verify` runs it as its first stage, "toolchain (paper sync --check)". In
the scaffold checkout there is nothing to sync, and the stage says so.

### The lock

```json
{
  "schema_version": 1,
  "scaffold": {
    "version": "4.0.0",
    "pin": "paper-scaffold @ git+https://github.com/pgarrett-scripps/paper-scaffold@v4.0.0"
  },
  "files": {
    "justfile": "<sha256>",
    "stats.typ": "<sha256>"
  },
  "overrides": {
    "journals/jpr-article.toml": "<sha256>"
  }
}
```

The lock is committed. It answers "which release wrote these files" without
the network or the scaffold checkout, as the dissertation's
`scaffold.lock.json` did for its hand-imported tools.

## Staleness

The build record (`.build-state/paper.pdf.json`) used to hash
`tools/<build tools>`, `journals/*.toml`, `word/paper-reference.docx` and the
`justfile` in the manuscript directory. It now hashes the build tools and
journal profiles through `paths.locate`, so the content comes from the package
unless the paper overrides it. `pyproject.toml` and `uv.lock`, which carry the
pin, stay in the record as before, so any pin move (a new package version)
marks `paper.pdf` and `paper.docx` stale. In the scaffold checkout the package
is installed editable and a tool edit does not change the version; the tool
contents catch that.

The Word reference document is not a file in the record (3.27.0). It is
generated from `project.toml`'s `[word.style]` by `paper_word_reference.py`
(both hashed), or it is the paper's own `[word] reference`, which
`project_hooks.build_inputs` adds to the record and the capture. A change to
either marks `paper.docx` stale.

The captured manuscript (`.build-state/manuscripts/<id>/`) still carries
`tools/` beside the sources, so an old capture converts the way it was built.

## Migration from 3.26.x and 3.27.x

```bash
cd ~/Repos/paper-scaffold          # a clone with the release tags
uv run paper migrate --project ~/Repos/koth-lfq-paper --dry-run
uv run paper migrate --project ~/Repos/koth-lfq-paper
```

`paper migrate` classes every file the scaffold owned at the paper's current
release (the `version` line in its `pyproject.toml`, or `--from`), using the
same comparison as `just upgrade-plan`: pristine (identical to that release,
after the identity fields new-paper.sh fills in) or customized.

| File | Pristine | Customized |
|---|---|---|
| `tools/`, `tests/`, `docs/`, `DOCUMENTATION.md`, `LICENSE.scaffold` | removed | **refused** |
| `justfile`, the Typst modules, the analysis helpers, the audio scripts, `slides/theme.typ` | replaced by sync | **refused** |
| `journals/*.toml`, `word/reference.docx` | removed | kept as an override |
| `word/paper-reference.docx` (no longer read from 3.27.0) | removed | compared as Word renders it: only recoloured black, removed; other edits, removed and their `[word.style]` block written into `project.toml`; edits no setting expresses, kept and declared as `[word] reference` |
| `HISTORY.md` (the package's from 4.0.0) | removed | **refused** (move the paper's notes to `notes/PROJECT-HISTORY.md`, restore the stock file) |
| `CLAUDE.md`, `STYLE.md`, `README.md`, `.gitignore`, `.claude/`, `.vscode/`, `cover-letter.typ`, `audio/config.py` | kept | kept |
| `pyproject.toml` | rewritten with the pin | rewritten; extra dependencies kept, anything else **refused** |
| a file in `tools/` or `tests/` the scaffold never had | | **refused** (move it to `hooks/`) |

A refusal lists every file and changes nothing. Move each local change into
`project.toml`, `project.just` or `hooks/` (the 3.26.0 upgrade did this for
most papers already), restore the scaffold file, and rerun. `migrate` also
refuses when git shows any file it would touch as uncommitted.

When nothing is refused it removes the pristine files, rewrites
`pyproject.toml` with the pin (`--pin` to choose it; the default is this
release's git tag), adds `.paper/docs/` to `.gitignore`, then runs `uv lock`, `uv sync` and
`paper sync` in the paper (`--no-install` skips the first two and syncs from
the environment running `migrate`). Then:

```bash
just paper && just verify
git add -A && git commit -m "Move to paper-scaffold 4.0.0 (toolchain package)"
```

Do `just text-baseline` before the migration and `just text-diff` after it:
the rendered text must not move.

## What breaks (why this is 4.0.0)

- `tools/`, `tests/` and `docs/` leave the paper. A paper hook that ran
  `python tools/x.py` must use `uv run paper tool x` (a Word step still gets
  the tools on its `sys.path`, as before).
- The root `justfile` is generated. A local recipe edit fails
  `paper sync --check`; it belongs in `project.just`.
- `just upgrade-plan` becomes `just upgrade-notes` (an alias keeps the old
  name). There is nothing to classify: an upgrade is `uv add` of the new tag,
  `uv sync`, `paper sync`.
- In a paper, `just test` runs the extractor fixture check (tests/fixture.typ,
  golden files, the reflow check) against the installed package: the part that
  depends on this machine's Typst and typstyle. The case suites (prose rules,
  resolver, submission, new-paper and the rest) test the toolchain itself;
  they run in the scaffold checkout and in CI before a release is tagged.
- `just version` prints the installed package version and the pin.
- `scripts/new-paper.sh` writes the pinned `pyproject.toml` and runs
  `paper sync` instead of copying the toolchain.

## Upgrading a paper on 4.x

```bash
uv add "paper-scaffold @ git+https://github.com/pgarrett-scripps/paper-scaffold@v4.1.0"
uv run paper sync          # prints the Upgrade: lines, rewrites the generated files
just paper && just verify
```

A paper with a local override (a reference document, a journal profile) keeps
it across upgrades. A change it needs from a newer stock file is a hand merge
of that one file, as before.
