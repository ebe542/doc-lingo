# First editable Scribus layout experiment

This exports the **source document**, before translation. A preparation command
reads immutable extraction/group JSON and creates `plan.json` plus portable graphic
assets. A separate script runs inside Scribus and creates a new editable document,
`layout.sla`, with one text frame per candidate text group. It writes readable and
JSON export reports. The manual font catalog is optional, not a prerequisite.

## Font choices

The separate [object/flow plan](pdf-protected-objects.md) records protected content
by source object ID. It is not yet consumed by this Scribus exporter.

`docs/examples/scribus-font-map.json` is an empty starting template. Copy it to
`font-map.json` and add only the choices needed by your document. With empty
mappings, the importer requires unique original PostScript-name matches. Fonts
are not downloaded or installed. Replacement names must match faces available in
your Scribus installation; selecting a replacement does not establish metric equality.

This export map is distinct from the file/face map used by `check_pdf_fonts`:
it names the actual Scribus face, not a font file. `fonts` is keyed by source
PostScript name without its PDF subset prefix. Each entry requires `kind`
(`original` or `replacement`), `scribus_name` and a nonempty `reason`.
`fragment_fonts` maps an uncertain extraction name to a source base name and is
accepted only if it identifies exactly one existing candidate. An optional
`extraction_sha256` restricts the map to one extraction; the plan always records
the source/extraction/group hashes and the complete mapping used.

For example, the following entry illustrates an explicit substitution. Both font
names are placeholders: replace the key with the source PostScript name from
your extraction and `scribus_name` with an installed face name from Scribus.

```json
{
  "schema_version": 1,
  "fonts": {
    "SourceSerif-Regular": {
      "kind": "replacement",
      "scribus_name": "Installed Serif Regular",
      "reason": "Original unavailable; replacement selected for manual layout review."
    }
  },
  "fragment_fonts": {}
}
```

An explicit font choice takes precedence. Without one, the importer requires a
unique available Scribus face with the original PostScript name. It fails before
creating a document if a font is missing/ambiguous or an `original` choice has a
different PostScript name. There is no silent font substitution.

## Prepare and import

From Git Bash in the repository, substituting your PDF path:

```bash
python -m scripts.prepare_scribus_layout input.pdf \
  --layout local-data/pdf-layout/extraction-01 \
  --groups local-data/pdf-layout/groups-01 \
  --font-map font-map.json \
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

Text frames use the original PDF text bounds. Different font metrics and line
wrapping can cause overflow even when an original font name matches. Translation
can also change text length. Adjust frames manually after reviewing the content;
overflow reports identify frames that require attention.

Images, vectors and text are placed on separate unlocked `Images`, `Vectors` and
`Text` layers. Select `Images` in the Layers panel when editing an image; hide
upper layers temporarily if they intercept selection. An imported raster image
remains an image frame, not editable text. Real selection behavior needs manual
verification in Scribus.

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
  at at least two pixels per point, increased to retain the source sampling
  density along both transformed image axes; image-internal text remains pixels. CMYK fidelity is
  not guaranteed by the RGB conversion.
- Line, cubic, rectangle and quadrilateral vector commands are rebuilt as SVG
  with available clip paths and fill/stroke opacity, then imported as Scribus
  vector objects. Dashed paths, unsupported vector operators and group records
  are reported. Complex transparency and SVG importer fidelity need visual review.
  Placement uses geometric curve extrema rather than control-point bounds or
  stroke padding. Clipped paths still require visual checking because Scribus
  may trim the imported geometry differently.
- Images precede vector graphics and all graphics precede editable text. This is
  an approximate paint order, not complete PDF compositing. Annotations and other
  content absent from the original extraction remain outside the supported subset.

Compare each exported page with the corresponding page in your source PDF.
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
