# ODT adapter design and sample inspection

Status: package inspection and a limited reader/writer are implemented. ODT CLI
translation is not yet available. Inline support uses conservative protection
by default, with opt-in alignment-based formatting through the library service.
The intended roadmap is TXT, Markdown, then OpenDocument text documents (ODT).
The earlier references to ODP presentations were a naming misunderstanding.

## Initial reader/writer subset

Import `OdtReader` and `OdtWriter` from `doc_lingo.documents.odt`. These implement
the existing protocols but are not yet exported at the library root or selected
by the CLI. UTF-8 `content.xml` is required for this editing subset.

Nonempty supported `text:p` and `text:h` elements in the direct main flow
or list containers are yielded. Nested lists retain their XML structure; a list
item's paragraphs have type `list_item` without guessing its numbering style.
IDs follow all paragraph/heading occurrences, so skipped blocks leave gaps.
Each new reading session produces an independent iterator and closes it on exit.
The complete XML and block index are in memory; this is not streaming XML editing.

`reader.skipped_blocks` records empty blocks, unsupported containers, and blocks
with unsupported inline children, comments, processing instructions or CDATA.
Fully protected blocks are skipped as well. These blocks remain
unchanged. This inventory covers `content.xml` only; header/footer text in
`styles.xml` remains untouched and is not inventoried here. Inventory entries are
not yet service-level issue callbacks. Consequently this subset must not be
advertised as a complete translation of the local sample.

The writer requires exactly the supported IDs and types in source order. An
unchanged text uses its original XML bytes, including entity spelling. Changed
text is XML-escaped and patches only the inner byte range, preserving surrounding
markup, namespaces and attributes. Byte offsets are private document coordinates,
not shared model-character coordinates. The parser uses Python's documented
[Expat byte positions](https://docs.python.org/3/library/pyexpat.html#xmlparser.CurrentByteIndex)
and rejects DTDs rather than resolving entities from external sources.

Empty/invalid XML text is rejected. Changed plain-text blocks containing tabs,
newlines or repeated spaces are still rejected; inline blocks retain their
existing explicit whitespace elements as protected XML fragments.
The writer copies other member payloads without XML reserialization, retaining
archive ordering and comment; compressed bytes of the entire ZIP may differ.
The existing source must remain unchanged throughout reader/writer use. Metadata
statistics and thumbnail bytes are preserved, not recalculated, and may be stale
after edits. Output package inspection precedes no-overwrite hard-link publication;
temporary output is cleaned on failure. The caller owns the translation iterator.

Model-free round trip from the project virtual environment:

```python
from pathlib import Path
from doc_lingo.documents.odt import OdtReader, OdtWriter

source = Path("local-data/Introduction-to-Machine-Learning.odt")
reader = OdtReader(source)
with reader.iter_segments() as segments:
    OdtWriter(source).write(Path("local-data/odt-round-trip.odt"), segments)
print([(block.segment.id, block.reason) for block in reader.skipped_blocks])
```

Choose a fresh destination. This copies untranslated content and checks the
adapter mechanics; it is not a real-model or visual-layout validation. Automated
tests use generated documents instead of the local sample.

## Conservative inline protection

Supported paragraphs can contain nested `text:span` elements and `text:a` links.
Decoded prose remains one segment across style boundaries. Exact opening/closing
tags are protected through the existing marker translation path; attributes,
style references and link destinations are not sent to the translation backend.
This is an intermediate preservation path, not invisible formatting projection:
markers may still affect translation quality. Supplying an aligner instead enables
the projection path described below for supported inline segments.

Explicit spaces, tabs, line breaks, bookmarks, page fields, sequence fields,
soft page breaks and drawing frames are retained as opaque source fragments.
Text inside a protected frame is not translated through its enclosing paragraph.
Unknown inline elements conservatively retain the entire paragraph. Tables and
text boxes remain unsupported containers; headers/footers remain untouched.

The writer requires protected fragments in their original order and escapes only
translated prose. Missing, duplicated or reordered markers cause the existing
service recovery to retain the original paragraph and report an issue through
`on_issue`; later paragraphs can continue. Direct writer calls with damaged
fragments fail before publication. Structural validation cannot establish that a
retained style or link still covers the linguistically correct words. Real-model
and visual review are therefore still required before CLI activation.

## Optional aligned formatting

Pass a caller-owned `aligner` to `translate_document` with `OdtReader` and
`OdtWriter`. Source layouts remove `text:span` and `text:a` wrappers from model
input; only opaque contents receive markers. XML attributes and link destinations
remain source-owned. Without an aligner the existing protected path is unchanged.

The shared pipeline translates sentence-sized units, with further subdivision
when required by the token budget, and aligns the exact source/target call pairs.
It never pairs independently split target sentences by ordinal position. A style
covering complete translation units can use their boundaries, including across
sentences; partial scopes require word correspondence.

Unresolved formatting is dropped and reported while translated text is retained.
Disjoint style mappings may split a style; links expand to a continuous range.
Crossing XML scopes and overlapping links are dropped with diagnostics. Markers
must restore the exact opaque contents in their original order, and projected
boundaries cannot split an opaque element. Content validation or recoverable
backend failures retain the original paragraph when `on_issue` is supplied.
Without that callback, content recovery remains strict.

The ODT renderer escapes translated prose and inserts original wrapper fragments.
The writer reproduces rendering from projection evidence before accepting it,
then applies the existing package validation and no-overwrite publication rules.
Wrappers with local namespace declarations or `xml:id` use the protected path:
moving namespace bindings or duplicating unique identities is unsupported.
Namespace bindings on surrounding unchanged document elements remain intact.

Formatting diagnostics use the existing callback and segment IDs; they do not
provide linguistic confidence scores. Model-free tests cover preservation and
failure handling. Real-model translation and visual layout still require review;
this step does not activate ODT CLI selection or add table/text-box support.

## Implemented package inspection

`doc_lingo.documents.odt.inspect_package(path)` returns an immutable
`OdtPackageInfo` containing member names and the original content/styles XML
bytes. It validates required members, duplicate/path checks, stored/deflated
compression, the ODT MIME entry and its first uncompressed local header without
extra fields, manifest document type and referenced files, XML roots and one text
body. Styles are optional, but when present must be declared and well formed.
Filesystem errors propagate; invalid/unsupported packages raise `OdtPackageError`.

Encrypted and signed packages and XML document type declarations are rejected.
Inspection limits are 16 MiB per parsed XML part and 256 MiB declared total
uncompressed package size. The parser is used only for inspection; original XML
bytes are retained, not serialized. Images and other opaque members are not read
or CRC-validated in this step. This is not full schema validation, a general ZIP
security audit, or a guarantee that an editor can render every member.

The implementation uses standard-library `zipfile` and `ElementTree`, without a
new dependency. Package checks are based on
[ODF 1.3 Part 2, sections 2–4](https://docs.oasis-open.org/office/OpenDocument/v1.3/os/part2-packages/OpenDocument-v1.3-os-part2-packages.html).
The XML policy also considers Python's
[XML processing security notes](https://docs.python.org/3/library/xml.html).
The supported subset intentionally rejects inputs beyond this first stage.

Synthetic ZIP packages are generated in pytest temporary storage by
`tests/documents/odt/conftest.py`; the local sample is not used by automated tests.
Fixtures exercise basic XML structure rather than claiming full ODF schema
conformance or editor round-trip validation. They contain headings, inline spans,
explicit whitespace, nested lists, cell paragraphs, a bookmark, a field and an
image reference. Additional model-free fixtures exercise aligned style and link
reconstruction, opaque contents, sentence boundaries and conservative fallback.

## Sample inspected on 2026-10-11

Local input: `local-data/Introduction-to-Machine-Learning.odt`. The file is not
a committed test fixture and must not be required by automated tests. This review
reads ZIP/XML structure; it does not render the document or verify visual layout.

| Observation | Count or value |
| --- | --- |
| File size | 2,923,581 bytes |
| ZIP entries | 17 |
| MIME entry | `application/vnd.oasis.opendocument.text` |
| Headings in content.xml | 9: one level 1, one level 2, seven level 3 |
| Paragraph elements in content.xml | 93 |
| Paragraph contexts | 25 body, 21 list-item, 43 table-cell, 4 text-box |
| Lists / list items | 9 / 21; observed maximum nesting depth 1 |
| Tables / rows / cells | 4 / 11 / 31 |
| Inline spans / links | 129 / 18 |
| Drawing frames / image references | 12 / 8 |
| Text boxes / sequence fields | 4 / 4 |
| Soft page breaks / explicit line breaks | 3 / 3 |
| Explicit space elements | 9 |
| Bookmark starts / ends / standalone bookmarks | 3 / 3 / 7 |
| Automatic style elements in content.xml | 72 |

The paragraph-context counts assign text boxes first, then table cells, then list
items; they are disjoint counts, not a count of future translatable segments.
Empty paragraphs and protected contents still need classification.

`styles.xml` also contains a header, footer, page-number and page-count fields.
`meta.xml` records six pages and 99 paragraphs. These are saved application
statistics, not a fresh layout calculation or a substitute for XML inspection.
The package includes eight image payloads and a thumbnail. The inspected manifest
contains no encryption entries. Signed/encrypted or malformed input still needs
an explicit policy before support is advertised.

## First supported subset

Start with headings and ordinary paragraphs in the main document flow, including
paragraphs in list items. Retain heading levels, list structure, paragraph style
references, images and other non-text content. Preserve empty paragraphs.

Translate a paragraph as one semantic segment even when multiple inline spans
divide its text. A span is a style boundary, not a sentence or translation unit.
Explicit line breaks inside an item must not split it into unrelated segments.
An item with multiple paragraphs yields multiple ordered segments while retaining
its list container. Nested lists require synthetic tests even though this sample
contains only one level.

Tables are the next increment: process paragraphs within cells while preserving
cell and row structure. The sample contains multiple paragraphs in some cells;
one cell must not automatically become one flat string.

Text boxes, captions/sequence fields, headers and footers need separate handling.
Until supported, preserve them and report skipped visible text. Do not advertise
the sample as completely translated when such regions are retained. Embedded
images are copied unchanged; text inside raster images is not translated.

## Architecture and preservation rules

- Add a `documents/odt` package implementing the existing `DocumentReader` and
  `DocumentWriter` contracts. Root exports and CLI selection follow only after a
  working read/write path exists.
- Assign stable IDs from traversal of supported text containers in an unchanged
  source. Retain XML-node references or paths separately from model-text offsets.
- Represent inline style scopes and link labels through shared source-layout and
  translation-input concepts where applicable. Preserve link destinations and
  attributes; do not send XML syntax to the model.
- Decode explicit space, tab and line-break elements deliberately rather than
  flattening everything with `itertext()`. Preserve field/bookmark/frame identity
  and avoid translating text-box children twice through an enclosing paragraph.
- Keep paragraph-level style references even when an uncertain inline style has
  to be dropped. Never guess character boundaries from original XML offsets after
  translation. Reuse complete-unit evidence and conservative word projection,
  with an ODT-specific renderer and validation rather than Markdown wrappers.
- Preserve non-edited package members as bytes, including image payloads and
  style definitions. This does not imply a byte-identical ZIP container. Select
  the XML editing approach after checking namespace and extension preservation;
  a naive whole-document serialization is not an accepted preservation guarantee.
- Write to a separate destination, validate the result before publication and
  reject existing output paths, following the existing writer contract.
- Decide how to handle stale statistics and thumbnails explicitly: neither may
  be presented as evidence of the translated document's page layout.

## Diagnostics and layout

Report segment ID, type and paragraph context for translation or formatting
problems. Leave `page` unset unless a trustworthy page association is available.
Do not infer it by counting paragraphs or soft-page-break hints. Retain the
original document language for recoverable failures with diagnostics, as in the
existing service; fatal package or XML failures must not publish a partial file.

Longer translated text can change wrapping, pagination and image placement.
Preserving style references is not a guarantee of unchanged layout. Final review
must open the output in an ODT-capable editor and inspect it visually. Verify
the original package remains untouched and that image payloads are unchanged.

## Implementation sequence

1. Package inspection/validation and synthetic fixture infrastructure; document
   unsupported input and archive/XML handling. No translation claim at this stage.
2. Main-body paragraph/heading/list reader plus matching writer, with a model-free
   unchanged-text round trip and stable ordering/resource-cleanup checks.
3. Inline text, protected content and formatting restoration; integrate the library
   service and CLI once the subset is usable. Add recoverable issue reporting.
4. Table-cell paragraphs, then separately text boxes and document peripheral text.
5. Real-model evaluation on the local sample and visual review of images, headings,
   lists, links, unsupported text and changed pagination.

Use small generated ODT fixtures for automated tests: multiple styles in one
paragraph, nested lists, cell paragraphs, explicit whitespace, a protected field,
a bookmark and an image anchor. Tests must not require the user's local file or
a model download. Before choosing XML/ODF dependencies, verify their relevant
preservation behavior and package requirements against authoritative documentation.
