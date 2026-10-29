# Editable translation review

Status: agreed design, not implemented. ODT is the review document format.
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
