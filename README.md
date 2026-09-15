# doc-lingo

A Python library and CLI for translating documents while preserving their structure
and formatting.

## Status

This productive learning project is in its initial scaffolding phase. Installation,
CLI help, version reporting, quality checks, and release tooling are available.
The CLI translates English UTF-8 TXT documents using the local CUDA backend.
The library provides a document translation service with an injectable backend.
A lazy CUDA Hugging Face backend is available through the `local` extra. See
[local model setup](docs/local-model.md) for CUDA 13.2 installation and smoke checks.
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

The initial backend runs Qwen3-1.7B locally on CUDA with versioned prompts.

## Format roadmap

Implement formats in this order, reusing the translation core:

1. **Plain text (`.txt`):** establish the complete translation workflow, from
   reading text to writing a separate translated file.
2. **Markdown (`.md`):** translate prose while preserving Markdown structure,
   code blocks, and link destinations.
3. **OpenDocument presentations (`.odp`):** translate presentation text while
   preserving styles, images, and slide structure. Longer translations may
   overflow text boxes; layout fit requires separate validation.

TXT reading, writing, and orchestration are available for a caller-supplied
translation backend. Markdown and ODP adapters are planned.

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
```

The default output is `document.de.txt` alongside the source. Existing output
files are never overwritten. Source language is English; target codes are `de`
and `en` (the latter retains the text). Markdown and ODP are not yet supported.
The first real translation may download the model. Translation quality still
requires review; long paragraphs exceeding the model limits are rejected.

Exit codes: `0` for success, `1` for expected file or translation failures, and
`2` for invalid command arguments. Error messages go to stderr. File logging is
planned separately.

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
