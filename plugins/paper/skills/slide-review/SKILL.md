---
name: slide-review
description: Review a talk deck under slides/ as an audience sees it. Checks that each slide carries one message with an assertion title, that text and figures are readable when projected, that numbers and claims agree with the paper, that the deck fits the time slot and tells problem, method, result, and that speaker notes and backup slides are ready. Use before a talk, a defense, or a lab meeting. Read-only.
context: fork
agent: general-purpose
model: opus
---

# Review a slide deck

Work from the manuscript root and follow AGENTS.md/CLAUDE.md and STYLE.md.
This skill is read-only on sources: it never edits a deck, `slides/config.typ`,
`slides/theme.typ` or the manuscript. It writes one findings file. It is the
one review besides `/paper:figure-review` that looks at images, because a talk
is judged by what the room can see.

`.paper/docs/slides-and-audio.md` (`docs/` in the scaffold itself) says how
decks are built. `just slides-check` is the mechanical layer (stale ids,
undeclared assets, four prose rules); this skill judges the talk.

## Parameters

Given in plain words after the skill name; state the interpretation at the
top of the report.

- **deck**: the name under `slides/` (`talk` for `slides/talk.typ`). With one
  deck, that one; with several, `just slides-list` names them; ask only if
  the choice is not obvious from the request.
- **length**: the time slot in minutes ("20 minute talk", "45 minute
  defense"). If not given, look for it in the deck's title slide, date line
  or speaker notes; otherwise assume 15 minutes plus questions and say so.
- **audience**: specialists, a mixed department, or a defense committee.
  Default: a mixed department audience in the paper's field.

`/paper:review-all` does not run this skill: a talk is reviewed on request.

## Read

1. `just slides-list`, then `just slides-check <deck>`. Quote its output
   verbatim under its own heading; do not repeat those findings.
2. The deck source `slides/<deck>.typ` and anything it includes, for the
   slide order, `#speaker-note[...]` blocks, `#pause` steps, the
   `#show: appendix` boundary (backup slides start there) and each
   `#s()`/`#fig()`/`#tbl()` id.
3. The rendered deck. If `slides/<deck>.pdf` is older than its source (or
   missing), run `just slides <deck>`; this writes only the deck's PDF.
   Then render pages to images outside the repo:
   `pdftoppm -r 60 -png slides/<deck>.pdf <tmpdir>/p` and view them. Use the
   handout (`just slides-handout <deck>`) when `#pause` steps make the page
   count differ from the slide count.
4. For claims: the paper's abstract (`config.typ`) and Conclusions, and
   `stats.json` or `just trace <id> --json` for the ids the deck uses.

## Check, in this order

1. **One message per slide, stated in the title.**
   - The title is the takeaway as a short sentence ("Filtering keeps 98% of
     identifications"), not a topic label ("Results", "Benchmark").
   - A slide that makes two points is a finding: split it or cut one.
   - Read the titles alone, in order, as a list. They should tell the talk.
2. **Readable when projected.** On each rendered page:
   - more than about 40 words of body text, or full sentences read aloud
     from the slide, is a finding;
   - text or axis labels that would be under about 18 pt when projected
     (small against the slide's own title), a figure's tick labels you
     cannot read at 60 dpi, or a table of more than about 5 rows by 5
     columns;
   - a figure copied from the paper at paper density, with panels the talk
     never mentions: route to a talk version of the figure;
   - colour carrying meaning with no other cue.
3. **Agrees with the paper.**
   - Every result number is a `#s()` id; a typed numeral that the analysis
     computes is a finding (`just slides-check` flags the exact matches;
     you catch rounded or paraphrased ones).
   - No claim goes further than the paper: a slide saying "preserves" or
     "outperforms" where the paper says "within 2%" or "matches" is a
     finding, quoted beside the paper's sentence.
   - Figures come from `#fig()` ids, not image files copied into `slides/`.
   - A result on a slide that the paper does not contain is flagged as
     unpublished, not as wrong: the author may intend it.
4. **Fits the slot and tells the story.**
   - Main-deck slides (before the appendix) against the length: about one
     per minute is the ceiling; more than 1.5 per minute is a finding.
   - The arc: the problem and who has it, why current approaches fall short,
     the method in one picture, the results that answer the aim, the
     limits, one closing takeaway. Name the missing step.
   - The method is shown, not listed: a schematic or toy example before
     real data (principle 3 of `.paper/docs/reviewer-lessons.md`).
   - The last main slide is the takeaway, not "Thank you" or "Questions?"
     alone.
5. **Ready to present.**
   - Every content slide has a `#speaker-note`; a slide with none is minor,
     a results slide with none is major for a defense.
   - Backup slides after `#show: appendix` answer the questions an audience
     will ask. Read the most recent `reviews/*-peer-review.md` if one exists
     and check its major points have a backup slide; otherwise list the
     three questions you would ask and whether a backup answers each.
   - Acknowledgements and funding appear; references are cited on the slide
     that uses them.

Severity:
- **major:** a claim beyond the paper, a number that disagrees with
  `stats.json`, a slide the room cannot read, a missing arc step, a deck
  well over its slot.
- **minor:** anything else.

## Report

Write `reviews/<YYYY-MM-DD>-slide-review-<deck>.md` (create the directory).
Shape:

1. A verdict paragraph: slides in the main deck and backup, the time budget
   against the slot, whether the titles alone tell the story, and the two or
   three changes that matter most.
2. The titles as a numbered list, each marked assertion or topic.
3. The findings table: severity, slide number and `file:line`, what is wrong,
   the fix, and the route: edit the deck by hand (decks have no editing
   skill), `/paper:new-figure` for a talk version of a figure,
   `/paper:declare-number` for a number no id holds, or "author decision".
4. The mechanical layer's output from `just slides-check`, verbatim.

Print the verdict paragraph and the file path. Do not run `just paper` or
`just verify`: a deck is outside the gate.

## Action ledger

Slide findings do not go in `reviews/ACTIONS.md` by default: the ledger
tracks the manuscript, and a talk is revised on its own schedule. If the
user asks for ledger rows, append each finding with
`just actions-add <severity> "<YYYY-MM-DD>-slide-review-<deck>.md#<ref>"
"<summary>" "<fix>"`, then run `just check-actions`.
