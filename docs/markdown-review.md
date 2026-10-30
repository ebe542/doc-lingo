# Markdown review jobs

This library-only step extracts plain review text and stores source evidence.
It does not prepare translations with a model or reconstruct a final Markdown
document. The review CLI remains TXT-only. Normal Markdown translation is unchanged.

## Supported text and protection

The existing Markdown adapter determines block IDs and boundaries. Headings,
paragraphs, list items, blockquotes and table cells become plain review blocks.
Emphasis, strikethrough and link syntax are removed from the review text. Entities
and escaped punctuation are decoded by the CommonMark parser. Line breaks inside
a block remain text newlines. Explicit link destinations stay in the snapshot.

Inline code is visible without backtick delimiters. Its content must remain exact
in proposals and corrections, although its position may change. CommonMark code
span whitespace normalization applies to the visible value; exact original
spelling stays in the snapshot. Autolinks and implicit reference labels are also
protected, following the existing document adapter's policy.

Each protected value must have one unambiguous literal occurrence in the selected
text. Word boundaries prevent matching `model` inside `models`. Repeated code,
the same spelling in ordinary prose, and overlapping protected values are
conservatively rejected with the block ID, even during job creation. This initial
policy deliberately does not guess identities. Literal validation does not prove
that the surrounding sentence remains semantically correct.

Pure code blocks (including their comments), YAML metadata and other regions the
document adapter excludes remain in the source snapshot, without review rows.
Mixed inline images/HTML and editable HTML blocks raise an explicit unsupported
error. They need a separate review representation before enabling them here.
The parser uses CommonMark plus tables and strikethrough. Unrecognized dialect
syntax may be ordinary text; arbitrary extensions are not guaranteed protection.

## Persistent evidence

Markdown jobs use schema 2 with `document_format="md"` and exactly two members:
`job.json` and `source.md`. Existing TXT jobs retain schema 1 and `source.txt`.
The UTF-8 source snapshot preserves BOM, newlines and all original syntax.

Each Markdown block adds `source_info`:

- `start` and `end`: half-open Python character offsets into the decoded source
  with its leading UTF-8 BOM removed, not byte offsets.
- `formatting`: block-local outer/inner source ranges from the existing adapter.
- `protected`: the exact visible protected values, in extraction order.

Validation rebuilds the block inventory and evidence from the snapshot. Altered
source positions, formatting evidence or protected values are rejected. These
are source coordinates, not target positions or a complete reconstruction plan.
Future reconstruction still needs to map formatting onto the selected target text.

## Model-free examples

Reusable synthetic inputs live in `tests/fixtures/review/`:

- `markdown-review.en.md`: headings, inline code, emphasis, a list, an explicit
  link, a blockquote, a table and excluded code/comments/metadata.
- `markdown-review.en-de.json`: eight expected plain blocks, fixed German
  proposals and sample corrections. These are test data, not model output.
- `markdown-ambiguous-code.en.md`: repeated inline code, expected to be rejected.
- `markdown-inline-html.en.md`: inline HTML, expected to be rejected.

The fixed examples are executable integration tests in
`tests/integration/test_markdown_review_workflow.py`. They create their artifacts
in pytest's temporary directory and require no model, external service or existing
`local-data` files. Run them from the project root in Git Bash:

```bash
python -m pytest tests/integration/test_markdown_review_workflow.py
```

The tests verify the eight-block inventory, archive save/load, source preservation,
plain-text export, unchanged proposals, all sample corrections and empty-correction
fallback. They also check reordered code in block 2, reject its deliberately
modified code with the correct block ID, and reject both unsupported source fixtures.
These checks run automatically as part of the normal milestone check and CI:

```bash
python -m scripts.check_milestone
```

No manual export/edit/import sequence is required for these fixed cases.
Optional visual inspection of the generated `review.txt` and `review_changed.txt`
can assess readability and spacing for translators; it is not a replacement for
assertions. Pytest prints the temporary artifact directory on failure. Successful
runs do not publish review files to `local-data`.

`markdown_review_segments` returns review text, not protection-aware backend
requests. `create_markdown_job` accepts already prepared plain proposals, not
Markdown or model markers. Retain original plain text on translation failure.
The TXT finalizer explicitly rejects Markdown jobs; these tests only export
and import review text, without producing a final Markdown document.

## Validation

The focused unit tests additionally cover source mutation, stored-evidence
tampering, varied code/reference protection, and rejection by the TXT finalizer.
No model evaluation is required for this extraction and persistence change.
