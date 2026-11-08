# First editable Scribus layout experiment

This exports the **English original**, before translation. A preparation command
reads immutable extraction/group JSON and creates `plan.json` plus portable graphic
assets. A separate script runs inside Scribus and creates a new editable document,
`layout.sla`, with one text frame per candidate text group. It writes readable and
JSON export reports. The manual font catalog is optional, not a prerequisite.

## Font choices

`docs/examples/scribus-font-map.json` is an explicit **example-book trial**, not a
global fallback policy. It selects NewBaskerville Regular for Roman, Franklin
Gothic Medium Regular/Italic for Demi/DemiItal, and DejaVu Sans Condensed Bold for
Humanist 521. These are documented replacements, not promises of metric equality.
It also explicitly resolves the example's two truncated source-font names.
Inspect or copy/edit this file before using it. Fonts are not downloaded or installed.

This export map is distinct from the file/face map used by `check_pdf_fonts`:
it names the actual Scribus face, not a font file. `fonts` is keyed by source
PostScript name without its PDF subset prefix. Each entry requires `kind`
(`original` or `replacement`), `scribus_name` and a nonempty `reason`.
`fragment_fonts` maps an uncertain extraction name to a source base name and is
accepted only if it identifies exactly one existing candidate. An optional
`extraction_sha256` restricts the map to one extraction; the plan always records
the source/extraction/group hashes and the complete mapping used.

An explicit font choice takes precedence. Without one, the importer requires a
unique available Scribus face with the original PostScript name. It fails before
creating a document if a font is missing/ambiguous or an `original` choice has a
different PostScript name. There is no silent font substitution.

## Prepare and import

From Git Bash in the repository, substituting your PDF path:

```bash
python -m scripts.prepare_scribus_layout input.pdf \
  --layout local-data/pdf-layout/extraction-02 \
  --groups local-data/pdf-layout/groups-02 \
  --font-map docs/examples/scribus-font-map.json \
  --output local-data/pdf-layout/scribus-01
```

The output directory must be new; its parent must exist. Existing source,
extraction and group files are never modified. Changed source/page hashes and
incomplete group coverage fail preparation. Review `plan.json`, the selected fonts
and `preparation.md` before import. The plan contains no executable code.

In Scribus, use **Script > Execute Script** to run
`scripts/import_scribus_layout.py`, then choose the generated `plan.json`.
Alternatively launch your installed Scribus executable with
`--python-script` followed by the absolute script path. Do not run this import
script in the project virtual environment; the installed Windows Scribus uses
its own Python 3.8, so the script uses only compatible standard-library features.

The importer validates asset hashes and font availability, creates a new document,
imports graphics, then creates text frames with explicit style ranges. It saves
`layout.sla` next to the plan and reopens that file for editing. The assets directory
must remain beside the SLA. Existing export outputs are refused. A failed import
can leave its newly created document open for diagnosis; it never closes an
existing user document. Publication is not a multi-file transaction: if saving a
report fails after the SLA is saved, the SLA may already exist.

`export-report.md` lists original-to-selected fonts by source PDF page and block,
including reasons, and the detected text overflows. `export-report.json` provides
the same evidence in structured form. The script does not shrink fonts or resize
frames automatically. Manual review always remains pending.

The completion dialog and reports summarize the number of overflowing text frames
and distinct font replacements (source PostScript name without subset prefix plus
selected Scribus face). Reusing a replacement across blocks does not increase the
replacement count. The dialog includes the readable report path. Zero overflows
does not prove matching line breaks or layout fidelity.

The first example-book visual review found the overall layout promising, with
additional line breaks. Its report recorded 18 overflowing frames across source
pages 20, 24 and 49, including frames using original fonts. Frame geometry is still
copied from PDF text bounds; automatic frame expansion is a separate follow-up.

## Supported first-pass layout and known limits

- Equal-sized, unrotated pages with horizontal BMP text. Rotated/vertical text,
  supplementary Unicode and mixed page sizes fail explicitly in this prototype.
- A text frame per candidate block, preserving font size, RGB color, inline font
  changes, fixed line spacing and first-line indentation. Original line breaks
  become soft breaks; hyphens remain. Full justification, tracking, ligatures,
  text opacity, baseline shifts and arbitrary per-line indentation are not rebuilt.
  The first-baseline policy uses glyph height, not exact original font metrics.
- Original source geometry is retained; replacement metrics can cause overflows.
  All text remains in the frame, including overflow text requiring manual repair.
- Standalone list-marker glyphs are rendered from their original PDF bounding box
  as small transparent PNG crops. This avoids substituting Wingdings character
  codes. These are not editable text or vector glyphs; inspect possible surrounding
  content inside the crop. No whole-page raster background is used.
- Image assets are converted to RGB PNG, preserving the extracted transform and
  optional mask within the observed image bounds. This is an extra rasterization
  at two pixels per point; image-internal text remains pixels. CMYK fidelity is
  not guaranteed by the RGB conversion.
- Line, cubic, rectangle and quadrilateral vector commands are rebuilt as SVG
  with available clip paths and fill/stroke opacity, then imported as Scribus
  vector objects. Dashed paths, unsupported vector operators and group records
  are reported. Complex transparency and SVG importer fidelity need visual review.
- Images precede vector graphics and all graphics precede editable text. This is
  an approximate paint order, not complete PDF compositing. Annotations and other
  content absent from the original extraction remain outside the supported subset.

Inspect source PDF pages 20, 24 and 49 against the resulting three layout pages.
Check paragraph/caption editing, list markers, inline italics, image orientation,
arrow placement, clipping, page dimensions, overflows and substitutions. Exporting
a PDF from Scribus and comparing it visually is separate from automated testing.

## Validation before commit

```bash
python -m scripts.check_milestone
```

Tests prepare actual synthetic PDF evidence and exercise the import protocol with
a fake Scribus API. They do not prove that Scribus renders the SLA correctly. A
manual real-Scribus run and visual review are required before judging layout quality.
