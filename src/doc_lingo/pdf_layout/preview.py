"""Render source pages with evidence overlays, not reconstructed PDF output."""

import hashlib
import json
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory


def _load(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Layout file escapes the extraction directory")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("Unsupported layout schema version")
    return value


def _rectangle(box, matrix, kind, title):
    import pymupdf

    rect = pymupdf.Rect(box) * matrix
    return (
        f'<rect class="{kind}" x="{rect.x0}" y="{rect.y0}" '
        f'width="{rect.width}" height="{rect.height}">'
        f"<title>{escape(title)}</title></rect>"
    )


def create_preview(
    source: Path, layout: Path, destination: Path, *, groups: Path | None = None
) -> Path:
    """Write an offline HTML inspection view into a new directory.

    Source SHA-256 must match the extraction. Source rendering is only a visual
    reference: it does not demonstrate successful reconstruction from JSON.
    """
    import pymupdf

    source, layout, destination = Path(source), Path(layout), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    manifest = _load(layout, "manifest.json")
    grouped_pages = {}
    if groups is not None:
        groups = Path(groups)
        grouped_manifest = _load(groups, "manifest.json")
        if (
            grouped_manifest["extraction_sha256"]
            != hashlib.sha256((layout / "manifest.json").read_bytes()).hexdigest()
        ):
            raise ValueError("Groups do not match extraction manifest")
        grouped_pages = {entry["pdf_page"]: entry["file"] for entry in grouped_manifest["pages"]}
        if set(grouped_pages) != {entry["pdf_page"] for entry in manifest["pages"]}:
            raise ValueError("Group page selection does not match extraction")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["source"]["sha256"]:
        raise ValueError("Source PDF does not match the extraction SHA-256")
    with (
        pymupdf.open(stream=data, filetype="pdf") as document,
        TemporaryDirectory(prefix=".pdf-preview-", dir=destination.parent) as temporary,
    ):
        root = Path(temporary) / "preview"
        root.mkdir()
        sections = []
        fonts = {font["id"]: font for font in manifest["fonts"]}
        for index, reference in enumerate(manifest["pages"]):
            evidence = _load(layout, reference["file"])
            number = reference["pdf_page"]
            if evidence["pdf_page"] != number:
                raise ValueError("Page evidence does not match manifest")
            page = document[number - 1]
            image = f"page-{number:04d}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).save(root / image)
            matrix = pymupdf.Matrix(evidence["rotation_matrix"])
            group_overlays, group_rows = [], []
            if groups is not None:
                grouped = _load(groups, grouped_pages[number])
                if (
                    grouped["page_sha256"]
                    != hashlib.sha256((layout / reference["file"]).read_bytes()).hexdigest()
                    or grouped["pdf_page"] != number
                ):
                    raise ValueError("Groups do not match page evidence")
                for block in grouped["blocks"]:
                    title = f"{block['id']}\n{block['kind']}\n{block['text']}"
                    group_overlays.append(_rectangle(block["bbox"], matrix, "group", title))
                    group_rows.append(
                        "<tr>"
                        + "".join(
                            f"<td>{escape(str(value))}</td>"
                            for value in (
                                block["id"],
                                block["kind"],
                                block["text"],
                                ", ".join(block["fragment_ids"]),
                            )
                        )
                        + "</tr>"
                    )
            overlays, rows = [], []
            for obj in evidence["objects"]:
                kind = obj["kind"]
                if kind not in {"text_fragment", "image"}:
                    continue
                text = obj.get("text", "Image")
                status = obj.get("font_match", "")
                candidates = ", ".join(
                    fonts[fid]["pdf_name"] for fid in obj.get("font_candidates", [])
                )
                title = f"{obj['id']}\n{text}\n{status}\n{candidates}"
                style = (
                    "image"
                    if kind == "image"
                    else ("text" if status == "name_unique" else "uncertain")
                )
                overlays.append(_rectangle(obj["source"]["bbox"], matrix, style, title))
                rows.append(
                    "<tr>"
                    + "".join(
                        f"<td>{escape(str(v))}</td>"
                        for v in (
                            obj["id"],
                            text,
                            obj["source"].get("font", ""),
                            status,
                            candidates,
                        )
                    )
                    + "</tr>"
                )
            graphics = _load(layout, evidence["graphics_file"])
            for path_index, path in enumerate(graphics["paths"]):
                box = path.get("rect", path.get("scissor"))
                if box is not None:
                    overlays.append(
                        _rectangle(box, matrix, "vector", f"Path {path_index}: {path['type']}")
                    )
            width, height = page.rect.width, page.rect.height
            sections.append(
                f"<section><h2>PDF page {number}</h2>"
                f'<input class="raw-toggle" id="toggle-{index}" type="checkbox" '
                f"{'checked' if groups is None else ''}>"
                f'<label for="toggle-{index}"> Show extracted bounds</label>'
                f'<input class="group-toggle" id="groups-{index}" type="checkbox" checked>'
                f'<label for="groups-{index}"> Show candidate text groups</label>'
                f'<svg viewBox="0 0 {width} {height}" role="img" '
                f'aria-label="PDF page {number} with extraction bounds">'
                f'<image href="{image}" width="{width}" height="{height}"/>'
                f'<g class="raw-bounds">{"".join(overlays)}</g>'
                f'<g class="group-bounds">{"".join(group_overlays)}</g></svg>'
                "<details open><summary>Candidate text groups</summary><table>"
                "<tr><th>ID</th><th>Kind</th><th>Text</th><th>Source fragments</th></tr>"
                f"{''.join(group_rows)}</table></details>"
                "<details><summary>Objects and font candidates</summary><table>"
                "<tr><th>ID</th><th>Text</th><th>Extracted font</th>"
                "<th>Match</th><th>Candidates</th></tr>"
                f"{''.join(rows)}</table></details></section>"
            )
        html = """<!doctype html>
<html lang="en"><meta charset="utf-8"><title>PDF layout inspection</title>
<style>
body{font:16px system-ui,sans-serif;margin:2rem;background:#eee;color:#222}
section{background:white;padding:1rem;margin:2rem 0}
svg{display:block;width:100%;max-width:1000px;margin-top:1rem}
rect{fill:transparent;stroke-width:.7;vector-effect:non-scaling-stroke}
rect:hover{fill:#ffff0066;stroke-width:2}
.text{stroke:#0672ce}.image{stroke:#16803c}.vector{stroke:#9b35ba}
.uncertain{stroke:#d05400;stroke-dasharray:3 2}
.group{stroke:#c40063;stroke-width:1.5}
.raw-toggle:not(:checked)~svg .raw-bounds{display:none}
.group-toggle:not(:checked)~svg .group-bounds{display:none}
td,th{border:1px solid #ccc;padding:.4rem;text-align:left;overflow-wrap:anywhere}
table{border-collapse:collapse;width:100%;table-layout:fixed}td{white-space:pre-wrap}
</style><h1>PDF layout inspection</h1>
<p>The background is rendered from the original PDF, not reconstructed from JSON.
Bounds only check extraction geometry, not completeness or correct reading order.</p>
<p>Blue: text; orange dashed: uncertain font; green: image; purple: vector/clip bounds.
Hover over a rectangle for its ID and text. Font details are listed below each page.</p>
<p>Pink: candidate text groups. Hide extracted bounds to inspect groups separately.
Group text preserves line breaks and hyphens; grouping does not establish reading order.</p>
"""
        html += "".join(sections) + "\n</html>\n"
        (root / "index.html").write_text(html, encoding="utf-8", newline="\n")
        if destination.exists():
            raise FileExistsError(destination)
        root.rename(destination)
    return destination / "index.html"
