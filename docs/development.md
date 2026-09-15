# Developer guide

## Working agreement

This is a productive learning project. Discuss each proposed commit with the
maintainer before implementing its changes: explain its purpose, scope, expected
behavior, and validation steps. Agree on one small, coherent step at a time.

- Every commit must leave the project installable and executable. Do not commit
  broken intermediate states or advertise unfinished behavior as available.
- Keep commits focused and small enough to review and understand independently.
  Commit subjects must contain at most 50 characters, including the prefix.
  Documentation-only changes must preserve the runnable state of the project.
- The maintainer writes the tests, runs validation, and creates commits. The
  assistant explains the expected checks and supplies Git Bash commands; it does
  not write or run tests, stage changes, commit, push, or tag on their behalf.
- Discuss each commit before it is created, including its exact files and a
  proposed Conventional Commit message. Avoid blanket staging commands.
- Create releases at agreed, useful milestones, not after every commit. Discuss
  the release scope and version before the maintainer creates a tag.
- Use English for project artifacts and German for collaboration.

An explicit request to edit an agreed document authorizes that documentation
change. It does not authorize creating a Git commit.

## Library and CLI architecture

The package is organized by responsibility:

```text
src/doc_lingo/
  __init__.py                 Public library exports
  interfaces/
    __init__.py
    cli.py                    Argument parsing and CLI entry point
  translation/
    __init__.py
    protocols.py              TranslationBackend and TranslationError
    service.py                translate_document orchestration
    prompts.py                Versioned translation instructions
    huggingface.py            Local model adapter
  documents/
    __init__.py
    protocols.py              DocumentReader and DocumentWriter
    models.py                 TextSegment
    errors.py                 SegmentMismatchError
    plain_text.py             TXT reader
    plain_text_writer.py      TXT writer
```

Interfaces depend on the translation service. The service depends on document
and backend contracts, not concrete providers. Document adapters own formatting;
translation adapters own model/provider behavior. Future GUI code belongs in
`interfaces`, and additional providers belong in `translation`.

Public imports such as `from doc_lingo import HuggingFaceBackend, translate_document`
remain unchanged. The CLI module is now `doc_lingo.interfaces.cli`. After pulling
this structural change, refresh the installed console entry point in Git Bash:

```bash
python -m pip install -e ".[dev,release]"
```

This does not remove an already installed `local` extra or replace a compatible
CUDA build. Tests continue to live in the existing `tests/` directory.

Publish one Python distribution, `doc-lingo`, containing both an importable
`doc_lingo` library and the `doc-lingo` command-line entry point. Other Python
applications must be able to use translation without invoking the CLI.

Build toward these responsibilities incrementally; this is a design target,
not a claim that translation is already implemented:

| Component | Responsibility |
| --- | --- |
| Public library API | Accept explicit translation options and return structured results. |
| Translation service | Coordinate document reading, text translation, and output writing. |
| Document adapters | Handle format-specific content and formatting, starting with plain text. |
| Translation backends | Translate text independently of document formats. |
| CLI | Parse arguments, resolve configuration, call the library, and render results. |

The CLI depends on the library; the library must not depend on the CLI. Keep
argument parsing, terminal output, and process exit codes at the CLI boundary.
Library operations return values or raise documented exceptions. Importing the
library must not load models, read `.env`, contact services, or modify files.

Pass configuration and backend dependencies explicitly to library operations.
Keep credential loading at the application boundary. Decide on the public API
in a dedicated commit discussion before adding it. The current library exposes
reader/writer protocols, plain-text processing, and translation orchestration
with a caller-supplied backend; the CLI connects TXT adapters to the local backend.

### Plain-text library API

```python
from doc_lingo import DocumentReader, PlainTextReader

reader: DocumentReader = PlainTextReader("document.txt")
with reader.iter_segments() as segments:
    for segment in segments:
        print(segment.id, segment.text)
```

`DocumentReader` is a structural protocol: adapters implement `iter_segments`
without having to inherit from it. The method returns a context manager containing
an iterator of immutable `TextSegment` values (`id` and `text`). Consume segments
inside the `with` block. Context exit closes the file and iterator after normal
completion, early termination, or an exception. Each call opens an independent
session; constructing the reader does not open a file.

`PlainTextReader` accepts a string or `pathlib.Path`. It reads UTF-8 strictly,
accepting and removing an optional leading BOM. Empty or whitespace-only lines
separate paragraphs and are omitted from the segments. Other whitespace and
line endings, including a paragraph's final line ending, remain unchanged.
An empty or whitespace-only document yields no segments. Paragraph IDs are
strings starting at `"1"`, stable for repeated reads of an unchanged document;
callers must treat IDs as opaque and local to that document.

The reader buffers one paragraph at a time, plus normal text I/O buffering.
A document without paragraph separators can therefore still require memory
proportional to its full size. Document segments are not model-sized chunks;
model token limits will be handled separately. Other formats may need to load
their document structure before yielding segments through the same protocol.

File-system and decoding errors propagate to callers; extensions are not checked.
The reader only extracts text. Omitted separators cannot be reconstructed from
segments alone; the writer rereads the unchanged original to preserve structure.

### Plain-text writing and errors

```python
from pathlib import Path

from doc_lingo import DocumentWriter, PlainTextWriter, TextSegment

writer: DocumentWriter = PlainTextWriter("document.txt")
# Supply exactly one translation per original segment, in the original order.
writer.write(Path("document.de.txt"), [TextSegment("1", "Hallo Welt!")])
```

`write(destination, translations)` accepts an iterable, including generators.
The writer checks every ID against the original paragraph order. Missing, extra,
duplicate, and out-of-order IDs raise `SegmentMismatchError`. It does not close
caller-owned iterators: keep reader contexts active while supplying their segments.
The source must not change between extraction and writing; content changes with
the same paragraph IDs are not detected by this contract.

The TXT writer preserves the original BOM, whitespace-only separator lines, and
each paragraph's final line ending (including no ending at EOF). It removes
trailing CR/LF characters from translated text before restoring that ending.
Internal line breaks come from the translation. Empty translations are permitted.

Output is prepared in a temporary directory next to the destination. After all
validation and file closing, a hard link publishes the complete result without
replacing existing paths, even if another process creates the target during
processing. The destination directory must exist and support hard links (for
example, NTFS); unsupported file systems raise `OSError`. No unsafe replacement
fallback is used. Temporary storage is cleaned up on normal completion and
exceptions; process termination or file-system cleanup failures can leave residue.
Publication is not a guarantee of durability across power loss.

Expected errors propagate as Python exceptions: `FileNotFoundError`,
`FileExistsError`, `UnicodeDecodeError`, `UnicodeEncodeError`, or other `OSError`
subclasses. Translation-iterator errors also propagate before publication.
The library configures no logging and prints no errors. The CLI maps expected
exceptions to concise stderr messages and exit code 1; invalid arguments use 2,
and success uses 0. Unexpected programming errors remain visible for diagnosis.
Optional file logging is a separate step.

Keep originals intact and write a separate result for every supported format.
The shared translation service must not assume slides, XML, or any particular
document format. Format-specific extraction and reconstruction belong in adapters.

### Translation service

`TranslationBackend.translate(text, *, source_lang, target_lang)` returns a string.
Backends know neither document paths nor segment IDs. They validate supported
languages and raise `TranslationError` for expected translation failures, using
messages without document text or credentials. Unexpected programming errors
are not converted into expected backend failures.

Applications supply their backend to the public service:

```python
from pathlib import Path

from doc_lingo import PlainTextReader, PlainTextWriter, TranslationBackend, translate_document


def translate_txt(backend: TranslationBackend) -> None:
    translate_document(
        PlainTextReader("document.txt"),
        PlainTextWriter("document.txt"),
        backend,
        Path("document.de.txt"),
        source_lang="en",
        target_lang="de",
    )
```

The service opens the reader context, translates each segment only when the
writer requests it, and retains its original ID. The reader stays open throughout
writing. The service closes its translation generator and reader context on
success, early writer termination, and exceptions. The writer manages output
cleanup; the caller owns the backend's lifecycle. Reader and writer must refer
to the same unchanged original document.

Backend, reader, and writer errors propagate unchanged. The service does not
configure logging, print messages, retry, or split paragraphs into model chunks.
One backend call handles one segment. Empty documents require no backend calls.
Language codes are passed through unchanged; model-specific validation belongs
to the backend. The CLI uses the local Hugging Face adapter with English source
text and a required target language. It accepts TXT input and an optional
`--output` path; otherwise it writes `NAME.LANG.txt` alongside the original.
Only TXT output paths are accepted. Argument validation precedes `.env` loading,
so help and version commands do not read local configuration.

See [local model setup](local-model.md) for the CUDA Hugging Face backend,
versioned prompt identities, installation commands, and manual GPU validation.

## Format implementation roadmap

Implement support in the order **TXT, Markdown, then ODP**. Each stage builds on
the same public library API and translation backend and is exposed through the CLI.
The roadmap describes the target behavior. TXT orchestration currently requires
a backend, such as `HuggingFaceBackend`, which the CLI supplies automatically.

1. **Plain text (`.txt`):** establish reading, translation, and separate output
   writing with English-to-German translation first. Preserve paragraph structure.
   Agree on encoding handling and output naming before implementation.
2. **Markdown (`.md`):** translate prose while preserving headings, lists, emphasis,
   code blocks, and link destinations. Define which text elements are translatable
   and how structure is retained before implementing the adapter.
3. **OpenDocument presentations (`.odp`):** preserve document structure, styles,
   images, and non-text content while changing translatable text. Longer translations
   may overflow existing text boxes; validate layout fit separately from formatting.

Split each stage into small, runnable commits using the working agreement above.
A usable TXT implementation can be a release milestone before Markdown or ODP
support exists; discuss release readiness and limitations with the maintainer.

## Commit and validation sequence

1. Discuss a single behavior or improvement and agree on its boundaries.
2. Implement the agreed production changes and explain the relevant design.
3. The maintainer writes appropriate tests and runs the supplied commands.
4. Review the diff, validation results, and exact staging list together.
5. The maintainer commits and pushes; verify the GitHub Actions result.

Run commands from the project root in Git Bash after activating the environment:

```bash
source .venv/Scripts/activate
python scripts/check_milestone.py
```

The shared gate checks formatting, lint, tests, coverage, and Git whitespace.
The assistant provides specific test and commit commands for each agreed step.
Tests must use synthetic documents and avoid secrets or online model services.

## Temporary files and directories

Remove every task-created temporary directory when the task is finished,
including after failures. Track which paths the task created and check their
resolved locations before cleanup. Never delete pre-existing or user-owned data.
Prefer context-managed temporary directories in tooling so cleanup is automatic.

The current quality command uses `.pytest-tmp`; the person running it must remove
that temporary directory after the check, including after a failed run. The
assistant must clean up its own temporary directories before handing work back.
A reusable `.venv` is a development environment, not a disposable task directory.

## Releases

A release represents a coherent, usable capability with documented limitations.
Agree on the milestone and version, update package metadata and dated changelog
notes, then have the maintainer run quality and package installation checks.
Commit and push the reviewed state and confirm green CI before tagging it.

The existing workflow builds and publishes GitHub release assets from annotated
version tags. See [CONTRIBUTING.md](../CONTRIBUTING.md) for its requirements.
A release must state the supported formats, model requirements, and known
translation-quality limitations.
