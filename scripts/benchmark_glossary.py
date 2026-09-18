"""Measure glossary storage/loading and matching offline, without a model."""

import argparse
import gc
import gzip
import json
import platform
import re
import statistics
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from doc_lingo import Glossary, GlossaryBackend


class EchoBackend:
    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        return text


def measure(size: int, repeats: int, directory: Path) -> dict:
    """Use shared-prefix terms to exercise shared lookup paths, not random words.

    Traced allocations are measured separately from latency. Regex caches used
    by placeholder restoration are cleared before construction measurements.
    File reads may use the OS cache.
    Memory figures are Python traced allocations, not total process/GPU memory.
    """
    payload = {
        "schema_version": 1,
        "source_lang": "en",
        "target_lang": "de",
        "entries": [
            {"source": f"term{i:06d}", "mode": "translate", "target": f"Begriff{i:06d}"}
            for i in range(size)
        ],
    }
    raw = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    packed = gzip.compress(raw, mtime=0)
    paths = [directory / "glossary.json", directory / "glossary.json.gz"]
    paths[0].write_bytes(raw)
    paths[1].write_bytes(packed)
    timings = {}
    loaded = []
    for path in paths:
        start = perf_counter()
        loaded.append(Glossary.load(path))
        timings[path.name] = round(perf_counter() - start, 6)
    if loaded[0] != loaded[1]:
        raise AssertionError("Compressed glossary differs from JSON")
    re.purge()
    start = perf_counter()
    backend = GlossaryBackend(EchoBackend(), loaded[0])
    build_seconds = perf_counter() - start
    last = f"term{size - 1:06d}"
    cases = {
        "no_hits": ("ordinary text " * 100, "ordinary text " * 100),
        "near_misses": ("term999999 " * 100, "term999999 " * 100),
        "late_hit": (f"A {last} example", f"A Begriff{size - 1:06d} example"),
        "dense_hits": (
            (f"term000000 {last} " * 50),
            (f"Begriff000000 Begriff{size - 1:06d} " * 50),
        ),
    }
    case_results = {}
    for name, (text, expected) in cases.items():
        durations = []
        for _ in range(repeats):
            start = perf_counter()
            result = backend.translate(text, source_lang="en", target_lang="de")
            durations.append(perf_counter() - start)
            if result != expected:
                raise AssertionError(f"Incorrect synthetic translation in {name}")
        case_results[name] = {
            "characters": len(text),
            "median_seconds": round(statistics.median(durations), 6),
        }
    del backend, loaded, payload, raw, packed
    gc.collect()
    re.purge()
    tracemalloc.start()
    try:
        measured = GlossaryBackend(EchoBackend(), Glossary.load(paths[0]))
        _, peak = tracemalloc.get_traced_memory()
        del measured
    finally:
        tracemalloc.stop()
    return {
        "entries": size,
        "json_bytes": paths[0].stat().st_size,
        "gzip_bytes": paths[1].stat().st_size,
        "load_seconds": timings,
        "build_seconds": round(build_seconds, 6),
        "load_build_python_peak_bytes": peak,
        "cases": case_results,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[50, 1000, 10000])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True, help="New benchmark JSON file")
    args = parser.parse_args(argv)
    if args.repeats < 1 or any(not 1 <= size <= 100000 for size in args.sizes):
        parser.error("Use positive repeats and glossary sizes from 1 to 100000")
    report = {
        "matcher": "prefix-trie-v1",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "repeats": args.repeats,
        "results": [],
        "scope": "Synthetic CPU measurements; no model quality or GPU inference measured",
    }
    # Reserve a new result file and keep disposable input files beside it.
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        with TemporaryDirectory(prefix=".glossary-bench-", dir=args.output.parent) as temporary:
            for size in args.sizes:
                report["results"].append(measure(size, args.repeats, Path(temporary)))
                print(f"Measured {size} entries", flush=True)
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
