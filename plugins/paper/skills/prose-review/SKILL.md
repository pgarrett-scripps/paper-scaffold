---
name: prose-review
description: Flag vague, decorative, or machine-sounding language that an academic reader would notice, sentence by sentence, and propose concrete wording the evidence supports. Use on any draft, and whenever prose was written or edited by an AI. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Review the prose for register and vagueness

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md,
especially "Sentences", "Words", and "Scientific terms and concrete claims".
This skill is read-only: it writes one findings file and routes every fix to
`/paper:copy-edit`. The question it answers is not "is this claim true" (that is
`/paper:claim-audit`) but "would a domain expert have written this sentence".

Scope defaults to the abstract (config.typ) and everything between the BODY
markers in paper.typ, including captions. The user may narrow it to a
section or extend it to si-body.typ.

## Read the action ledger first

`reviews/ACTIONS.md` records every finding earlier reviews raised and whether
it was fixed; its header states the rules. Read it before reviewing. If it is
missing, create it with `just check-actions --init` (a paper on a scaffold
older than 3.24.0 has no such recipe: write a file whose table header is
`| id | severity | status | source | summary | fix | closed |` with a
`|---|---|---|---|---|---|---|` separator under it). A problem that matches an
`open`, `done` or `wontfix` row is not a new finding: cite the existing id in
the findings file instead of raising it again. A `done` row whose problem is
back in the current text is reopened, not duplicated. Appending to the ledger
is the only write this skill makes outside its findings file; it still never
edits the manuscript.

## Take the mechanical layer as given

Run `just prose-check` and `just word-audit` first and copy their findings
into the report under their own heading. Do not repeat what they flag;
spend the pass on what a word list cannot see. Where the same unflagged
phrase recurs across the manuscript, propose adding it to
`[vocabulary.verbose-phrase]` in prose-check.toml so the checker catches it
next time. Propose; do not edit the file.

## Read every sentence against these questions

Read `paper.review.txt`, not the PDF and not the Typst sources: run
`just review-text` unless the caller says the copy is current. It has every
number resolved and every caption in place, at a fraction of the tokens of
paper.typ plus stats.json. Open the source only to quote a `file:line` for
a finding. For each sentence in scope, ask:

1. **Does every noun phrase have a referent?** "Signal landscape",
   "analytical framework", "information-rich regime", "holistic view",
   "nuanced picture": if you cannot say what was measured or done, flag it.
   A method called a "framework", "strategy", or "paradigm" when it is a
   filter or a script is the same fault.
2. **Does every evaluative word earn its place?** "Robust", "powerful",
   "novel", "comprehensive", "rigorous", "seamless", "critical", "crucial",
   "elegant", "substantial", "remarkable": keep it only when the measurement
   that justifies it is in the same sentence or the one before. "Significant"
   without a test is a finding.
3. **Is there throat-clearing or framing that adds no content?** "It is
   worth noting", "Importantly", "Notably", "Overall", "Taken together", "In
   this context", "To this end", "serves as", "plays a pivotal role", "paves
   the way", "sheds light on", "underscores the importance of", "opens new
   avenues", "broad implications", "valuable insights".
4. **Is the rhythm doing the work the content should?** Triplets of
   adjectives or nouns arranged for cadence; "not only X but also Y";
   balanced contrasts with nothing on one side; a paragraph-final sentence
   that restates the paragraph; a sentence announcing what the next will
   say; a rhetorical question; "This" opening a sentence with no noun after
   it.
5. **Is the hedging or precision fake?** "May potentially", "could possibly",
   "to some extent", "a number of", "various", "several" where the count is
   known and could be a `#s()` id; "approximately" in front of an exact
   declared value.
6. **Is anything given agency it does not have?** "The data tell a story",
   "the method seeks to", "the algorithm understands", "the results
   speak to".
7. **Does the register hold?** Contractions, colloquialisms, journalistic
   hooks, editorial first person ("we strongly believe"), "In this paper,
   we" more than once, a claim of what "future work will" do.
8. **Is a term of art being flagged wrongly?** "Robust" in robust
   statistics, "significant" with a reported test, "framework" for an actual
   software framework, and any term STYLE.md's domain section defines, are
   not findings. When unsure, say so rather than flag.

A finding names the sentence with `file:line`, the phrase, the question it
fails, and the replacement. The replacement is one of: concrete wording the
source or stats.json supports (quote where it comes from), "delete" when
the sentence loses nothing, or "ask author: <question>" when a real
statement is missing. Never invent a measurement, mechanism, or comparison
to fill a vague phrase; that is a worse fault than the one being fixed. A
replacement that would change a scientific claim is routed to
`/paper:claim-audit`, not written here.

Group a phrase that recurs into one finding with its count and locations.
Rank by where a reader forms their impression: the abstract, the first
paragraph of the introduction, the first paragraph of the discussion, and
the conclusions before anything else.

## Report

Write `reviews/<YYYY-MM-DD>-prose-review.md` (create the directory). Shape:

1. A one-paragraph verdict: findings per hundred sentences overall and for
   the abstract, the two or three habits that dominate, and whether the
   text would read as expert-written after the fixes.
2. The mechanical layer's output, verbatim, under its own heading.
3. The findings table: severity (major / minor), location, phrase, question
   failed, replacement, routed to `/paper:copy-edit` or `/paper:claim-audit` or "ask
   author".
4. Proposed prose-check.toml additions, if any.

Print the verdict paragraph and the file path. Nothing was edited, so do
not run `just paper` or `just verify`.

## Update the action ledger

After writing the findings file, and before the final print:

1. Every row of the findings table becomes one action (a
   recurring phrase already grouped into one finding stays one action). The
   mechanical layer's output is not added: `just verify` already tracks it.
2. Skip a finding that matches an `open` or `wontfix` row. Reopen a matching
   `done` row whose problem is back: `status` to `open`, `closed` to
   `reopened <YYYY-MM-DD>: <what came back>`.
3. Append each remaining finding as a row: the next id (`just check-actions`
   prints it), its severity, `open`, source
   `<YYYY-MM-DD>-prose-review.md#<ref>` naming the finding, a one-line summary,
   the routed fix as `fix`, and an empty `closed`.
4. Run `just check-actions` and repair any format error in the rows you
   wrote. Print the ids you added or reopened with the verdict.

When `/paper:review-all` launched this review (its prompt says so), skip
this section: review-all merges every review into the ledger once, after all
of them finish, so parallel reviews never write the file at the same time.
