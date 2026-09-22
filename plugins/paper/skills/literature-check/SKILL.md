---
name: literature-check
description: Check that each citation supports the sentence it is attached to, look for foundational or competing work the manuscript does not cite, and audit citation hygiene. Needs the network. Use before submission or when a reviewer questions the related work. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Check the citations and the related work

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md
"Citations". This skill is read-only: it never edits prose or
references.bib. It uses the network, so it is slow, its answer has a shelf
life, and it is not part of `just verify` or the default `/paper:review-all`.

Scope defaults to every citation in paper.typ and si-body.typ. The user may
narrow it to a section, to one or more bib keys, or to one of the three
passes below.

## The rule that matters most

Never propose a reference you did not resolve online in this pass. A
proposed addition carries the DOI you fetched, the title and authors as the
registry returned them, and the URL you read them from. A work you recall
but could not resolve is reported as "could not verify: <what you
remember>" and nothing more. An invented or misremembered reference is the
worst outcome this skill can produce, worse than a missed one.

## Take the mechanical layer as given

Run `just bib-audit` and copy its output under its own heading: dead DOIs,
metadata that disagrees with the registry, retractions. `just viz` writes
`viz/report.json` with the bibliography's age profile and self-citation
share; read that rather than recount. Do not repeat what they report.

## Pass 1: does each citation support its sentence

1. `just review-text` writes `paper.review.txt` with citation keys in
   brackets beside the sentence that cites them. Build one row per
   (sentence, key) pair with the `file:line` from the source.
2. For each key, read the entry in references.bib, then fetch what the work
   actually says: the abstract via the DOI's registry record or publisher
   page, and where the claim is specific (a number, a mechanism, a
   method's origin), the relevant section of the paper if it is openly
   available. Note when only the abstract was reachable.
3. Verdict per row: **supports** (the cited work states or shows what the
   sentence attributes to it); **partial** (it supports a weaker or
   narrower version; quote both); **does not support** (the work is about
   something else, or says the opposite); **wrong source** (the claim is
   true but this is not where it comes from, for example a review cited
   for a primary result, or a later paper cited for a method it borrowed;
   name the primary source only if resolved); **unverifiable** (paywalled
   or unreachable; say what was tried).

A string of keys on one sentence is checked key by key; a bundle where only
one member supports the claim is a finding.

## Pass 2: what is missing

1. From the abstract and the introduction's last paragraph, write down the
   manuscript's two to four load-bearing claims of contribution, and the
   names of the methods, instruments, datasets, and prior tools it builds
   on.
2. Search for each: the originating paper of each named method or tool,
   the prior work that made the same or a closely related claim, and
   anything published since the newest reference in references.bib that a
   reviewer in the field would expect to see. Use the venue's field: read
   `journal.toml` and its profile for the audience.
3. Report each candidate as: what it is (resolved as above), which
   sentence or claim it bears on, and whether it is **foundational** (the
   manuscript uses the thing without citing its origin), **competing** (it
   makes a claim the manuscript presents as new, or reaches a different
   conclusion), or **context** (a reader would expect it but nothing
   depends on it). Say plainly when a search turned up nothing, which is
   itself useful.

Do not assert priority. "This was done before" is a question to the author
with the resolved reference attached, not a verdict.

## Pass 3: hygiene

From the rows above and viz/report.json, note: a preprint cited where the
published version exists (resolve it); a claim supported only by
self-citation; a citation cluster of more than three keys on one
sentence; a reference cited only in the SI or only once in a list; a
reference whose entry lacks a DOI that exists; and whether the age
profile or self-citation share would draw a reviewer's comment for this
venue.

## Report

Write `reviews/<YYYY-MM-DD>-literature-check.md` (create the directory).
Shape:

1. A one-paragraph verdict: citations checked, how many in each verdict,
   how many candidates found in pass 2 and of which kind, and the two or
   three findings that would draw a reviewer's comment.
2. The mechanical layer's output, verbatim.
3. Pass 1 as a table: severity (major / minor), location, key, sentence,
   what the work says, verdict, routed fix.
4. Pass 2 as a list, each with the resolved reference block ready to paste
   into references.bib and the sentence it should attach to.
5. Pass 3 as a short list.

Route fixes to `/paper:copy-edit` (the sentence overstates what the source
says), "bibliography change" (add, replace, or update an entry in
references.bib, with the resolved entry given), or "author decision" (a
priority or framing question). Apply none of them here. Print the verdict
paragraph and the file path. Nothing was edited, so do not run
`just paper` or `just verify`.
