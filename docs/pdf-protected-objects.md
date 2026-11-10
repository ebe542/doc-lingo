# Protected PDF objects and text flows

An object plan adds explicit content ownership to the extracted PDF evidence.
It does not crop rectangles, render a new document, or invoke a translator.
Geometry remains evidence for later layout reconstruction. Overlapping positions
never assign neighboring prose to an image, code listing or formula.

## Assignments

Create a UTF-8 JSON file using IDs from your own extraction. Names below are
illustrative placeholders, not IDs of a supplied document.

```json
{
  "schema_version": 1,
  "extraction_sha256": "SHA256 OF THE EXACT manifest.json FILE BYTES",
  "objects": [
    {
      "id": "equation-1",
      "kind": "formula",
      "reason": "Keep the original mathematical expression",
      "members": ["formula-text-fragment-id", "page-0001-vector-00000"]
    }
  ],
  "flows": [
    {
      "id": "paragraph-1",
      "parts": [
        {"text_id": "preceding-text-fragment-id"},
        {"object_id": "equation-1"},
        {"text_id": "following-text-fragment-id"}
      ]
    }
  ]
}
```

Text and image IDs come from page JSON `objects`. Vector references are
`<page.id>-vector-<five-digit-index>` using the zero-based position in the graphics
file's `paths` array, including clip/group entries. Raw extraction files are not
modified. Formula members may combine text fragments and vector records; code
can similarly reference its constituent text fragments. Include required graphic
dependencies explicitly; this step does not infer clipping or compositing.

Every member must exist, belong to only one protected object, and be on the same
page as that object's other members. A protected object requires an ID, kind and
reason. Images not explicitly assigned receive automatic `image:<source-ID>`
objects. The `image:` ID prefix is reserved for these automatic entries.

Flows specify reading order explicitly. A part is either a text-fragment reference
or a protected-object reference. Repeated use and protected text used as prose
are rejected. No marker string is inserted yet. Whitespace remains in the original
fragments; joining, segmentation and translator placeholder handling are future
steps. Fragment boundaries are currently indivisible: mixed text/formula fragments
need finer segmentation before they can be assigned separately.

## Build the intermediate

Obtain the manifest checksum with Git Bash `sha256sum` and copy its hexadecimal
value into the assignment file:

```bash
sha256sum local-data/pdf-layout/extraction-01/manifest.json
python -m scripts.prepare_pdf_objects local-data/pdf-layout/extraction-01 \
  --assignments assignments.json \
  --output local-data/pdf-layout/object-plan-01.json
```

The output must not exist and its parent must exist. Validation finishes before
publication. The plan records source/manifest/assignment hashes and page/graphics
hashes, an inventory with original object evidence, protected objects and flows.
Image asset paths in the evidence remain relative to the original extraction;
keep that directory with the plan. This is not a self-contained image archive.

Unassigned text, unplaced protected objects and unassigned vectors are listed
explicitly. They are not discarded or automatically added to a guessed reading
order. A partial plan is valid for inspection but not ready for translation.

## Current boundary

This plan is independent of the Scribus import plan. Neither the translator nor
the Scribus exporter consumes it yet. Font ambiguities, rotated-text rendering,
formula recognition and semantic math reconstruction remain separate work.
The abandoned rectangular protection option is removed from Scribus preparation;
old region files are not accepted or automatically converted to object membership.
