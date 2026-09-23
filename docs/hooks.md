# Extension hooks

The scaffold owns the `justfile`, `tools/`, `tests/`, `word/` and
`journals/`. When a paper needs one more gate stage or a Word touch-up, the
fix used to be an edit to one of those files. Every upgrade then had to find
that edit and merge it back by hand. The hooks let the paper keep such
changes in files it owns, which the scaffold reads but never ships or
replaces:

| File | Holds |
|---|---|
| `project.toml` | The declarations: gate stages, the bibliography audit, one reference list, Word steps, extra Typst sources |
| `project.just` | Extra `just` recipes, imported by the scaffold's `justfile` |
| `hooks/` | Scripts the declarations name (suggested location) |

`just upgrade-plan` treats them as project-owned, like `paper.typ`.
Every hook is opt-in: with no `project.toml` and no `project.just`, every
recipe behaves exactly as it did before hooks existed. `just hooks` lists
what this paper declares.

`project.toml` is validated strictly. An unknown table or key, a stage with
no `run`, or a `schema_version` other than 1 is an error. The stage runner
reports it inside `verify`, so a typo cannot become a stage that never runs.

```toml
schema_version = 1
```

## Gate stages

Each gate runs the paper's own stages after its built-in ones:

| Table | Runs in | Where |
|---|---|---|
| `stages.verify` | `just verify` | After `check-actions` |
| `stages.check` | `just check`, and so also `verify` | After the submission-set note |
| `stages.preflight` | `just preflight` | After `bib-audit`, before the verdict |
| `stages.submission` | `just submission` and `just all` | After the upload set is written |

A stage has a `name` and a `run`. The `run` value is a bash command, run from
the manuscript root with `$PAPER_ROOT` set to that root. Each stage prints
under its own `=== name (project.toml) ===` header. A non-zero exit fails the
gate. Every stage runs even after an earlier one fails, as in the built-in
gates. In `submission` and `all`, a failing stage stops the recipe instead.

```toml
[[stages.verify]]
name = "provenance"
run = "uv run --quiet python hooks/check_provenance.py"

[[stages.check]]
name = "overflow"
run = "uv run --quiet python hooks/check_overflow.py paper.pdf"

[[stages.preflight]]
name = "figure QC"
run = "uv run --quiet python hooks/figure_qc.py --check"

[[stages.submission]]
name = "source data"
run = "uv run --quiet python hooks/source_data.py"
```

Stages extend a gate; they cannot remove or replace a built-in stage. A
stage that needs a slow rebuild belongs in `submission`, not in `verify`:
`verify` is the gate you run constantly, and it rebuilds nothing.

### The bibliography audit

`just preflight` runs `just bib-audit --require-complete`. A paper whose
references cannot all carry DOIs (software, standards, theses) may drop the
flag. The audit still runs, and a DOI it does find must still resolve and
match:

```toml
[preflight]
bib_audit_require_complete = false
```

## One reference list

The scaffold gives the SI its own reference list, and `@si-key` routes a
citation there ([manuscript.md](manuscript.md)). A journal that wants one
list for the whole paper gets it by removing the Alexandria setup: the
`#show: alexandria(...)` line in `paper.typ` and the `#bibliographyx` call
in `si-body.typ`. The SI then cites `@key`, and `just submission` gives the
separately uploaded SI file a local list of only the works it cites
([submission.md](submission.md)). Then declare the choice:

```toml
[bibliography]
single = true
```

The declaration tells a reader, human or agent, that a bare `@key` in the SI
is intended, so the `@si-key` rule in `CLAUDE.md` and `STYLE.md` does not
apply. `just prose-check` holds the sources to it: a declaration with the
Alexandria setup still present is an error (`si-bibliography-mode`). Without
the declaration nothing changes. A paper that removed Alexandria before this
flag existed still builds and checks as before.

## Word post-processing

A paper that needs its tables sized, a title style changed, or a footer
added to `paper.docx` declares the step instead of editing
`tools/export_docx.py`:

```toml
[word]
lua_filters = ["hooks/word.lua"]
before_pagination = ["hooks/polish_tables.py"]
after_pagination = ["hooks/size_tables.py"]
inputs = ["hooks/docx_common.py", "hooks/table-widths.json"]
```

The export runs them in this order:

1. The Lua filters are passed to pandoc (`--lua-filter`, in list order) on
   the final conversion to `.docx`. Citations are already set by then.
2. Each `before_pagination` script runs as `python <script> <docx>` and
   edits the file in place.
3. The scaffold's pagination pass runs. It keeps captions with their floats,
   stops table rows from splitting and keeps run-in labels with what follows.
4. Each `after_pagination` script runs the same way. Then every property
   block in `document.xml` and `styles.xml` is put back in schema order. Word
   rejects a file with properties out of order ("unreadable content"), so a
   step may append properties without sorting them.

A step runs with the toolchain's Python, with `tools/` on its path (so
`from word_xml import W, order_properties` works), from the manuscript
root, and with `$PAPER_ROOT` set. A non-zero exit fails the export. Use only
the standard library and the toolchain's packages: the root `pyproject.toml`
is scaffold-owned.

The Word steps are build inputs. `project.toml` and every file `[word]`
names are hashed into the staleness record of `paper.pdf` and `paper.docx`,
like the `justfile` and `word/paper-reference.docx`. They are also captured
with the manuscript, so `just main-docx` and `si-docx` convert the upload set
the way the build did. List any other file a step reads under `inputs`, such
as a helper module or a table of widths. A file not listed is neither
tracked nor captured, and a captured build will not find it.

The steps apply to every single-paper Word export: `just docx`, `just paper`
and the upload set's Word halves. Multi-document projects
(`manuscript.toml`) have their own Word adapter and do not run them.

## Extra Typst sources

The `justfile`'s `typst_sources` lists the scaffold's hand-written files.
A paper adds its own in `project.toml` rather than editing that line:

```toml
[sources]
typst = ["reviewer_response.typ", "macros.typ"]
```

A declared file is:

- formatted by `just fmt` and checked by `just fmt-check`;
- checked by `just prose-check` for the sentence rules (spelling, em dashes,
  doubled words, long sentences and the rest) and for open `#todo` notes,
  reported under its file name.

A declared file that does not exist is an error (`project-config`), not a
silent skip. A typo would otherwise leave the file unformatted and
unchecked for good.

Only the checks that make sense outside a manuscript half run on these
files. They are not word-counted, and they get no section-order,
figure-citation or derivable-number checks. A response letter's "line 212"
and "Reviewer 2" are not results to trace.

They are also not staleness inputs of `paper.pdf` or `paper.docx`. A file
the manuscript `#include`s or `#import`s is one already: the build records
every file the compiler reads. A reviewer response is not, so editing it
does not mark the paper stale. `project.toml` itself is a build input (see
[Word post-processing](#word-post-processing)), so adding a file to the
list does.

## Project recipes

The `justfile` ends its settings with `import? "project.just"`. Recipes in
that file appear in `just --list` with their descriptions and run like any
other recipe. Their paths are relative to the manuscript root. A stage can
call one:

```just
# project.just
# Package the source-data workbook the journal asks for
source-data:
  uv run --quiet python hooks/package_source_data.py

# Fail if the source-data workbook is behind the figures
check-source-data:
  uv run --quiet python hooks/package_source_data.py --check
```

```toml
# project.toml
[[stages.submission]]
name = "source data"
run = "just source-data"

[[stages.preflight]]
name = "source data"
run = "just check-source-data"
```

A recipe with the same name as a scaffold recipe is an error from `just`,
not an override. The scaffold deliberately leaves `allow-duplicate-recipes`
off: with it on, `just` silently keeps the scaffold's recipe, and the
paper's version would never run. Give the recipe a new name. To change what
a gate does, declare a stage.

The recipes run with the scaffold's settings (`positional-arguments`). Keep
`set` lines out of `project.just`: `just` applies settings to the whole
justfile, so one there would change every scaffold recipe too.

## What is not hooked

- **Replacing a built-in recipe.** See [project recipes](#project-recipes).
- **Resolver and extractor behaviour.** These are the pipeline's contract
  with the PDF, the Word file and the word count. A paper that needs a change
  there needs an upstream fix, so every paper gets it.
