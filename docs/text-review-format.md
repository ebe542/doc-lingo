# Plain-text review format

Status: initial version-1 TXT export/import and finalization are implemented
in the library and CLI. TXT is the only review format; there is no ODT-review
compatibility path. Normal ODT document translation is unaffected.
This replaces the rich ODT review design. It does not replace the original source
document or the persistent job archive.

## Translator view

Use UTF-8 TXT with no cover page, rich text, checkboxes or diagnostic rows.
Present source location, original, machine translation and correction per block:

```text
doc-lingo-review: 1
Job-ID: 01234567-89ab-4cde-8012-3456789abcde

=== Block 12 ===
Source: example.odt
Page: 3
--- Original ---
Learning objectives

--- Translation ---
Lernziele

--- Correction ---

=== End Block ===
```

The ODT filename illustrates future structured-source support, not an implemented
feature. Page is optional and appears only when the source adapter supplies a
reliable original page. TXT has no page field. Review-editor pagination is never
used as a source location. Labels are English project UI text.

Only Correction is editable. A translator may copy the translation there and
change it. Nonempty corrections win; empty or whitespace-only corrections accept
the saved proposal. Untranslated blocks contain their original as the proposal.
Deletion is not encoded by an empty correction. Reordering complete blocks is
allowed; IDs determine the final source order.

No heading markers, list prefixes or inline formatting syntax are added to payload
text. Source adapters distinguish markup from literal content; a literal asterisk
or `#` in prose must not be removed just because Markdown uses it as syntax.
Technical failures remain in a separate machine-readable diagnostic file.

## Unambiguous text boundaries

Structural lines must match exactly and occupy a whole line. Block IDs are opaque,
job-owned identifiers represented using ASCII letters, digits, `.`, `_`, `:` or
`-`; the first implementation uses existing numeric TXT IDs. Unknown, duplicate
or missing IDs are errors. Labels inside a paragraph are ordinary text unless
they occupy an entire reserved line.

Payloads may contain arbitrary text, including text that resembles these controls.
Use a reversible line escape: prefix a backslash to any payload line that starts
with a backslash or exactly matches a structural line (including a block-start
line). Decode only such valid escapes. A normal line is otherwise untouched.
For example, literal `--- Correction ---` in prose is stored as
`\--- Correction ---`. This is delimiter escaping, not document formatting.
Do not interpret HTML, Markdown, XML or model markers in payloads.

Each section header is followed by a newline, the escaped payload, then one
mandatory framing newline before the next structural line. That final newline is
not payload. If payload already ends with a newline, the file therefore contains
an additional blank line, preserving that ending unambiguously. Empty corrections
contain only the framing newline. Never strip arbitrary blank lines from payloads.

Export uses UTF-8 without BOM and LF. Import may accept a leading UTF-8 BOM and
editor CRLF/CR line endings, normalizing them to LF before parsing. Original byte
spelling, BOM and block endings remain in the job snapshot for reconstruction.
Source filenames/location labels must be rendered on one line with reversible
escaping for backslashes and control characters; do not insert raw filename
newlines into document structure. Metadata values are compared to the job.

## Import contract

- Require a supported review version and matching job identity.
- Validate the job/source fingerprint using the existing job contract. The review
  does not need to show a long hash; the job retains it.
- Require exactly one complete block per expected ID and the fixed section order.
  Reject malformed controls and invalid escaping instead of guessing boundaries.
- Compare original, proposal and source-location fields with the job after the
  documented text normalization. Reject reference edits with the affected block ID.
- Reject unassigned nonempty text outside the defined header/blocks. Do not silently
  discard a correction pasted into the wrong location.
- Select corrections or saved proposals without translation. Validate the complete
  review before publishing a new final document. Preserve inputs on all failures.

The existing TXT writer supplies source separators and list prefixes. Subsequent
structured adapters will restore formatting from job metadata and project inline
scopes onto the selected text. This review format itself carries no editable
formatting and cannot establish word correspondence.

## Validation

Cover unchanged review, human correction, empty correction, multiline payloads,
Unicode, BOM/CRLF, original trailing newlines, escaped control lines/backslashes,
duplicate/missing/reordered blocks, changed references, invalid job/version and
failed publication. Tests must use synthetic inputs without models.

The maintainer reported successful milestone checks and a successful plain-text
export/edit/import/finalization round trip using the existing sample job. This
confirms the first practical workflow, not all editor or source-format behavior.
After the CLI switch, the maintainer also reported successful milestone checks
and confirmed that corrections were applied through the CLI workflow.
The previous ODT review experiment was unreleased and has been removed. Review TXT
must never be mistaken for a new source document during finalization.

## Library API and practical check

The library exposes `export_review_txt` and `import_review_txt` to
`doc_lingo.review`. `finalize_text_review` always reads TXT reviews; no format
selector is needed. This is interchange version 1, independent of job schema 1. Imports read at
most 128 MiB; exports enforce the same limit. Both currently hold text in memory.

The CLI supports TXT sources. The library additionally accepts
[Markdown review jobs](markdown-review.md); neither supplies source page metadata. Export labels use JSON
string escaping without surrounding quotes for source filenames. Original and
proposal comparisons normalize only line endings. Empty corrections select the
exact saved proposal, so its original newline spelling remains available to the
TXT writer. No additional markup stripping is performed on existing TXT blocks.

After milestone checks pass, export the previously saved sample without models:

```bash
python - <<'PY'
from pathlib import Path
from doc_lingo.review import load_job, export_review_txt

root = Path("local-data/review-export/run-01")
export_review_txt(load_job(root / "example.review.zip"), root / "example.review.txt")
print(f"Text review created: {root / 'example.review.txt'}")
PY
```

Open `example.review.txt` in a plain-text editor. Put a correction into one
Correction area, preserving the control lines and other sections. Save as
`example.review_changed.txt` in UTF-8. Then:

```bash
python - <<'PY'
from pathlib import Path
from doc_lingo.review import load_job, import_review_txt, finalize_text_review

root = Path("local-data/review-export/run-01")
job = load_job(root / "example.review.zip")
review = root / "example.review_changed.txt"
for block, selected in zip(job.blocks, import_review_txt(job, review), strict=True):
    status = "correction" if selected.text != block.proposal else "proposal"
    print(f"Block {block.id}: {status}")
output = root / "example.text-review.final.de.txt"
finalize_text_review(job, review, output)
print(f"Final TXT written: {output}")
PY
```

Choose fresh export/output paths on repeat runs. Check that the selected correction
appears in the final TXT and untouched blocks retain their proposals. Also assess
whether the control lines and spacing are practical for a translator; this is an
initial format that can be refined based on translator feedback. Both the library round trip
and the practical CLI correction workflow have passed maintainer verification.
