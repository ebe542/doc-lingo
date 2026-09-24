"""Command-line interface for doc-lingo."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import suppress
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from time import monotonic

from dotenv import load_dotenv

from doc_lingo import (
    HuggingFaceBackend,
    MarianBackend,
    MarkdownReader,
    MarkdownWriter,
    PlainTextReader,
    PlainTextWriter,
    SegmentMismatchError,
    TranslationBackend,
    TranslationError,
    translate_document,
)
from doc_lingo.translation.glossary import Glossary, GlossaryBackend
from doc_lingo.translation.selection import BACKEND_NAMES, DEFAULT_BACKEND, validate_language_pair


def build_parser() -> argparse.ArgumentParser:
    """Describe the local document translation interface."""
    parser = argparse.ArgumentParser(
        prog="doc-lingo",
        description="Translate UTF-8 TXT and Markdown documents locally on CUDA.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('doc-lingo')}")
    parser.add_argument("file", type=Path, help="English UTF-8 source document (.txt or .md)")
    parser.add_argument(
        "--target-lang", required=True, choices=["en", "de"], help="Target language"
    )
    parser.add_argument("--output", type=Path, help="New output file (default: NAME.LANG.EXT)")
    parser.add_argument("--glossary", type=Path, help="Optional terminology JSON file")
    parser.add_argument(
        "--backend",
        choices=BACKEND_NAMES,
        default=DEFAULT_BACKEND,
        help="Local backend (default: marian; en to de only). Qwen also accepts target en.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Translate one document and report expected failures without a traceback."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_language_pair(args.backend, "en", args.target_lang)
    except ValueError as error:
        parser.error(str(error))
    extension = args.file.suffix.lower()
    if extension not in (".txt", ".md"):
        parser.error("Only .txt and .md source documents are supported")
    destination = args.output or args.file.with_name(
        f"{args.file.stem}.{args.target_lang}{extension}"
    )
    if destination.suffix.lower() != extension:
        parser.error(f"Output must use the {extension} extension")
    glossary = None
    if args.glossary:
        try:
            glossary = Glossary.load(args.glossary)
            if (glossary.source_lang, glossary.target_lang) != ("en", args.target_lang):
                raise ValueError("Glossary language mismatch")
        except (OSError, UnicodeError, ValueError):
            parser.error("Cannot use glossary; check its file, schema, entries and languages")
    # Environment loading is optional. A missing or unreadable .env must not
    # prevent commands that do not need Hugging Face authentication.
    with suppress(OSError, UnicodeError):
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)

    started = monotonic()
    print(
        f"Preparing translation with {args.backend}; "
        "the first segment may require model loading...",
        file=sys.stderr,
        flush=True,
    )

    def show_progress(count: int, segment_type: str) -> None:
        print(
            f"Segments translated: {count} | Type: {segment_type} | "
            f"Elapsed: {monotonic() - started:.1f}s",
            file=sys.stderr,
            flush=True,
        )

    issues_path = destination.with_name(destination.name + ".issues.jsonl")
    issue_count = 0
    report_created = False

    try:
        with issues_path.open("x", encoding="utf-8", newline="\n") as report_file:
            report_created = True

            def record_issue(issue):
                nonlocal issue_count
                report_file.write(json.dumps(asdict(issue), ensure_ascii=False) + "\n")
                report_file.flush()
                issue_count += 1

            backend: TranslationBackend = (
                MarianBackend() if args.backend == "marian" else HuggingFaceBackend()
            )
            if glossary is not None:
                backend = GlossaryBackend(backend, glossary)
            translate_document(
                MarkdownReader(args.file) if extension == ".md" else PlainTextReader(args.file),
                MarkdownWriter(args.file) if extension == ".md" else PlainTextWriter(args.file),
                backend,
                destination,
                source_lang="en",
                target_lang=args.target_lang,
                on_progress=show_progress,
                on_issue=record_issue,
            )
    except FileExistsError:
        parser.exit(
            1,
            f"Error: Output already exists or issue report exists: {destination}. "
            "Choose another --output.\n",
        )
    except FileNotFoundError:
        parser.exit(1, "Error: Source file or output directory does not exist.\n")
    except PermissionError:
        parser.exit(1, "Error: Permission denied while reading or writing the document.\n")
    except UnicodeError:
        parser.exit(1, "Error: Source or translated text is not valid UTF-8.\n")
    except SegmentMismatchError:
        parser.exit(1, "Error: Translated segments do not match the source document.\n")
    except TranslationError as error:
        parser.exit(1, f"Error: {error}\n")
    except OSError:
        parser.exit(1, "Error: Document I/O failed; check storage and hard-link support.\n")
    finally:
        if report_created and issue_count == 0:
            issues_path.unlink()
    if issue_count:
        print(f"Partially translated document written to {destination}")
        parser.exit(
            3, f"Warning: {issue_count} original text units retained. Report: {issues_path}\n"
        )
    print(f"Translation written to {destination}")


if __name__ == "__main__":
    main()
