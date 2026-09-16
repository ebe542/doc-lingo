"""Generate translations for manual quality review; never assign semantic passes."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any

from dotenv import load_dotenv

from doc_lingo import (
    HuggingFaceBackend,
    MarianBackend,
    PlainTextReader,
    PlainTextWriter,
    SegmentMismatchError,
    TranslationBackend,
    TranslationError,
    translate_document,
)
from doc_lingo.translation.prompts import TRANSLATION_DIRECTION, TRANSLATION_SYSTEM
from doc_lingo.translation.selection import BACKEND_NAMES, DEFAULT_BACKEND, validate_language_pair

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = PROJECT_ROOT / "tests/fixtures/translation_quality/en-de.json"


def load_suite(path: Path) -> dict[str, Any]:
    """Validate the fixture before model loading or creating an output directory."""
    suite = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(suite, dict) or suite.get("schema_version") != 1:
        raise ValueError("Expected suite schema version 1")
    if type(suite.get("suite_version")) is not int or suite["suite_version"] < 1:
        raise ValueError("Expected a positive suite version")
    if suite.get("evaluation") != "manual":
        raise ValueError("Only manual evaluation suites are supported")
    for field in ("source_lang", "target_lang"):
        if not isinstance(suite.get(field), str) or not suite[field].strip():
            raise ValueError(f"Missing {field}")
    examples = suite.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError("Expected a nonempty examples list")
    ids = set()
    for example in examples:
        if not isinstance(example, dict):
            raise ValueError("Each example must be an object")
        for field in ("id", "category", "source", "reference"):
            if not isinstance(example.get(field), str) or not example[field].strip():
                raise ValueError(f"Example requires {field}")
        if example["id"] in ids:
            raise ValueError("Example IDs must be unique")
        ids.add(example["id"])
        criteria = example.get("criteria")
        if (
            not isinstance(criteria, list)
            or not criteria
            or any(not isinstance(item, str) or not item.strip() for item in criteria)
        ):
            raise ValueError("Each example requires nonempty review criteria")
    return suite


def evaluate_suite(
    suite: dict[str, Any], backend: TranslationBackend, output: Path, *, metadata: dict[str, Any]
) -> dict[str, Any]:
    """Run each example independently; retain results and clean temporary documents.

    Output must be a new directory. Reports are saved after each example so an
    interrupted run retains completed work. Expected failures are marked blocked;
    unexpected programming errors propagate. The backend can reuse loaded weights.
    """
    output.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "report_version": 1,
        "started_at": datetime.now(UTC).isoformat(),
        "suite_version": suite["suite_version"],
        "suite_fingerprint": sha256(
            json.dumps(suite, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "source_lang": suite["source_lang"],
        "target_lang": suite["target_lang"],
        "metadata": metadata,
        "complete": False,
        "results": [],
    }

    def save() -> None:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    save()
    for index, example in enumerate(suite["examples"], 1):
        result = dict(example)
        result.update(actual=None, verdict="pending", notes="", error=None)
        started = monotonic()
        with TemporaryDirectory(prefix=".quality-", dir=output) as temporary:
            source = Path(temporary) / "source.txt"
            destination = Path(temporary) / "translated.txt"
            source.write_bytes(example["source"].encode("utf-8"))
            try:
                translate_document(
                    PlainTextReader(source),
                    PlainTextWriter(source),
                    backend,
                    destination,
                    source_lang=suite["source_lang"],
                    target_lang=suite["target_lang"],
                )
                result["actual"] = destination.read_bytes().decode("utf-8")
            except (TranslationError, SegmentMismatchError, OSError, UnicodeError) as error:
                result["verdict"] = "blocked"
                # Raw provider errors can contain source text or credentials.
                result["error"] = type(error).__name__
        result["elapsed_seconds"] = round(monotonic() - started, 3)
        report["results"].append(result)
        save()
        print(f"Example {index}/{len(suite['examples'])}: {result['verdict']}", flush=True)
    report["complete"] = True
    save()
    return report


def runtime_metadata(backend: HuggingFaceBackend | MarianBackend) -> dict[str, Any]:
    """Capture configuration for comparisons without recording credentials."""
    packages = {}
    for name in ("torch", "transformers", "doc-lingo", "sentencepiece", "sacremoses"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    import torch

    is_marian = isinstance(backend, MarianBackend)
    metadata = {
        "backend": "marian" if is_marian else "qwen",
        "python": platform.python_version(),
        "packages": packages,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "model": backend.model_name,
        "revision": backend.revision,
        "max_input_tokens": backend.max_input_tokens,
        "max_new_tokens": backend.max_new_tokens,
        "dtype": "float32" if is_marian else "float16",
        "do_sample": False,
        "enable_thinking": None if is_marian else False,
        "prompts": []
        if is_marian
        else [
            {"name": prompt.name, "version": prompt.version, "fingerprint": prompt.fingerprint}
            for prompt in (TRANSLATION_SYSTEM, TRANSLATION_DIRECTION)
        ],
    }
    if is_marian:
        metadata["generation"] = {
            "num_beams": 4,
            "num_return_sequences": 1,
            "early_stopping": True,
            "length_penalty": 1.0,
            "renormalize_logits": True,
            "forced_eos_token_id": None,
        }
        metadata["prompt_mode"] = "none"
    else:
        metadata["prompt_mode"] = "chat"
    return metadata


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate translations for manual quality review")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument(
        "--backend",
        choices=BACKEND_NAMES,
        default=DEFAULT_BACKEND,
        help="Local backend (default: marian; en to de only)",
    )
    parser.add_argument("--output", type=Path, required=True, help="New report directory")
    args = parser.parse_args(argv)
    try:
        suite = load_suite(args.suite)
        try:
            validate_language_pair(args.backend, suite["source_lang"], suite["target_lang"])
        except ValueError as error:
            parser.error(str(error))
        load_dotenv(Path.cwd() / ".env", override=False)
        backend = MarianBackend() if args.backend == "marian" else HuggingFaceBackend()
        report = evaluate_suite(suite, backend, args.output, metadata=runtime_metadata(backend))
    except (OSError, ValueError, ImportError):
        parser.exit(1, "Error: Check the suite, new output path, and installed local extra.\n")
    print(f"Review translations in {args.output / 'report.json'}; pending is not a quality pass.")
    if any(result["verdict"] == "blocked" for result in report["results"]):
        parser.exit(1, "Some examples were blocked; review the report.\n")


if __name__ == "__main__":
    main()
