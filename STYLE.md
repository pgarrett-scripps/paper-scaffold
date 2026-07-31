# Prose conventions

House style for the manuscript. These are the author's conventions, not rules
handed down by a journal, so edit them for your own project. What matters is that
they are written down somewhere a collaborator (or an agent) will read, rather
than re-litigated in every review pass.

The journal's own requirements always win where they conflict. Record those in
the "Target journal" section at the bottom.

## Punctuation

**No em dashes.** Not in prose, not in figure captions, not in bibliography
entries. Split the sentence, or use a comma or parentheses. En dashes in numeric
ranges are fine (`5–15 min`), as is the hyphen in a compound modifier.

**Avoid colons and semicolons in prose.** They are easy to overuse and often end
up joining clauses that should be two sentences. Prefer the split. This applies
to running prose only, never to Typst markup (`#figure(caption: [...])` obviously
keeps its colons), and a colon introducing a genuine list is fine.

## Words

Say what a number is before you say what it means. "MS1 peaks fell by 84.9%,
shrinking the frame binary by 56.4%" beats "a substantial reduction was observed".

Prefer the concrete term over the umbrella one. If the mechanism is a filter, call
it a filter, not an approach.

Keep a term consistent once chosen. If the paper says "intensity", it never says
"brightness" for the same quantity. Grep before introducing a synonym.

## Claims

Every load-bearing number in the text should be traceable to a generated table or
figure, not typed in by hand. See the `si/` contract in [README.md](README.md).

State the scope of a claim in the sentence that makes it. "Identifications were
unchanged in ddaPASEF" needs the acquisition mode in it, because the diaPASEF
result was different.

Do not describe a result as resolved unless its interval excludes the null. If a
comparison is a near-tie, write that it is a near-tie.

## Mechanics

Reflow with `just fmt` before committing prose changes, so diffs stay line-scoped
and reviewable. Run `just fmt-verify` if you touched inline markup, math, links,
or cross-references.

Check `just readability` when a section starts to feel dense. It is a rough signal
rather than a target, but a Flesch-Kincaid grade drifting well past the rest of
the paper usually marks a paragraph worth splitting.

## Target journal

Fill this in for your submission and delete the placeholders.

- **Journal:**
- **Word limits:** main text, abstract (check with `just wordcount`)
- **Reference style:** set `paper-bib-style` in `config.typ`
- **Figure requirements:** format, resolution, colour mode
- **Submission format:** PDF or Word (`just docx`)
- **Known deviations from this file's house style:**
