# History

What changed in the pipeline, and why. Read the "Decisions reversed" section
before proposing a change that looks obvious. Several obvious things were tried
here and were wrong.

Entries are deliberately short: what changed, the one-line reason, and the
upgrade step. The full arguments live as comments next to the mechanisms they
justify, where someone touching the code will actually read them.

## Versioning

The version lives in one place, `version` in `pyproject.toml`, and travels with
the scaffold when it is copied into a project. `just version` prints it.

What bumps what is judged from the manuscript's point of view, not the code's:

- **Major** breaks a manuscript. An existing `paper.typ`, `si-body.typ`, or
  `analysis/` has to be edited to keep working.
- **Minor** adds a capability without touching an existing manuscript. A new
  check, a new metric, a new recipe.
- **Patch** fixes something without changing the interface.

Tag every release: `git tag -a v1.2.3 -m "..."`.

### Upgrading a project built on an older version

```bash
just version                                    # what the project is on
git -C ~/Repos/paper-scaffold log --oneline vOLD..vNEW
git -C ~/Repos/paper-scaffold diff vOLD..vNEW -- justfile tools/ tests/ scripts/
```

(Before 2.0.0 the toolchain sat in the root, so upgrading from 1.x needs
`justfile *.py tests/` as the path list instead.)

Then apply what you want by hand. There is deliberately no automatic upgrade: a
manuscript diverges from the scaffold the moment real writing starts, and a
merge tool cannot tell your `paper.typ` from the placeholder it replaced. Read
the major entries first — those need an edit rather than a copy. For moving an
existing manuscript onto the scaffold, see MIGRATING.md.

---

## 3.12.1

Math in the Word export rendered ~9% smaller than the text around it: frames
carry the manuscript's em (11pt, typically) and pandoc's Word body is 12pt,
and the rasterizer sized images by raw ink points. Each frame's em is now
read from its own style attribute and rescaled to Word's.

Found while chasing a report from dnoise that $m/z$ arrived in Word as "a
weird small artifact". The dominant cause there was notation, not pipeline:
in Typst math, `/` builds a stacked fraction, so $m/z$ was a tiny m-over-z
in the PDF too, and crop-to-ink turned it into a 5px image in Word. The
slash the field convention wants is written `$m\/z$`. Worth knowing before
writing any inline ratio.

## 3.12.0

Four packaged AI workflows, as skills in `.claude/skills/` that travel with
new-paper.sh: `/copy-edit` (a wording pass bracketed by the edit guard),
`/fix-verify` (the intended fix per finding class, as a table -- never
weakening a check), `/declare-number` (the four-tier ladder as a procedure),
`/new-figure` (all four steps, wordcount scope included). The design rule:
each skill encodes the pipeline's contracts and ENDS by running the check
that proves it behaved, so an agent cannot report success without the
pipeline agreeing. A generic prompt does not know it must never edit a
number; a shipped one does.

## 3.11.0

Two additions in the #lit() spirit -- inline, self-enforcing, each closing a
gap between what the pipeline checks and what authors actually do:

- **`just edit-baseline` / `just edit-check`**: prove a copy-edit pass changed
  only wording. Snapshots every number, label, reference, figure and heading;
  afterwards a number may be DROPPED (a note -- STYLE.md permits thinning) but
  never INVENTED (fatal), and references, floats and headings must survive
  exactly. Judged manuscript-wide, because content legitimately moves between
  main text and SI. Upstreamed from the koth manuscript, which wrote it for
  exactly this and ran it in anger first. Snapshots live in .edit-guard/,
  local state like .build-stamp.
- **`#todo("...")`: a note that cannot ship.** Renders as a loud marker in
  draft mode; PANICS `just paper` and `just docx`, so a final PDF with an
  unresolved note is not producible -- where a `// FIXME` comment survives to
  submission silently. Stripped by the extractors (a note is not prose), a
  no-op in the word count, and surfaced by `just prose-check` as
  unresolved-todo so the gate shows open notes without a build.

Found while wiring it: paper.typ had never received the `lit` import -- the
3.10.0 sed missed its exact line and the placeholder never calls lit, so
nothing noticed. The import list is now `lit, n, s, todo` in all three files,
and the failure it would have caused is the include-scope gotcha CLAUDE.md
already documents.

## 3.10.0

`#lit("40")`: vouch for a deliberate prose literal in place, instead of a
value-level exception in prose-check.toml far from the sentence. Renders as
the text typed (string argument required -- Typst rounds bare floats its own
way), silences unaccounted-number at that spot only, and deliberately does
NOT silence derivable-number: a computed value wrapped in lit() still gets
flagged, because vouching must not bypass the stronger rule. prose-check
reports how many literals are vouched inline, so the count cannot grow
silently. The four tiers, weakest claim to strongest: #lit() -> hand entry
with a note -> #s(). Recognized by both extractors with fixture coverage,
reflowed form included.

## 3.9.2

`just --list` is the first thing a newcomer sees, and ten of its descriptions
were sentence fragments -- "watch means restarting it.", "and the one uv knows
nothing about." -- because just shows the LAST comment line before a recipe,
and rationale appended after the description line decapitated it. The
convention is now stated at the top of the justfile and every block ends with
its one-liner. Four plumbing recipes (default, render-stats, check-declared,
check-build) went [private]: callable and documented, off the front page.

## 3.9.1

`check-stats-deep`'s summary said "(re-derived)" whether or not anything was:
on an all-hand-entered manuscript _rederive has nothing generator-owned to do,
and on a frozen analysis it degrades to a note -- both still wore the
verification label. The status now comes from _rederive itself: "N value(s)
re-derived", "nothing generator-owned to re-derive", or "could not re-run the
generator". Found by the koth-paper pipeline audit; dnoise's audit hit the
other branch of the same defect.

## 3.9.0

The checkers report through rich (one shared findings table in report.py --
severity styled, messages wrapping in their own column, everything through
Text so a bracketed range is not eaten as markup), and audiobook synthesis
shows a progress bar for the minutes it always ran silent (transient, and
absent from piped logs, which keep their per-chapter lines).

Plus four fixes from a downstream audit of the scaffold by the dnoise agent:

- **Narration read `\u{2082}` escapes aloud.** The fix existed in the shared
  layer for the word count and was never wired into audio -- and the golden
  file had blessed the broken narration. Proven by the goldens themselves:
  readability.txt said log2 (the character), narration.txt said the escape.
- **bib-audit reported correct software/data DOIs as unresolvable.** Crossref
  registers articles; Zenodo/figshare/Dryad mint through DataCite. A Crossref
  404 now falls through to DataCite, which resolves the DOI but has no
  retraction concept, and the summary says so.
- **The fixture's #s() ids resolved against the manuscript's stats.json**,
  coupling the permanent fixture to the placeholder analysis it exists to
  outlive. tests/fixture-stats.json is owned by tests/ now; the manuscript's
  file is the fallback for fixtures already adapted to their own ids.
- **The hand-vs-generator id clash said "rename one of them"**, the opposite
  of the migration handover where the ids SHOULD collide. The message now
  describes the handover (delete the hand entry, seeds fill in); the takeover
  stays manual, because a hand entry with a note is authored data.

## 3.8.2

`unaccounted-number` met its first real manuscript and produced 189 warnings.
Three fixes from the encounter: a clause comma is no longer part of the number
("median 1, mean 2.67" reported '1,'), digits inside an identifier are not a
result ("PXD070049" reported '070049'), and each document now shows eight
findings plus a count of the rest -- one value reported once, because a
189-line wall is read by nobody. On the same manuscript: 19 lines.

## 3.8.1

Two fixes found downstream, in the dnoise manuscript, and taken upstream:

- **`check-stats-deep` ran the generator with the toolchain's interpreter**,
  which lacks the analysis environment's dependencies (pandas, typically), so
  it died on ModuleNotFoundError -- downgraded to a "could not re-run" note.
  The strongest check in the pipeline silently reduced itself to nothing on
  exactly the projects with a real analysis. It runs through `uv run` now,
  resolved from the generator's directory like analysis/justfile does, with a
  sys.executable fallback when uv is absent.
- **Two tests hardcoded `figures/example_figure.png`**, which a real
  manuscript deletes in its second week; the tests then failed for a reason
  unrelated to what they check. The figure is discovered from `figures/` now,
  and the cases skip with a note when none exists.

## 3.8.0

The console reports render through rich, styled once in `tools/report.py`:
real tables, right-aligned numbers, styling dropped automatically when piped.
Piped output gets a 200-column console, because rich's 80-column fallback
truncated "numerals" to "nume…" -- worse than no styling at all.
`wordcount.sh` runs its formatting through `uv run` now (rich lives in the
locked environment), so doctor's python3 requirement belongs to the justfile's
inline recipes alone.

## 3.7.1

The build report was a wall on a real manuscript: three stacked header blocks,
two disagreeing columns both named "words", a nine-column density table, and
section names truncated at 34 characters in a report whose job is to name
sections. Now: `just paper` prints the word count and readability as eleven
lines (density moved fully behind `just density`, where CLAUDE.md always said
it lived); readability lost its own words column rather than disagree with the
journal count above it; density aligns full section names and reports
"value (median N)".

## 3.7.0

`just text-baseline` / `just text-diff`: snapshot the PDF's extracted text,
word-diff it after a structural refactor. The one property no other check
watches — verify guards the machinery, not the words. Word-level because a
reflow rewraps every line. pdftotext (poppler) joins `doctor` as an optional
tool.

## 3.6.1

MIGRATING.md: the runbook for moving an existing manuscript onto the scaffold —
phases, the paper-must-not-change invariant, the traps from 3.6.0. Excluded
from `new-paper.sh` copies, along with `.hash-cache.json` and `viz/`, local
state its exclude list predated.

## 3.6.0

Lessons from watching a real migration — the seat the scaffold had never sat
in.

- **`just adopt note="..."`** declares figures/tables whose analysis is gone:
  `origin.by = "adopted"`, note mandatory (the hand-entry contract). Hash and
  reference checks still apply; regeneration is honestly absent and the checks
  say so. A generator later calling `record()` with the id takes it over.
- **Three load-bearing constraints written down**: `analysis/` must live inside
  the manuscript (the provenance resolution depends on it); `#include` gives a
  file its own scope, so every included `.typ` needs its own imports; the BODY
  markers define what the word count *means* (back matter excluded), so a
  migrated headline number drops without an edit.

## 3.5.0

The README gained the pipeline's ideas as fifteen lines, audited against the
code. Twelve held; three fixes made the rest true:

- **`unaccounted-number`** (warning): a distinctive numeral matching *nothing*
  declared was the only silent number in the paper. Years and short counts
  skipped.
- **check-stats renders every entry**: a broken `fmt` edited into stats.json
  used to pass verify and kill the next build instead.
- **`tools/hashcache.py`**: verify re-hashed every declared input on every run,
  gigabytes included. A (size, mtime_ns)-keyed cache decides *when* to re-hash;
  the sha256 stays the only recorded truth; recording paths still hash bytes
  directly.

## 3.4.1

Ten defects in the 3.3.0/3.4.0 code, found by adversarial review, each
verified before fixing. The theme: stats.json became hand-edited JSON, and
hand-edited JSON can be malformed in ways the code crashed on or silently
accepted.

- A malformed `values` block was treated as empty and rewritten, deleting
  every hand entry. Now refused, like invalid JSON always was.
- `_rederive` ran the generator against an empty shadow, so stale seed guards
  judged the values and a guard death was downgraded to a note — deep checking
  silently disabled by the documented workflow. The shadow now starts as a
  copy of the real file; a guard violation there is an error.
- NaN passed every range guard after the per-bound rewrite. Explicit error now,
  in generator and gate.
- Unknown `expect` keys, quoted bounds, and list-shaped `pinned` blocks were
  silences or gate-killing tracebacks. All named error findings now.
- Deleting an author-owned field resurrected the seed via `old.get(f,
  seed[f])`. Deletion is an edit: it stays deleted.
- A v1-checksum mismatch is a warning, not an error — v1 covered value+fmt and
  cannot tell the documented fmt edit from tampering.
- `just pin` no longer marks builds STALE: the stamp hashes stats.json without
  `pinned`.
- `origin.at` moves when 35 becomes 35.0: value comparison checks type.

## 3.4.0

Three holes between "the checks pass" and "the submitted file is not stale":

- **check-build checks the output itself.** The stamp only proved a build
  happened from the sources, not that the file on disk is that build's output —
  a paper.pdf swapped in from Downloads passed as current. The stamp now
  records the output's hash too (mismatch: REPLACED), and the source hash is
  captured *before* the compile so a mid-compile edit errs toward stale.
- **`just preflight`**: fresh builds + verify + check-stats-deep + bib-audit as
  one command. Three "run before submitting" notes in three places was a
  conditional ritual, and those get skipped. `just assets` deliberately not
  included — a rebuild, not a check.
- **render-stats removes stats-rendered.json when stats.json is gone**, so the
  derived file cannot outlive its source and be read by a compile.

## 3.3.0

The ownership of stats.json split by field, following what each field is.

- **The script owns `value` (plus checksum and origin); `fmt`, `unit`, `desc`
  and `expect` are the author's**, edited in stats.json and surviving `just
  assets`. `st.add(...)`'s extra arguments seed a *new* entry only; a stale
  seed is ignored with a note. The fresh value is judged against the *file's*
  guard — the author's — with one-sided bounds supported. Editing `expect` went
  from undetectable drift to the supported way to state an assumption.
- Checksums narrowed to the value alone (v2); v1 still verifies so existing
  manuscripts upgrade cleanly.
- **`pinned`**: files no generator declares, watched by hand — declare
  `"path": null` in stats.json, `just pin` records the hash, `check-stats`
  reports changes.
- **`origin.at`** on every value and asset: when it last *changed*, not when
  the script ran — identical output keeps its date.
- Fixed: the CI figure-survival check counted `image(` calls, which went to
  zero when figures moved behind the manifest, so it compared against zero and
  could never fail (it now counts `fig("` references and fails on zero);
  `.build-stamp` now covers render_stats.py, typst_prose.py and typst2docx.py;
  assorted stale references from the stats.json move.

## 3.2.0

`just verify` re-ran the analysis: `check-stats` re-derived every value by
re-running gen_stats.py, invisible on the scaffold's 0.02s example and ruinous
on a real project. Re-derivation moved behind `just check-stats-deep`; the
default path reads files only. Two cheaper checks replace it: a per-generator
`sources` hash block (has the analysis moved) and a per-entry `checksum` (was
a generated value hand-edited). Provenance consolidated into
`_provenance.py`, which also stopped recording the contract modules — editing
`_assets.py`'s docstring used to mark every asset stale.

**Upgrading:** `just assets` once; add `inputs=[...]` to `st.write()`.

## 3.1.0

Subtraction: five things that stopped earning their place, mostly made
redundant by 3.0.0.

- **`.assets-stamp` removed.** assets.json had taken over both its jobs with
  strictly better messages. What went with it, stated plainly: an input a
  generator reads without declaring or importing is now invisible — and no
  mechanism can enumerate inputs and be right, so the author declares what
  matters. Mitigations: `_unclaimed` became an error; `record()` notes an
  empty input list.
- `check-assets-manifest` renamed to `check-assets` (the stamp freed the name).
- Removed: `source` in stats.json (write-only, superseded by `origin.by`),
  `s-unit()` (called by nothing), a stale root `__pycache__`.
- `verify` runs the two declaration checks as one stage.
- The figure/table docs stopped claiming "no wiring" — a new asset needs
  `record(...)`, an id reference, and (once per project) the wordcount eval
  scope.

**Upgrading:** `git rm .assets-stamp`; rename any `check-assets-manifest`
reference.

## 3.0.0

Everything generated is declared and referenced by id; nothing generated is
tracked in git; staleness is answered by content hashes, never git history.

- **paper.pdf untracked; `check-pdf` replaced by `check-build`.** Builds record
  a content stamp of their sources in the untracked `.build-stamp`; the check
  recompares. This also fixed two quiet holes: the docx mtime check's glob
  missed stats.json, and the git check's source list missed stats.typ and
  wordcount.typ. No check reads git any more, so everything works in an
  exported tree.
- **stats.json moved to the root and became a file you own.** Entries record
  `origin.by` (script or `"hand"`); a generator replaces only its own entries,
  so hand-added numbers survive `just assets` — previously `write()` rebuilt
  the file and they vanished. Hand entries require `origin.note`.
  `check-stats` re-runs guards against committed values and re-derives.
- **The rendered string left stats.json.** `value` + `fmt` only;
  `tools/render_stats.py` renders `stats-rendered.json` (gitignored,
  regenerated by every compile) through the one shared formatter,
  `typst_prose.display_of` — Typst has no format spec and rounds floats
  differently, so the display cannot be decided by whichever language reads it.
- **assets.json: figures and tables declared by `record(...)`, referenced by
  `fig("id")` / `tbl("id")`.** The manifest is on the compile path, so an
  undeclared id fails the build — the ledger is load-bearing, not bookkeeping.
  `prose-check` errors on a declared file named directly. Inputs are part
  automatic (the sys.modules walk — exact, since imports are Python-level)
  and part declared (data files — an audit hook cannot see C-level reads).
- Found while building it: a bare `fig()` call leaked into the word count and
  narration (both extractors strip it now); the first input walk recorded 257
  inputs for one figure because `analysis/.venv` is inside `analysis/`.

**Upgrading:** gitignore paper.pdf and .build-stamp, `git rm --cached
paper.pdf`; `git mv si/stats.json stats.json` and repoint stats.typ; add
`record(...)` to each generator; replace `image("figures/x.png")` with
`fig("id")` and `include "si/x.typ"` with `tbl("id")`; import and scope
`fig`/`tbl` in paper.typ, si-body.typ and wordcount.typ — missing the eval
scope leaves `just paper` working and `just wordcount` failing.

## 2.0.0

The scaffold became something that can be handed to someone else.

- **Toolchain moved to `tools/`** (the root is what a person edits and a build
  produces). Path constants became `ROOT = ...parent.parent`.
- **`scripts/new-paper.sh`**: the documented start was `cp -r`, which carried
  the scaffold's git history and made two checks answer the wrong question.
  The script copies with tar (symlinks survive), fills config.typ, builds both
  outputs, starts a fresh history. Tested in `tests/run.py`.
- **`just verify` and `just doctor`**: one command for the gate (the old
  instruction was a four-step ritual with conditions, and conditional rituals
  get skipped); one report of whether the external tools are present and new
  enough.
- **Typst floor is 0.14, not the obvious 0.13**: on 0.13 `just docx` exits 0
  and silently drops every figure. Measured, not read from a changelog. CI
  holds the floor.
- **CI**: the gate on a Typst matrix, a generated manuscript, and audio on
  Linux + macOS — because every prior bug was found by slow hand-porting.
- **Piper became a uv dependency** (abi3 wheels: Linux, both Macs, Windows),
  replacing an x86_64-only curl'd tarball.
- **The SI could not use generated numbers**: only paper.typ imported
  stats.typ, and `include` gives a file its own scope. si-body.typ imports it
  now.
- **Four extractor leaks fixed** (`#n()`, bare `#link("url")`, bare `#table(`,
  footnotes welding onto words), all with fixture cases.
- `.assets-stamp` gained an output hash, so a hand-edit to a generated file
  was finally caught. LICENSE (MIT) added; AGENTS.md symlinks CLAUDE.md.

## 1.6.0

The bibliography is checked. Offline in prose-check: `duplicate-reference`
(error; same DOI twice), `uncited-reference`, `missing-doi` (2000 onward —
older work predates DOIs), `implausible-year`. Online in `just bib-audit`:
every DOI against Crossref for resolution and retraction — not in `verify`,
because a gate that fails on a slow API gets skipped. The retraction check
shipped reading the wrong Crossref field and was caught only by testing
against a known-retracted DOI; a test pins the field.

## 1.5.0

Spell checking via codespell's confusion pairs, chosen by measurement: on
15,175 real words, pyspellchecker flagged 418 (the subject matter),
proselint 7 (mostly tool flags), codespell zero false positives and every
injected typo. Runs on code-removed prose. Words adjacent to a hyphen are
skipped (codespell's fragment entries fire wrongly on split compounds) but not
for the British list, which must catch `colour-coded`.

## 1.4.0

Severity and vocabulary became the project's call: `[severity]` re-rates any
rule, `[vocabulary.*]` adds/removes words. The `RULES` registry stays in
Python — it is a manifest of what the code implements, not configuration.

## 1.3.0

Print-proof checks: `low-resolution-figure` (effective dpi at the *rendered*
width, against the measured 160 mm text block — it immediately caught the
scaffold's own example at 227 dpi, fixed in the generator) and
`oversized-table` (columns, rows, longest cell; bracket-depth parsing because
a lazy regex cuts a cell at its first inner bracket; all three `columns:`
spellings including `(1fr,) * 12`).

## 1.2.0

- **`just draft`**: unresolved `#s()` renders as `?id?` in `paper-draft.pdf`,
  never `paper.pdf`, so a placeholder cannot reach a file mistaken for the
  paper. `n()` still fails — no placeholder can sit inside arithmetic.
- **`orphaned-asset`**: a generated file the manuscript no longer includes was
  regenerated forever while appearing nowhere.
- **audio/ became genuinely optional**: deleting it used to break `just all`
  and the test suite.

## 1.1.0

Numbers in prose are generated, guarded, and checked. `gen_stats.py` declares
them; `#s("id")` reads them back and panics on an unknown id; guards
(`sign=`, `between=`) fail the build when the analysis changes meaning under a
sentence; `derivable-number` flags a typed numeral matching a declared value.
Only distinctive values are compared — a declared `3` would match every `3`.

## 1.0.2

Five fixes from porting into a second manuscript (`koth`): native `#ref(` was
unrecognized (68 leaks); reference *sites* were counted as float definitions
(a phantom "Figure 10"); `tab:` labels were invisible to the float checks (37
tables exempt while reporting clean); `\u{XXXX}` escapes reached the narrator
verbatim ("log u 2082", 41 times); `word-repetition` fired on repeated file
paths (12 of 18 findings were noise).

## 1.0.1

Three fixes from porting into a real manuscript (`FeNovo`): `just fmt` rebuilt
the PDF (a backquoted string in a just message is a shell command); the
sentinel gap turned unwrapped inline code into a false doubled-word; CLAUDE.md
described checks removed in 1.0.0.

## 1.0.0

First release, extracted from the `dnoise` manuscript, where every piece was
written in response to something that had actually gone wrong. Typst build
with SI appended in one compilation; Word export via HTML + pandoc with the
template bypassed and equations rasterized; `config.typ` as the single
identity source; `analysis/` inside the manuscript writing directly to
`figures/` and `si/`; word counts, readability, density, prose-check;
typstyle formatting pinned to the same width as the editor; staleness checks;
offline Piper audiobooks.

---

## Decisions reversed

Each of these was built, shipped, and then undone. They are recorded because all
of them look reasonable in the abstract, and the reasons they failed are only
visible from use.

### Construct coverage in the placeholder prose

The first skeleton put one of every special-cased Typst construct into
`paper.typ`, so `just all` on a fresh clone was a smoke test. Placeholder prose
is deleted the moment real writing starts, so the test ran exactly once and
then the constructs went untested for the life of the project. Coverage now
lives in `tests/fixture.typ`, which is never part of the manuscript.

### A general "-ise to -ize" spelling rule

The regex for the whole `-ise` family flagged the project's own software name,
`dnoise`/`denoise`, on every mention. A checker that cries wolf on the
project's vocabulary gets switched off within a week. The British list is
explicit and grown by hand.

### Spell-checking inline code

`readability.clean` unwraps inline code into a bare word (journals count it),
and spell-checking that output flagged the column name `Ms1.Normalised` as a
British spelling. The spelling pass runs on a code-removed variant instead.

### Commit dates for generated-asset staleness

Comparing commit dates of `figures/` against `analysis/` cannot handle
deterministic generators: re-running after a no-op edit produces nothing to
commit, so the check nagged forever with no way to satisfy it. Content hashes,
no git.

### `figures.map` and an external analysis tree

The analysis was a sibling directory figures were copied out of. The copy was
the whole problem: a re-analysis updated the plot upstream, the copy stayed
put, and the PDF kept rendering a figure that no longer matched its own
caption. The analysis moved inside and writes to the destination.

### `fmt-verify`, and five other recipes

`just --list` reached 30 entries. `fmt-verify` was superseded, compared a
no-op, and restored via `git checkout --`, the most dangerous line in the
repo. The `.m4b` staleness checks went too: every prose edit marked the
audiobooks stale, clearing that cost minutes of narration, and a warning
almost always present and almost never acted on erodes trust in the rest.

### Re-deriving every value in `just verify` (3.0.0 → 3.2.0)

The strongest possible stats check, run on every verify — affordable only
because the scaffold's own generator reads a four-row CSV. On a real analysis
the gate costs the analysis. The general lesson: the scaffold cannot surface a
cost that scales with project size, so anything whose cost depends on scale
needs a deliberate "what does this look like at 1000×" pass, not a green gate
on the example.

---

## Bugs worth remembering

**A reflow can break the prose extractors.** typstyle breaks long lines inside a
call or an emphasis pair, so `#refn(<sec:x>)`, `_Saccharomyces cerevisiae_`, and
`#link(` all became multi-line forms. Patterns written for the one-line version
then leaked a bare `#refn(` into the word count and the narration, or left
literal underscores for the voice to pronounce. The PDF looked correct
throughout. The recognition patterns now live in `typst_prose.py`, shared by both
extractors, because each of those three fixes otherwise had to be made twice.

**Typst line continuations.** A method chain broken across lines after `#let x =`
or inside `[...]` ends at the first newline, and the continuation is parsed as
literal text. The error points at a closure parameter and reads
`unknown variable: a`. Wrap the chain in a code block.

**matplotlib stamps a creation date into PNG metadata.** Every regeneration then
looks like real drift. Pass `metadata={"Software": None}` and seed any RNG.

**A check can die silently when the thing it counts moves.** The CI
figure-survival check counted `image(` calls; the assets manifest reduced that
count to zero, and a comparison against zero passes forever. A counting check
must also fail when it counts nothing.
