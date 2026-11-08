# Local PDF font inspection

This experimental step examines local font files against an existing layout
extraction. It never changes the extraction, installs fonts, downloads files,
selects fallback fonts automatically or modifies Scribus settings.

For missing fonts, start with [download and purchase sources](pdf-font-sources.md):
obtain the original or choose an explicitly documented alternative, install it,
then rerun the report. The manual Scribus catalog below is optional diagnostics.

```bash
python -m pip install -e ".[dev]"
python -m scripts.check_pdf_fonts local-data/pdf-layout/extraction-02 \
  --output local-data/pdf-layout/fonts-01
```

Open `fonts-01/report.md` for the readable report. `report.json` contains detailed
evidence, and `mapping-template.json` is an empty, extraction-bound mapping template.
The output directory must be new and its parent must exist. Completion means the
report was generated, **not** that every required font was found.

Default locations cover system/user font folders on Windows and macOS and common
Linux font folders. Custom font-manager directories and registry-only Windows
locations are not exhaustively discovered. Use repeated `--font-dir` options to
replace the defaults with explicit search roots. TTF, OTF, TTC and OTC are supported;
standalone legacy Type 1/PFB and CFF files are not scanned. Damaged or inaccessible
files are reported while the remaining scan continues. A partial scan must not be
interpreted as proof that a font is absent from the computer.

FontTools reads internal PostScript names, family, style, collection face index,
variable-font presence and Unicode coverage. Matching uses the PDF base name
(without its six-letter subset prefix) against the internal PostScript name,
case-insensitively. This avoids matching only the family while overlooking bold or
italic. A name match is not proof of identical outlines, metrics or font version.
File SHA-256 values are recorded. Different files with the same name stay ambiguous.
Variable-font axes/instances are not selected in this version.

Status meanings:

| Status | Meaning |
| --- | --- |
| `name_match` | One named face found; no automatic explicit selection |
| `ambiguous` | Multiple local faces have the same PostScript name |
| `family_candidates` | No exact name match, but unverified family/style candidates exist |
| `not_found_in_scan` | No match in the searched files |
| `explicit_original` | User-selected file/face with matching PostScript name |
| `explicit_replacement` | User deliberately selected a replacement |

Without exact matches, `related_candidates` compares internal PostScript/full names
and family/style combinations. Whitespace, hyphens and underscores are normalized;
common style suffixes are interpreted (for example Roman/Regular, Ital/Italic and
Cond/Condensed). Family digits remain significant. Matching style names are listed
before candidates whose style differs. This is a naming heuristic, not proof of
equivalence: no arbitrary vendor suffixes or family aliases are removed, no file
is selected, and `original` mappings still require an exact PostScript-name match.
The report explains every related candidate separately from exact matches.

The report includes PDF pages referencing each font resource. Such resources can
be unused on a page. Unresolved text-fragment assignments are listed separately:
finding a font file does not resolve a truncated or ambiguous PDF resource name.

The Unicode probe covers ASCII letters, digits and `ÄÖÜäöüßẞ`. Missing characters
are listed; no Unicode cmap means coverage is unknown. This is not proof of full
German, symbol, formula or technical-document coverage. Embedded subsets are
marked separately and never assumed to be complete or installed.

## Explicit mappings

Copy `mapping-template.json` to your own mapping file. Keep its schema version and
extraction hash; populate `fonts` using the IDs in the report:

```json
{
  "schema_version": 1,
  "extraction_sha256": "keep-the-generated-hash-here",
  "fonts": {
    "font-123": {
      "file": "../my-fonts/Example-Regular.ttf",
      "face_index": 0,
      "kind": "original"
    }
  }
}
```

Paths are relative to the mapping file, or absolute. For a collection, select the
zero-based face index shown in the report. Use `replacement` when choosing a
different PostScript name; `original` rejects a name mismatch. A replacement can
change line lengths and overflow: it is recorded, not applied to a layout yet.
Incomplete mappings are allowed; unmapped entries retain their scan status.

```bash
python -m scripts.check_pdf_fonts local-data/pdf-layout/extraction-02 \
  --mapping local-data/pdf-layout/font-mapping.json \
  --output local-data/pdf-layout/fonts-02
```

The report records selected file metadata and hashes even when the selected file
is outside the scan roots. Mapping is machine-local evidence: installing fonts,
confirming Scribus availability and layout export are separate steps. It does
not override uncertain text-fragment-to-PDF-font assignments.

The JSON report contains local paths intentionally to support file selection;
avoid publishing private machine details unintentionally. No font bytes are copied.

Before committing this step, run `python -m scripts.check_milestone` and inspect
the generated report. Synthetic tests build small fonts themselves, so CI does
not require installed proprietary fonts.

## Scribus availability and replacement policy

The practical target is a readable, editable layout with approximately preserved
appearance, not identical typography. The visual target is not an automated
percentage score. Prefer original faces when available; otherwise explicitly
record the source font, replacement file/face, actual Scribus name and affected
pages/blocks in the future export plan. The layout must reference the selected
Scribus name, not leave an unavailable original name behind. Check wrapping,
overflow and overlaps after replacement. A replacement must never be silent.

If a locally installed font does not appear as expected in Scribus, optionally
capture Scribus's own font catalog. Use **Script > Execute Script** and select
`scripts/scribus_font_catalog.py` from this repository. Save the result as
`local-data/pdf-layout/scribus-fonts-01.json`. Run inside Scribus, not the project's
Python environment. No document needs to be open. The script requires no external
Python dependencies and changes no document or font settings.

The JSON records the names accepted by Scribus, family, internal PostScript name,
file path and catalog timestamp/version. It combines `getFontNames()` availability
with `getXFontNames()` metadata. Subset/export settings in this API are **not**
evidence that the font itself is a subset. Missing extended metadata stays null.
The script refuses an existing destination and reports completion in a dialog.
Refresh the catalog after installing or changing fonts and restarting Scribus.

This optional catalog helps diagnose actual layout font names. It does not yet
create an SLA or validate glyph rendering. The [first Scribus layout export](scribus-export.md)
uses concrete original/replacement choices and checks availability inside Scribus.

API references: [FontTools TTFont](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html)
and [font naming tables](https://fonttools.readthedocs.io/en/latest/ttLib/tables/_n_a_m_e.html).
