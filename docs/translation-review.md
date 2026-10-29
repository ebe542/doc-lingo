# Editable translation review

Status: TXT job persistence, ODT review export/import and TXT finalization are
available through library APIs and the TXT review CLI. Structured-format
correction transfer remains planned. ODT is the agreed review document format.
The existing direct translation workflow remains available. PDF support is
deferred until the review and finalization workflow works reliably.

## Two workflows

Direct translation produces the translated document immediately, with the existing
diagnostics for unsupported content and recovery. It does not require human review.

Reviewed translation creates a persistent translation job and an editable ODT
review document. The translator returns the fully reviewed document; finalization
imports the chosen texts and generates the final document from the original
structure. Human corrections must never be sent through machine translation again.
Review export, import and finalization belong in the library; the CLI exposes them.

## Review document layout

Use one single-column table with four rows per source block, in source order:

| Row | Content |
| --- | --- |
| 1 | Source filename, reliable original page if available, and stable block ID |
| 2 | Original text with supported formatting |
| 3 | Machine translation with supported formatting |
| 4 | Initially empty space for the translator's replacement |

Use short labels to distinguish original, translation and correction. Labels and
block metadata are not part of the editable translation payload. Long blocks may
span pages; review-document pagination is not the original document's pagination.
TXT has no reliable page numbers. Do not infer ODT pages from paragraph counts or
stored page-number fields. Omit an unknown page rather than inventing one.

Do not add error rows, technical diagnostics, XML, marker strings, approval
checkboxes or per-block review flags. Returning the document means the translator
has completed review. Keep machine-readable diagnostic evidence separately.

The original and machine proposal are reference material; corrections belong in
row 4. A translator may copy a proposal into that row and edit text and supported
formatting. Supported style/link formatting should be visible, not represented
as XML. Review tables are a presentation device, not target-document tables.

## Selection and finalization

- A nonempty correction replaces the proposal, including supported formatting.
- An empty correction accepts the proposal shown in row 3.
- If translation fails or a text block cannot be translated, put the original in
  row 3. An empty proposal must not silently erase source content.
- Empty corrections, including editor-created empty paragraphs or whitespace-only
  content, never mean deletion. Intentional deletion is outside the first version.
- Changes to reference rows must not be silently ignored. Import should identify
  the affected block and ask the user to move edits into the correction row.

Structural items such as page templates, image anchors, table geometry and
headers/footers come from the original document. Corrected inline formatting is
authoritative where the target adapter supports it; do not run automatic word
alignment over a manually formatted correction to guess the translator's intent.
Accepted machine proposals retain their saved formatting evidence.

TXT finalization accepts text only. The initial review document must state this
once at the document level; formatting applied in a correction cannot become TXT
formatting. For structured target formats, unsupported edits must be reported
explicitly rather than silently discarded. Supported formatting and conversion
rules will be agreed before implementing those adapters.

The inventory must distinguish editable blocks from retained structural or
unsupported content. Visible unsupported text can be shown with its original as
the proposal, but that does not imply it can already be replaced safely. If a
translator edits such a block, finalization must explain the unsupported operation
instead of discarding the correction. Pure layout/field-only blocks need not be
presented as prose requiring review.

## Persistent job and identity

Keep the original, ordered block inventory, machine proposals and reconstruction
information in a persistent job separate from the editable review document.
Store a job identity, schema version, source fingerprint, source/target languages,
stable block IDs, block types and available source locations. Retain the original
model output independently of human edits for traceability.

The review document must carry the job identity and block identities in a form
that survives normal saving in the supported editor. The exact ODT identity
encoding and on-disk job schema are implementation decisions to validate with
editor round trips; row numbers and translated text are not reliable identifiers.

Import validates the job/schema, unchanged original, and complete unique block
mapping before publishing output. Reject missing, duplicate or unknown IDs and
malformed review structure with a readable explanation. Do not match by similar
text or silently accept a partial review. Block IDs determine source placement,
not the order in which edited tables happen to occur.

Save to a new destination and preserve the source, review document and job data on
failure. Finalization must be repeatable without loading translation models.
Job data is user-owned persistent work, not disposable temporary storage.

## Implementation sequence and acceptance

1. Define versioned job data and implement the full TXT round trip with ODT review:
   prepare, export, edit, import and finalize. Keep format-specific reconstruction
   outside the shared job/selection logic.
2. Add Markdown and ODT formatting transfer with explicit supported-edit policies.
3. Assess translation quality using several documents and human corrections.
4. Discuss PDF input/output requirements, then implement PDF support.

Split implementation into runnable commits with an agreed scope. Do not advertise
review commands until the complete workflow is available.

Acceptance must cover unchanged review, corrected text, empty corrections, failed
translation fallback, stable block mapping, missing/duplicate IDs, changed sources,
edited reference rows and publication failure. Include Unicode, long blocks and
literal marker-like text. Synthetic fixtures must not require private documents,
model downloads or GPU access. Real editor save/reopen/import checks are separate
from automated ZIP/XML checks and remain necessary.

## Later reuse of corrections

Original, machine proposal and final human text can form evaluation pairs or a
translation memory. They do not automatically train a model. Corpus export or
training is a separate feature requiring explicitly authorized documents and
traceable provenance; it is not part of the initial workflow.

## Implemented job persistence (schema 1)

Import `create_text_job`, `save_job`, `load_job` and `ReviewJobError` from
`doc_lingo.review`. For manual job construction, the caller supplies
ordered `TextSegment` proposals with the source IDs/types; this API does not run
translation. On translation failure, supply the original text as the proposal.
Source stability during proposal generation remains the caller's responsibility.

```python
from doc_lingo import PlainTextReader
from doc_lingo.review import create_text_job, save_job, load_job

# Model-free example: retain source text as each initial proposal.
with PlainTextReader("example.txt").iter_segments() as proposals:
    job = create_text_job("example.txt", proposals, source_lang="en", target_lang="de")
save_job(job, "example.review.zip")
loaded = load_job("example.review.zip")
loaded.verify_source("example.txt")
```

The ZIP contains exactly `job.json` and `source.txt`. The latter preserves original
bytes, including BOM, list prefixes, separators and line endings. JSON contains
schema version, UUID job identity, display filename, language pair, source SHA-256,
format `txt` and ordered blocks with ID/type/original/proposal. TXT has no reliable
page coordinates; none are invented. IDs follow the existing TXT reader.

Loading verifies the source hash and reconstructs the inventory with the TXT block
parser, rejecting changed original text, duplicate/reordered blocks, unknown fields
and unsupported versions. The display filename is never used as an extraction
path. The snapshot can be loaded after the external source is moved or removed;
`verify_source` explicitly checks a caller-selected original. Hashes detect
inconsistency, not malicious modification of both metadata and source.

Publication refuses existing destinations and uses temporary storage followed by
no-overwrite publication. Each uncompressed member is limited to 64 MiB; the first
implementation holds the job in memory. Store the archive as persistent user data.
Human edits, formatting evidence and diagnostics integration will extend the job
contract in subsequent steps; schema 1 does not accept structured document jobs.

## ODT export (review schema 1)

```python
from doc_lingo.review import load_job, export_review_odt

export_review_odt(load_job("example.review.zip"), "example.review.odt")
```

The export creates one four-row table per TXT block: source/ID, original,
proposal, and blank correction. Each text row has a label paragraph followed by
its payload paragraph. Labels are not part of the payload. Plain TXT has no rich
formatting; this step does not yet implement Markdown/ODT formatting transfer.
TXT list prefixes remain in the job's source snapshot; the review shows the same
translatable block text stored in the job, not reconstructed list numbering.

XML metacharacters are escaped. Tabs, spaces and line endings use explicit ODF
text elements. CRLF/CR display as line breaks; the exact original byte spelling
remains in the job archive. Long rows may split across pages. The correction row
has a minimum height rather than a fixed limit. The review's page numbers are not
source coordinates, so TXT blocks show no original page number.

Identity encoding is provisional until editor round-trip validation: tables use
`table:name="DLBlock_ID"`; custom document properties `doc-lingo.review-version`,
`doc-lingo.job-id` and `doc-lingo.source-sha256` bind the document to its job. These
are standard ODT metadata rather than visible technical rows. Prefix spelling of
XML namespaces is not part of the contract. The later importer must validate the
metadata and complete ID mapping instead of relying on table order.

Output paths must be new. Export validates the job, rejects XML-incompatible text,
checks the generated package and publishes without overwriting. It neither changes
the job archive nor loads translation/alignment models. Keep the job ZIP alongside
the ODT; see the import/finalization API below.

### Manual export example

After milestone checks pass, run from the repository root in Git Bash:

```bash
python - <<'PY'
from pathlib import Path
from dataclasses import replace
from doc_lingo import PlainTextReader
from doc_lingo.review import create_text_job, save_job, load_job, export_review_odt

root = Path("local-data/review-export/run-01")
root.mkdir(parents=True, exist_ok=False)
source = root / "example.txt"
source.write_text(
    'Keep model.predict(data) unchanged.\n\n'
    'Read <examples> & compare the results.\n\n'
    + 'This long paragraph tests page wrapping and table continuation. ' * 80,
    encoding="utf-8", newline="\n",
)
translations = {
    "1": "model.predict(data) unverändert lassen.\n",
    "2": "<examples> lesen und die Ergebnisse vergleichen.\n",
    "3": "Dieser lange Absatz prüft den Seitenumbruch und die Tabellenfortsetzung. " * 80,
}
with PlainTextReader(source).iter_segments() as segments:
    proposals = [replace(s, text=translations[s.id]) for s in segments]
job = create_text_job(source, proposals, source_lang="en", target_lang="de")
save_job(job, root / "example.review.zip")
export_review_odt(load_job(root / "example.review.zip"), root / "example.review.odt")
print(f"Review export complete: {root / 'example.review.odt'}")
PY
```

This uses explicit sample translations, not a model. Choose `run-02` etc. for a
repeat. Open the ODT in LibreOffice, inspect all four rows and the long paragraph,
then enter a correction and save under a new filename. Reopen it and check that
text remains editable, table continuation is readable, and document properties
and table names retain their IDs. Return the saved example for later import
validation; this stage does not claim an editor-verified round trip automatically.

## TXT correction import and finalization

```python
from doc_lingo.review import load_job, import_review_odt, finalize_text_review

job = load_job("example.review.zip")
segments = import_review_odt(job, "example.review_changed.odt")
finalize_text_review(job, "example.review_changed.odt", "example.final.de.txt")
```

`import_review_odt` returns selected `TextSegment` values in original job order.
Nonempty corrections win; empty or whitespace-only corrections accept the exact
saved proposal. Multiple correction paragraphs become newline-separated TXT text.
Inline styles and link labels contribute their text, not formatting or link URLs,
as stated in the exported document. Explicit tabs/spaces/line breaks are decoded.

The importer checks the job/version/source fingerprint, unique complete table IDs,
four-row/one-column structure, labels, and original/proposal reference text. Tables
may be reordered. References are compared after ODF whitespace decoding and newline
normalization, rather than by serialized XML. Editor-added spans, bookmarks and
soft page breaks do not change the reference text. Edits outside designated areas,
tracked changes, merged/repeated cells, embedded objects, fields and nested lists
or tables are rejected. Failures in a block identify its table ID.

`finalize_text_review` uses the original bytes in the validated job archive and the
existing TXT writer to preserve BOM, separators, list prefixes and block-ending
newlines. Internal correction line breaks become LF; multiline reflow follows the
existing TXT writer policy. No translation or alignment model is loaded. An optional
`original="example.txt"` argument checks an external source against the job hash
before import. Without it, the stored snapshot is authoritative; no original path
is inferred from metadata. Existing outputs are never overwritten, and temporary
snapshot/output files are cleaned up on failure and success.

### Validate the saved editor example

After milestone checks pass, use the saved example from the export review:

```bash
python - <<'PY'
from pathlib import Path
from doc_lingo.review import load_job, import_review_odt, finalize_text_review

root = Path("local-data/review-export/run-01")
job = load_job(root / "example.review.zip")
review = root / "example.review_changed.odt"
selected = import_review_odt(job, review)
for block, segment in zip(job.blocks, selected, strict=True):
    print(f"Block {block.id}: {'changed' if segment.text != block.proposal else 'proposal'}")
output = root / "example.final.de.txt"
finalize_text_review(job, review, output, original=root / "example.txt")
print(f"Review finalization complete: {output}")
PY
```

Choose a fresh output filename on repeat runs. For the previously reviewed example,
block 2 should contain the translator's correction; blocks 1 and 3 should retain
their proposals. Compare the output with the reviewed text and source structure.
The job ZIP and edited ODT remain unchanged. No model run is required.

## CLI workflow

The existing direct translation syntax is unchanged. For a human-reviewed TXT
translation, run from Git Bash with the project environment active:

```bash
doc-lingo review prepare local-data/review-export/run-01/example.txt \
  --target-lang de --output-dir local-data/review-cli/run-01
```

Create the parent directory first if necessary (`mkdir -p local-data/review-cli`).
The output directory itself must not exist. Preparation uses the same local Marian
backend by default, or `--backend qwen`; `--glossary FILE` is supported. The source
language is English and the existing backend language constraints apply. Only TXT
is supported in this review workflow. Alignment options are unnecessary for TXT.
Optional `.env` loading occurs only during preparation, never help or finalization.

Preparation snapshots the source before translation, calls the shared translation
service, and rechecks the external original before returning the job. Library
callers can use `translate_text_job(source, backend, source_lang=..., target_lang=...)`
with optional progress/issue callbacks. Supplying an issue callback enables the
existing recoverable-error source retention; unexpected/fatal failures propagate.

The new directory contains:

- `job.zip`: source snapshot, job identity and machine proposals.
- `review.odt`: editable four-row review tables.
- `issues.jsonl`: technical diagnostics only when translation issues occurred.

Preparation prints segment progress and artifact paths. A recoverable failure
keeps the original as the proposal and returns exit code 3 after publishing the
review. Exit code 0 means preparation completed without reported issues, not that
translation quality is approved. Fatal failures return 1; invalid command syntax
or language/format choices return 2. Fatal preparation discards staged artifacts
and their diagnostics. Normal publication failures roll back files linked by this
invocation. Abrupt process termination during publication can leave a partial
folder; do not use it as a complete job.

Edit the ODT Correction areas and save, for example as `review_changed.odt`. Then:

```bash
doc-lingo review finalize local-data/review-cli/run-01/job.zip \
  local-data/review-cli/run-01/review_changed.odt \
  --output local-data/review-cli/run-01/final.de.txt \
  --original local-data/review-export/run-01/example.txt
```

`--original` is optional; it verifies the external source against the job before
import. The job snapshot always supplies reconstruction structure. Finalization
loads no translation/alignment model and publishes only a new `.txt` file. It
returns 0 on completion and 1 for validation or I/O failure; wrong output extension
or command syntax returns 2. Keep the ZIP and edited ODT for repeatable revisions.
Run `doc-lingo review --help` for both commands.
