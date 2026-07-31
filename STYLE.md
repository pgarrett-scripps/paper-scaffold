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

**Colons are fine.** Use them to introduce a list, an example, or a definition,
which is what they are for.

**Semicolons sparingly.** A semicolon joining two clauses is almost always two
sentences that have not been split yet. The one place to keep it is separating
items in a list whose items already contain commas.

Applies to running prose only. Typst markup keeps its own punctuation
(`#figure(caption: [...])`).

## Words

Say what a number is before you say what it means. "MS1 peaks fell by 84.9%,
shrinking the frame binary by 56.4%" beats "a substantial reduction was observed".

Prefer the concrete term over the umbrella one. If the mechanism is a filter, call
it a filter, not an approach.

Keep a term consistent once chosen. If the paper says "intensity", it never says
"brightness" for the same quantity. Grep before introducing a synonym.

Pick the word that describes what actually happened. "Compression" is not
"removal", "improved" is not "changed", "detected" is not "identified". A
near-synonym that overstates the mechanism is the easiest thing for a reviewer to
catch and the hardest to defend.

**"Significant" means statistically significant.** For anything else, say large,
substantial, or marked.

Cut the intensifiers and the throat-clearing: "very", "quite", "clearly",
"obviously", "importantly", "it should be noted that", "in order to". They add
words and never add evidence.

## Numbers and units

Give units on first mention of every quantity, and keep significant figures
consistent within a comparison. Do not write 84.9% next to 63% for the same kind
of measurement.

Spell out approximation in prose ("roughly 50%"), and reserve the `~` symbol for
tables and figures where space is tight.

Do not open a sentence with a numeral or an abbreviation. Recast the sentence.

## Abbreviations

Define at first use, once in the abstract and again at first use in the main text,
since the abstract is read on its own.

Do not abbreviate a term you use fewer than three times. The expansion costs the
reader less than the lookup does.

## Claims

Every load-bearing number in the text should be traceable to a generated table or
figure, not typed in by hand. See the `si/` contract in [README.md](README.md).

State the scope of a claim in the sentence that makes it. "Identifications were
unchanged in ddaPASEF" needs the acquisition mode in it, because the diaPASEF
result was different.

Do not describe a result as resolved unless its interval excludes the null. If a
comparison is a near-tie, write that it is a near-tie.

Attribute causation only where the design supports it. Otherwise write what was
observed and let the discussion propose the mechanism.

## Structure

One claim per paragraph, stated in the first sentence. If a paragraph needs two
topic sentences it is two paragraphs.

Prefer prose to bullet lists in the main text. A bulleted manuscript reads as
slides, and journals typeset lists unpredictably. Lists are fine in the SI for
genuinely enumerable things such as parameter settings.

Past tense for what was done and found. Present tense for what remains true:
"denoising removed 84.9% of MS1 peaks" but "the filter exploits a structural
prior".

Figure and table captions should stand alone. A reader who jumps to the figure
should learn what it shows and what to conclude without hunting for the paragraph
that cites it.

## Mechanics

Reflow with `just fmt` before committing prose changes, so diffs stay line-scoped
and reviewable. Run `just test` and `just fmt-verify` if you touched inline
markup, math, links, or cross-references.

Check `just readability` when a section starts to feel dense. It is a rough signal
rather than a target, but a Flesch-Kincaid grade drifting well past the rest of
the paper usually marks a paragraph worth splitting.

Run `just wordcount` before submission rather than after writing to a limit. The
abstract has its own cap and is counted separately.

## Domain conventions

Delete this section or replace it with your field's. The entries below are
examples of the kind of thing worth pinning down once.

- Species names italic, genus spelled out at first use and abbreviated after
  (_Escherichia coli_, then _E. coli_).
- Software named as its authors name it, with version on first mention.
- Accession numbers given in full, with the repository, at first mention.

## Target journal

Fill this in for your submission and delete the placeholders.

- **Journal:**
- **Word limits:** main text, abstract (check with `just wordcount`)
- **Reference style:** set `paper-bib-style` in `config.typ`
- **Figure requirements:** format, resolution, colour mode
- **Submission format:** PDF or Word (`just docx`)
- **Known deviations from this file's house style:**
