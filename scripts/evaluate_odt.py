"""Translate the supported ODT subset and prepare an explicit manual review."""

import argparse
import json
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import file_digest
from pathlib import Path
from time import monotonic
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from dotenv import load_dotenv

from doc_lingo import MarianBackend, TranslationError, translate_document
from doc_lingo.documents.odt import OdtReader, OdtWriter, inspect_package
from doc_lingo.documents.odt.blocks import package_blocks, package_parts
from doc_lingo.translation.alignment import AlignmentError
from doc_lingo.translation.alignment_statistics import AlignmentStatistics
from doc_lingo.translation.awesome_adapter import AwesomeAlignAdapter
from scripts.evaluate_translation_quality import runtime_metadata

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
BLOCKS = {f"{{{TEXT}}}p", f"{{{TEXT}}}h"}


def fingerprint(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def inventory(package):
    """Include unsupported contexts without implying reliable page coordinates."""
    blocks = {b.segment.id: b for b in package_blocks(package)}
    rows = []
    number = 0

    def visit(element, ancestors, part):
        nonlocal number
        if element.tag in BLOCKS:
            number += 1
            identifier = str(number) if part == "content.xml" else f"{part}:{number}"
            block = blocks[identifier]
            rows.append(
                {
                    "segment_id": identifier,
                    "part": part,
                    "type": block.segment.type,
                    "context": ancestors,
                    "status": "skipped" if block.reason else "eligible",
                    "reason": block.reason,
                    "page": None,
                    "source_text": "".join(element.itertext()),
                }
            )
        for child in element:
            visit(child, [*ancestors, element.tag], part)

    for part, xml in package_parts(package).items():
        number = 0
        visit(ET.fromstring(xml), [], part)
    peripheral = [row for row in rows if row["part"] == "styles.xml"]
    return rows, peripheral


def evaluate_odt(source, output, backend, aligner, *, metadata):
    """Use a fresh directory; keep partial diagnostics if processing fails."""
    source, output = Path(source), Path(output)
    package = inspect_package(source)
    rows, peripheral = inventory(package)
    original_hash = fingerprint(source)
    output.mkdir(parents=True, exist_ok=False)
    destination = output / "translated.de.odt"
    stats = AlignmentStatistics()
    started = monotonic()
    report = {
        "report_version": 2,
        "started_at": datetime.now(UTC).isoformat(),
        "source": str(source.resolve()),
        "source_sha256": original_hash,
        "source_lang": "en",
        "target_lang": "de",
        "metadata": metadata,
        "complete": False,
        "status": "running",
        "manual_review": "pending",
        "processed_segments": 0,
        "issue_count": 0,
        "blocks": rows,
        "peripheral_text": peripheral,
        "eligible_segments": sum(row["status"] == "eligible" for row in rows),
        "skipped_blocks": sum(row["status"] == "skipped" for row in rows),
        "limitations": [
            "Cells with formulas/stored values and unsupported drawing containers remain unchanged",
            "Unsupported header/footer containers and inline content remain unchanged",
            "No reliable page coordinates or visual-layout validation",
            "Source text and diagnostics may contain private document content",
        ],
    }

    def save():
        report["elapsed_seconds"] = round(monotonic() - started, 3)
        report["alignment_statistics"] = asdict(stats)
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    save()
    try:
        with (output / "issues.jsonl").open("x", encoding="utf-8", newline="\n") as log:

            def issue(value):
                log.write(json.dumps(asdict(value), ensure_ascii=False) + "\n")
                log.flush()
                report["issue_count"] += 1

            def progress(count, kind):
                report["processed_segments"] = count
                save()
                print(
                    f"Processed {count}/{report['eligible_segments']} | {kind} | "
                    f"{monotonic() - started:.1f}s",
                    flush=True,
                )

            translate_document(
                OdtReader(source),
                OdtWriter(source),
                backend,
                destination,
                source_lang="en",
                target_lang="de",
                aligner=aligner,
                alignment_statistics=stats,
                on_issue=issue,
                on_progress=progress,
            )
        inspect_package(destination)
        unchanged = []
        with ZipFile(source) as original, ZipFile(destination) as translated:
            if original.namelist() != translated.namelist():
                raise ValueError("ODT package member list changed")
            for name in original.namelist():
                if name not in package_parts(package):
                    if original.read(name) != translated.read(name):
                        raise ValueError("Non-editable ODT member changed")
                    unchanged.append(name)
        report["source_unchanged"] = fingerprint(source) == original_hash
        if not report["source_unchanged"]:
            raise ValueError("Source changed during review")
        report.update(
            complete=True,
            status="completed",
            output_sha256=fingerprint(destination),
            unchanged_members=unchanged,
        )
    except BaseException as error:
        report.update(
            status="failed", error_type=type(error).__name__, output_exists=destination.exists()
        )
        save()
        raise
    save()
    print(
        f"ODT review complete: {destination}\n"
        f"Report: {output / 'report.json'} | Issues: {report['issue_count']} | "
        f"Skipped blocks: {report['skipped_blocks']} | "
        f"Peripheral text blocks: {len(peripheral)}\nManual review remains pending.",
        flush=True,
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--alignment-model",
        type=Path,
        required=True,
        help="Existing local awesome-align checkpoint directory (CPU)",
    )
    parser.add_argument("--output", type=Path, required=True, help="New review directory")
    args = parser.parse_args(argv)
    try:
        inspect_package(args.source)
        if args.output.exists() or not args.alignment_model.is_dir():
            raise ValueError("Choose a new output directory and an existing model directory")
        with suppress(OSError, UnicodeError):
            load_dotenv(Path.cwd() / ".env", override=False)
        print("Preparing Marian translation (CUDA) and awesome-align (CPU)...", flush=True)
        backend = MarianBackend()
        aligner = AwesomeAlignAdapter.load(str(args.alignment_model))
        metadata = runtime_metadata(backend)
        metadata["input_splitting"] = "paired-aligned-chunks"
        metadata["alignment"] = {
            "model": str(args.alignment_model.resolve()),
            "device": aligner.device,
            "threshold": aligner.threshold,
            "files": {
                str(p.relative_to(args.alignment_model)): fingerprint(p)
                for p in sorted(args.alignment_model.rglob("*"))
                if p.is_file()
            },
        }
        root = Path(__file__).resolve().parents[1]
        metadata["code_sha256"] = {
            str(p.relative_to(root)): fingerprint(p)
            for p in sorted((root / "src/doc_lingo").rglob("*.py"))
        }
        metadata["evaluation_script_sha256"] = fingerprint(Path(__file__))
        evaluate_odt(args.source, args.output, backend, aligner, metadata=metadata)
    except (
        OSError,
        ValueError,
        RuntimeError,
        ImportError,
        TranslationError,
        AlignmentError,
    ) as error:
        parser.exit(
            1,
            f"ODT review failed ({type(error).__name__}). "
            "Check inputs/dependencies and report.json if created.\n",
        )


if __name__ == "__main__":
    main()
