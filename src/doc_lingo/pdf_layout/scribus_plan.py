"""Prepare an inspectable Scribus import package; never launch Scribus."""

import hashlib
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory

from .extract import _base_name, _json
from .preview import _load
from .scribus_graphics import image_png, vector_svg


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_frame(block, lines, objects, fonts, mapping):
    text, runs = "", []
    for line_id in block["line_ids"]:
        line = lines[line_id]
        if text:
            text += "\u2028"  # soft line break: first-line indent applies only once
        offset, cursor = len(text), 0
        text += line["text"]
        for fid in line["fragment_ids"]:
            fragment = objects[fid]
            value = fragment["text"]
            start = line["text"].find(value, cursor)
            if start < 0:
                raise ValueError(f"{fid}: grouped text no longer matches source fragment")
            cursor = start + len(value)
            font_id = fragment["font_id"]
            if font_id is None:
                alias = mapping.get("fragment_fonts", {}).get(fragment["source"]["font"])
                candidates = [
                    fid
                    for fid in fragment["font_candidates"]
                    if _base_name(fonts[fid]["pdf_name"]) == alias
                ]
                if len(candidates) != 1:
                    raise ValueError(f"{fid}: explicitly resolve the uncertain source font")
                font_id = candidates[0]
            original = fonts[font_id]["pdf_name"]
            choice = mapping.get("fonts", {}).get(_base_name(original))
            if choice is not None and (
                choice.get("kind") not in {"original", "replacement"}
                or not choice.get("scribus_name")
                or not choice.get("reason")
            ):
                raise ValueError(f"{original}: require kind, scribus_name and reason")
            if value:
                runs.append(
                    {
                        "start": offset + start,
                        "length": len(value),
                        "font_id": font_id,
                        "pdf_font": original,
                        "choice": choice,
                        "size": fragment["source"]["size"],
                        "color": fragment["source"].get("color", 0),
                    }
                )
    if any(ord(char) > 0xFFFF for char in text):
        raise ValueError("First Scribus prototype supports BMP text only (selection offsets)")
    selected_lines = [lines[key] for key in block["line_ids"]]
    if not all(line["horizontal"] for line in selected_lines):
        raise ValueError(f"{block['id']}: rotated/vertical text is not supported yet")
    steps = [
        b["baseline"] - a["baseline"]
        for a, b in zip(selected_lines, selected_lines[1:], strict=False)
    ]
    return {
        "id": block["id"],
        "bbox": block["bbox"],
        "text": text,
        "runs": runs,
        "fragment_ids": block["fragment_ids"],
        "line_spacing": median(steps) if steps else selected_lines[0]["size"] * 1.2,
        "first_indent": block["layout"]["first_line_indent"],
    }


def prepare_scribus(source, layout, groups, mapping_file, destination):
    """Export supported evidence into assets and a plan bound to source/group hashes."""
    import pymupdf

    source, layout, groups, destination = map(Path, (source, layout, groups, destination))
    if destination.exists():
        raise FileExistsError(destination)
    manifest, grouped = _load(layout, "manifest.json"), _load(groups, "manifest.json")
    mapping = json.loads(Path(mapping_file).read_text(encoding="utf-8"))
    if mapping.get("schema_version") != 1 or (
        mapping.get("extraction_sha256") is not None
        and mapping["extraction_sha256"] != _hash(layout / "manifest.json")
    ):
        raise ValueError("Font mapping does not match extraction")
    if grouped["extraction_sha256"] != _hash(layout / "manifest.json"):
        raise ValueError("Groups do not match extraction")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["source"]["sha256"]:
        raise ValueError("Source PDF does not match extraction")
    group_files = {p["pdf_page"]: p["file"] for p in grouped["pages"]}
    fonts = {font["id"]: font for font in manifest["fonts"]}
    pages, issues = [], []
    with (
        pymupdf.open(stream=data, filetype="pdf") as pdf,
        TemporaryDirectory(prefix=".scribus-plan-", dir=destination.parent) as temporary,
    ):
        root = Path(temporary) / "export"
        (root / "assets").mkdir(parents=True)
        for ref in manifest["pages"]:
            page = _load(layout, ref["file"])
            group = _load(groups, group_files[ref["pdf_page"]])
            if (
                group["page_sha256"] != _hash(layout / ref["file"])
                or page["pdf_page"] != ref["pdf_page"]
                or group["pdf_page"] != ref["pdf_page"]
            ):
                raise ValueError("Stale or mismatched page/group evidence")
            if page["rotation"]:
                raise ValueError("First Scribus prototype requires unrotated pages")
            number = page["pdf_page"]
            objects = {obj["id"]: obj for obj in page["objects"]}
            lines = {line["id"]: line for line in group["lines"]}
            all_ids = [fid for block in group["blocks"] for fid in block["fragment_ids"]]
            expected = {obj["id"] for obj in page["objects"] if obj["kind"] == "text_fragment"}
            if len(all_ids) != len(set(all_ids)) or set(all_ids) != expected:
                raise ValueError("Groups must cover every text fragment exactly once")
            graphics, texts = [], []
            for block in group["blocks"]:
                if block["kind"] == "list_marker":
                    name = f"assets/{block['id']}.png"
                    if "/" in block["id"] or "\\" in block["id"]:
                        raise ValueError("Invalid block ID")
                    pdf[number - 1].get_pixmap(
                        clip=pymupdf.Rect(block["bbox"]), matrix=pymupdf.Matrix(4, 4), alpha=True
                    ).save(root / name)
                    graphics.append(
                        {"kind": "image", "file": name, "bbox": block["bbox"], "id": block["id"]}
                    )
                    issues.append(
                        f"Page {number}, {block['id']}: symbol retained as a raster crop; "
                        "inspect for adjacent content."
                    )
                else:
                    texts.append(_text_frame(block, lines, objects, fonts, mapping))
            for index, obj in enumerate(page["objects"]):
                if obj["kind"] == "image":
                    name = f"assets/page-{number}-image-{index}.png"
                    (root / name).write_bytes(image_png(layout, obj))
                    graphics.append(
                        {
                            "kind": "image",
                            "file": name,
                            "bbox": obj["source"]["bbox"],
                            "id": obj["id"],
                        }
                    )
            clips = {}
            for index, path in enumerate(_load(layout, page["graphics_file"])["paths"]):
                level = path.get("level", 0)
                clips = {key: clip for key, clip in clips.items() if key < level}
                if path["type"] == "clip":
                    clips[level] = path
                    continue
                if path["type"] not in {"f", "s", "fs"} or path.get("dashes", "[] 0") != "[] 0":
                    issues.append(
                        f"Page {number}, vector {index}: unsupported group or dashed path skipped."
                    )
                    continue
                box = list(path["rect"])
                padding = max(path.get("width", 0) / 2, 0.01)
                box = [box[0] - padding, box[1] - padding, box[2] + padding, box[3] + padding]
                name = f"assets/page-{number}-vector-{index}.svg"
                try:
                    content = vector_svg(path, list(clips.values()), box)
                except ValueError as error:
                    issues.append(f"Page {number}, vector {index}: {error}")
                    continue
                (root / name).write_bytes(content)
                graphics.append(
                    {"kind": "vector", "file": name, "bbox": box, "id": f"vector-{number}-{index}"}
                )
            pages.append(
                {
                    "pdf_page": number,
                    "size": page["display_rect"][2:],
                    "graphics": graphics,
                    "texts": texts,
                }
            )
        if not pages or any(page["size"] != pages[0]["size"] for page in pages):
            raise ValueError("First Scribus prototype requires equal-sized selected pages")
        issues.append(
            "Graphics are placed below editable text; cross-type paint order, annotations "
            "and complex transparency require visual review."
        )
        plan = {
            "schema_version": 1,
            "kind": "scribus_layout_plan",
            "source": manifest["source"],
            "extraction_sha256": _hash(layout / "manifest.json"),
            "groups_sha256": _hash(groups / "manifest.json"),
            "mapping": mapping,
            "pages": pages,
            "issues": issues,
            "assets": {
                str(p.relative_to(root)).replace("\\", "/"): _hash(p)
                for p in (root / "assets").iterdir()
            },
        }
        _json(root / "plan.json", plan)
        (root / "preparation.md").write_text(
            "# Scribus preparation\n\n" + "\n".join(f"- {item}" for item in issues) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if destination.exists():
            raise FileExistsError(destination)
        root.rename(destination)
    return destination / "plan.json"
