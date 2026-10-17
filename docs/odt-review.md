# ODT review runs

Run from the repository root in Git Bash with the project virtual environment
active. Use the existing CUDA-enabled local dependencies and awesome-align setup.
This script uses the pinned Marian English-to-German backend on CUDA and the
caller-selected local awesome-align checkpoint on CPU. The regular CLI also
supports the same ODT subset; this script adds hashes, inventories and review
statistics. The private sample is not an automated test fixture.

```bash
python -m scripts.evaluate_odt \
  local-data/Introduction-to-Machine-Learning.odt \
  --alignment-model "$USERPROFILE/.cache/huggingface/hub/models--aneuraz--awesome-align-with-co/snapshots/777756717e1fa9556e304d4d5db173ee386b9c16" \
  --output local-data/odt-review/run-01
```

Use a different checkpoint path if your local installation differs. Select a new
run directory for each attempt; existing directories are never reused. Optional
Hugging Face credentials are loaded from `.env` without overriding environment
variables. Checkpoint loading/hashing and initial translation model loading can
take time. Each processed segment prints its type and elapsed time; a final
`ODT review complete` message identifies the output and report.

## Artifacts

- `translated.de.odt`: translation of the supported main-flow/list subset.
- `issues.jsonl`: flushed recovery and formatting diagnostics, including segment
  identity and available attempted translations. An empty file means no issues
  were reported; it does not prove correct translation.
- `report.json`: source/output SHA-256, runtime/model metadata, checkpoint file
  hashes, implementation/script hashes, alignment call counts/timings, source
  block inventory and skipped reasons. Paragraph contexts use XML expanded names.
  Text paragraphs in `styles.xml`, including headers/footers, are listed separately.

Page numbers remain unknown. Inventory text is extracted XML text, not a rendered
page view; explicit whitespace elements and field contents may look different in
the editor. A nested text-box paragraph can also occur within its parent's
extracted text. Counts describe XML blocks, not distinct visible text occurrences.

The script validates the output package, verifies all non-`content.xml` member
payloads and checks the source file hash remained unchanged. ZIP compression size
may differ. It does not validate that images kept their visible placement or that
pagination stayed the same. Tables, text boxes and peripheral text remain in the
original language. Existing metadata/thumbnail content can be stale.

The report is refreshed as segments are processed, before final publication.
Processing failures retain a report with `status: failed`, exception type and
whether output exists; raw exception details are not stored. Invalid input or
checkpoint-loading failure before evaluation may produce no report. Interruptions
handled by Python also mark the report failed; abrupt process termination can
leave `status: running`. A failed run is not a usable review result.

Exit code 0 means processing and preservation checks completed, including runs
with recovery warnings or skipped text. Exit code 1 denotes an expected fatal
failure. Always inspect the report: `manual_review` deliberately remains `pending`.
Reports contain document text and should stay under ignored `local-data`.

## Manual review

Open source and translated ODT side by side in an ODT-capable editor. Review:

1. Meaning, terminology, negations and completeness in supported paragraphs.
2. Heading levels, list structure, nested styles and link labels/destinations.
3. Split or expanded formatting and every dropped-formatting diagnostic.
4. Images, anchors, fields, explicit whitespace and changed page wrapping.
5. Retained source paragraphs and the explicitly skipped table/text-box/peripheral
   text, so untranslated regions are not mistaken for a successful translation.

Record observations separately alongside the run artifacts. Hashes and settings
identify the inputs and implementation; they do not guarantee bitwise reproducible
GPU results or establish a semantic quality score.

## Follow-up to run-01

The first local run exposed nonvisual language styles being split/dropped like
optical formatting, and a leading image marker causing `Learning objectives:`
to be retained despite a usable translation. These cases now have separate
handling. Run the same command with `--output local-data/odt-review/run-02` after
the milestone checks. Keep run-01 unchanged as the baseline.

Compare retained-source and formatting issue counts, the `Learning objectives:`
paragraph, image preservation and the remaining link/style diagnostics. A lower
warning count is not a quality pass: real optical styles remain subject to strict
projection, and source document language defaults are not rewritten. Model
terminology and unsupported table/text-box content are outside this change.
