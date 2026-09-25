# AI editing and review

Claude Code and Codex read the same instructions and skills. CLAUDE.md states the rules tersely; this page carries the reasons.

## Working with an AI

`just review-text` writes `paper.review.txt` for upload to an AI reviewer.
`just paper` runs the PDF, Word, and review-text exports together; `just pdf`,
`just docx`, and `just review-text` remain available for individual formats.
It preserves wording, headings, evaluated numbers, equations in plain-text
notation, code, and numbered figure/table captions. Images, table bodies,
reference lists, page furniture, and repeated front matter are omitted.
Citation keys remain in brackets so feedback can identify the cited source;
figure/table references use compiled numbers. Other cross-references retain
their source labels. This is an export, not an AI summary or rewrite.

The export evaluates current Typst sources in a temporary copy and does not
require a current PDF or Word file. Main prose comes from BODY markers;
single-paper exports also include the configured title/abstract, back matter
before the bibliography, and included `si-body.typ`. Manifest projects export
their selected BODY parts in order: `just review-text chapter-id` selects a
chapter and `just review-text all` exports every target. Each text file sits
beside its corresponding PDF, with `.review.txt` replacing `.pdf`.

Unknown content constructs stop the export rather than silently deleting text;
arbitrary context-dependent prose needs explicit exporter support. Existing
exports remain intact on failure. Re-run the command after edits; these review
copies are not included in the PDF/Word freshness gate. They support prose and
argument review, but visual, table-data, and bibliography checks require the
full manuscript.

Open the manuscript repository in Claude Code or Codex and give your editing
request. Both use the same standing instructions: `AGENTS.md` links to
`CLAUDE.md`. The agent edits source files and runs the pipeline through `just`.
No MCP server is required.

For prose work, agents read and edit the Typst source directly. After a
successful build, `paper.resolved.typ` provides a readable text view with the
statistics, tables, and reference numbers filled in. It is generated and must
not be edited. Check `just check-build` before treating it as current; during
edits, use the source and `just trace <id> --json` to inspect a displayed number.
`just resolve` also builds the PDF, so it is not needed for each prose change.
The final `just paper` refreshes the resolved text.

Ordinary wording edits use text review and command-line checks. PDF or image
inspection is reserved for requested visual review, layout or figure changes,
and specific rendering defects. Copy-editing records its initial metrics with
`just wordcount` and `just readability`, then builds after editing and runs
`just verify`. The writing review also checks defined terminology and concrete,
supported claims using [STYLE.md](../STYLE.md#scientific-terms-and-concrete-claims).

Thirteen workflows ship as skills: five that edit (`copy-edit`, `fix-verify`,
`declare-number`, `new-figure`, `cover-letter`) and seven read-only reviews (`claim-audit`,
`methods-vs-code`, `figure-review`, `prose-review`, `literature-check`,
`story-review`, `peer-review`) that write findings under `reviews/`, plus
`review-all`, which runs the fix-list reviews in parallel (the network-bound
literature check only on request; the story review is a plan to discuss and
stays out) and merges them. Their maintained files live in `plugins/paper/skills/`
in the scaffold and reach every paper as the `paper` Claude Code plugin
(`.claude/settings.json` enables it; the `paper-scaffold` marketplace serves it).
`.agents/skills` is a symlink into the scaffold checkout so Codex discovers the
same instructions. Neither is copied by `new-paper.sh`. What a methods
reviewer presses on (undefined tolerances, missing comparators, figures that
do not answer one question) is written up in
[Reviewer lessons](reviewer-lessons.md); the review skills look for it in
their own passes and cite that document for the reasons.

| Skill | Does |
|---|---|
| `copy-edit` | Polish the requested prose while guarding retained numbers, helper IDs, citations, and structure |
| `fix-verify` | Diagnose failed or incomplete checks and repair the cause while preserving author edits |
| `declare-number` | Connect a number to the right source; check that a literal conversion preserves displayed text |
| `new-figure` | Add a generated plot/table, declaration, caption, citations, and the required imports and checks |
| `cover-letter` | Draft or revise `cover-letter.typ`: significance from the manuscript, numbers via `#s()`, each item the journal profile requires, `#todo` for what only the author knows |

For example, use `/copy-edit Shorten the Results section` in Claude Code or
`$copy-edit Shorten the Results section` in Codex. The workflows can also be
selected from a matching plain-language request. Start a new agent session
after installing the shared paths and check that these five skills appear in
its skill list. Discovery locations are documented by
[Claude Code](https://code.claude.com/docs/en/skills) and
[Codex](https://learn.chatgpt.com/docs/build-skills).

The skills instruct the agent to run the relevant checks and report their
results. Checks establish mechanical consistency; the agent must still read
the edited prose for scientific meaning. Instructions alone do not force an
agent to run a check. A check that could not finish must be reported as
incomplete, not passed.

## The review action ledger

Each review writes a dated findings file, and a findings file is a snapshot:
it cannot say which of its findings were fixed since. Without a record of
that, the next review raises the same points again and an editing agent has
no list of what is outstanding. `reviews/ACTIONS.md` is that record, one
markdown table for the life of the paper:

```markdown
| id | severity | status | source | summary | fix | closed |
|---|---|---|---|---|---|---|
| A-0001 | major | done | 2026-09-22-claim-audit.md#row 4 | "Increased" for a tie within the interval | /paper:copy-edit | 3f2a91c |
| A-0002 | minor | open | 2026-09-22-prose-review.md#row 11 | "Robust" with no measurement behind it | /paper:copy-edit | |
```

- `id` is `A-` plus four digits, never reused. `severity` is `blocker`,
  `major` or `minor`; `status` is `open`, `done` or `wontfix`. `source`
  names the findings file and the finding in it; `fix` is the owner the
  review routed it to; `closed` is the commit hash that fixed it, or
  `uncommitted: <note>` until there is one, or the reason for `wontfix`.
- **Review skills** read the ledger before reviewing and do not raise a
  finding that matches an `open`, `done` or `wontfix` row. A `done` row
  whose problem is back is reopened in place (`closed` becomes
  `reopened <date>: <why>`). New findings are appended with the next ids.
  They still never edit the manuscript. `review-all` has its parallel
  reviews read the ledger but not write it, and merges all of them into it
  once at the end, in place of a separate ranked list; its ship verdict is
  decided by every open row. `story-review` writes nothing to the ledger:
  its plan becomes rows only for the items the author accepts.
- **Editing skills** start with `just check-actions --open` and name the open
  rows that bear on the task, and close each row they fix.
- The ledger is plain markdown so an author can edit it by hand (write a
  literal pipe as `\|`). `just check-actions`, in `verify`, fails only when
  the table no longer parses or a row breaks the rules above; open blockers
  print a WARNING line. A paper with no ledger passes silently.
  `just check-actions --init` creates it from `tools/actions-template.md`,
  whose header repeats these rules for the agent reading the file;
  `new-paper.sh` seeds it for a new paper.

## Project scope

The scaffold supports writing and checking a manuscript, linking claims to
declared results, and producing deliverables. Agents use the same source files
and commands as authors, with shared skills for the recurring workflows.
Keep changes focused on concrete manuscript problems and preserve the cheap
local checks, generated-file ownership, and existing export paths.

## The agent rules, with their reasons

The long form of the rules in [CLAUDE.md](../CLAUDE.md), as they stood before
that file was trimmed.

**Never hand-edit `si/*.typ`.** Those files are written by
`analysis/scripts/gen_*_table.py` and carry an "AUTO-GENERATED, do not edit by
hand" header. An edit survives until the next `just assets` and then vanishes,
usually unnoticed. Change the generator or the data it reads.
`just check-assets` catches it now, and names the file.

**`stats-rendered.json` is a build artifact — never edit or commit it.** It is
written by `tools/render_stats.py` from `stats.json` and regenerated by every
recipe that compiles. Edit `stats.json`.

**`stats.json` is the exception: you MAY edit it.** The split is by field, not
by file. In every entry the generating script owns only `value` (plus its
`checksum` and `origin`); `fmt`, `unit`, `desc` and `expect` are the author's,
edited here, and survive `just assets`. So: to change how a number is shown or
what the prose assumes about it (its guard), edit `stats.json` — the arguments
in `gen_stats.py` only seed a NEW entry and are ignored afterwards. To change
the number itself, change the analysis. Do not edit a generated `value` by
hand: the checksum catches it. A number no script can compute — a protocol
figure, a vendor spec, a value from a paper — is added by hand with
`origin.by = "hand"` and an `origin.note` saying where it came from. Give it a
`value` and a `fmt`; there is no rendered string in this file.

You may also declare files worth watching under a top-level `pinned` block:
`"pinned": {"analysis/data/raw.csv": null}`, then `just pin` to record the
hash. `just check-stats` reports when a pinned file changes; re-run `just pin`
to accept it deliberately. This is for files no generator declares — nothing
finds them programmatically, which is the point.

**Never hand-edit files under `figures/`.** They are written by `analysis/`.
Change the script that produces the plot and run `just assets`.

**Never name a generated figure or table by filename.** They are declared in
`assets.json` by the script that writes them and referenced by id:
`#figure(fig("fig.example"), caption: [...])`. Naming the path directly bypasses
the manifest, so it stops describing the manuscript; `just prose-check` reports
that as an error. Add a new one by calling `record(...)` in the generator.

**Never type a result into the prose.** Declare it in
`analysis/scripts/gen_stats.py` and read it back as `#s("id")`. A typed numeral
drifts from the table beside it and nothing notices; `just prose-check` reports
one that matches a declared value. Guard anything the sentence assumes: if the
prose says "fell", the entry's `expect` should carry `"sign": "-"` so a re-run
that reverses the sign fails the build instead of shipping "fell by -3.1%".
Seed the guard from `gen_stats.py` for a new value; edit `expect` in
`stats.json` for an existing one. If a number is worth stating, it is worth
being traceable.

Four tiers, weakest claim to strongest: a number the analysis computes is
`#s("id")`; one no script can compute but that deserves an audit trail is a
hand entry in `stats.json` with a note; a deliberate prose literal ("40 °C")
is vouched in place with `#lit("40")`, which silences only the
unaccounted-number warning at that spot; a global value-level exception goes
in `prose-check.toml` with a written reason. `lit()` never silences
`derivable-number` — a computed value wrapped in it still gets flagged.

**A stale slide deck is not a `verify` failure.** Decks live in `slides/`, are
built by name (`just slides talk`), and sit outside the gate on purpose: `just
check` and `just verify` say nothing about them, and `just fmt` does not touch
them. Do not "fix" a deck during a verify pass, and do not add `slides/*.typ` to
`typst_sources`. Check one when the user asks, or before a talk: `just
slides-check`. A deck reuses the paper's declarations -- `#s("id")`,
`#fig("id")`, `config.typ`, `references.bib` -- so never type a number onto a
slide, for the same reason you never type one into the prose. The talk's own
identity -- title, author line, institution, date -- is `slides/config.typ`, NOT
the manuscript's `config.typ`: renaming a talk must not touch the file five
manuscript tools read. `slides/theme.typ` is the only place Touying is
configured, and neither of those two shared files is a deck `just slides`
builds.

**A journal's limit comes from `journals/<profile>.toml`, never from memory.**
`journal.toml` selects the profile; its word limits join `just check-words`,
its resolution floor joins `just prose-check`, and `just check-journal` (in
`verify`) covers keywords, main-text figure and table counts, and the
graphical abstract's size. Every profile carries `source`, `guidelines-dated`
and `checked`, and does not load without them: to change a limit, re-read the
source, change the number, move `checked`. A section the profile names by
role is mapped in `[sections]`. The graphical abstract is declared once in
`paper.typ` as `toc-graphic`; `[placement]` puts it under the abstract in the
PDF and on the last page of the Word file by default, and the build passes
that choice, so do not move the block in the source to change where it lands.

**Cite in `si-body.typ` as `@si-key`, never `@key`.** The Supporting
Information has its own reference list, set by Alexandria because Typst allows
one native `#bibliography` per document, and the `si-` prefix is what routes a
citation to it. A bare `@key` in the SI compiles, renders an ordinary
superscript, and quietly joins the MAIN list instead. `just prose-check` reports
that as `misrouted-citation`, and reports the prefix in paper.typ's
`#show: alexandria(...)` drifting from the one in si-body.typ's
`#bibliographyx(...)`. Both lists read `references.bib`; there is one
bibliography file. `just docx` sets both. A paper whose `project.toml` sets
`[bibliography] single = true` has removed the SI's list on purpose, and its
SI cites `@key` ([hooks.md](hooks.md#one-reference-list)).

**Never delete the `// >>> BODY START` / `// <<< BODY END` markers** in
`paper.typ`. The word counter, the readability report, and the narrator all slice
the prose at them, and each hard-fails without them. Moving them changes what
the word count MEANS, not just its value: the convention here is that back
matter (the bibliography above all) sits outside the markers and is not
counted. A count that used to include it will drop on migration to this
scaffold without a word of prose changing -- expected, and worth knowing
before quoting the number.

One environment per concern, both managed by uv. The manuscript toolchain is
`pyproject.toml` at the root; the analysis has its own in `analysis/`. Run things
with `uv run`, never a bare `python3` that picks up whatever is on PATH, and never
`uv run --with X` inline: add the dependency to the right pyproject so the lock
stays honest.

**Every tool lives in `tools/`, not the root.** The root is for what a person
edits and what a build produces. A new checker or metric goes in `tools/` and
gets a `just` recipe; adding one to the root is how this directory got cluttered
the first time.

Each tool sits one level down, so it resolves paths against the manuscript root
with `ROOT = Path(__file__).resolve().parent.parent`, not `.parent`. Copy that
line from an existing one rather than writing `Path(".")`, which works when you
run it by hand from the root and breaks under `just` from anywhere else.
