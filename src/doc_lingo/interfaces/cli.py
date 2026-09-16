"""Command-line interface for doc-lingo."""

from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from importlib.metadata import version
from pathlib import Path
from time import monotonic

from dotenv import load_dotenv

from doc_lingo import (
    HuggingFaceBackend,
    MarianBackend,
    PlainTextReader,
    PlainTextWriter,
    SegmentMismatchError,
    TranslationError,
    translate_document,
)
from doc_lingo.translation.selection import BACKEND_NAMES, DEFAULT_BACKEND, validate_language_pair


def build_parser() -> argparse.ArgumentParser:
    """Describe the local TXT translation interface."""
    parser = argparse.ArgumentParser(
        prog="doc-lingo",
        description="Translate UTF-8 TXT documents locally on CUDA.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('doc-lingo')}")
    parser.add_argument("file", type=Path, help="English UTF-8 source document (.txt)")
    parser.add_argument(
        "--target-lang", required=True, choices=["en", "de"], help="Target language"
    )
    parser.add_argument("--output", type=Path, help="New output file (default: NAME.LANG.txt)")
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
    if args.file.suffix.lower() != ".txt":
        parser.error("Only .txt source documents are supported")
    destination = args.output or args.file.with_name(f"{args.file.stem}.{args.target_lang}.txt")
    if destination.suffix.lower() != ".txt":
        parser.error("Output must use the .txt extension")
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

    try:
        translate_document(
            PlainTextReader(args.file),
            PlainTextWriter(args.file),
            MarianBackend() if args.backend == "marian" else HuggingFaceBackend(),
            destination,
            source_lang="en",
            target_lang=args.target_lang,
            on_progress=show_progress,
        )
    except FileExistsError:
        parser.exit(1, f"Error: Output already exists: {destination}. Choose another --output.\n")
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
    print(f"Translation written to {destination}")


if __name__ == "__main__":
    main()
