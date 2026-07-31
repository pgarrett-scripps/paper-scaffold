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

## Spelling

**American English throughout.** Not British, and not mixed, which is what
actually happens when nobody says so. The traps that recur: analyze not analyse,
normalize not normalise, color not colour, behavior not behaviour, center not
centre, modeled and labeled with one L, toward not towards, while not whilst,
among not amongst.

Journal names in the bibliography keep whatever spelling they publish under.

## Sentences

**One idea per sentence.** A run-on is usually two findings that got welded with
a comma or an "and". Split them. If a sentence needs a comma to hold two
independent clauses together, it needed a full stop.

Keep most sentences under about 25 words. `just readability` reports mean words
per sentence, so this is checkable rather than a matter of taste. A section
drifting well above the rest of the paper is a section to break up.

**Shorter is better.** Use not utilize, show not demonstrate, because not due to
the fact that, to not in order to, about not approximately in running prose. The
long form never reads as more rigorous, only as more words.

Prefer the verb to the noun built from it. "We measured the shift" beats "a
measurement of the shift was performed". Nominalization is the main engine of
academic verbosity and it hides who did what.

Cut redundant pairs ("each and every", "first and foremost") and double hedges
("may possibly suggest"). Hedge once or not at all.

## Repetition

Repetition is the most common thing a reader notices and the easiest to fix.
Watch for it at four scales:

- **Word.** The same distinctive word twice in a sentence, or in adjacent
  sentences. Ordinary words are fine to repeat, and a technical term should be
  repeated rather than replaced with a synonym (see below). It is the incidental
  vocabulary that grates.
- **Sentence opening.** Three sentences in a row starting "We found", or every
  paragraph in a section opening with "The". Vary the entry point.
- **Content.** A result stated in Results and then restated in Discussion in the
  same words. The Discussion should say what it means, not say it again.
- **Caption and body.** A caption that paraphrases the paragraph citing it is
  wasted space. The caption says what the figure shows; the body says what to
  take from it.

The one thing to repeat deliberately is a defined technical term. Consistency
beats elegant variation, and a synonym introduced for variety reads as a second
concept.

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
and reviewable. Run `just test` if you touched inline markup, math, links, or
cross-references.

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
- **Figure requirements:** format, resolution, color mode
- **Submission format:** PDF or Word (`just docx`)
- **Known deviations from this file's house style:**
