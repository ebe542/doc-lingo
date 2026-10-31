# Markdown review jobs

The library extracts plain review text, stores source evidence and reconstructs
Markdown from selected proposals or human corrections. It does not prepare
Markdown review translations with a model. The review CLI remains TXT-only.
Normal Markdown translation is unchanged.

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
Finalization maps formatting onto selected target text using optional alignment;
source offsets alone do not establish target positions.

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
The TXT finalizer explicitly rejects Markdown jobs. Use the separate
`finalize_markdown_review` function for Markdown reconstruction.

## Markdown finalization

```python
from doc_lingo.review import finalize_markdown_review, load_job

job = load_job("document-review/job.zip")
issues = finalize_markdown_review(
    job,
    "document-review/review_changed.txt",
    "document.final.de.md",
)
for issue in issues:
    print(f"Block {issue.segment_id}: {issue.reason}")
```

The job must be Markdown schema 2 and the output must not exist. The optional
`original=...` checks an external source fingerprint; reconstruction always uses
the snapshot. No translator or automatic model loader is invoked. Pass an
initialized `TextAligner` through `aligner=...` to project partial formatting from
original plain text onto the selected correction (or proposal).

- Unchanged blocks retain their original spelling exactly, without alignment.
- Block syntax, source separators, BOM and excluded contents stay source-owned.
- Inline code, autolinks and implicit references regain their original syntax at
  their validated new locations. Ordinary correction punctuation is escaped so
  literal text cannot become new Markdown markup.
- Complete-block formatting can be restored without word alignment. Partial
  formatting needs alignment evidence; absent, failed or uncertain alignment
  drops that formatting while retaining the reviewed text.
- The existing projection policy splits optical styles, expands discontinuous
  links, and drops conflicting or unrenderable scopes. Every such event is
  returned as a `TranslationIssue`, optionally also sent to `on_issue` for logging.
- Hard Markdown line breaks in changed blocks are not projected yet. They produce
  a formatting warning; plain correction newlines become soft line breaks.
- Corrections may change soft wrapping, including list continuations, but must
  retain the block inventory and hierarchy. Table-cell corrections must stay on
  one line. Introducing extra paragraphs or losing protected contents is an error.

Before publication, the complete output is parsed again to verify its visible
text and block structure. Errors and logging callback failures prevent publication.
Temporary files are cleaned up and existing outputs are never replaced. No extra
issue file is created implicitly by the library; consume the returned issues or
supply the existing application logging callback. Unknown Markdown dialects and
mixed HTML/images retain the extraction limitations described above.

## Validation

The focused unit tests additionally cover source mutation, stored-evidence
tampering, varied code/reference protection, and rejection by the TXT finalizer.
`tests/review/test_markdown_finalize.py` covers final reconstruction, corrected
text, nested styles, split/expanded scopes, alignment failures, literal punctuation,
tables, block boundaries, source snapshots and publication cleanup. The reusable
fixture is also finalized and re-extracted to verify all selected texts.
No model evaluation is required for these deterministic tests.
