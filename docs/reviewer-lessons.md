# Reviewer lessons for methods papers

What a skeptical reviewer of a methods paper asks for, so the draft answers it
before the review does. The lessons come from a round of peer review of a
computational mass spectrometry method in which three reviewers independently
raised the same problems. The problems were in how the paper argued, not in
the software, so expect them in any methods paper written the same way,
whatever the field. The examples are mass spectrometry because that is where
the lessons were learned; they are paraphrased or invented, and no reviewer
text is reproduced here.

Use this document when you:

- review a draft: run the draft checklist, then read the principle behind any
  item that fails;
- add a figure or panel: run the figure checklist before the figure goes in
  the paper;
- plan an experiment: run the experiment checklist before any data is
  collected or run.

Report failures as findings with the file and line. Do not rewrite the paper
unasked.

## Where the review skills use this

The `paper` plugin's skills look for these problems in their own passes and
report them in their own findings format; this document is the rationale they
cite, not a list they run.

| Skill | What it takes from here |
|---|---|
| `/paper:peer-review` | The methods-and-statistics reviewer's concerns: undefined tolerances, comparators, held-out data and settings, parameters, contribution versus plumbing, physical assumptions, downstream benefit, availability (principles 2, 4 to 6, 8 to 10) |
| `/paper:story-review` | Goal, user and scope up front; Introduction and Limitations agree (principle 1) |
| `/paper:claim-audit` | "Preserved", "negligible", "comparable" with no tolerance and no number (principle 2) |
| `/paper:figure-review`, `/paper:new-figure` | The figure checklist below |
| `/paper:prose-review` | Promotional headings, informal verbs, adjectives where a number exists (principle 10) |
| `/paper:intro-review` | The Introduction on its own: problem sized from the literature, each existing approach with its gap, terms and formats defined, aim, scope and design with reasons, no results before the Results (principles 1 and 7) |
| `/paper:literature-check` | The Introduction surveys existing approaches before it states the gap (principle 7) |

The experiment checklist has no skill: use it by hand before collecting data.

## Checklists

### Reviewing a draft

1. The first paragraph states the problem, who has it, and what is out of
   scope.
2. Every "preserved", "negligible", "comparable" or "high agreement" has a
   tolerance stated in Methods and a number in Results.
3. Every factual claim in the Introduction is cited or points to our own
   result.
4. The method has a schematic on a toy example and pseudo-code, in the main
   text or the SI.
5. There is at least one comparison against an existing tool or a naive
   baseline, not only against the unprocessed input.
6. Results show a benefit users care about (accuracy, identifications,
   runtime, cost), not only the metric the method optimises.
7. Parameters were tuned on data not used to report performance, or the paper
   says plainly that they were not.
8. The paper names its upstream libraries and any processing already applied
   to the data by the vendor, the instrument or the depositor.
9. Headings name a topic or a metric. None of them sells a result.
10. The licence, code version and DOI, and data accessions appear in the
    abstract or the Availability section.

### Adding a figure or panel

1. The panel answers one question. The caption states the question and gives
   the answer as a number.
2. A panel that explains a mechanism shows a small toy example (a few cells
   or points, annotated) before any real data.
3. Every phenomenon the text names, such as an artifact the method removes,
   is pictured somewhere.
4. The plot type suits the data. Dense 2D data goes in a heatmap, not an
   overplotted scatter. A structural gap is not drawn as empty space.
5. Comparisons share axes and scales, one row per condition, and the baseline
   appears in the same panel.
6. Wherever the text says "preserved" or "within", the figure draws the
   tolerance band or pass/fail line.
7. Replicates and spread are shown, not only means.
8. A preference, not a rule: draw schematics in CeTZ, so their text and
   fonts match the Typst manuscript, and keep matplotlib for data.

### Planning an experiment

1. Write down the claim the experiment supports and the result that would
   refute it.
2. Fix the metric and tolerance before running, for example "ID loss ≤ 1%" or
   "median CV change within ±2 points". Base the tolerance on replicate
   spread or a field convention.
3. Include comparators: an existing tool, a naive baseline (fixed threshold,
   or random removal at matched size), and the unprocessed input.
4. Keep tuning data and evaluation data separate. Evaluate on held-out data
   from at least one other instrument, lab or setting.
5. Record every acquisition and analysis setting the paper must report, and
   the reason for each.
6. Plan a sensitivity sweep for the parameters that matter. State them in
   physical units where possible.
7. Ask what the method discards and who would need it. Either test that case
   or scope it out in writing.

## Principles

Ordered roughly by how much reviewer attention each drew.

### 1. State the goal, the user and the scope first

An unclear goal was the most common complaint. It led reviewers to read every
later result in the least favourable way.

- Open with the problem, who has it and what changes for them. Put the number
  showing how large the problem is next to the number showing how much of it
  the method fixes.
- Say what the method is for and what it is not for. Readers who have to guess
  the scope pick the scope that looks worst.
- Do not call primary data or established practice disposable or wrong.
  Present the output as an addition (a working copy, a derived product),
  unless you can defend a replacement.
- The Limitations section must agree with the Introduction. If Limitations
  says "keep the original", the Introduction cannot rest on deleting it.
- Explain why the benchmark dataset suits the goal and how it resembles real
  use.

Example: "raw files are wasteful and should be replaced" draws fire. "The raw
file stays as the archive; the output is a smaller working copy for transfer
and routine analysis" holds up.

### 2. Define "good enough" before showing results

Words like "preserved", "negligible" and "high agreement" read as advertising
unless a threshold was set in advance.

- For each claim, state the metric, the tolerance and where the tolerance
  comes from: replicate variation, a field convention or a user requirement.
- Report quantities with their direction and spread, for example "−0.6% (95%
  CI −0.9 to −0.3)", not "slightly fewer".
- Keep one description per result. "Identical" and "2.2% missing" in
  adjacent sentences reads as a contradiction.
- Put the numbers in a table or a figure. A qualitative sentence on its own
  is not a result.

Example: "precision was likewise preserved" draws fire. "Median CV changed by
+0.4 points (tolerance ±2, set from replicate spread); all three conditions
passed" holds up.

### 3. Show the method on a toy example, then give pseudo-code

Reviewers could not tell what the algorithm did from prose and real-data plots
alone. Several independently asked for the same picture.

- Draw one schematic per step on a small grid or a few points: input, rule
  and output, with kept and removed items marked.
- State the dimensionality and the unit of each operation: per point, per
  spectrum or per feature, and whether it works in 1D or 2D.
- Define every term before first use and keep it fixed, for example "point"
  versus "peak" or "run" versus "gap".
- Give pseudo-code with the defaults written in. Where the method merges or
  aggregates data, explain how it decides and what it can get wrong.
- Illustrate every artifact the method targets. A named phenomenon with no
  picture reads as unsupported.

### 4. Compare against something other than yourself

Showing only that the output resembles the input does not show that the method
is useful, or better than the alternatives.

- Include at least one existing tool, even if it needs a format conversion.
  Being competitive is enough, but it has to be shown.
- Include a naive baseline. If the baseline does as well, the method is not
  the contribution.
- Show a downstream benefit the user cares about: in mass spectrometry,
  identifications, quantitative accuracy, FDR behaviour, runtime or memory.
  A saving on the metric the method optimises (storage, say) persuades no
  one on its own.
- Relate any baseline threshold to values people actually use, and cite
  them.

### 5. Show that it generalises beyond the tuning data

Using a single instrument or dataset, with parameters tuned on the same samples
used for reporting, was flagged as limiting every conclusion.

- Keep tuning and evaluation data separate. If they overlap, say so and add a
  held-out check.
- Test on more than one instrument, lab or acquisition setting, and say why
  the main dataset was chosen.
- Express parameters in physical units (seconds, ppm, ion mobility) rather
  than counts that depend on acquisition settings, or give the conversion.
- Give a tuning procedure a new user can follow, or an automatic default,
  plus a sensitivity plot for each key parameter.
- Report every acquisition parameter that affects the method (for a mass
  spectrometer, ramp time, mass range, cycle time) for every dataset.

### 6. Document every parameter and analysis choice

An unexplained parameter list read as opacity, and unjustified search settings
undermined the metrics built on them.

- Give a table of every exposed parameter: purpose, default, range and
  effect. Mark which parameters matter and which rarely need changing.
- Justify the downstream software and its settings (tolerances, ranges,
  filters). If a metric depends on them, they are part of the method.
- Anything in an SI table must be discussed in the text or removed.
- Say exactly what changes in the output files and what stays untouched.

### 7. Ground the Introduction in the literature

Conclusions without citations, and no survey of existing approaches, made the
gap look asserted rather than shown.

- Survey current approaches: what each does well and where each falls short.
  Then state the unmet need.
- Introduce the data type and file formats before discussing results. Explain
  domain formats in one sentence.
- If the paper depends on a design choice, such as keeping a native format,
  explain why that choice matters to users.
- Cite the sources of the datasets separately from background references.

### 8. Separate the contribution from the plumbing

Reviewers judged novelty by the algorithm. They saw engineering that is easy to
reproduce, or that others have already done, as no contribution.

- State what is new in one sentence. Credit upstream libraries for
  everything else.
- Treat validation as part of the contribution: breadth of conditions,
  replicates, independent downstream tools and round-trip checks.
- Name any processing already applied to the data and discuss how it
  interacts with the method.
- If a core component can be used on its own, as a library or an API, say so
  in the main text, not only in the README.

### 9. Check the physical assumptions

A rule that treats the instrument as ideal, such as a perfectly sharp isolation
window or a fixed resolution, invites the question of whether it behaves that
way.

- List the method's assumptions about the instrument or the sample. Give
  evidence for each: a calibration, a measurement or a citation.
- Where the evidence is thin, add a margin and show that the results are not
  sensitive to it.
- State which information the method removes permanently and which analyses
  need it (in mass spectrometry, method development or reviewing unselected
  precursors). Scope those uses out explicitly.

### 10. Write like a methods paper

Informal verbs, promotional headings and vague quantities lowered the clarity
score from every reviewer who noticed them.

- Headings name a topic or metric ("Identification rate after filtering"),
  not a result ("Nothing is lost").
- Do not describe results with informal verbs or metaphors ("gave up", "a
  small trim").
- Replace an adjective with a number wherever a number exists.
- State the licence, code version, DOI and data accessions. Put the licence
  in the abstract if the journal allows it.

Example: "the halo filter is a small final trim" draws fire. "The halo filter
removes a further 3.1% of points (2.4 to 3.9% across 12 runs)" holds up.
