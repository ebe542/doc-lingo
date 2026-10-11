# ODT adapter design and sample inspection

Status: design only. No ODT reader, writer or CLI support is implemented yet.
The intended roadmap is TXT, Markdown, then OpenDocument text documents (ODT).
The earlier references to ODP presentations were a naming misunderstanding.

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
