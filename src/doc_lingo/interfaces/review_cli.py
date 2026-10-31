"""Prepare and finalize human-reviewed TXT and Markdown translations."""

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

from doc_lingo.review import (
    export_review_txt,
    finalize_markdown_review,
    finalize_text_review,
    import_review_txt,
    load_job,
    save_job,
    translate_markdown_job,
)
from doc_lingo.review.markdown import markdown_blocks
from doc_lingo.review.preparation import translate_text_job
from doc_lingo.translation.alignment import AlignmentError
from doc_lingo.translation.awesome_adapter import AwesomeAlignAdapter
from doc_lingo.translation.glossary import Glossary, GlossaryBackend
from doc_lingo.translation.huggingface import HuggingFaceBackend
from doc_lingo.translation.marian import MarianBackend
from doc_lingo.translation.protocols import TranslationBackend, TranslationError
from doc_lingo.translation.selection import BACKEND_NAMES, DEFAULT_BACKEND, validate_language_pair


def build_parser():
    parser = argparse.ArgumentParser(prog="doc-lingo review", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser(
        "prepare", help="Translate TXT/Markdown into an editable TXT review"
    )
    prepare.add_argument("file", type=Path, help="English UTF-8 .txt or .md source")
    prepare.add_argument("--target-lang", required=True, choices=("en", "de"))
    prepare.add_argument("--output-dir", type=Path, required=True, help="New review directory")
    prepare.add_argument("--backend", choices=BACKEND_NAMES, default=DEFAULT_BACKEND)
    prepare.add_argument("--glossary", type=Path)
    finish = commands.add_parser("finalize", help="Create final TXT/Markdown without retranslating")
    finish.add_argument("job", type=Path, help="Saved job.zip")
    finish.add_argument("review", type=Path, help="Edited review.txt")
    finish.add_argument(
        "--output", type=Path, required=True, help="New output matching the job format"
    )
    finish.add_argument("--original", type=Path, help="Optional original to check against the job")
    finish.add_argument(
        "--aligner", choices=("awesome",), help="Optional Markdown formatting alignment"
    )
    finish.add_argument("--alignment-model", type=Path, help="Local awesome-align model directory")
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
    extension = args.file.suffix.lower()
    if extension not in (".txt", ".md"):
        parser.error("Review preparation supports .txt and .md sources")
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
    if extension == ".md":
        markdown_blocks(args.file.read_bytes())
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

            translate_job = translate_markdown_job if extension == ".md" else translate_text_job
            job = translate_job(
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


def _finalize(args, parser):
    if args.output.suffix.lower() not in (".txt", ".md"):
        parser.error("Final review output must use the .txt or .md extension")
    if bool(args.aligner) != bool(args.alignment_model):
        parser.error("--aligner and --alignment-model must be supplied together")
    report = args.output.with_name(args.output.name + ".issues.jsonl")
    if os.path.lexists(args.output) or os.path.lexists(report):
        raise FileExistsError(args.output)
    if not args.output.parent.is_dir():
        raise FileNotFoundError("Output directory does not exist")
    job = load_job(args.job)
    if args.output.suffix.lower() != "." + job.document_format:
        parser.error(f"Output must use the .{job.document_format} extension")
    if args.aligner and job.document_format != "md":
        parser.error("--aligner requires a Markdown review job")
    if args.original is not None:
        job.verify_source(args.original)
    # Validate human edits before optional alignment dependencies are loaded.
    import_review_txt(job, args.review)
    aligner = None
    if args.aligner:
        if not args.alignment_model.is_dir():
            raise FileNotFoundError("Alignment model directory does not exist")
        print("Loading Markdown formatting aligner...", file=sys.stderr, flush=True)
        aligner = AwesomeAlignAdapter.load(str(args.alignment_model))
    issues = ()
    with TemporaryDirectory(prefix=".doc-lingo-review-", dir=args.output.parent) as directory:
        staging = Path(directory)
        output = staging / args.output.name
        if job.document_format == "md":
            issues = finalize_markdown_review(
                job, args.review, output, original=args.original, aligner=aligner
            )
        else:
            finalize_text_review(job, args.review, output, original=args.original)
        staged_report = staging / report.name
        if issues:
            staged_report.write_text(
                "".join(json.dumps(asdict(issue), ensure_ascii=False) + "\n" for issue in issues),
                encoding="utf-8",
                newline="\n",
            )
        published = []
        try:
            if issues:
                os.link(staged_report, report)
                published.append(report)
            os.link(output, args.output)
        except BaseException:
            for path in published:
                path.unlink()
            raise
    print(f"Review finalization complete: {args.output}")
    if issues:
        parser.exit(3, f"Warning: {len(issues)} formatting issues. Diagnostics: {report}\n")


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
            _finalize(args, parser)
    except FileExistsError:
        parser.exit(1, "Error: Output already exists; choose a new output path.\n")
    except (OSError, ValueError, TranslationError, AlignmentError) as error:
        parser.exit(1, f"Error: {error}\n")
