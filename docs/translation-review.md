# Translation review workflow

## Current scope

TXT is the single review interchange format in both the library and CLI. The
unreleased ODT review exporter/importer and format-selection option were removed;
there is no ODT-review compatibility path. Normal ODT document translation is
unaffected. Job schema 1 currently supports TXT source documents only.

Translators receive source location/ID, original text, machine proposal and an
initially empty correction area for each block. No cover page, rich formatting,
checkboxes or technical diagnostics are included. See the exact
[TXT review contract](text-review-format.md) for delimiter escaping and validation.

Only Correction is editable. A nonempty correction replaces the proposal; an empty
or whitespace-only correction accepts it. Translation failures retain original
text as the proposal. Empty corrections never delete a block. Returning a review
means it has been fully checked. Corrections are never machine-translated again.

## CLI

With the existing local model environment active, run from Git Bash:

```bash
doc-lingo review prepare document.txt --target-lang de --output-dir document-review
```

The parent directory must exist and `document-review` must be new. Preparation
uses Marian by default, supports `--backend qwen` and `--glossary FILE`, and follows
the existing English-source language constraints. Optional `.env` loading occurs
only during preparation, never help or finalization. There is no alignment for TXT.

The directory contains:

- `job.zip`: immutable original snapshot, identity and ordered proposals.
- `review.txt`: the editable plain-text review.
- `issues.jsonl`: separate technical diagnostics, only when issues occurred.

Edit the Correction areas in a UTF-8 text editor and save as `review_changed.txt`.
Preserve control lines and reference text. Finalize without a model:

```bash
doc-lingo review finalize document-review/job.zip document-review/review_changed.txt \
  --output document.final.de.txt --original document.txt
```

The output must be new. `--original` optionally verifies an external source against
its stored fingerprint; the snapshot always supplies reconstruction structure.
The job filename is display metadata, never an inferred filesystem path.

Preparation prints segment progress and artifact paths. Recoverable translation
issues retain source text, publish the review, and return exit code 3. Success
without issues returns 0; this is not a linguistic quality verdict. Fatal errors
return 1; invalid command syntax/language/format choices return 2. Fatal preparation
discards staging files and diagnostics. Normal publication failures remove the
files created by that invocation. Abrupt termination can leave a partial folder;
do not treat it as a complete job. Finalization returns 0 on completion, 1 for
validation/I/O errors and 2 for invalid command syntax/output extension.

## Library and persistent job

```python
from doc_lingo.review import load_job, export_review_txt, import_review_txt, finalize_text_review

job = load_job("document-review/job.zip")
export_review_txt(job, "another-review.txt")
# Edit Correction sections and save another-review_changed.txt before continuing.
segments = import_review_txt(job, "another-review_changed.txt")
finalize_text_review(job, "another-review_changed.txt", "another-final.de.txt")
```

`translate_text_job(source, backend, source_lang=..., target_lang=...)` prepares a
job through the existing translation service, with optional progress/issue
callbacks. It translates an immutable snapshot and checks the external source
afterward. An issue callback enables recoverable source retention; without one,
recovery is strict. `create_text_job` accepts caller-supplied ordered TextSegment
proposals instead, with matching IDs/types and source text as the failure fallback.
`save_job` and `load_job` persist and validate the result.

Job ZIP schema 1 contains exactly `job.json` and `source.txt`. JSON stores schema
version, UUID job ID, source display filename, source/target languages, source
SHA-256, format `txt` and ordered blocks with ID/type/original/proposal. Source
bytes preserve BOM, list prefixes, separators and line endings. TXT has no reliable
source page numbers. Loading validates the hash and reconstructs the inventory
using the existing TXT parser, rejecting inconsistent identities or references.
Hashes detect inconsistency, not malicious changes to both source and metadata.

Archive members are limited to 64 MiB each; jobs are currently held in memory.
Publication refuses existing paths. Temporary files are removed after success or
failure. The archive is persistent user data and must be retained with the review.

## Finalization and formatting

Import checks review version, job identity, complete unique block IDs and unchanged
source labels/originals/proposals. Block order may change; IDs determine source
placement. Empty corrections select the exact saved proposal. Nonempty corrections
are used with normalized LF line endings. Validate the complete review before
publishing. Text outside defined sections and malformed boundaries are errors.

The existing TXT writer preserves the source BOM, separators, list prefixes and
block-ending newlines. Internal multiline reflow follows that writer's policy.
No formatting is inferred from punctuation in plain TXT. Literal asterisks, hashes
and XML-looking text remain text, not instructions or formatting.

For future structured formats, keep formatting and reconstruction evidence in job
metadata rather than in the review. Paragraph-level formatting can be reapplied
to its block. Inline styles/links still need correspondence to the selected target
text; original positions alone cannot establish it. Use conservative projection
and separate diagnostics for uncertain mappings, without retranslating corrections.
Schema 1 does not yet store Markdown/ODT formatting evidence. Protected formula/
field context and structured-source extraction need their own design and tests.

## Validation and next steps

The maintainer reported successful milestone checks after the CLI switch to TXT
and confirmed that corrections were applied in the practical CLI workflow. The
library export/edit/import/finalization example also passed. These checks do not
establish correctness across all documents/editors.

Next, define source-format metadata and plain-text extraction/reconstruction for
Markdown and ODT. Assess translation quality on several documents before adding
PDF or TeX/LaTeX. Original/proposal/correction pairs may later support evaluation
or translation memory; training is a separate, explicitly authorized feature.
