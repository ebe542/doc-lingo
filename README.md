# doc-lingo

A Python library and CLI for translating documents while preserving their structure
and formatting.

## Status

Version 0.2.0 is the prepared Markdown release of this productive learning project.
TXT and Markdown translation, reusable terminology glossaries, quality checks,
and release tooling are available. See the [release notes and limitations](CHANGELOG.md#020---2026-10-10).
Markdown includes table cells and supported embedded HTML text; see the
[Markdown scope and limitations](docs/markdown.md).
The CLI translates English UTF-8 TXT and Markdown documents using local CUDA models.
The library provides a translation service with an injectable backend. Marian is
selected by default; optional model dependencies are installed through `local`.
See [local model setup](docs/local-model.md) for the project's CUDA configuration.
The library provides a shared reader protocol and incremental UTF-8 paragraph
extraction, plus a writer that inserts ordered translations into the original TXT
structure and protects existing output files. See the
[plain-text API](docs/development.md#plain-text-library-api).

## Initial scope

- Accept one document and a target language.
- Start with English source documents and German translations.
- Start with plain text (`.txt`) and preserve paragraph structure.
- Write a separate output, such as `document.de.txt`, preserving the original.
- Expose translation through both an importable library and a CLI.

Marian is the default local CUDA backend for English-to-German translation.
Qwen3-1.7B remains available with `--backend qwen` and versioned prompts.

## Format roadmap

Implement formats in this order, reusing the translation core:

1. **Plain text (`.txt`):** establish the complete translation workflow, from
   reading text to writing a separate translated file.
2. **Markdown (`.md`):** translate prose while preserving Markdown structure,
   code blocks, and link destinations.
3. **OpenDocument text documents (`.odt`):** translate document text while
   preserving headings, paragraphs, lists, styles, images, and document structure.
   Longer translations can change line wrapping and pagination; layout requires
   separate review rather than a guarantee of identical page counts.

TXT and Markdown reading, writing, and orchestration are available for a
caller-supplied translation backend. ODT adapters support main-flow headings,
paragraphs, list paragraphs and textual table cells; peripheral text remains unsupported.

## Development setup

Use Python 3.11, 3.12, or 3.13. Commands below target Git Bash on Windows,
from the `doc-lingo` directory:

```bash
py -3.13 -m venv .venv && source .venv/Scripts/activate
python -m pip install -e ".[dev,release]"
doc-lingo --help
doc-lingo --version
```

On Linux or macOS, create the environment with `python3 -m venv .venv`
and activate it with `source .venv/bin/activate`.

After installing the `local` extra and CUDA build below, translate a document:

```bash
doc-lingo document.txt --target-lang de
doc-lingo document.txt --target-lang de --output translated.txt
doc-lingo document.txt --target-lang de --backend qwen --output translated-qwen.txt
```

The default output is `document.de.txt` alongside the source. Existing output
files are never overwritten. Source language is English; target codes are `de`
and `en` (`en` requires `--backend qwen` and retains the text). Marian accepts
only `de`; incompatible requests fail before model loading or file creation.
TXT, Markdown and the limited ODT subset are supported.
The first real translation may download the model. Translation quality still
requires review. Segments are translated internally in sentence-sized units; oversized sentences
are split at word boundaries using the selected tokenizer. An indivisible oversized word or incomplete generated unit is retained in its
original language and recorded in a local `.issues.jsonl` report. See [segment splitting](docs/segment-splitting.md) for limits.

Exit codes: `0` for success, `1` for expected file or translation failures, and
`2` for invalid command arguments, and `3` for a published document containing
retained source text or formatting warnings. Error messages go to stderr; local
`.issues.jsonl` reports record recovery and formatting diagnostics.

During translation, stderr shows the translated segment count, segment type, and
elapsed seconds. Types are `paragraph`, `heading`, `bullet_item`, and `numbered_item`.
The initial message explains that the first segment may require model
loading. No percentage is shown because paragraphs are read incrementally without
a counting pass. The final success message appears only after output publication.

## Optional Markdown and ODT alignment

After the local translation setup, install the alignment extra:

```bash
python -m pip install -e ".[awesome]"
doc-lingo document.md --target-lang de \
  --aligner awesome --alignment-model /path/to/local/awesome-align-checkpoint \
  --output document-aligned.de.md
```

Replace the checkpoint path with an existing local model directory; the CLI does
not download alignment weights automatically. See [alignment setup and evaluation](docs/alignment.md)
for the pinned checkpoint. Alignment runs on CPU while the translator uses CUDA.
It is opt-in; ordinary Markdown translation remains available without the extra.

Complete translation units can retain their formatting using exact call boundaries.
Within a unit, uncertain word correspondences can still cause formatting loss.
Review the output and warnings. Local re-alignment proposals are available only
in evaluation scripts and are never automatically applied by the document CLI.

## Simple TXT lists

Lines starting with `-`, `*`, `•`, or numbers followed by `.` or `)` are treated
as individual list items when the marker is followed by spaces/tabs and text.
The adapter retains indentation, marker, and spacing after the marker exactly;
only the item text is translated. Blank lines and line endings remain intact.
Prose before and after lists remains paragraph-based. Progress counts include
each list item as a separate segment with its own type.

Unmarked lines following a list marker belong to that item until the next marker,
a blank line, or EOF, even without indentation. The complete item is sent to the
model in one call. Separate following prose from a list with a blank line.
Internal translated line breaks may change; original item prefixes and final
line endings are retained.

This is a small TXT convention, not Markdown parsing: tables and nested-list
semantics are not supported. Indented markers are retained
without interpreting their nesting level. A line such as `1.5 units` or `-word`
is ordinary text. Internal prose indentation still depends on the translated text.

## CUDA 13.2 installation (Windows / Git Bash)

For local GPU inference, activate the environment and install the CUDA build
explicitly before the `local` extra:

```bash
source .venv/Scripts/activate
python -m pip install "torch==2.13.0+cu132" --index-url https://download.pytorch.org/whl/cu132 && python -m pip install -e ".[dev,local,release]"
```

The `+cu132` suffix matters: `torch==2.13.0` alone can accept an installed CPU
build. The extra declares dependencies but does not select the CUDA package index.
The PyTorch wheel supplies the CUDA runtime; a separate CUDA Toolkit installation
is not required for this backend. A compatible NVIDIA driver is required.

Verify the installed runtime and GPU:

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA unavailable')"
```

For the project's RTX 3060 Ti setup, expect `2.13.0+cu132`, `13.2`, `True`, and
`NVIDIA GeForce RTX 3060 Ti`. If the build ends in `+cpu`, repeat the explicit
CUDA installation above. See [local model setup](docs/local-model.md) for the
first model download and a manual translation check.

## Hugging Face configuration

Keep your existing Hugging Face token in the local `.env` file. It is ignored by
Git and excluded from release distributions. The CLI loads `.env` from the current
working directory without overriding existing environment variables. Run it from
the project root to use the project's file. The standard token variable is
`HF_TOKEN`; never commit its real value.

The library does not load `.env` automatically. For direct Python calls, load it
before importing or initializing the backend, as shown in the
[manual smoke check](docs/local-model.md#manual-smoke-check). The backend can
download model files from Hugging Face on first use.

Quality, clean-CI, and release scripts need no token and do not load `.env`
themselves. CI uses model substitutes and requires no model downloads.

Store private input documents and generated translations in `local-data/`.
Only synthetic, redistributable documents belong in `tests/fixtures/`.

## Quality checks

See [evaluation inputs and commands](docs/evaluation-files.md) for committed
sample files, generated reports, and consistent output naming.

An optional [terminology glossary](docs/glossary.md) can preserve terms, supply
fixed translations, or include the original term alongside a translation. Use
`--glossary docs/examples/glossary-en-de.json` in the CLI or quality runner.
Compressed `.json.gz` glossaries use the same option. The example contains 36
ML/AI rules with documented sources; an offline benchmark measures larger synthetic
glossaries without model inference. See the glossary guide for commands and limits.

The [Marian backend](docs/marian-model.md) translates English to German without
chat prompts and is the default in both the CLI and quality runner. Select
`--backend qwen` explicitly for Qwen comparisons.

See [translation quality](docs/translation-quality.md) for ten English/German
evaluation examples, abbreviation handling, and manual assessment criteria.
These semantic checks are separate from automated code tests.

```bash
python scripts/check_milestone.py
python scripts/check_release_package.py
```

The milestone gate runs Ruff, pytest with at least 90% package coverage, and
`git diff --check`. It requires a Git checkout. See [CONTRIBUTING.md](CONTRIBUTING.md)
for the development and release workflow.

The [developer guide](docs/development.md) describes the library/CLI architecture
and the agreed process for small, runnable commits and milestone releases.
Source code is grouped into `interfaces`, `translation`, and `documents` packages.
The CLI entry point is `doc_lingo.interfaces.cli:main`; public library imports
remain available directly from `doc_lingo`.

## License

[MIT](LICENSE).
## Optional Markdown and ODT alignment

Use `--aligner awesome --alignment-model PATH` to enable the alignment-based
Markdown or ODT path. `PATH` must be a local awesome-align model directory containing
the weights and tokenizer files; install the project's awesome-align optional
dependencies first. The aligner runs on CPU with layer 8 and threshold 0.001.
The translation backend keeps its normal device settings.

```bash
doc-lingo example.md --target-lang de --aligner awesome --alignment-model local-data/models/awesome-align --output example.aligned.de.md
```

Use the evaluated `aneuraz/awesome-align-with-co` checkpoint at revision
`777756717e1fa9556e304d4d5db173ee386b9c16`. This option does not download an
alignment model automatically. Without the option, translation behaves as before.
Markdown and ODT accept it; unsupported HTML-wrapper segments keep the existing translation
path. Split styles, expanded links and dropped formatting are written to the
usual `.issues.jsonl` report and return warning exit code 3. These warnings do
not mean that the underlying translated text was retained from the source.
Alignment remains imperfect, especially for reordered repeated terms; review
the generated document. Encoder-limit failures keep valid translated content
and omit unresolved formatting. Invalid protected markers or changed document
structure retain the original segment and are reported separately.

## OpenDocument text (ODT)

```bash
doc-lingo document.odt --target-lang de --output document.de.odt

doc-lingo document.odt --target-lang de \
  --aligner awesome --alignment-model local-data/models/awesome-align \
  --output document.aligned.de.odt
```

ODT support covers main-flow headings, paragraphs, list paragraphs and textual
table cells, including nested tables and multiple paragraphs per cell.
Images and non-content package members are preserved. Optional alignment removes
style/link syntax from model input; without it, inline XML uses conservative
marker protection. Translated text can change wrapping and pagination.

Textbox and caption paragraphs in supported drawing frames are translated,
including nested frames; numbering fields and frame attributes remain protected.
Headers/footers, unsupported inline text and cells with formulas or
separately stored values remain unchanged. Merged/repeated cell structure and
table attributes are preserved; repeated cells are translated once in stored XML.
Recognized preformatted paragraph styles and their descendants preserve code and
comments verbatim. Unmarked code or arbitrary custom code styles are not detected
automatically; see the [style policy](docs/odt.md).
The CLI reports these as `skipped_content` in `OUTPUT.odt.issues.jsonl`, separately
from translation recoveries and formatting warnings. Such outputs return exit
code **3**, even when all supported paragraphs were processed. Empty paragraphs
and purely protected blocks do not themselves trigger a warning. Source text can
appear in the diagnostic file; it is a local review artifact.

Exit code 0 means no issues were reported, 1 means a fatal processing failure,
and 2 means invalid arguments. Output and report paths must be new. See
[ODT support and limitations](docs/odt.md) and the separate
[reproducible review script](docs/odt-review.md).
