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
