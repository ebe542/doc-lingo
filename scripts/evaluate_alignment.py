"""Compare alignment settings on fixed pairs without translating documents."""

import argparse
import json
import platform
from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from doc_lingo.translation.alignment import AlignmentError
from doc_lingo.translation.awesome_adapter import AwesomeAlignAdapter
from doc_lingo.translation.marker_alignment import anchor_registered_markers
from doc_lingo.translation.simalign_adapter import SimAlignAdapter


def evaluate_case(
    adapter, case: dict, *, anchor_markers: bool = False, local_review: bool = False
) -> dict:
    """Preserve raw links even when marker validation rejects their correction."""
    start = perf_counter()
    raw = None
    corrected = None
    error = None
    reviews = []
    try:
        result = adapter.align(case["source"], case["target"])
        raw = asdict(result)
        if anchor_markers and "markers" in case:
            result = anchor_registered_markers(
                result, tokens=tuple(case["markers"]), prefix=case["marker_prefix"]
            )
        corrected = asdict(result)
        if local_review:
            from scripts.local_alignment import evaluate_local

            reviews = evaluate_local(adapter, result, case)
    except AlignmentError as exc:
        error = str(exc)
    return {
        "case": case,
        "alignment": corrected,
        "raw_alignment": raw,
        "error": error,
        "seconds": perf_counter() - start,
        "verdict": "pending",
        "local_reviews": reviews,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("tests/fixtures/alignment/en-de.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="google-bert/bert-base-multilingual-cased")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--backend", default="simalign", choices=("simalign", "awesome"))
    parser.add_argument("--thresholds", nargs="+", type=float)
    parser.add_argument("--anchor-markers", action="store_true")
    parser.add_argument("--local-review", action="store_true")
    args = parser.parse_args()
    if args.thresholds is not None and args.backend != "awesome":
        parser.error("--thresholds requires --backend awesome")
    thresholds = args.thresholds if args.thresholds is not None else [0.001]
    if any(not 0 < value < 1 for value in thresholds) or len(set(thresholds)) != len(thresholds):
        parser.error("Thresholds must be distinct values between zero and one")
    if args.output.exists():
        parser.error("Output already exists; choose a new report path")
    raw = args.suite.read_bytes()
    cases = json.loads(raw)
    from huggingface_hub import snapshot_download

    weights = "pytorch_model.bin" if args.backend == "awesome" else "*.safetensors"
    snapshot = snapshot_download(
        args.model, revision=args.revision, allow_patterns=["*.json", "*.txt", weights]
    )
    adapter = (
        AwesomeAlignAdapter.load(snapshot, device=args.device)
        if args.backend == "awesome"
        else SimAlignAdapter.load(snapshot, device=args.device)
    )
    methods = ("softmax",) if args.backend == "awesome" else ("inter", "itermax")
    packages = (
        ("awesome-align", "torch")
        if args.backend == "awesome"
        else ("simalign", "torch", "transformers")
    )
    report = {
        "model": args.model,
        "backend": args.backend,
        "revision": Path(snapshot).name,
        "device": args.device,
        "python": platform.python_version(),
        "suite_sha256": sha256(raw).hexdigest(),
        "packages": {name: version(name) for name in packages},
        "softmax_threshold": thresholds[0]
        if args.backend == "awesome" and len(thresholds) == 1
        else None,
        "thresholds": thresholds if args.backend == "awesome" else [],
        "anchor_markers": args.anchor_markers,
        "local_review": args.local_review,
        "tokenization": "unicode-words-punctuation-v1",
        "layer": 8,
        "results": [],
    }
    for case in cases:
        for method, threshold in (
            (method, threshold)
            for method in methods
            for threshold in (thresholds if args.backend == "awesome" else [None])
        ):
            if isinstance(adapter, SimAlignAdapter):
                adapter.method = method
            else:
                assert threshold is not None
                adapter = AwesomeAlignAdapter(
                    adapter.model, adapter.tokenizer, device=args.device, threshold=threshold
                )
            row = evaluate_case(
                adapter, case, anchor_markers=args.anchor_markers, local_review=args.local_review
            )
            row.update(method=method, softmax_threshold=threshold)
            report["results"].append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    errors = sum(
        int(item["error"] is not None)
        + sum(review["status"] == "error" for review in item["local_reviews"])
        for item in report["results"]
    )
    print(
        f"Evaluation complete: {len(cases)} cases, "
        f"{len(report['results'])} evaluations, {errors} execution errors."
    )
    print(f"Report saved: {args.output}")
    return int(errors > 0)


if __name__ == "__main__":
    raise SystemExit(main())
