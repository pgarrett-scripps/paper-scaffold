# Final paper audit prompt

Copy the prompt below into an AI coding agent working in the paper's project.

```text
Perform a final, evidence-based audit of this paper and its supporting project.
Read the project instructions first. Review the entire manuscript, abstract,
supplement, bibliography, and available submission materials.

The goal is to finish the paper, not expand the project. Inspect thoroughly,
but report only concrete defects, consequential ambiguities, or material gaps
in verification. Do not manufacture findings to fill this checklist. A section
with no issues needs no suggestions, and "no actionable findings" is a valid
outcome.

Use existing local sources, data, code, outputs, logs, and validation reports.
Do not rerun analyses, experiments, literature searches, dependency
installations, or long-running processes. Use local searches and lightweight,
read-only checks as needed. Check whether existing outputs and reports match
the current sources before relying on them. Do not edit files.

Audit these five areas:

1. Completeness and authorship
Find TODOs, placeholders, unfinished passages, missing sections, broken
references, uncited figures or tables, missing files, and inconsistent
terminology. Check author names, order, affiliations, contributions,
corresponding-author details, acknowledgments, funding, conflicts, ethics
statements, and data/code availability for completeness and internal
consistency. Flag details that need author confirmation.

2. Citations and factual support
Check that citations resolve and bibliography entries have appropriate,
consistent metadata. Where source texts are available, verify that they
support the specific claims, including qualifications and attribution.
Identify unsupported claims, misleading citations, and potentially outdated
statements. Do not treat a title, abstract, or bibliography entry as proof of
an entire claim. Flag anything requiring external verification rather than
assuming it is correct.
Treat currentness, retraction status, and citation accuracy as unverified
where the necessary sources are unavailable. Record these limits concisely in
the coverage checklist; lack of access alone is not evidence of a defect.

3. Scientific and numerical consistency
Trace substantive claims and reported numbers to available evidence. Check
agreement across the abstract, text, equations, figures, tables, and
supplement. Inspect units, denominators, sample sizes, exclusions, uncertainty,
statistical methods, comparisons, and causal language. Look for contradictions,
overstatement, missing methodological details, and conclusions that exceed the
results. Distinguish internal consistency from independently reproduced
correctness.

Check analysis validity where relevant: data leakage, pseudoreplication,
inappropriate statistical tests, unmet assumptions, missing multiple-comparison
corrections, and unfair benchmark comparisons. Tie each concern to the actual
study design or implementation; do not list hypothetical failure modes.

Check figure and table integrity against available data and plotting code:
axis labels, units, scales, error-bar definitions, sample sizes, legends, and
whether captions accurately describe what is shown. Inspect existing rendered
figures where needed; do not regenerate analyses merely to review them.

4. Software and algorithm drift
Compare described methods with the source code actually used, when
identifiable. Inspect relevant implementations, configurations, dependency
versions, defaults, preprocessing, filtering, normalization, thresholds, random
seeds, and statistical calculations. Trace code through to the reported
outputs. Check for changes since those outputs were generated and descriptions
inherited from older implementations. Distinguish the version used for the
study from current code; a newer version alone does not invalidate the study.
Mark unavailable implementation or version evidence as unverified.

Check whether the methods and supporting materials provide the parameters,
software versions, dataset identifiers, exclusions, and procedural details
needed to repeat the reported work. Report specific missing information that
affects reproducibility, not generic requests for more documentation.

5. Grammar, clarity, and scientific terminology
Read every sentence, including captions and table notes, for grammatical
errors, run-on sentences, fragments, ambiguous pronouns, faulty parallelism,
punctuation, and inconsistent tense or spelling. Check that acronyms are
expanded at first use in each independently read component, as required by
the journal, and used consistently afterward. Flag unexplained abbreviations,
symbols, and technical terms. Check for redundant explanations and fragmented
academic paragraphs, including one-sentence paragraphs.

Pay particular attention to vague AI-style language: decorative jargon,
invented labels, inflated claims, generic descriptions, and plausible-sounding
substitutes for established scientific terms. Flag words such as "robust,"
"efficient," "significant," "optimized," or "enhanced" when the sentence does
not establish their precise meaning, comparison, or supporting evidence. Do
not apply a mechanical word blacklist; assess each term in its scientific
context. Every claim should make clear what was measured or done, under what
conditions, and what the evidence supports.

Require terminology that accurately names the quantity, method, mechanism, or
finding. Check definitions, units, existing usage, and available analysis or
source code before recommending a replacement. Do not substitute technical
synonyms for variety or make prose sound more academic by adding jargon. For
example, do not replace measured intensity with abundance unless the study
establishes that relationship, or use "significant" to imply statistical
significance without the relevant evidence. Quote each problematic passage
and propose precise wording only when its meaning is supported; otherwise
state exactly what needs clarification. Preserve necessary uncertainty and
do not invent a mechanism, metric, or conclusion to make a sentence specific.
Report actual errors or loss of scientific precision, not personal stylistic
preferences or rewrites of already clear, accurate prose.

Scope and essential additions
Flag existing material outside the paper's stated scope only when it causes
confusion, unsupported claims, or a submission problem. Recommend adding
material only when its absence prevents understanding, evaluating, or
reproducing an existing claim, or meeting a documented submission requirement.
Prefer a local clarification, narrower claim, or removal over expanding the
study. Put essential scope suggestions last and at low priority unless the
evidence establishes a validity or submission blocker. Explain why each is
necessary; omit this category entirely when there is nothing essential to add.
Do not propose speculative extensions, extra experiments, broader literature
coverage, refactors, or nice-to-have improvements merely because an audit was
requested.

Final report
Report actionable findings in severity order, with the exact manuscript
location, supporting evidence or code location, why it matters, and the
smallest recommended correction. Separate confirmed defects, suspected
problems, and unverifiable items. Include a compact coverage checklist showing
what was checked, partially checked, or unavailable. Identify submission
blockers and the specific additional evidence or checks needed to resolve
them.
Distinguish "checked and supported" from "no obvious issue found." Suspected
problems need a specific evidentiary basis; unsupported possibilities are not
findings. Consolidate repeated instances of the same issue and separate
submission blockers from minor corrections and essential scope suggestions.

Be exhaustive in inspection and concise in reporting. Do not invent missing
facts, silently resolve ambiguities, or claim full verification when evidence
is unavailable. Passing automated checks is evidence, not proof of scientific
correctness.
Land the plane: stop after covering the available materials and resolving
reasonable local follow-ups. Deliver a finite list of necessary corrections
and material verification limits, without inventing another round of work.
```
