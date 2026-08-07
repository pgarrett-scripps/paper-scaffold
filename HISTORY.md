# History

What changed in the pipeline, and why. Read the "Decisions reversed" section
before proposing a change that looks obvious. Several obvious things were tried
here and were wrong.

## Versioning

The version lives in one place, `version` in `pyproject.toml`, and travels with
the scaffold when it is copied into a project. `just version` prints it.

What bumps what is judged from the manuscript's point of view, not the code's:

- **Major** breaks a manuscript. An existing `paper.typ`, `si-body.typ`, or
  `analysis/` has to be edited to keep working. Renaming the BODY markers,
  changing where `analysis/` writes, or changing the `si/` include contract are
  all major.
- **Minor** adds a capability without touching an existing manuscript. A new
  check, a new metric, a new recipe.
- **Patch** fixes something without changing the interface. A regex that was
  missing a case, a wrong path, a doc correction.

Tag every release: `git tag -a v1.2.3 -m "..."`.

### Upgrading a project built on an older version

A project carries its version in its own `pyproject.toml`, and this file, both
copied at the time. To upgrade:

```bash
just version                                    # what the project is on
git -C ~/Repos/paper-scaffold log --oneline vOLD..vNEW
git -C ~/Repos/paper-scaffold diff vOLD..vNEW -- justfile tools/ tests/ scripts/
```

That path list was `justfile *.py tests/` before 2.0.0, when the toolchain sat
in the root. Upgrading from 1.x means the `*.py` half of it matches nothing and
reports a clean diff over the files that changed most.

Then apply what you want by hand. There is deliberately no automatic upgrade: a
manuscript directory diverges from the scaffold the moment real writing starts,
and a merge tool cannot tell your `paper.typ` from the placeholder it replaced.
Read the major entries below first, since those are the ones that need an edit
rather than a copy.

---

## 3.5.0

The README gained the pipeline's ideas as fifteen lines, and the lines were
then audited against the pipeline. Twelve held. Three did not, and the code
moved to match the claims rather than the claims to match the code:

**"A number worth stating is worth tracing"** was only enforced in one
direction: a typed numeral matching a declared value was flagged, but a
distinctive numeral matching *nothing* -- mistyped, stale from an earlier
draft, or from a source nobody recorded -- was the least traceable number in
the paper and the only silent one. `unaccounted-number` (warning) closes it:
compute it, declare it by hand with a note, or suppress it with a comment --
every path leaves a trail. Years and short counts are skipped, because a
checker whose warnings are mostly noise is one nobody reads.

**"Silence is not success -- fail where the mistake was made"**: a broken
`fmt` edited into stats.json passed `just verify` and killed the next build
inside render_stats instead. check-stats now renders every entry through the
same function the build uses, and names the entry.

**"The gate you run constantly must cost nothing"** was false at scale: verify
re-hashed every declared input and pinned file on every run, and a declared
input can be a multi-gigabyte HDF5 -- the 3.2.0 scale-blindness one layer
down. tools/hashcache.py adds a stat-keyed cache: (size, mtime_ns) decides
when to re-hash, the sha256 stays the only recorded truth, and the cache file
is disposable local state like .build-stamp. Recording paths (`just pin`, the
generators) still hash the bytes directly -- the moment a hash becomes the
recorded truth it is computed, not looked up.

---

## 3.4.1

Ten defects in the 3.3.0/3.4.0 code, found by an adversarial review of that
range and each verified before fixing. The theme: the ownership split made
stats.json hand-edited JSON, and hand-edited JSON can be malformed in ways the
code either crashed on or -- worse -- silently accepted.

The dangerous ones:

- **A malformed `values` block deleted every hand entry.** write() replaced a
  non-dict block with `{}` and rewrote the file with only its own entries. It
  now refuses, like the invalid-JSON case always did.
- **A stale seed guard silently disabled deep re-derivation.** _rederive ran
  the generator against an empty shadow, so every entry counted as new and the
  seeds -- not the file's author-edited guards -- judged the values. Widening a
  guard in stats.json (the documented workflow) made the shadow run die on the
  stale seed, and the death was downgraded to a note: preflight reported OK
  while the one check that recomputes numbers never ran. The shadow now starts
  as a copy of the real file, and a guard violation there is an error.
- **NaN passed every range guard.** The per-bound rewrite (`v < lo or v > hi`)
  is False for NaN where the old chained comparison flagged it. NaN is now an
  explicit error in both the generator and the gate.
- **A guard the code did not understand was a guard that never fired.**
  `"expect": {"between": [0, 1]}` -- mirroring add()'s own argument name -- was
  silently ignored; `"min": "0"` was a TypeError that killed the gate without
  naming the entry; a list-shaped `pinned` block was an AttributeError in both
  check-stats and `just pin`. All are named error findings now.
- **Deleting an author-owned field resurrected the seed.** `old.get(f, seed[f])`
  fell back to the add() argument when the author deleted a key, reinstating a
  retired guard from the file that no longer contained it. Deletion is an edit:
  the field stays deleted, and the stale seed is reported in the IGNORED note.

The wrong-signal ones:

- A v1-checksum mismatch is a warning, not an error: v1 covered value AND fmt,
  so it cannot tell the now-documented fmt edit from tampering, and failing the
  gate punished the documented workflow on exactly the clones that cannot run
  `just assets` to clear it.
- `just pin` no longer marks both outputs STALE: the build stamp hashes
  stats.json without its `pinned` block, since no build renders the pins.
- `origin.at` moves when 35 becomes 35.0: the value comparison now checks type,
  because the file's representation and checksum change even when Python's `==`
  says nothing did.

---

## 3.4.0

Three holes between "the checks pass" and "the file being submitted is not
stale", found by auditing the guarantee chain end to end and demonstrating each
one before fixing it.

### check-build now checks the output, not just the sources

The build stamp recorded only the hash of the sources. That proves a build
happened from them -- not that the paper.pdf on disk is that build's output. A
PDF overwritten, truncated, or restored from Downloads after the build passed
as "current with the source", demonstrated by replacing it with a line of text.
`_record-build` now records the output's own hash too, and check-build reports
the mismatch as REPLACED. A stamp from before this change reports UNKNOWN; one
rebuild upgrades it.

The source stamp is also captured BEFORE the compile now. Stamping afterwards
meant an edit saved mid-compile was claimed as built; capturing first errs
toward stale, which is the safe direction.

### `just preflight`: the submission gate as one command

check-stats-deep, bib-audit and fresh builds were each documented as "run
before submitting" -- three commands in three places, a conditional ritual, and
conditional rituals get skipped (the reasoning that created `verify`).
`preflight` is that ritual as one command: build both outputs fresh, run the
whole verify gate, re-derive every generated number, audit every DOI. As slow
as the analysis plus the network, which is why it is not `verify`.

Deliberately not included: `just assets`. Regenerating every figure is a
rebuild, not a check, and check-assets already reports when the analysis has
moved out from under the committed figures.

### render-stats removes its output when the source is gone

A stats-rendered.json outliving a deleted stats.json was a corpse a compile
could still read -- the one way the render step could serve stale numbers.

---

## 3.3.0

stats.json's entries were owned whole by whichever script wrote them, which put
editorial decisions in the wrong file: changing how a number is typeset, or what
the prose assumes about it, meant editing the analysis. The ownership is now
split by field, following what each field is.

### The script owns the value; the author owns everything else

In a generated entry, the script writes `value`, its `checksum`, and `origin`.
`fmt`, `unit`, `desc` and `expect` are the author's, edited in stats.json, and
survive `just assets` -- the arguments to `st.add(...)` beyond the value are
seeds that populate a NEW entry and are ignored afterwards. A seed that differs
from the file is ignored WITH A NOTE, so a stale script argument is visible
rather than silently fighting the file.

Two consequences worth naming:

- The fresh value is judged against the guard as it stands in the file -- the
  one the author maintains -- not against whatever the script passed. A guard
  violation still fails `just assets`, now naming stats.json as where the
  assumption lives. One-sided bounds (`min` with no `max`) are supported,
  including in `check_stats`, whose range check previously required both bounds
  and silently skipped a one-sided one.
- The checksum narrowed to the value alone ("v2"). v1 also covered fmt, from
  when fmt was script-owned; editing fmt must not read as tampering now. v1
  checksums are still verified, so an existing manuscript upgrades cleanly and
  the next `just assets` rewrites them.

This also dissolves a hole rather than patching it: hand-editing `expect` on a
generated entry used to be undetectable drift that the next regeneration
silently reverted. It is now the supported way to state an assumption.

### Pinned files: watching what no script reads

The provenance recorded automatically stops at what a generator imported or
declared. For files that matter without any script reading them -- a raw
export, a protocol document -- the author declares a `pinned` block in
stats.json (`"path": null`) and runs `just pin` to record the hash. From then
on `just check-stats` reports a change, and accepting one is deliberate: re-run
`just pin`. Generators carry the block through untouched.

### `origin.at`: when it last changed, not when the script last ran

Every stats entry and every asset records `origin.at`. A regeneration that
reproduces the same value or byte-identical output keeps the old date, so the
timestamp carries information instead of churning on every `just assets`.

### Fixed

- **The CI "every figure survives the Word export" check was dead.** It counted
  `image(` calls in the sources, which went to zero when figures moved behind
  the assets manifest -- so it compared against zero and passed forever. It now
  counts `fig("` references (plus direct `image(` calls) with comments
  stripped, and fails outright when it finds none, so it cannot silently die
  the same way twice.
- `.build-stamp` now covers the three tools that shape the output
  (render_stats.py, typst_prose.py, typst2docx.py): editing them changes what a
  build produces, and used to leave paper.pdf looking current.
- Stale references: gen_stats.py and analysis/justfile still said stats.json
  lived under si/; CLAUDE.md and README named a `check-assets-manifest` recipe
  that is actually `check-assets`; .gitignore listed an intermediate that no
  longer exists; the justfile's viz and bib-audit doc comments had been
  interleaved by an edit.

---

## 3.2.0

`just verify` re-ran the analysis. That was a bug in 3.0.0 and it hid behind the
scaffold's own numbers: `check-stats` re-derived every value by re-running
gen_stats.py, which here reads a four-row CSV and costs 0.02s. On a real project
whose stats generator does real work, the gate cost the analysis -- every time,
for a command CLAUDE.md describes as rebuilding nothing and safe to run
constantly.

The code even carried the precondition in a comment ("affordable only because
gen_stats.py is a single fast script") without anything guaranteeing it.

### Re-derivation is opt-in

`just check-stats` now reads files and nothing else. `just check-stats-deep`
re-runs the generator and diffs, and is what to run before submitting. `verify`
calls the cheap one.

Nothing was lost from the default path, because two cheaper checks replace what
re-derivation was covering:

- **`sources`**, a per-generator block of `{path: sha256}` covering the script,
  every module it imports from `analysis/`, and the data files it declares. This
  answers "has the analysis behind these numbers moved" without running it.
  Recorded once per generator rather than per entry, so a thousand values do not
  carry a thousand copies of the same map.
- **`checksum`**, a per-entry digest of `value` + `fmt` written by the generator.
  A hand-edited generated value does not know to update it. Protection against
  accident, which is the threat model; nothing that keeps the record beside the
  value can do better.

Verified both catch their case with the analysis untouched: a changed CSV reports
the source moved, and a value edited to 999 reports the checksum mismatch.

### Provenance moved into one module

`_stats.py` and `_assets.py` had separate copies of the hashing and the
sys.modules walk. Both now import `analysis/scripts/_provenance.py`.

While consolidating, the walk stopped recording the contract modules themselves.
`_assets.py` was an input to every asset it wrote, so editing its DOCSTRING
marked every figure and table in the manuscript stale -- the one file guaranteed
not to affect any output was also the one guaranteed to invalidate all of them.

**Upgrading:** run `just assets` once to write the `sources` block and the
checksums. Add `inputs=[...]` to `st.write()` naming the data your generator
reads, or it will say it cannot detect data changes.

## 3.1.0

Subtraction. Nothing new here -- five things came out that had stopped earning
their place, most of them made redundant by 3.0.0 rather than wrong to begin
with. Minor rather than major: no manuscript has to change, though a recipe
disappeared and a check got weaker.

### `.assets-stamp` is gone

Two whole-tree hashes, and `assets.json` had quietly taken over both jobs.
Measured before removing it:

| Case | assets.json | .assets-stamp |
|---|---|---|
| generated file edited by hand | error, names the file and its generator | error, "figures/ or si/ has changed" |
| generator edited, not re-run | error, names which figure it ruins | error, "analysis/ has changed" |
| unclaimed file appears | warn, names it | error |
| new `analysis/` file nothing imports | silent | error |

Redundant in the first two rows, with a strictly worse message. Unique only in
the fourth, where it is arguably wrong: a file no generator imports cannot have
changed any output, so it nagged about a change that changed nothing and was
cleared by regenerating identical bytes.

**What went with it, stated plainly:** an input a generator READS without
declaring or importing is now invisible to every check. The stamp caught that
when the file happened to sit under `analysis/` outside `data/` -- which is to
say, its coverage was a function of file location rather than of whether the file
mattered, since `data/` is where data lives.

That is the real argument for the removal, and it is stronger than "redundant".
No mechanism can enumerate a generator's inputs and be right: an audit hook
misses C-level reads, a directory hash misses everything outside it and fires on
changes that altered nothing. The scaffold now declines to pretend otherwise and
puts the decision where the knowledge is -- the author says which files matter.
An explicit partial answer beats an implicit one that looks total.

Two mitigations, neither a full replacement:

- `_unclaimed` in check_assets.py went from warning to **error**, restoring the
  severity the stamp gave the leftover-output case -- the one failure that leaves
  a figure frozen with nothing able to refresh it.
- `record()` now prints a note when a generator declares no `inputs` at all, so
  the omission is visible where it is made.

**Upgrading:** `git rm .assets-stamp`, delete it from `.gitignore` if it is
listed, and drop any reference to `just check-assets` meaning the stamp -- that
name now belongs to the manifest check.

### `check-assets-manifest` is `check-assets`

The stamp's departure freed the name. Two checks called `check-assets` and
`check-assets-manifest` was a coin flip every time.

### `source`, `s-unit`, and a stale cache

- **`source`** in stats.json was write-only: `_stats.py` wrote it, nothing ever
  read it, and nothing verified it. It predated `origin.by`, which names the
  script that wrote a value and IS checked. One provenance field now, the true one.
- **`s-unit()`** in stats.typ was defined, documented, and called by nothing.
  Gone, and `render_stats.py` stops emitting `unit` into the rendered file. `unit`
  stays in stats.json: unlike `source` it describes the value rather than
  duplicating its provenance, and an auditor reading the file wants it.
- **A root `__pycache__`** left over from before the 2.0.0 `tools/` move, some of
  it `cpython-312` bytecode for modules that have not lived there in two releases.

### `verify` runs five stages, not six

`check-stats` and `check-assets` answer the same question -- are the declarations
still consistent with what produced them -- so they run under one `declarations`
stage via `just check-declared`. Both remain separate recipes underneath, so
either can be run alone while working on it.

### The figure/table docs stopped claiming "no wiring"

They still said a new table needs no wiring beyond the filename pattern, which
has been false since 3.0.0: it also needs a `record(...)` call, an id reference in
the prose, and -- for the project's first one -- `fig`/`tbl` in `wordcount.typ`'s
eval scope. That last omission leaves `just paper` working and only
`just wordcount` failing, which is the least obvious way for it to break. The
README now lists all four steps and says why the last two are worth their cost.

## 3.0.0

Everything the analysis produces -- numbers, figures, tables -- is now declared
in a manifest and referenced by id, and every output stopped being tracked in
git. Two threads, and they meet in the same place: staleness is answered by
hashing content, never by asking git what it remembers.

Major, and this time by the letter of the policy as well as its spirit.
`paper.typ` and `si-body.typ` reference figures and tables differently,
`si/stats.json` moved, `analysis/` scripts gained a call they did not have, and
`just check-pdf` no longer exists.

### paper.pdf is no longer tracked, and no check reads git

`paper.pdf` was tracked so a reader could get the manuscript without installing
Typst. That is a real benefit and it was not worth the cost: git keeps every
version of a binary forever, a clone pays for all of them, and getting one back
out means rewriting history. Ship it as a release asset or a CI artifact.

`just check-pdf` went with it, because it compared git commit dates and there is
no longer a commit to compare. `just check-build` replaces it. `just paper` and
`just docx` each record the sha256 of every source they rendered into
`.build-stamp`; the check recomputes and compares.

`.build-stamp` is untracked too, and has to be: it describes local build output.
Tracking it would mean a rebuild on one machine reports every other checkout
stale, for a file those checkouts do not have.

The separate mtime check for `paper.docx` is gone, folded into the same
mechanism. It had been quietly wrong: its input list globbed `si/*.typ`, which
does not match `si/stats.json`, so changing a generated number never marked the
Word export stale. The old git check had its own version of the same hole --
`stats.typ` and `wordcount.typ` were not in its source list, so editing either
left the PDF looking current. Both are covered now.

No check reads git history any more, which means they all work in an exported
tree, a shallow clone, or no repository at all. CI dropped `fetch-depth: 0`.
`just doctor` no longer lists git as required by anything.

**Upgrading:** add `paper.pdf` and `.build-stamp` to `.gitignore`, run
`git rm --cached paper.pdf`, and rebuild once so the stamp exists. A recipe that
called `just check-pdf` should call `just check-build`.

### stats.json is a file you own

It moved from `si/` to the manuscript root, and that is not cosmetic. `si/` means
"written by the analysis, never edit" everywhere else in this directory, and this
file is now one you are invited to edit.

Every entry records `origin.by`: the script that generated it, or the literal
`"hand"`. A generator replaces only its own entries when it runs, so a number
typed in by hand survives `just assets` instead of being silently overwritten by
the next one. That was the actual bug: the old `write()` rebuilt the whole file
from scratch, so anything added by hand lasted until the next regeneration and
then vanished.

A hand entry must carry `origin.note` saying where the number came from. It is
guarded exactly as tightly as a derived one; what it cannot have is
re-derivation, so the note is the audit trail instead.

`stats.json` came out of the `.assets-stamp` output hash, necessarily: that hash
exists to report any edit as wrong, and editing is now the point.

### `just check-stats` replaces the hash that used to guard it

Per entry, rather than one hash over the file:

- every `expect` guard re-run against the value **as committed**. Previously
  guards fired only while `gen_stats.py` ran, which did nothing for a value
  edited afterwards and nothing at all for a typed one.
- `gen_stats.py` re-run into a scratch file and diffed, so a generated number
  edited by hand is caught outright. This is the one check here that establishes
  something rather than checking consistency, and it is affordable only because
  that generator is a single fast script. There is no equivalent for figures.
- `display` re-derived from `value` and `fmt`, catching an edit to one that no
  longer matches the other -- the edit that changes what a reader sees without
  changing what `#n("id")` computes with.

### The rendered string left stats.json entirely

`display` used to sit beside `value` in every entry, and `"display": "3"` for the
value `3` carried nothing at all. It was a derived field living in a source file:
redundant, able to drift, and it needed its own check to notice when it had.

Formatting moved into the build instead. `stats.json` holds the `value` and the
`fmt`; `tools/render_stats.py` renders them into `stats-rendered.json`, which is
what `stats.typ` reads. Nothing is stored twice, so nothing can drift, and the
check that guarded the disagreement was deleted along with the field.

The step is needed because Typst cannot do the job: it has no format spec, and
its `str()` rounds floats where Python's does not -- `1.0899999999999999` is
`1.09` there and the full expansion here. So the display would otherwise be
decided by whichever language happened to read the value.

`typst_prose.display_of` is the single formatter, called by the renderer and by
the extractors, so the PDF, the word count and the narration cannot disagree
about what a number looks like.

`stats-rendered.json` is gitignored and regenerated by `just paper`, `just docx`,
`just draft` and `just wordcount`, so it is never stale. `typst compile paper.typ`
by hand now needs `just render-stats` first.

**Upgrading:** delete `display` from every entry in `stats.json` (or just re-run
`just assets`), and add `render-stats` as a dependency of any custom recipe that
compiles Typst.
- a `by` naming a script that no longer exists.
- a hand entry with no note.
- ids nothing reads (a warning; the opposite direction already panics at compile).

**Upgrading:** `git mv si/stats.json stats.json`, repoint `json("si/stats.json")`
in `stats.typ`, and run `just assets` once. Entries written before this release
have no `origin`, and the first generator to declare one claims it -- so the
upgrade is a no-op rather than a conflict.

### Figures and tables are declared and referenced by id

`assets.json` is the same contract for files. Each generator calls `record(...)`
to declare what it wrote; the manuscript references the id:

```typst
#figure(fig("fig.example", width: 70%), caption: [...]) <fig:example>
```

The indirection is the entire point, and it is worth being precise about why. A
manifest that sits beside the files it describes rots, because nothing reads it
and nothing notices when it stops being true. This one is on the path the compile
takes: an undeclared id stops the build the same way an undeclared `#s("id")`
does. The ledger is load-bearing rather than bookkeeping.

Verified before building on it that Typst accepts a computed path for both
`image()` and `include`, on 0.14.2, the version floor. `include` was the one in
doubt -- `import` requires a literal -- and it works.

`just check-assets-manifest` then checks per entry: the output still hashes to
what was recorded, the generator still exists, and the declared inputs are
unchanged. The first two are attributed to a specific file, which the old
`analysis/ has changed` could not do. The third is new capability: `_stamp-source`
deliberately skips `analysis/data/`, so a changed dataset was invisible to every
check in the pipeline.

A new `bypassed-asset` error in `prose-check` reports a declared file named
directly rather than through its id. Without it the mechanism is opt-in and
erodes on the first hurried edit.

Inputs are part automatic and part declared, and the split is deliberate. The
generator and every module it imports from `analysis/` are recorded by walking
`sys.modules`, which is exact because an import is always Python-level. Data
files are declared by hand. The automatic version was considered and rejected:
an audit hook on `open` cannot see the reads HDF5, parquet and most binary
readers do from C, so it would record an empty input set for precisely the
formats that matter. A missed input means a stale figure reported as current --
failing open, where every other check here fails closed.

`.assets-stamp` is kept for that reason. It over-approximates and nags; the
manifest under-approximates because it only knows what was declared. Dropping it
would trade a check that fails closed for one that fails open.

**Upgrading:** add `record(...)` to each generator, import `fig`/`tbl` in
`paper.typ` and `si-body.typ`, replace `image("figures/x.png")` with
`fig("id")` and `include "si/x.typ"` with `tbl("id")`, and add both to
`wordcount.typ`'s eval scope. That last one is the step that bites: the import
alone is not enough, the scope names them again, and missing it leaves
`just paper` working while `just wordcount` fails with `unknown variable: fig`.

### Two bugs found by testing rather than by reasoning

**A bare `fig()` call leaked into the word count and the narration.** Nearly
every call is inside a `#figure(...)` that is stripped whole, so the case was
easy to miss by inspection; a bare one in running prose came through verbatim,
id and all, to be counted as words and read aloud. Both extractors strip it now,
with fixture cases including the reflowed and layout-argument forms.

**The first `_code_inputs()` recorded 257 inputs for one figure.** `analysis/`
contains `.venv/`, so "every imported module under analysis/" meant every
site-package the generator touched -- PIL, matplotlib, the lot. Left in, a
dependency upgrade would have marked every figure stale.

### Also

- `analysis/justfile`'s `clean` no longer deletes `stats.json`. It holds
  hand-entered values as well as generated ones, and deleting it to "clean"
  throws away the half no script can rebuild.
- `check_orphaned_assets` skips anything declared in `assets.json`. It matches
  filenames against the prose, and once assets are referenced by id the filename
  never appears there, so every declared asset looked orphaned.
- `_stamp-manuscript` covers `stats.json`, `assets.typ` and `assets.json`.
- `new-paper.sh` excludes `.build-stamp` from the copy, with a test. Inherited,
  it would claim the new paper's outputs were built from sources it has never
  seen, and `just check` would report clean on day one.

## 2.0.0

The scaffold became something that can be handed to someone else. Until now it
was a directory that worked on the machine it was written on, documented well
enough to be copied by hand. Most of this release is the difference between
those two things, and most of the bugs below were found by asking what happens
on a machine that is not this one.

Major because the layout changed. Nothing in `paper.typ`, `si-body.typ` or
`analysis/` has to be edited, so by the letter of the policy above this is a
minor. It is a major anyway, because the upgrade instructions themselves broke:
the toolchain is no longer `*.py` in the root, and a 1.x project running the old
diff command sees a clean result over the files that changed most. A version
number that makes someone read the entry is doing its job.

### The toolchain moved to `tools/`

The root had reached 28 files, nine of them Python and shell that nothing in the
manuscript imports -- they all read it. That is the split: the root is what a
person edits and what a build produces, `tools/` is what processes it. 19 files
left in the root, and a layout map in the README, which it never had.

Six tools defined `HERE = Path(__file__).resolve().parent` meaning "the
manuscript root", which stopped being true when they moved down a level. They
are `ROOT` now and point at `.parent.parent`; a variable called HERE pointing at
its parent directory is how the next bug gets written.

**Upgrading:** create `tools/`, move `prose_check.py`, `prose_rules.py`,
`readability.py`, `typst_prose.py`, `typst2docx.py`, `density.py`, `viz.py`,
`bib_audit.py` and `wordcount.sh` into it, fix those path constants, and take the
new `justfile`. `audio/extract_prose.py` and `tests/run.py` both reach for the
shared patterns and need their `sys.path` updated too.

### Starting a paper: `scripts/new-paper.sh`

The documented way to start a manuscript was `cp -r`, which copies `.git` along
with everything else. The new paper then carried the scaffold's history, and two
checks answered the wrong question while reporting confidently: `check-pdf`
compared the paper against the *scaffold's* commits, and `just version` reported
the scaffold's last commit as the manuscript's state.

The script copies the working files, fills in `config.typ`, builds the first PDF
and Word export, and starts a history belonging to the paper. Interactive, or
every field as a flag.

Three things it does that are not obvious. It copies with `tar`, not `cp -r`, so
the `AGENTS.md` symlink stays a symlink rather than becoming a second copy of
CLAUDE.md free to drift. It builds the PDF *before* the first commit, because
`check-pdf` compares commit dates and the reverse order makes a brand-new
manuscript report itself stale. And it builds the Word export nobody asked for on
day one, because `paper.docx` is gitignored and `just check` reports a missing
one -- without it the first thing a new manuscript does is fail its own gate.

It is tested in `tests/run.py` rather than as its own recipe, and skips itself in
a derived manuscript, where `scripts/` is gone: a paper does not make papers.

### `just verify`, and `just doctor`

`verify` runs `fmt-check`, `test`, `prose-check` and `check` in one pass,
rebuilding nothing. Every part of it already existed and was already documented;
what did not exist was a single thing to run. The instruction was a four-step
ritual with two conditions in it ("if you changed prose...", "if you changed
inline markup..."), and a conditional ritual is one people skip -- the conditions
need a judgement about which files a change touched that is easy to get wrong
from inside the edit. CLAUDE.md is now `just paper && just verify`.

`doctor` reports whether the external tools are present and new enough, instead
of leaving a missing one to surface as "command not found" from inside whichever
recipe needed it first. `just setup` depends on it, because `uv sync` succeeding
proves nothing about typst.

### The Typst floor is 0.14, and the obvious answer was wrong

`--features html` and `html.frame()` both arrived in 0.13, so 0.13 is the
obvious floor. On 0.13 `just docx` runs, exits 0, and silently contains **no
figures**: that version's HTML export emits no `<img>` for an `image()` call,
while tables and the rasterized equations survive. The result is a .docx that
looks finished with every plot missing.

Established by running 0.13.1, 0.14.2 and 0.15.1 through `just docx` and
comparing the output, not by reading a changelog.

CI holds the floor by counting `<img>` in the export against `image()` calls in
the source. Counting embedded images in the .docx cannot do it, and that was the
first attempt: 0.13 keeps both rasterized equations, so the file still contains
images and still looks fine.

### CI

Every bug in this repository's history was found by hand-porting the scaffold
into another manuscript. That works and it is slow, and it only happens when
someone starts a paper.

Three jobs: the gate across a Typst version matrix, a generated manuscript built
from `new-paper.sh` and checked, and the audio toolchain on Linux and macOS.
Tools install from pinned release binaries by curl rather than marketplace
actions.

### Piper is a uv dependency

The audiobooks were the one part of this directory that could not run on a Mac.
Piper was a binary tarball fetched by curl, pinned to a release that shipped
x86_64 Linux only. `piper-tts` on PyPI ships abi3 wheels covering Linux, both
Macs and Windows, and installs with everything else -- which is what pandoc and
ffmpeg already did here.

Narration is a library call now rather than a subprocess, so the ONNX model
loads once instead of once per chapter. `VOICE_LANG` is gone: it held a
hand-built path into a HuggingFace repo that had to be kept in step with
`VOICE_NAME`, and a mismatch arrived as a 404 that read like a network failure.

The migration left `_audio-check` still gating on `piper/piper`, which is the
kind of thing that passes locally forever. Only a fresh clone would have hit it.

### The SI could not use generated numbers

Only `paper.typ` imported `stats.typ`, and Typst's `include` gives the included
file its own scope, so `#s("id")` anywhere in `si-body.typ` failed with
`unknown variable: s` one line below a file that imports it. The SI is the
data-heavy half and is where a generated number most belongs.

The two sides disagreed, which is the worse half. `readability.py`,
`wordcount.typ` and the SI narration all resolve `#s()` out of `si-body.typ` and
always did, so the tooling reported a number the compiler refused to produce.

**Upgrading:** add `#import "stats.typ": n, s` to `si-body.typ`.

Removing the mechanism was also documented wrong. Three `.typ` files import it,
and `wordcount.typ` names the helpers a second time in its eval scope, so the old
instructions left `just paper` working and `just wordcount` failing -- the
command you run constantly is fine and the one you run before submitting is not.
Now a four-step procedure, verified by doing exactly it to a copy.

### Four extractor leaks

`#n("id")` was never handled at all. Rarer in prose than `s`, and an unhandled
one put the call text verbatim into the word count and gave the narrator
`#n("cohort.total_n")` to read aloud.

The other three came from testing constructs the fixture did not contain, which
is the trap a fixture sets: everything in it passes, and what a real manuscript
uses instead was never looked at.

- **A bare `#link("url")` leaked entirely.** The pattern required the
  `[shown text]` bracket. `#link("https://...")` with no body is valid Typst
  that renders the URL as its own visible text, and it is what a data- or
  code-availability statement is written with -- the one section every paper now
  has. This is the `#ref(` failure again, which reached 68 places.
- **A bare `#table(` in prose leaked.** Only `#figure(` was stripped.
- **A footnote welded onto the word it annotates.** The generic `#name[` rule is
  gap-free on purpose, so `H#sub[2]O` stays "H2O". A footnote attaches the same
  way and must not: "high#footnote[...]" counted and narrated as one word.

All four have fixture cases. Links now go through `strip_links()` in
`typst_prose.py`, shared, because these two extractors have been fixed
separately three times already.

Probed at the same time and found correct, so unchanged: `config.typ`'s
`surname-of` across suffixes, single names, hyphens and particles, and all four
draft-mode behaviours.

### `.assets-stamp` carries two hashes

The stamp covered the analysis *source*, so it caught a generator edited and not
re-run. It never caught the reverse: an edit to the *generated* file. That is the
rule CLAUDE.md states most loudly and nothing enforced it, and the failure is
quiet and total -- the edit renders, every check reports current, and the next
`just assets` overwrites it. An "AUTO-GENERATED" header is a request; this is a
check.

**Upgrading:** run `just assets` once to rewrite the stamp in the new two-line
form. The old single-hash file is reported as stale rather than guessed at.

### Distribution

`LICENSE` (MIT). The whole use case is copying this directory, which nobody
could legally do. `new-paper.sh` carries it into a new project renamed
`LICENSE.scaffold`, so a `LICENSE` at a manuscript root does not read as a claim
about the paper.

`AGENTS.md`, a symlink to `CLAUDE.md`, so tools following either convention read
one document. A symlink rather than a copy for the reason everything else here
is shared: the copy drifts, and the drifted one is what the agent read.

## 1.6.0

**The bibliography is checked.** It was the last artifact in the directory that
nothing read. Typst already fails on a citation with no entry, so only the
reverse directions were open, and all of them survive every rebuild silently.

Offline, in `just prose-check`:

- **`duplicate-reference`** (error) -- two keys, one DOI. The same work entered
  twice is how a manuscript ends up citing one paper inconsistently.
- **`uncited-reference`**, **`missing-doi`**, **`implausible-year`** (warnings).

Two decisions came from running it against a real 52-entry bibliography:

*Not duplicate title.* A title match flagged `pxd070049` and
`vanpuyvelde2026genbeta` -- a PRIDE dataset and the preprint describing it, which
share a title and are correctly cited as two things. Duplicate DOI is the signal
that means what it looks like.

*`missing-doi` only from 2000 onward.* DOIs were introduced then and older work
was retrofitted patchily, so demanding one from a foundational 1952 citation
reports an absence nobody can fix, on exactly the references papers cite most.
Both of this scaffold's own example entries are pre-DOI, and the rule flagged
both before the era check went in.

**`just bib-audit`** (new recipe) checks every DOI against Crossref: does it
resolve, and has the work been retracted? Online, so it is deliberately NOT in
`just verify` -- a gate that can fail because an API was slow is one people learn
to skip. Being offline is reported, not failed.

The retraction check shipped wrong the first time and looked right. Crossref
relates a paper and its notices in both directions: `update-to` lives on the
NOTICE and points at what it retracts, `updated-by` lives on the PAPER. Reading
`update-to` returned nothing for the Wakefield MMR paper, retracted since 2010.
Caught only by testing against a known-retracted DOI rather than reading the API
docs and believing them. A test now pins the field name.

Against the 52-entry bibliography this was developed on: 50 DOIs checked, none
retracted, none unresolvable.

## 1.5.0

**`misspelling`, from codespell's dictionary.** Runs on the same code-removed
prose the British-spelling check uses, so a tool's own flag is never reported as
a typo.

The choice of tool is the whole point, and it was made from measurement rather
than preference. Three candidates were run against 15,175 words of a real
manuscript:

- **pyspellchecker** flagged 418 words, 18% of the vocabulary. After discarding
  hyphenated compounds whose parts are all known, 181 remained, and they were
  `bruker`, `cerevisiae`, `centroider`, `ddapasef`, `carbamidomethyl`,
  `bonferroni` -- essentially no typos. A dictionary check asks "is this word in
  the wordlist", which on a scientific manuscript flags the subject matter.
- **proselint** produced 7 findings, of which 3 were `--reanalyse`, a DIA-NN
  command-line option it could not tell from prose. This pipeline already solves
  that, which is exactly why the check has to run on cleaned prose.
- **codespell** produced **zero** false positives and caught every injected typo.
  It ships curated confusion pairs rather than a dictionary, so it only fires
  when confident.

Zero findings on a finished manuscript is the right result: the check costs
nothing now and is there for the next typo typed.

One implementation note worth keeping. Matching word-by-word disagreed with
codespell on exactly one token: `mis-transferred`. codespell's list contains
fragments that are wrong only standing alone (`mis -> miss, mist`), so splitting
a compound and matching its prefix invents a finding codespell itself does not
make. Words adjacent to a hyphen are therefore skipped by this check and NOT by
the British one, whose list is curated and must still catch the `colour` in
`colour-coded`. Both behaviours have cases.

Grammar checking was considered and rejected for now. `language_tool_python` is
the only serious option; it needs Java 17 or newer and downloads about 250 MB, so
it breaks the clone-and-run property. If it is ever added it belongs behind its
own recipe with `just doctor` reporting the JVM, never in `just verify`.

## 1.4.0

**Severity and vocabulary are the project's call.** Before this, a rule could be
switched off or have named values exempted, and its thresholds could be moved,
but two things were fixed in Python: whether a rule was an error or a warning,
and the word lists it judged against.

Both are project policy, not properties of the checker. Whether an em dash should
stop a build depends on the house style; whether "essentially" is filler depends
on the field. A checker you cannot teach gets switched off wholesale, which is
the outcome every one of these rules exists to avoid.

- **`[severity]`** re-rates any rule, in both directions. `long-sentence` can be
  an error before submission; `em-dash` can be a warning for a group that
  tolerates them. Applied in `report()` rather than where each Finding is built,
  so there is one place to get right and no check needs to know the config
  exists. `Finding` is frozen, so it rebuilds rather than assigns -- the first
  version silently did nothing, and the test now covers exactly that.
- **`[vocabulary.<name>]`** takes `add` and `remove` for `verbose-phrase`,
  `british-spelling`, `common-words` and `abbreviations`. The shipped lists
  become a starting point instead of a verdict.

What did NOT move, and why: the `RULES` registry stays in Python. It is not
configuration, it is a manifest of what the code implements, and a test asserts
every rule the checker can emit is declared there. Putting it in TOML would not
let anyone add a rule -- there would be no implementation behind it -- it would
only split one tightly-coupled pair across two files where they can drift.
`DEFAULT_LIMITS` stays for the same kind of reason: it is already overridable in
`[limits]`, so shipping the defaults as TOML too would add a file without adding
a capability.

Also: `--list-rules` computes its column width from the longest rule name.
`low-resolution-figure` was one character past the hard-coded guess and pushed
its own row out of line.

## 1.3.0

Two checks for the defects that only appear in the proof, when the analysis is
finished and regenerating an asset is most annoying.

**`low-resolution-figure`.** The number that matters is not what the file stores,
it is pixels divided by the width the figure is actually rendered at. Effective
dpi is computed from the `width: NN%` in the `image(...)` call against the text
block, with no width treated as full width, which is how Typst scales an image to
its container. Vector formats are skipped, having no resolution to be below.

The default text width, 160 mm, is this scaffold's arkheion page measured with
`typst query` (A4 less 25 mm margins), not a plausible-looking guess. Change
`figure-text-width-mm` if you change the page, or every dpi is computed against
the wrong ruler.

The check immediately caught the scaffold's own example figure at 227 dpi. Fixed
in the generator rather than suppressed: a template that ships below its own
standard teaches the wrong thing.

**`oversized-table`.** Columns, rows, and the longest cell. A generated table
grows a column per condition or a row per run, and the first sign is a proof
where the columns are unreadably narrow, a header is stranded on the previous
page, or one long cell wraps to three lines and drags its row with it. None of
that is visible from the source.

Cells are found by tracking bracket depth, not by a non-greedy `\[.*?\]`, because
a cell legitimately contains brackets of its own and the lazy match cuts it at
the first inner close -- a long cell containing a link would measure as a few
characters and pass. `columns:` is read in all three spellings, including the
repeat form `(1fr,) * 12`: read as a bare tuple it counts one column and every
row count derived from it is wrong by that factor. Both have regression cases.

New limits, all overridable in `prose-check.toml`: `min-figure-dpi` (300),
`figure-text-width-mm` (160), `max-table-columns` (8), `max-table-rows` (40),
`max-cell-chars` (60).

Each check was confirmed to fail its tests when disabled.

## 1.2.0

Three additions, all additive.

**`just draft`.** `#s("id")` panics on an unknown id, which is right for a real
build: a number that stopped existing must not render blank. While drafting it is
the wrong trade, because renaming a value breaks every call site at once and
until the last one is fixed there is no PDF at all, not even to read the
paragraph you were in the middle of writing.

Draft mode renders an unresolved id as a loud `?id?` placeholder and writes
**`paper-draft.pdf`, never `paper.pdf`**. Keeping the output file separate is
what makes this safe: a placeholder cannot reach a PDF anyone would mistake for
the finished paper, so `check` needs to know nothing about the mode. `n("id")`
still fails in draft mode, because no placeholder can stand in for a number
inside an expression without making the arithmetic that reads it silently wrong.

**`orphaned-asset`.** `uncited-figure` catches a float the manuscript defines but
never references. Nothing caught the opposite: a generated table dropped from
`si-body.typ`, or a figure whose `image(...)` line was rewritten, keeps being
regenerated by `just assets` forever while appearing nowhere. Every staleness
check reports it current, correctly -- it is simply not in the paper. Matched on
filename anywhere in the `.typ` sources rather than by parsing includes, since a
false negative is far cheaper than telling someone to delete a file the
manuscript needs. `si/stats.json` is exempt: it is read by id, never by name.

**`audio/` is genuinely optional.** It was documented as deletable and was not:
`just all` had a hard dependency on `audiobook-all`, and `tests/run.py` imported
`extract_prose` at module level, so deleting the directory broke the default
build and the whole test suite on a project that had declined a feature it never
asked for. `all` now skips narration when the directory is absent and says so,
and the test run reports "no audio/ so narration skipped" rather than quietly
testing half of what its summary line claims.

Verified by deleting `audio/` and running `test`, `prose-check`, `readability`
and `all` against a manuscript without it.

## 1.1.0

**Numbers in prose are generated, guarded, and checked.** Tables and figures
always tracked the analysis, because a script wrote them. Numbers in sentences
were typed, and that is where drift lives: a unit error, a percentage stale after
a re-run, a value corrected in the table but not in the paragraph beside it. A
manuscript built on this scaffold had exactly that failure, in three places, with
the tables correct throughout.

New and additive. An existing project takes it by copying `stats.typ`,
`typst_prose.py`, `readability.py`, `prose_check.py`, `prose_rules.py`,
`audio/extract_prose.py`, `analysis/scripts/_stats.py` and `gen_stats.py`, then
adding the `stats` recipe to `analysis/justfile` and `s` to the eval scope in
`wordcount.typ`. A project that states no computed numbers deletes the three
stats files and is otherwise unaffected.

- `analysis/scripts/gen_stats.py` declares every number the prose states and
  writes `si/stats.json`. ONE script, not a glob like the table and figure
  generators: they would all write the same file, so a second would silently
  clobber the first.
- `#s("id")` reads it back and **panics at compile time** on an unknown id.
  `readability.py` and the narrator resolve the same call, since both read the
  source rather than the PDF. Stripping it would silently delete a number from
  the word count; leaving it would leak the call text into the narration.
- **Guards run at generation.** `sign="-"` and `between=(0, 100)` are assertions
  about what the analysis is allowed to produce. The case they exist for: a
  sentence reads "fell by #s(...)%", a re-run turns the value positive, and the
  paper ships "fell by -3.1%". The build now fails first, naming the assumption
  the sentence makes, rather than a reader finding it.
- **`derivable-number`** flags a typed numeral matching a declared value, which
  is what turns the convention into something enforced rather than intended.

Only *distinctive* values are compared: a decimal point, a thousands separator,
or four characters or more. A declared `3` would otherwise match every `3` in the
manuscript, and 1.0.2 already recorded what a mostly-noise checker is worth.

Rounding stays with the analysis, set per value with `fmt`. Typst has no
equivalent of siunitx, and reimplementing rounding in the document would put the
same decision in two places.

Every guard and the new rule were verified by breaking the mechanism and
confirming the tests fail, not by reading the code.

## 1.0.2

Five fixes, all found by porting the scaffold into a second real manuscript
(`koth`). None change an interface; an existing project takes them by copying
`typst_prose.py`, `readability.py`, `prose_check.py` and `tests/`.

**`#ref(<x>)` was not recognized.** `typst_prose.REFN` matched only the
manuscript's own `#refn(` helper. Typst's native `#ref(` is the more natural
thing for an author to write, and koth is written almost entirely in it. The
result was a bare `#ref( )` surviving into the word count, the reading-level
score and the narration, in 68 places, with the PDF correct throughout. `REFN` is
now `#refn?\(`, and `tests/run.py` forbids a leaked `#ref` the way it already
forbade `refn`.

**Reference SITES were counted as float definitions.** `check_reference_order`
scanned for a bare `<fig:x>`, which `#ref(<fig:x>)` and `#refn(<fig:x>)` contain
just as a definition does. Each float was therefore numbered by its LAST
occurrence in the file, so a figure cited twice moved. In koth the checker
believed the main text defined 15 figures, in citation order, and reported a
"Figure 10" that does not exist; there are five. A definition is now a label
following a closing paren, which is where Typst attaches one. The same scan in
`check_structure` had the same fault, attributing a float to whichever document
cited it first.

**Tables labelled `tab:` were invisible.** The float vocabulary was `fig|tbl|eq`.
koth labels every table `tab:`, so all 37 of them were silently exempt from the
uncited-float and reference-order checks while the checker reported clean. The
prefix is a project convention, not a Typst rule, so both spellings are now
recognized through one `FLOAT` constant. Fixing this immediately turned up an SI
table that nothing cited.

**`\u{XXXX}` escapes reached the prose verbatim.** A manuscript writing
subscripts as `log\u{2082}` had the word counter treat that as one opaque token
and the narrator read it aloud as "log u 2082", 41 times.
`typst_prose.unescape_unicode()` resolves the escape to the character, so the
count sees the word a reader sees and the narrator's spoken-Unicode map can
handle the result like any other symbol.

**`word-repetition` fired on repeated file paths.** It ran on the prose with
inline code UNWRAPPED, because a journal counts an inline-code term as a word. A
sentence listing three reproducer scripts under one directory then read as that
directory name three times. It now runs on `spellable`, the same code-removed
text the spelling check uses, for the same reason. That was 12 of koth's 18
findings, and a checker whose warnings are mostly noise is a checker nobody
reads.

## 1.0.1

Three fixes, all found by porting 1.0.0 into a real manuscript (`FeNovo`). None
of them change an interface, so an existing project can take them by copying
`justfile`, `readability.py` and `tests/run.py`.

**`just fmt` rebuilt the PDF.** The recipe's closing message was double-quoted
and contained `` `just paper` ``. just evaluates a backquoted string as a shell
command, so formatting the sources ran a full compile and printed a word count
nobody asked for. Single-quoted now, with the explanation above the recipe rather
than inside it, since recipe-body `#` comments are echoed.

**The sentinel gap did not cover inline code.** `readability.clean` unwraps an
inline-code span into a bare word, because a journal counts it as one. Under a
sentinel gap the caller is looking for adjacent duplicate words instead, and an
unwrapped `` `--proteome-k K` `` reads as a doubled "k K" the author never wrote
— firing the one duplicate-word rule that gates. Inline code is now dropped
whole under a non-default gap, and the regression cases cover it.

**CLAUDE.md described checks that no longer exist.** It told an agent that
`just check` covers audiobook staleness and figure-copy drift. Both were removed
in 1.0.0 (see "Decisions reversed"), so the instruction sent agents looking for
output that never appears. It now describes what `check` actually does and points
at the reversal.

---

## 1.0.0

First release. The pipeline was extracted from the `dnoise` manuscript, where
every piece of it was written in response to something that had actually gone
wrong.

**Build.** Typst to PDF with the Supporting Information appended as one
compilation, so cross-references resolve in both directions and numbering cannot
drift. Word export through Typst's HTML output and pandoc, with the template
bypassed and equations rasterized, because HTML export silently discards the
template's front matter, every section heading, and all math.

**Identity.** `config.typ` is the single source for title, authors,
affiliations, abstract, keywords, and bibliography style. The Word front matter
derives its numbered affiliation superscripts from the same author list the PDF
template uses. `audio/config.py` parses the title out of `config.typ` rather than
holding its own copy, after a finished audiobook spent weeks announcing a title
the paper no longer had.

**Generated assets.** `analysis/` lives inside the manuscript and writes figures
into `figures/` and tables into `si/` directly. Its whole contract with the
manuscript is one recipe, `assets`. Both output directories are tracked, so a
fresh clone compiles without re-running an analysis that may take hours, and
`just check-assets` guards them with a content stamp.

**Prose tooling.** Journal word counts with the exemptions spelled out,
readability metrics, density metrics (numerals, parentheticals, acronyms,
nominalizations, passives, hedges per 1,000 words, with per-section outliers
judged against the paper's own median), and `prose-check` for the mechanical
rules in `STYLE.md`.

**Formatting.** `just fmt` runs typstyle, and `.vscode/settings.json` pins
tinymist to the same width and prose-wrap setting so format-on-save and the CLI
cannot fight.

**Staleness.** `just check` reports a committed `paper.pdf` that predates a
source commit, a Word export older than what it renders, and generated assets
older than the analysis that produced them.

**Audio.** Offline Piper narration into chaptered `.m4b` files with cover art.

---

## Decisions reversed

Each of these was built, shipped, and then undone. They are recorded because all
of them look reasonable in the abstract, and the reasons they failed are only
visible from use.

### Construct coverage in the placeholder prose

The first skeleton put one of every special-cased Typst construct into
`paper.typ`, so `just all` on a fresh clone was a smoke test. The flaw is fatal
and was pointed out immediately: placeholder prose is deleted the moment real
writing starts, so the test ran exactly once and then the constructs went
untested for the life of the project, which is the failure it was meant to
prevent.

Coverage now lives in `tests/fixture.typ`, which is never part of the manuscript,
with golden files and a reflow-invariance assertion. `paper.typ` is a short
placeholder that says to replace it.

### A general "-ise to -ize" spelling rule

The American-English check started with a regex for the whole `-ise` family. Run
against the real manuscript it flagged the name of the software itself, `dnoise`
and `denoise`, on every mention. A checker that cries wolf on the project's own
vocabulary gets switched off within a week. The British list is now explicit and
grown by hand.

### Spell-checking inline code

`readability.clean` unwraps an inline-code term into a bare word, because
journals count it as a word. Spell-checking that output then flagged the DIA-NN
column name `Ms1.Normalised` as a British spelling. The spelling pass now runs on
a variant with code removed rather than unwrapped.

### Commit dates for generated-asset staleness

`check-assets` first compared the commit date of `figures/` and `si/` against
`analysis/`. Dogfooding hit the case it cannot handle within minutes: the
generators are deterministic on purpose, so re-running them after an edit that
does not move the output produces nothing to commit, and the check then nags
forever with no way to satisfy it.

Replaced with `.assets-stamp`, a content hash of the analysis source written when
`just assets` runs. It clears whether or not the bytes changed, and needs no git.

### `figures.map` and an external analysis tree

The analysis was originally modeled as a sibling directory that figures were
copied out of, governed by `figures.map` and policed by a byte-compare. The copy
was the whole problem: a re-analysis updated the plot upstream, the copy in
`figures/` stayed put, and the PDF kept rendering a figure that no longer matched
its own caption. Moving the analysis inside the manuscript and writing to the
destination removed the failure instead of guarding it.

### `fmt-verify`, and five other recipes

`just --list` reached 30 entries, which is the first thing a newcomer sees.
`fmt-verify` was superseded by `just test`, compared a no-op once sources were
always formatted, and restored via `git checkout --`, the most dangerous line in
the repo. Four one-flag wrappers and a redundant flat-narration path went with
it. The two `.m4b` staleness checks went too: every prose edit marked both
audiobooks stale and clearing that cost minutes of narration, so the warning was
almost always present and almost never acted on.

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
