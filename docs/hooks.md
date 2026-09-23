# Extension hooks

The scaffold owns the `justfile`, `tools/`, `tests/`, `word/` and
`journals/`. When a paper needs one more gate stage or a Word touch-up, the
fix used to be an edit to one of those files. Every upgrade then had to find
that edit and merge it back by hand. The hooks let the paper keep such
changes in files it owns, which the scaffold reads but never ships or
replaces:

| File | Holds |
|---|---|
| `project.toml` | The declarations: extra gate stages and the bibliography-audit setting |
| `hooks/` | Scripts the declarations name (suggested location) |

`just upgrade-plan` treats them as project-owned, like `paper.typ`.
Every hook is opt-in: with no `project.toml`, every
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

## What is not hooked

- **Resolver and extractor behaviour.** These are the pipeline's contract
  with the PDF, the Word file and the word count. A paper that needs a change
  there needs an upstream fix, so every paper gets it.
