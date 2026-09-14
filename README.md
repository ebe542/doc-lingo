# doc-lingo

A Python library and CLI for translating documents while preserving their structure
and formatting.

## Status

This productive learning project is in its initial scaffolding phase. Installation,
CLI help, version reporting, quality checks, and release tooling are available.
Document translation is not implemented yet; translation requests fail explicitly.
The library provides a shared reader protocol and incremental UTF-8 paragraph
extraction. Document writing is planned separately. See the
[plain-text API](docs/development.md#plain-text-library-api).

## Initial scope

- Accept one document and a target language.
- Start with English source documents and German translations.
- Start with plain text (`.txt`) and preserve paragraph structure.
- Write a separate output, such as `document.de.txt`, preserving the original.
- Expose translation through both an importable library and a CLI.

The translation model and local or hosted execution are still to be selected.

## Format roadmap

Implement formats in this order, reusing the translation core:

1. **Plain text (`.txt`):** establish the complete translation workflow, from
   reading text to writing a separate translated file.
2. **Markdown (`.md`):** translate prose while preserving Markdown structure,
   code blocks, and link destinations.
3. **OpenDocument presentations (`.odp`):** translate presentation text while
   preserving styles, images, and slide structure. Longer translations may
   overflow text boxes; layout fit requires separate validation.

Translation for these formats is planned; TXT paragraph extraction is available.

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

Planned translation command (currently reports that translation is unavailable):

```bash
doc-lingo document.txt --target-lang de
```

## Hugging Face configuration

Keep your existing Hugging Face token in the local `.env` file. It is ignored by
Git and excluded from release distributions. The scaffold does not read `.env`
or contact Hugging Face yet. Environment loading and the token variable will be
connected when the translation backend is implemented. Never commit real tokens.
CI currently requires no token or model downloads.

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

## License

[MIT](LICENSE).
