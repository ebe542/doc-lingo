"""Prepare and finalize human-reviewed TXT translations."""

import argparse
import json
import os
import sys
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from dotenv import load_dotenv

from doc_lingo.review import export_review_txt, finalize_text_review, load_job, save_job
from doc_lingo.review.preparation import translate_text_job
from doc_lingo.translation.glossary import Glossary, GlossaryBackend
from doc_lingo.translation.huggingface import HuggingFaceBackend
from doc_lingo.translation.marian import MarianBackend
from doc_lingo.translation.protocols import TranslationBackend, TranslationError
from doc_lingo.translation.selection import BACKEND_NAMES, DEFAULT_BACKEND, validate_language_pair


def build_parser():
    parser = argparse.ArgumentParser(prog="doc-lingo review", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Translate TXT and create an editable TXT review")
    prepare.add_argument("file", type=Path, help="English UTF-8 TXT source")
    prepare.add_argument("--target-lang", required=True, choices=("en", "de"))
    prepare.add_argument("--output-dir", type=Path, required=True, help="New review directory")
    prepare.add_argument("--backend", choices=BACKEND_NAMES, default=DEFAULT_BACKEND)
    prepare.add_argument("--glossary", type=Path)
    finish = commands.add_parser("finalize", help="Create final TXT without a translation model")
    finish.add_argument("job", type=Path, help="Saved job.zip")
    finish.add_argument("review", type=Path, help="Edited review.txt")
    finish.add_argument("--output", type=Path, required=True, help="New TXT output")
    finish.add_argument("--original", type=Path, help="Optional original to check against the job")
    return parser


def _publish(staging: Path, destination: Path):
    """Claim a new directory before linking complete artifacts; roll back our files on failure."""
    destination.mkdir()
    published = []
    try:
        for source in sorted(staging.iterdir()):
            target = destination / source.name
            os.link(source, target)
            published.append(target)
    except BaseException:
        for path in published:
            path.unlink()
        with suppress(OSError):
            destination.rmdir()
        raise


def _prepare(args, parser):
    if args.file.suffix.lower() != ".txt":
        parser.error("Review preparation currently supports only .txt sources")
    if os.path.lexists(args.output_dir):
        raise FileExistsError(args.output_dir)
    if not args.output_dir.parent.is_dir() or not args.file.is_file():
        raise FileNotFoundError("Source file or output parent directory does not exist")
    glossary = None
    if args.glossary:
        glossary = Glossary.load(args.glossary)
        if (glossary.source_lang, glossary.target_lang) != ("en", args.target_lang):
            raise ValueError("Glossary language mismatch")
    # Reject undecodable input before constructing the backend.
    args.file.read_bytes().decode("utf-8-sig")
    with suppress(OSError, UnicodeError):
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    backend: TranslationBackend = (
        MarianBackend() if args.backend == "marian" else HuggingFaceBackend()
    )
    if glossary is not None:
        backend = GlossaryBackend(backend, glossary)
    started = monotonic()
    print(
        f"Preparing review with {args.backend}; the first segment may load the model...",
        file=sys.stderr,
        flush=True,
    )
    count = 0
    with TemporaryDirectory(prefix=".doc-lingo-review-", dir=args.output_dir.parent) as directory:
        staging = Path(directory)
        with (staging / "issues.jsonl").open("w", encoding="utf-8", newline="\n") as log:

            def issue(value):
                nonlocal count
                log.write(json.dumps(asdict(value), ensure_ascii=False) + "\n")
                log.flush()
                count += 1

            def progress(number, kind):
                print(
                    f"Segments translated: {number} | Type: {kind} | "
                    f"Elapsed: {monotonic() - started:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )

            job = translate_text_job(
                args.file,
                backend,
                source_lang="en",
                target_lang=args.target_lang,
                on_issue=issue,
                on_progress=progress,
            )
        if not count:
            (staging / "issues.jsonl").unlink()
        save_job(job, staging / "job.zip")
        export_review_txt(job, staging / "review.txt")
        _publish(staging, args.output_dir)
    print(
        f"Review preparation complete: {args.output_dir / 'review.txt'}\n"
        f"Job: {args.output_dir / 'job.zip'}\n"
        "Edit the Correction areas, save the TXT, then use doc-lingo review finalize."
    )
    if count:
        parser.exit(
            3,
            f"Warning: {count} translation issues; source text was retained where needed. "
            f"Diagnostics: {args.output_dir / 'issues.jsonl'}\n",
        )


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            try:
                validate_language_pair(args.backend, "en", args.target_lang)
            except ValueError as error:
                parser.error(str(error))
            _prepare(args, parser)
        else:
            if args.output.suffix.lower() != ".txt":
                parser.error("Final review output must use the .txt extension")
            if os.path.lexists(args.output):
                raise FileExistsError(args.output)
            finalize_text_review(
                load_job(args.job), args.review, args.output, original=args.original
            )
            print(f"Review finalization complete: {args.output}")
    except FileExistsError:
        parser.exit(1, "Error: Output already exists; choose a new output path.\n")
    except (OSError, ValueError, TranslationError) as error:
        parser.exit(1, f"Error: {error}\n")
