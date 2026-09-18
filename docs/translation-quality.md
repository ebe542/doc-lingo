# Translation quality examples

The versioned [English/German fixture](../tests/fixtures/translation_quality/en-de.json)
contains ten original, synthetic examples. It is a manual evaluation set, not an
exact-string unit test or evidence that the current model passes. English is used
for metadata and criteria; source and reference texts use their respective languages.
The local comparison results below record a manual review of all ten examples.

## Abbreviations and technical terms

When a technical term is translated, keep its established abbreviation and
original expansion identifiable at its first occurrence in the document:

```text
Retrieval-Augmented Generation (RAG)
→ Abrufgestützte Generierung (RAG = Retrieval-Augmented Generation)
```

This is the project's terminology policy, not a claim that one German rendering
is universally mandatory. Equivalent accurate wording is acceptable. If the
English term is retained, do not duplicate its expansion unnecessarily. Later
mentions may use the abbreviation alone. Do not invent translated abbreviations
or expansions for unknown abbreviations. Bare unknown abbreviations are retained.
An approved glossary can later supply expansions not stated in a source document.

The current service processes segments independently. It has no document-wide
first-mention state or glossary. The final example checks that future requirement
and must be reported separately as a known limitation, not silently skipped.

## Evaluation procedure

1. Record the suite version, model ID/revision, both prompt names/versions/
   fingerprints, generation settings, package versions, and GPU/runtime.
2. Translate each example as its own document through the TXT reader, service,
   and writer. Do not combine all examples into one document: that changes context.
   In particular, preserve the multi-paragraph source of the final example.
3. Save actual translations and a short assessment under `local-data/quality/`.
   Keep model results separate from the committed reference fixture.
4. Compare actual output against the criteria and source meaning. The German
   reference is one acceptable translation, not an exact expected string.
5. Change one factor at a time, such as the prompt or model. Increment prompt
   versions when their instructions change. Re-evaluate the same full suite.

Use these per-example verdicts:

| Verdict | Meaning |
| --- | --- |
| pass | All criteria met; wording may differ from the reference. |
| minor_issue | Meaning retained, but grammar, fluency, or terminology needs correction. |
| major_issue | Meaning changed, content omitted/invented, numbers altered, or required abbreviation identity lost. |
| blocked | No usable output, such as a token-limit or GPU failure. |

Record the specific failed criterion alongside every non-pass result. Report
verdict counts for all ten cases plus the document-context result separately.
Do not conceal regressions behind an average score. A passing small suite is not
a guarantee of quality for arbitrary documents; add regression cases for newly
observed failures. The current article error, "Der Dokument", belongs to the
grammar-article example and would receive `minor_issue` if meaning is unchanged.

## Running the evaluation

The runner supports `--backend marian` (default) and `--backend qwen`. See
[Marian setup](marian-model.md) for its extra tokenizer dependencies and limits.
Marian reports contain no chat prompt identities because that backend uses none.

The runner processes each fixture entry as an independent TXT document through
the real reader, translation service, and writer. It reuses the loaded model.
From the project root in Git Bash, after installing the `local` extra:

```bash
python scripts/evaluate_translation_quality.py --backend qwen --output local-data/quality/baseline-v1
```

This is a real GPU run and may download the model. The script loads the current
directory's `.env` without overriding existing environment variables. Choose a
new output directory for every run; existing directories are rejected.

The persistent `report.json` contains the original source, reference, criteria,
actual translation, elapsed time, model/prompt/runtime metadata, and a fingerprint
of the parsed suite. Timing includes first-use model loading. Temporary source
and output documents are removed after each example. Completed results are saved
after each example; an unexpected exception leaves `complete: false`. This is not
a resume mechanism. `complete: true` means all cases were attempted, not passed.

Successful inference produces verdict `pending`, never an automatic semantic
pass. Edit each verdict and its notes after review using the rubric above.
Expected failures become `blocked`, with a sanitized exception class instead of
raw diagnostic text, and remaining examples continue. The runner exits with 1
if any example was blocked; exit 0 means inference completed, not that quality
was approved. Never copy real private documents into the committed fixture.

## Automated tests

Tests validate the fixture, real TXT document processing with a substitute backend,
pending/blocked results, failure cleanup, and existing-output protection. They do
not download models, need CUDA, or judge the linguistic quality of translations.
Run them and then the project gate:

```bash
python -m pytest tests/test_translation_quality.py -q
python scripts/check_milestone.py
```

## Comparing system prompt v2

System prompt v2 adds explicit rules for complete meaning, negations, technical
terms, German grammar, and original abbreviation expansions. The direction prompt,
model revision, and decoding settings remain unchanged. No reference translations
or example-specific corrections are embedded in the prompt.

Keep the existing v1 baseline and generate a separate candidate report:

```bash
python scripts/evaluate_translation_quality.py --backend qwen --output local-data/quality/prompt-v2
```

Compare all cases, including regressions, using the same criteria. A longer prompt
uses more of the unchanged input-token budget. The new instructions do not add
document-wide memory or guarantee better translations. This is a development-set
comparison; later validation should include examples not used to guide the prompt.

The maintainer reported no meaningful improvement from prompt v2 in the local
comparison. This is a qualitative observation, not an automatically measured
score. Prompt v2 remains a comparison baseline; it is not a demonstrated quality
improvement. Local reports remain outside Git under `local-data/quality/`.

## Local model comparison (2026-09-15)

The assistant reviewed source meaning, criteria, and actual translations in all
three suite-version-1 reports. These are manual judgments, not automated scores.
The suite fingerprint is
`2111b9df96336ceb68609e7d17061bea1a05cde25a694e865b036df5c3307acf`.

| Report | pass | minor_issue | major_issue | blocked | Document context (included in totals) |
| --- | ---: | ---: | ---: | ---: | --- |
| Qwen baseline-v1 | 2 | 5 | 3 | 0 | minor_issue |
| Qwen prompt-v2 | 1 | 4 | 5 | 0 | major_issue |
| Marian marian-v1 | 8 | 1 | 1 | 0 | pass |

Qwen v2 still mistranslates supervised learning and the prohibition against
overwriting, omits the translation instruction in the numbered item, and regresses
on RAG terminology. Marian preserves most examples, but translates document
retrieval as document restoration (Dokumentwiederherstellung), a meaning error.
Its numbers example has a missing article and percent-spacing issues; values
remain correct. Retaining the original English RAG expansion is permitted.

Marian is the stronger candidate on this small development set. This result does
not establish quality on arbitrary documents or robust document-wide glossary
handling. Marian is now the default in the CLI and quality runner; Qwen remains
explicitly selectable. Unsupported suite language pairs exit with code 2 before
loading the runtime or creating a report directory.


## Recheck after TXT processing changes

Keep suite version 1 unchanged for a direct comparison with `marian-v1` and
`prompt-v2`. New runs use sentence-sized calls, TXT heading recognition, and
original-text fallback with diagnostics. They evaluate the complete current
processing path, not a model-only change. The runner now records per-example
`issues`, matching CLI recovery. Pending results still require manual review;
retained originals must not be counted as successful translations automatically.
Exit code 3 indicates retained source units, while blocked cases take precedence
with exit code 1. Historical reports without `issues` predate this reporting field.

Run each command separately in Git Bash so one backend's nonzero status does not
prevent the other comparison:

```bash
python scripts/check_milestone.py
python scripts/evaluate_translation_quality.py --backend marian --output local-data/quality/marian-processing-v2
python scripts/evaluate_translation_quality.py --backend qwen --output local-data/quality/qwen-processing-v2
```

Review every result against its source and criteria. Record verdict changes from
the old reports, retained originals, and the document-context result separately.
Do not overwrite previous runs or infer semantic quality from exit status alone.

For a reproducible long-document check, use the committed synthetic input:

```bash
mkdir -p local-data/translations
doc-lingo tests/fixtures/translation_quality/long-technical-document.en.txt --target-lang de --output local-data/translations/long-technical-document.marian.run-01.de.txt
```

Compare the sensor-data introduction, classification, training/evaluation,
retrieval/generation, and final review sections. Check headings, negations,
enumerations, numbers, and terminology. See [evaluation files](evaluation-files.md)
for the current commands and output naming. The dated results below refer to the
earlier local input, not this new synthetic document.

## Processing comparison reviewed 2026-09-18

Both new reports completed all ten examples without blocked cases or recorded
fallbacks. Suite fingerprints and model revisions match the respective earlier
runs. These are assistant manual judgments of the saved outputs, not new GPU runs.

| Report | pass | minor_issue | major_issue | Document context (included) |
| --- | ---: | ---: | ---: | --- |
| Marian marian-v1 | 8 | 1 | 1 | pass |
| Marian marian-processing-v2 | 8 | 1 | 1 | pass |
| Qwen prompt-v2 | 1 | 4 | 5 | major_issue |
| Qwen qwen-processing-v2 | 1 | 7 | 2 | minor_issue |

Marian retains its earlier quality level; the missing article in the numbers
example is corrected, but percent spacing and the incorrect rendering of document
retrieval remain. Qwen improves supervised-learning terminology, the overwriting
prohibition, and the document-context expansion from major to minor issues.
Its standalone RAG explanation and numbered-list instruction still change or omit
meaning. Grammar remains weak. Marian remains the preferred backend on this set.

The local long-text output `ex_long_quality_v2.de.txt` now includes all reviewed
sections: ML introduction, both rainfall approaches, classification, unsupervised
learning, reinforcement learning, and generative AI through the final product-image
example. The previously missing classification and final training material are
present. This is a section-by-section review, not proof of complete semantic fidelity.

Remaining long-text issues include:

- `Classification` becomes `Einreihung`, an unsuitable ML heading.
- `multiclass classification` becomes `mehrstufige Klassifikation`, confusing
  multiple classes with multiple stages.
- `sleet` becomes `Schleuder`, a clear meaning error.
- `Reinforcement learning` becomes `Staerkung des Lernens` as a heading, with
  inconsistent terminology in the following prose.
- Sentence completion is rendered as the malformed phrase `autokomplette Saetze`.
- The description of additional supervised/reinforcement training has substantial
  grammar problems, although its main subject matter is present.

Some physical lines remain long because existing model/sentence line breaks bypass
the writer's collapsed-single-line reflow. Heading separation is retained. The
source itself announces a partial list without supplying that list; this is not a
translation omission. The processing changes improve observed coverage but do not
make unattended book translation reliable. Terminology and fluency need further
work, followed by evaluation on additional independent examples.

## Expanded glossary reviewed 2026-09-18

`marian-glossary-expanded-v1` completed all ten examples without recorded issues
or blocked cases. Manual review assigns 6 pass, 4 minor_issue, 0 major_issue.
The document-context example is minor_issue and is included in the totals.

Compared with `marian-processing-v2` (8/1/1), document retrieval is now correct
and original terms are included as requested. However, verbatim replacements
produce lowercase sentence starts in technical-terms, abbreviation-first-mention,
and abbreviation-document-context. Numbers-units retains its percent-spacing
issue. More minor issues therefore accompany the removal of the major meaning
error; pass counts alone would conceal the tradeoff.

The fixture's historical document-context limitation mentions no shared glossary;
this run does have the optional glossary, but still has no first-mention state.
Original fixture text and generated translations remain unchanged in the report.
See [glossary measurements](glossary.md#first-measured-results-2026-09-18) for
performance results and the remaining limitations. No new long-document review
is implied by this ten-example report.

## Trie and capitalization review (2026-09-18)

The latest `marian-with-glossary-run-01` short report scores 8 pass, 2 minor_issue,
0 major_issue and 0 blocked, with no recorded fallbacks. The document-context
case passes. The previous three sentence-start capitalization defects are fixed;
input terminology and percent spacing remain minor issues.

The separately reviewed committed long fixture has one fallback, recorded in
`long-technical-document.marian-glossary.run-01.de.txt.issues.jsonl`: heading
segment 3, Classification, remains original. Its other sections and final
requirement are present, but grammar and terminology remain imperfect. This
long-document result must not be conflated with the ten-example success rate.
See the glossary guide for the measured trie speed and memory changes.
