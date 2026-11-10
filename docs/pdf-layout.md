# Experimental PDF layout evidence

The `experiment/pdf-layout` work starts with PDF inspection and separately
reviewable text grouping, before translation or Scribus export. `doc_lingo.pdf_layout.extract_layout`
exports schema-versioned JSON and separate assets. It does not yet reconstruct
an editable document or promise a lossless rendering round trip.

## Run

Install the optional extraction dependency in the active virtual environment:

```bash
python -m pip install -e ".[pdf]"
python -m scripts.extract_pdf_layout input.pdf \
  --pages 1 2 3 \
  --output local-data/pdf-layout/extraction-01
```

Page numbers are **1-based physical PDF pages**, not printed book numbers.
Omit `--pages` to extract the entire book. The output parent must exist and the
output directory must not exist. Extraction stages its files in a sibling
temporary directory, cleans that directory on ordinary failure, and publishes
after writing the manifest. Completion prints the manifest path. No translator,
GPU, network access or `.env` is involved.

PyMuPDF is optional for normal translation, and included in the development
extra so synthetic PDF tests also run in CI. PyMuPDF is available under AGPL or
a commercial license; installing it as an extra does not exempt its use or
distribution from those terms. The experiment does not change the project's
own MIT license. See the [upstream licensing information](https://pymupdf.io/licensing).

## Files and objects

```text
manifest.json
pages/page-0001.json
assets/images/<sha256>.<extension>
assets/graphics/page-0001.json
fonts/<sha256>.<extension>       # only with --export-fonts
```

The manifest records schema version 1, the input basename and SHA-256, source
page count, selected page files, extraction engine/version, coordinate conventions,
and the shared font inventory. It never stores an absolute source path.

Each page records its physical number, label, MediaBox, CropBox, rotation and
conversion matrices. Extracted coordinates use unrotated MuPDF page space:
top-left origin, x right, y down, points. The display rectangle includes page
rotation; it is not the coordinate system of the text fragments. Original PDF
boxes and the recorded matrices allow explicit conversion.

Objects are currently plain JSON mappings:

- `text_fragment`: engine block/line references, direction and writing mode,
  Unicode text, original span data with character origins/bounding boxes, font
  size, flags and color. Spans stay separate across font/style changes. Engine
  blocks are extraction hints, **not established paragraphs**.
- `image`: one occurrence with original geometry/transform and image metadata,
  a content-addressed image file, and a separate mask when supplied by the engine.
  Identical image bytes share a file. Labels baked into pixels remain pixels.
- `unhandled`: an unexpected raw block retained for inspection.

IDs combine physical page number, engine block enumeration, line and span.
They are deterministic for the same input and engine; changes to the PDF or
extractor version can change them. They are not yet translation-job identities.

Vector drawings are separate JSON path records from `get_cdrawings(extended=True)`.
They include drawing attributes and available clipping/group records, not guessed
semantic figures or SVG exports. A separate page paint log records rendering
sequence and bounds. Its entries are **not yet mapped to text/image IDs**; raw
text extraction order must not be mistaken for paint order or reading order.

## Fonts

PDF font resources reference shared inventory entries by xref-based ID. Entries
record the original PDF name, subset prefix, base name, PDF type, reported
embedding status, extension and optional font asset. A base name is not a verified
family/style classification. A subset may lack characters needed for German.

Text spans are matched to page fonts only when their normalized names have one
candidate. Name matching is recorded as such, not treated as proof of resource
identity. Ambiguous/unmatched spans have `font_id: null` and retain the engine
font name and candidate list. Resource inventories can include unused fonts.

When no exact match exists, names with at least 16 characters are checked against
resource-name prefixes. A single candidate is marked `name_prefix_candidate`;
`font_id` stays null because truncation is not proof of identity. Multiple
candidates remain unresolved. Exact matches take precedence, so a regular or bold
font is never replaced by a longer italic name through this heuristic.

Extraction itself leaves `system_availability` as `not_checked`. The separate
[local font report](pdf-fonts.md) scans common font directories and supports
explicit file/face mappings without modifying this evidence. No silent
substitution, installation or automatic downloads are attempted.

With `--export-fonts`, embedded bytes are exported when available. Use this only
when you have the necessary rights; PDF embedding alone does not grant permission
to reuse or redistribute a font. No attempt is made to turn subsets into complete
fonts. Export status distinguishes not requested, exported and unavailable.

## Limits and next steps

This is extraction evidence, not yet a complete scene graph. Annotations/widgets,
patterns, complex transparency and exact text-to-paint-order association require
further work before layout reproduction. Missing/incorrect Unicode mappings and
text inside raster images are not repaired or OCRed. The original PDF remains the
authoritative visual reference. It is not copied into the export.

Processing keeps one source snapshot and one page's extraction data in memory;
large PDFs and image-heavy pages can still require substantial memory. Character
records make JSON intentionally verbose. Compression can be added after the
format and reconstruction requirements have been exercised.

## Derived text groups

Group existing extraction data without reopening the PDF or changing its JSON:

```bash
python -m scripts.group_pdf_layout local-data/pdf-layout/extraction-01 \
  --output local-data/pdf-layout/groups-01
python -m scripts.preview_pdf_layout input.pdf \
  --layout local-data/pdf-layout/extraction-01 \
  --groups local-data/pdf-layout/groups-01 \
  --output local-data/pdf-layout/group-preview-01
```

The separate group manifest records the algorithm `conservative-lines-v2` and
the extraction manifest hash. Per-page files contain the original page JSON hash,
derived lines and candidate paragraphs. Every group references its line IDs and
original fragment IDs. Each text fragment belongs to exactly one candidate block.
Group IDs are deterministic for the same evidence and algorithm, not stable across
algorithm revisions. Image and vector objects remain in the original extraction.

The rules retain engine block boundaries except for geometrically compatible
continuations of separately marked list items. Within each engine block, visual
rows are rebuilt by baseline proximity, independently of engine line numbers.
Horizontal fragments are ordered by x position and joined only across
small gaps and compatible baselines. Existing text is preserved; a space is
inserted across a visible gap when neither fragment already supplies whitespace.
Subsequent lines join only with similar font sizes, plausible baseline spacing,
compatible left margins and horizontal overlap. A first-line indent may return
to the margin. New list markers, larger gaps, new indentation, short preceding
lines and size changes end a candidate paragraph. Rotated/vertical fragments stay
separate. Inline style changes do not by themselves split a line.

These are geometric heuristics, not semantic classification. Small captions,
headings, code, tables or tightly spaced columns can still be grouped incorrectly.
Distinct engine blocks outside marked lists are not joined even if they belong to the same paragraph.
No cross-page merging, reading-order inference or hyphen removal is performed.
Group text keeps line breaks, including `inspira-\ntion`; it is not yet a final
translation input. Original character geometry remains available in the evidence.

Standalone bullet glyphs (including private-use Wingdings/Dingbats symbols) are
retained as separate `list_marker` groups, not converted to raster graphics.
The following text block references the glyph via `marker_ids`; the glyph is not
included in its translation text. A nearby continuation aligned with the list
text may cross an engine block boundary. A new marker starts another item.
This initial rule requires a separate glyph fragment on the same visual row;
symbols embedded inside a larger text fragment are not split automatically.

Each block records `layout.line_lefts` and `layout.first_line_indent` in points.
These preserve first-line indentation explicitly, in addition to the unchanged
source coordinates. Grouping does not remove inline emphasis or original spaces.
The experimental Scribus exporter uses first-line indentation; arbitrary per-line
indentation is not yet reconstructed.

The preview adds pink candidate-block bounds and a table with their text and
source fragment IDs. With groups supplied, raw bounds are initially hidden to make
overlapping fragment and group rectangles distinguishable. They can be enabled
independently. Manifest/page
hashes prevent displaying stale groups against changed extraction data. Visual
inspection is required before using these candidates for translation or export.

The [first Scribus export experiment](scribus-export.md) follows grouping review.
Translation integration remains a later step.

## Validation

Create a separate offline HTML view after extraction:

```bash
python -m scripts.preview_pdf_layout input.pdf \
  --layout local-data/pdf-layout/extraction-01 \
  --output local-data/pdf-layout/preview-01
```

Open the resulting `index.html` in a browser. It uses local PNG reference pages
rendered from the source PDF and SVG bounding rectangles from the extracted data.
Blue means text, orange dashed means uncertain font matching, green means images,
and purple means vector/clip bounds. Hover for IDs/text; expand the object table
to inspect font candidates. Each page has an overlay toggle. Rotation is applied
to the bounds before display. Vector rectangles are bounds, not redrawn paths.

The source SHA-256 must match the extraction; the original JSON is never modified.
The view requires no web server, external fonts or network requests. It is **not**
a reconstructed layout: looking correct cannot demonstrate complete extraction,
correct clipping, reading order, or successful Scribus conversion.

Synthetic fixtures are generated by executable tests, without copyrighted books,
installed fonts or model downloads:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/pdf_layout
python -m scripts.check_milestone
```

Tests cover text geometry, repeated image assets, vector paths, page selection,
rotation, blank pages, font-export opt-in, source hashes, stable IDs, rejected
encrypted input, cleanup and existing-output protection. Book inspection remains
separate from these deterministic checks.

Extraction APIs: [PyMuPDF Page](https://pymupdf.readthedocs.io/en/latest/page.html),
[Document/font resources](https://pymupdf.readthedocs.io/en/latest/document.html).
