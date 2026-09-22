# Numbers in prose

How a number gets from the analysis into a sentence, and how it is checked.

## Numbers in prose: `#s("id")`, not a typed numeral

A table tracks the analysis because a script writes it. A number in a *sentence*
is typed by hand, and that is where drift lives: a unit error, a percentage
stale after a re-run, a value fixed in the table but not in the paragraph beside
it.

`analysis/scripts/gen_stats.py` declares the numbers the prose states and writes
them into `stats.json`. The manuscript reads them back:

```typst
the treated group scored #s("effect.treated_over_control") over control
```

Three things make it hold:

- **An unknown id fails the build.** `#s(...)` panics at compile time, so a
  number that stops existing is loud rather than blank. `tools/readability.py` and the
  narrator resolve the same call, because they read the source, not the PDF.
- **Guards run when the file is generated.** Each entry's `expect` block can
  assert a sign or a plausibility band. If a sentence says "fell" and a re-run
  turns the value positive, `just assets` fails and names the assumption,
  instead of the paper shipping "fell by -3.1%". A band catches the unit error.
  The fresh value is judged against the guard *as it stands in `stats.json`* —
  the author's — not against whatever the script happened to pass.
- **`just prose-check` flags a typed numeral** — one that matches a declared
  value (use `#s()` instead), and one that matches *nothing* declared, which is
  worse: mistyped, stale from an earlier draft, or from a source nobody
  recorded. Four ways out, each leaving a trail: compute it (`#s()`), declare
  it by hand with a note, vouch for it in place with `#lit("40")` when it is
  genuinely just prose, or suppress the value in `prose-check.toml` with a
  written reason. `lit()` deliberately does not silence the first rule — a
  computed value wrapped in it is still flagged. Years and short counts are
  skipped, and prose-check reports how many literals are vouched inline, so
  the count cannot grow silently.
- **`just check-stats` re-checks the committed file, without running anything.**
  Every guard is re-run against the values as they sit in `stats.json`; each
  generated value is compared to the checksum its generator recorded, so a
  hand-edit is caught; and the `sources` block hashes the code and data behind
  the numbers, so "the analysis moved" is answered in milliseconds. The guards
  above only fire while the generator runs, which does nothing for a value edited
  afterwards.
- **`just check-stats-deep` re-runs the generator and diffs.** Stronger — it
  recomputes from the data rather than comparing fingerprints — and it costs
  whatever your analysis costs, so it is deliberately not part of `just verify`.
  `verify` must rebuild nothing; run this before submitting.

## stats.json is yours, not just the analysis's

The split is by field, and it follows what each field *is*. The script owns the
`value` — a fact about the data, which nobody else can honestly write — plus
the `checksum` that catches a hand-edit to it and the `origin` that says who
wrote it and when it last changed. Everything else in an entry is the author's,
edited in `stats.json` directly:

- `fmt` and `unit` — how the number is shown. An editorial choice, not an
  analysis result.
- `desc` — what the number is, for whoever audits the file later.
- `expect` — what the *prose* assumes ("fell", "roughly 80–90%"). That
  assumption lives next to the sentence, so the author maintains it. A
  one-sided bound (`min` with no `max`) is fine.

The arguments to `st.add(...)` beyond the value are seeds: they fill in a new
entry so the file is never born empty, and are ignored once the entry exists —
with a note when they differ from the file, so a stale script argument is
visible rather than silently dead.

Every entry also records `origin.by`: the script that generated it, or
`"hand"`. A generator rewrites only its own entries, so a number you add by
hand survives `just assets` instead of being silently overwritten by it.
`origin.at` is when the value last *changed* — a re-run that reproduces the
same number leaves it alone, so the date means something.

```json
"cohort.sites": {
  "value": 4, "fmt": "",
  "expect": {"sign": "+"},
  "origin": {"by": "hand", "note": "study protocol v3, Table 1"}
}
```

A hand entry must carry `origin.note` saying where the number came from, and it
is guarded exactly as tightly as a derived one. What it cannot get is
re-derivation: `check-stats-deep` recomputes generated values from the data and
compares, and nothing can do that for a number that came off a printout. The
note is the audit trail instead.

That is also why `stats.json` sits at the manuscript root rather than under
`si/`: a file you are invited to edit is not generated output, and cannot be
guarded by "did anything change".

## Pinned files: watching what no script reads

Provenance the pipeline records automatically stops at what a generator
imported or declared. Plenty of files matter without any script reading them —
a raw instrument export, a protocol document, an upstream config. Declare those
by hand in `stats.json`:

```json
"pinned": {
  "analysis/data/raw_export_2026-06.csv": null
}
```

`just pin` records the sha256, and from then on `just check-stats` (so `just
verify`) reports when the file changes. The fix it names is deliberate: check
the numbers that depend on it, then `just pin` again to accept the new state.
Generators carry the block through untouched — declaring what is worth watching
is the author's call, made in the file.

**`stats.json` stores no rendered string.** It holds the `value` and the `fmt`;
`tools/render_stats.py` turns them into `stats-rendered.json`, which is what
`stats.typ` reads. Every recipe that compiles regenerates it first, and it is
gitignored, so it can never be stale and never disagrees with its source.

That step exists because Typst has no format spec — no thousands separator, no
`+.2f` — and its `str()` rounds floats where Python's does not
(`1.0899999999999999` is `1.09` there, the full expansion here). Doing the
formatting in the document would mean reimplementing Python's spec in a language
that cannot express it, and storing the result beside the value would put a
derived field in a source file, free to drift.

One formatter, `typst_prose.display_of`, is used by the renderer *and* by the
word count and the narrator, so the PDF and the extractors cannot disagree about
what a number looks like.

While ids are still in flux, `just draft` renders an unresolved one as a loud
`?id?` placeholder instead of stopping the compile, and writes `paper-draft.pdf`
so a placeholder can never reach the real PDF. `n("id")` fails even there: no
placeholder can stand in for a number inside an expression without making the
arithmetic that reads it silently wrong.

Available in the SI as well as the main text. `si-body.typ` imports the helpers
itself rather than inheriting them, because Typst's `include` gives the included
file its own scope: without that import an `#s("id")` in the SI fails with
`unknown variable: s` even though `paper.typ` imports it one line above the
include. The SI is the data-heavy half, so it is where generated numbers belong
most.

To drop the mechanism from a project that states no computed numbers, four steps.
Typst has no conditional import and no way to ask whether a file exists, so the
references have to come out by hand; each one is commented to say so.

```bash
rm stats.typ stats.json analysis/scripts/gen_stats.py
```

1. Delete the `#import "stats.typ": n, s` line from **`paper.typ`,
   `si-body.typ` and `wordcount.typ`**. All three carry it.
2. In `wordcount.typ`, also drop the helpers from the eval scope:
   `scope: (refn: refn, s: s, n: n, fig: asset-fig, tbl: asset-tbl)` becomes
   `scope: (refn: refn, fig: asset-fig, tbl: asset-tbl)`. The import alone is not
   enough — this line names them again, and missing it is the one that bites,
   because `just paper` still works and only `just wordcount` fails.
3. Remove any `#s()` / `#n()` calls left in the prose.

The generated-**assets** mechanism comes out the same way and separately:

```bash
rm assets.typ assets.json
```

Delete the `#import "assets.typ": fig, tbl` line from `paper.typ` and
`si-body.typ`, drop `fig: asset-fig, tbl: asset-tbl` (and the import above it)
from `wordcount.typ`, remove the `record(...)` calls from the generators in
`analysis/scripts/`, and go back to naming files directly:
`#figure(image("figures/x.png"), ...)`.

Verified by doing exactly this to a copy and confirming `just paper`,
`just wordcount`, `just readability` and the narration all still work.

## Tracing numbers and assets

Use `just trace <id>` before editing a claim or its supporting asset:

```bash
just trace effect.treated_over_control
just trace fig.example --json
```

`--json` emits exactly one JSON object on stdout. The stable envelope contains
`schema_version` (currently 1), `id`, `status`, `exit_code`, and `findings`.
A completed inspection also returns the declaration, display value for a
statistic, declared input hashes, usage locations (`path`, `line`, `context`),
and suggested commands. Findings carry stable rule IDs. Suggestions are never
executed automatically, and some findings require an author decision instead
of a command.

`status` is `ok`, `failed`, or `incomplete`. `exit_code` is respectively 0, 1,
or 2; an invalid request also uses 2. The underlying Python CLI returns those
codes. `just` collapses failed recipes to a nonzero wrapper status, so agents
should use the JSON fields to distinguish failure from incomplete inspection.
If an ID exists in both manifests, select `--kind stats` or `--kind assets`.

Trace checks recorded consistency. It does not run the analysis or establish
scientific correctness. Usage discovery follows literal calls and literal
Typst includes/imports from the manuscript entrypoints; dynamically computed
IDs and paths are outside that source index. Comments, raw examples, and old
`paper.resolved.typ` output do not count as uses. Missing declared inputs are
reported as incomplete, not silently treated as verified.

The command behavior matters as much as its name:

| Intent | Command | Cost and changes |
|---|---|---|
| Understand one declaration | `just trace <id> --json` | Reads sources/declarations; may refresh the local hash cache; never runs analysis |
| Make a wording pass | `just edit-baseline`, edit, `just edit-check` | Checks literal numbers, helper IDs, citation occurrences, headings, and declarations, including the abstract and literal includes |
| Build deliverables | `just paper`, `just docx` | Writes build artifacts; never regenerates analysis outputs |
| Check current work | `just verify` | Cheap local checks; rebuilds nothing |
| Refresh declared results | `just assets` | Runs analysis and updates tracked generated outputs; potentially expensive |
| Check a submission | `just preflight` | Builds outputs, runs gates and deep statistics, and requires online bibliography checks to complete |

The edit guard protects mechanical invariants, not prose meaning. Numeric
statements may be dropped, but new or substituted statistic calls, changed
asset calls, and edited declarations fail. Snapshots from before this protection
was added must be recorded again before starting another pass.
