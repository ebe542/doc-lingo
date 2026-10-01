"""Compare SimAlign methods on fixed pairs without translating documents."""

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
from doc_lingo.translation.simalign_adapter import SimAlignAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("tests/fixtures/alignment/en-de.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="google-bert/bert-base-multilingual-cased")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--backend", default="simalign", choices=("simalign", "awesome"))
    args = parser.parse_args()
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
        "softmax_threshold": 0.001 if args.backend == "awesome" else None,
        "tokenization": "unicode-words-punctuation-v1",
        "layer": 8,
        "results": [],
    }
    for case in cases:
        for method in methods:
            if isinstance(adapter, SimAlignAdapter):
                adapter.method = method
            start = perf_counter()
            try:
                result = asdict(adapter.align(case["source"], case["target"]))
                error = None
            except AlignmentError as exc:
                result, error = None, str(exc)
            report["results"].append(
                {
                    "case": case,
                    "method": method,
                    "alignment": result,
                    "error": error,
                    "seconds": perf_counter() - start,
                    "verdict": "pending",
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return int(any(item["error"] for item in report["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
