"""Conservative, page-local grouping; raw extraction evidence stays immutable."""

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory

from .extract import _json
from .preview import _load

ALGORITHM = "conservative-lines-v2"


def _marker(fragment):
    text = fragment["text"].strip()
    font = fragment["source"].get("font", "").lower()
    return len(text) == 1 and (
        text in "•◦▪‣●○■"
        or (
            0xE000 <= ord(text) <= 0xF8FF
            and any(name in font for name in ("wingdings", "dingbats"))
        )
    )


def _visual_rows(parts):
    """Reconcile engine lines by baseline, without crossing engine blocks."""
    rows = []
    for part in sorted(parts, key=lambda f: f["source"]["origin"][1]):
        for row in rows:
            first = row[0]
            tolerance = 0.2 * min(first["source"]["size"], part["source"]["size"])
            if (
                _horizontal(first)
                and _horizontal(part)
                and abs(first["source"]["origin"][1] - part["source"]["origin"][1]) <= tolerance
            ):
                row.append(part)
                break
        else:
            rows.append([part])
    return rows


def _bounds(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def _horizontal(fragment):
    direction = fragment["direction"]
    return (
        fragment["writing_mode"] == 0 and abs(direction[0] - 1) < 0.01 and abs(direction[1]) < 0.01
    )


def _line(fragments, identifier):
    text = ""
    previous = None
    for fragment in fragments:
        value = fragment["text"]
        if previous is not None and text and value:
            gap = fragment["source"]["bbox"][0] - previous["source"]["bbox"][2]
            if (
                gap > 0.15 * fragment["source"]["size"]
                and not text[-1].isspace()
                and not value[0].isspace()
            ):
                text += " "
        text += value
        previous = fragment
    return {
        "id": identifier,
        "fragment_ids": [f["id"] for f in fragments],
        "text": text,
        "bbox": _bounds([f["source"]["bbox"] for f in fragments]),
        "size": median(f["source"]["size"] for f in fragments),
        "baseline": median(f["source"]["origin"][1] for f in fragments),
        "engine_block": fragments[0]["engine_block"],
        "horizontal": all(_horizontal(f) for f in fragments),
        "role": "list_marker" if len(fragments) == 1 and _marker(fragments[0]) else "text",
        "marker_ids": [],
    }


def _joins(previous, current, group):
    size = max(previous["size"], current["size"], 1)
    if not previous["horizontal"] or not current["horizontal"]:
        return False
    if previous["role"] == "list_marker" or current["role"] == "list_marker":
        return False
    if previous["engine_block"] != current["engine_block"] and not (
        group[0]["marker_ids"] and abs(current["bbox"][0] - group[0]["bbox"][0]) <= 0.35 * size
    ):
        return False
    if abs(previous["size"] - current["size"]) > 0.08 * size:
        return False
    step = current["baseline"] - previous["baseline"]
    if not 0.7 * size <= step <= 1.65 * size:
        return False
    if re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", current["text"]):
        return False
    left = min(line["bbox"][0] for line in group)
    # Allow a first-line indent to return to the column margin, not a new indent.
    if not -1.5 * size <= current["bbox"][0] - left <= 0.35 * size:
        return False
    overlap = min(previous["bbox"][2], current["bbox"][2]) - max(
        previous["bbox"][0], current["bbox"][0]
    )
    if overlap <= 0:
        return False
    # A significantly shorter preceding line is evidence of a paragraph ending.
    right = max(line["bbox"][2] for line in group)
    return previous["bbox"][2] >= max(right, current["bbox"][2]) - 2 * size


def group_page(page):
    """Return derived lines and candidate paragraphs with complete fragment provenance.

    Engine block boundaries remain boundaries except for marked list continuations.
    No cross-page reading order, dehyphenation or semantic classification is inferred.
    """
    buckets = defaultdict(list)
    fragments = [o for o in page["objects"] if o["kind"] == "text_fragment"]
    if len({f["id"] for f in fragments}) != len(fragments):
        raise ValueError("Duplicate text fragment IDs")
    for fragment in fragments:
        buckets[fragment["engine_block"]].append(fragment)
    lines = []
    for parts in (row for block in buckets.values() for row in _visual_rows(block)):
        ordered = (
            sorted(parts, key=lambda f: f["source"]["bbox"][0])
            if all(_horizontal(f) for f in parts)
            else parts
        )
        run = []
        for part in ordered:
            if run:
                previous = run[-1]
                size = max(part["source"]["size"], previous["source"]["size"], 1)
                gap = part["source"]["bbox"][0] - previous["source"]["bbox"][2]
                baseline = abs(part["source"]["origin"][1] - previous["source"]["origin"][1])
                if (
                    not _horizontal(part)
                    or not _horizontal(previous)
                    or gap > 1.5 * size
                    or baseline > 0.35 * size
                    or _marker(part)
                    or _marker(previous)
                ):
                    lines.append(_line(run, f"{page['id']}-line-{len(lines):05d}"))
                    run = []
            run.append(part)
        if run:
            lines.append(_line(run, f"{page['id']}-line-{len(lines):05d}"))
    for previous, line in zip(lines, lines[1:], strict=False):
        size = max(line["size"], 1)
        if (
            previous["role"] == "list_marker"
            and line["role"] == "text"
            and previous["horizontal"]
            and line["horizontal"]
            and previous["engine_block"] == line["engine_block"]
            and abs(previous["baseline"] - line["baseline"]) <= 0.35 * size
            and 0 <= line["bbox"][0] - previous["bbox"][2] <= 2 * size
        ):
            line["marker_ids"] = previous["fragment_ids"]
    groups = []
    current = []
    for line in lines:
        if current and not _joins(current[-1], line, current):
            groups.append(current)
            current = []
        current.append(line)
    if current:
        groups.append(current)
    blocks = [
        {
            "id": f"{page['id']}-block-{index:05d}",
            "kind": (
                "list_marker"
                if group[0]["role"] == "list_marker"
                else "list_item_candidate"
                if group[0]["marker_ids"]
                else "paragraph_candidate"
                if len(group) > 1
                else "single_line"
            ),
            "marker_ids": group[0]["marker_ids"],
            "line_ids": [line["id"] for line in group],
            "fragment_ids": [fid for line in group for fid in line["fragment_ids"]],
            "bbox": _bounds([line["bbox"] for line in group]),
            "text": "\n".join(line["text"] for line in group),
            "layout": {
                "line_lefts": [line["bbox"][0] for line in group],
                "first_line_indent": group[0]["bbox"][0] - min(line["bbox"][0] for line in group),
            },
        }
        for index, group in enumerate(groups)
    ]
    return {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "id": page["id"],
        "pdf_page": page["pdf_page"],
        "lines": lines,
        "blocks": blocks,
        "warnings": [
            "Candidate groups require visual review; marked lists may cross engine blocks.",
            "Line breaks and hyphenation are preserved; no global reading order is inferred.",
        ],
    }


def group_layout(layout: Path, destination: Path) -> Path:
    """Write derived groups separately, bound to exact manifest/page bytes."""
    layout, destination = Path(layout), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    manifest = _load(layout, "manifest.json")
    with TemporaryDirectory(prefix=".pdf-groups-", dir=destination.parent) as temporary:
        root = Path(temporary) / "groups"
        root.mkdir()
        pages = []
        for reference in manifest["pages"]:
            page = _load(layout, reference["file"])
            if page["pdf_page"] != reference["pdf_page"]:
                raise ValueError("Page evidence does not match manifest")
            result = group_page(page)
            result["page_sha256"] = hashlib.sha256(
                (layout / reference["file"]).read_bytes()
            ).hexdigest()
            filename = f"page-{page['pdf_page']:04d}.json"
            _json(root / filename, result)
            pages.append({"pdf_page": page["pdf_page"], "file": filename})
        _json(
            root / "manifest.json",
            {
                "schema_version": 1,
                "algorithm": ALGORITHM,
                "extraction_sha256": hashlib.sha256(
                    (layout / "manifest.json").read_bytes()
                ).hexdigest(),
                "pages": pages,
            },
        )
        if destination.exists():
            raise FileExistsError(destination)
        root.rename(destination)
    return destination / "manifest.json"
