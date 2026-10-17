"""Command-line interface for doc-lingo."""

from __future__ import annotations

import argparse
import json
import os
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
from doc_lingo.documents.odt import OdtPackageError, OdtReader, OdtWriter
from doc_lingo.documents.odt.diagnostics import skipped_text_issues
from doc_lingo.translation.alignment import AlignmentError
from doc_lingo.translation.alignment_statistics import AlignmentStatistics
from doc_lingo.translation.awesome_adapter import AwesomeAlignAdapter
from doc_lingo.translation.glossary import Glossary, GlossaryBackend
from doc_lingo.translation.selection import BACKEND_NAMES, DEFAULT_BACKEND, validate_language_pair


def build_parser() -> argparse.ArgumentParser:
    """Describe the local document translation interface."""
    parser = argparse.ArgumentParser(
        prog="doc-lingo",
        description="Translate TXT, Markdown and supported ODT text locally on CUDA.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('doc-lingo')}")
    parser.add_argument("file", type=Path, help="English source (.txt/.md UTF-8 or .odt)")
    parser.add_argument(
        "--target-lang", required=True, choices=["en", "de"], help="Target language"
    )
    parser.add_argument("--output", type=Path, help="New output file (default: NAME.LANG.EXT)")
    parser.add_argument("--glossary", type=Path, help="Optional terminology JSON file")
    parser.add_argument(
        "--aligner", choices=["awesome"], help="Opt-in Markdown/ODT alignment (CPU)"
    )
    parser.add_argument("--alignment-model", type=Path, help="Local awesome-align model directory")
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
    if bool(args.aligner) != bool(args.alignment_model):
        parser.error("--aligner and --alignment-model must be supplied together")
    if args.aligner and extension not in (".md", ".odt"):
        parser.error("--aligner requires a Markdown or ODT document")
    if extension not in (".txt", ".md", ".odt"):
        parser.error("Only .txt, .md and .odt source documents are supported")
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
    repair_count = 0
    skipped_count = 0
    report_created = False
    alignment_statistics = AlignmentStatistics()

    try:
        skipped = ()
        if extension == ".odt":
            if os.path.lexists(destination):
                raise FileExistsError(destination)
            skipped = skipped_text_issues(args.file)
        reader_class, writer_class = {
            ".txt": (PlainTextReader, PlainTextWriter),
            ".md": (MarkdownReader, MarkdownWriter),
            ".odt": (OdtReader, OdtWriter),
        }[extension]
        with issues_path.open("x", encoding="utf-8", newline="\n") as report_file:
            report_created = True

            def record_issue(issue):
                nonlocal issue_count, repair_count, skipped_count
                report_file.write(json.dumps(asdict(issue), ensure_ascii=False) + "\n")
                report_file.flush()
                issue_count += 1
                repair_count += issue.action.startswith("formatting_")
                skipped_count += issue.action == "skipped_content"

            for issue in skipped:
                record_issue(issue)
            if skipped_count:
                print(
                    f"ODT: {skipped_count} unsupported text blocks will remain unchanged; "
                    f"see {issues_path}",
                    file=sys.stderr,
                    flush=True,
                )

            backend: TranslationBackend = (
                MarianBackend() if args.backend == "marian" else HuggingFaceBackend()
            )
            if glossary is not None:
                backend = GlossaryBackend(backend, glossary)
            alignment_options = {}
            if args.aligner:
                alignment_options["aligner"] = AwesomeAlignAdapter.load(str(args.alignment_model))
                alignment_options["alignment_statistics"] = alignment_statistics
            translate_document(
                reader_class(args.file),
                writer_class(args.file),
                backend,
                destination,
                source_lang="en",
                target_lang=args.target_lang,
                on_progress=show_progress,
                on_issue=record_issue,
                **alignment_options,
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
    except OdtPackageError:
        parser.exit(1, "Error: Invalid or unsupported ODT package or document structure.\n")
    except (TranslationError, AlignmentError) as error:
        parser.exit(1, f"Error: {error}\n")
    except OSError:
        parser.exit(1, "Error: Document I/O failed; check storage and hard-link support.\n")
    finally:
        if report_created and issue_count == 0:
            issues_path.unlink()
    if args.aligner:
        print(
            "Alignment path statistics: " + json.dumps(asdict(alignment_statistics)),
            file=sys.stderr,
        )
    if issue_count:
        status = (
            "Partially translated document"
            if issue_count > repair_count
            else "Translation with formatting warnings"
        )
        print(f"{status} written to {destination}")
        parser.exit(
            3,
            f"Warning: {issue_count - repair_count - skipped_count} original text units retained; "
            f"{repair_count} formatting warnings. "
            + (f"{skipped_count} unsupported text blocks skipped. " if skipped_count else "")
            + f"Report: {issues_path}\n",
        )
    print(f"Translation written to {destination}")


if __name__ == "__main__":
    main()
