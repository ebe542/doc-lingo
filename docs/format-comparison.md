# Translation quality across formats

The paired suite `tests/fixtures/translation_quality/format-comparison.en-de.json`
contains three sentence groups, each as TXT, Markdown and embedded HTML:

| Group | Main question |
| --- | --- |
| `classification` | Is `processes` translated as a verb, and is emphasis retained? |
| `guide` | Is the German article correct, and does the link keep its label and destination? |
| `keep-code` | Is the instruction to keep code unchanged retained despite German word order? |

Each group uses the same English sentence wording. Formatting introduces either
emphasis, a link or protected code. This isolates one sentence at a time; it does
not reproduce all context from the longer Markdown example. In the TXT code
baseline the function call is ordinary text, so it deliberately has no syntax
protection. Differences show sensitivity to these inputs, not proof of a single
cause or overall model quality.

## Run

Use the existing quality runner, without a glossary for the initial comparison:

```bash
python -m scripts.evaluate_translation_quality --suite tests/fixtures/translation_quality/format-comparison.en-de.json --output local-data/quality/format-comparison-run-01
```

Marian is the default; `--backend qwen` selects the alternative model. The same
backend instance is reused across all nine examples. Existing CUDA/local-extra
requirements apply. Choose a fresh output directory for each run. No model
training, sampling change, prompt change or automatic correction is performed.

## Review

Open the new directory's `report.json`. Results are adjacent in groups identified
by `comparison_id`, with `format` identifying each variant. For every group compare:

- `source`, `reference` and `actual`: meaning, grammar and retained formatting;
- `backend_inputs`: exact service-to-backend input, including protection markers;
- `issues`: retained originals or repaired formatting, with available diagnostics.

Backend inputs are captured before backend-internal sentence splitting and token
budget handling. They are not token IDs or per-generation traces. If a glossary
is explicitly added, they are captured before that wrapper processes the input.
Do not infer model success from an unchanged original returned by recovery.

All completed translations remain `verdict: pending` for manual review. Reference
translations illustrate acceptable meaning, not a mandatory verbatim answer.
Model/runtime metadata, marker policy and suite fingerprint accompany the report.
Exit code 3 means there are issues to review; exit code 1 indicates blocked cases
or a setup failure. Reports are saved after each example; temporary document
directories are cleaned up on success and failure.

The existing default TXT suite remains unchanged. An omitted example `format`
still means TXT. The optional suite flag `capture_backend_input` defaults to false.
`format: html` means embedded HTML processed through the Markdown adapters, not
a newly supported standalone HTML document type.

## Review of the first Marian run (2026-09-29)

The locally generated `format-comparison-run-01/report.json` completed all nine
cases with marker policy `deterministic-prefix-v2`. The file is a local result,
not a required input. Its suite fingerprint is
`20558b87a3ec177013a5d8fcdcef9495db2deec424c52aa54d468aa887ae3061`.

| Group | TXT | Markdown | HTML |
| --- | --- | --- | --- |
| Classification | Correct verb: `verarbeitet` | Incorrect noun: `Prozesse` | Same incorrect noun |
| Guide | Correct | Correct; link retained | Correct; link retained |
| Keep code unchanged | Meaning retained | Valid candidate rejected by the old structure check | Meaning and code retained |

The marked Markdown and HTML variants supplied identical backend inputs within
each group. In the classification group, the marked input produced the same
grammatical error while unmarked TXT translated correctly. This demonstrates
sensitivity to protection markers for this example, not general model accuracy.

The Markdown code candidate started with the unchanged code followed by
`unverändert aufbewahren und das Ergebnis überprüfen.` The old check rejected
the missing leading plain-text token. The narrow fix excludes ordinary text-token
positions from structure comparison, while retaining block/inline nesting,
destinations, code contents, line breaks and nonempty inline-container checks.
Offline regression cases cover this candidate and forbidden structural changes.
The original run is not rewritten. Existing `pending` verdicts remain unchanged.

## Verification with the second Marian run (2026-09-29)

The local `format-comparison-run-02/report.json` uses the same suite fingerprint
and model/runtime metadata as the first run. All nine cases completed without
reported issues or errors. Eight outputs are unchanged; only the Markdown
`keep-code` case changed from retained English source to the German candidate:

```markdown
`model.predict(data)` unverändert aufbewahren und das Ergebnis überprüfen.
```

The code remains unchanged and the instruction is present. For software,
`unverändert lassen` would be more natural than `unverändert aufbewahren`.
The Markdown and HTML classification cases still incorrectly use `Prozesse`
instead of a verb. Links, attributes and emphasis are retained in these examples.
An empty issue list indicates that structural checks passed; it does not certify
linguistic quality. Manual verdicts in the generated report remain `pending`.

Marker-induced language degradation remains a known limitation. A future design
discussion will consider translating clean text and restoring formatting through
source/target alignment. No alignment implementation is part of this change.
