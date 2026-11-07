"""Export inspectable PDF evidence without guessing paragraphs or font substitutions."""

import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory


def _json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _asset(root: Path, folder: str, data: bytes, extension: str) -> str:
    # Never use names supplied by the PDF as filesystem paths.
    if not re.fullmatch(r"[a-zA-Z0-9]+", extension):
        extension = "bin"
    name = f"{folder}/{hashlib.sha256(data).hexdigest()}.{extension}"
    path = root / name
    if not path.exists():
        path.write_bytes(data)
    return name


def _base_name(name: str) -> str:
    return re.sub(r"^[A-Z]{6}\+", "", name)


def _match_font(name, font_ids, inventory):
    """Prefer exact names; expose truncated-name matches as tentative only."""
    name = _base_name(name)
    exact = sorted(fid for fid in font_ids if inventory[fid]["base_name"] == name)
    if exact:
        return (
            exact[0] if len(exact) == 1 else None,
            exact,
            "name_unique" if len(exact) == 1 else "unresolved",
        )
    # Short prefixes such as Arial or Times are insufficient evidence of truncation.
    candidates = sorted(
        fid for fid in font_ids if len(name) >= 16 and inventory[fid]["base_name"].startswith(name)
    )
    # A unique prefix is still not proof: keep font_id unset until verified.
    return None, candidates, "name_prefix_candidate" if len(candidates) == 1 else "unresolved"


def _fonts(document, page, root, inventory, export_fonts):
    references = []
    for xref, extension, kind, name, resource, encoding, referencer in page.get_fonts(full=True):
        identifier = f"font-{xref}"
        if identifier not in inventory:
            asset = None
            status = "not_requested"
            if export_fonts:
                _, extracted_extension, _, data = document.extract_font(xref)
                status = "exported" if data else "unavailable"
                if data:
                    asset = _asset(root, "fonts", data, extracted_extension)
            inventory[identifier] = {
                "id": identifier,
                "xref": xref,
                "pdf_name": name,
                "base_name": _base_name(name),
                "pdf_type": kind,
                "subset_prefix": name[:6] if re.match(r"^[A-Z]{6}\+", name) else None,
                "embedded": extension != "n/a",
                "extension": extension,
                "file": asset,
                "export_status": status,
                "system_availability": "not_checked",
                "replacement": None,
            }
        references.append(
            {
                "font_id": identifier,
                "resource": resource,
                "encoding": encoding,
                "referencer_xref": referencer,
            }
        )
    return references


def _page(document, page, root, inventory, export_fonts):
    identifier = f"page-{page.number + 1:04d}"
    references = _fonts(document, page, root, inventory, export_fonts)
    font_ids = {ref["font_id"] for ref in references}
    raw = page.get_text("rawdict", sort=False)
    objects = []
    for index, block in enumerate(raw["blocks"]):
        object_id = f"{identifier}-object-{index:05d}"
        if block["type"] == 1:
            image = block.pop("image")
            mask = block.pop("mask", None)
            objects.append(
                {
                    "id": object_id,
                    "kind": "image",
                    "source": block,
                    "file": _asset(root, "assets/images", image, block["ext"]),
                    "mask_file": _asset(root, "assets/images", mask, "png") if mask else None,
                }
            )
        elif block["type"] == 0:
            # These are engine groupings, not inferred semantic paragraphs.
            for line_index, line in enumerate(block["lines"]):
                for span_index, span in enumerate(line["spans"]):
                    font_id, candidates, match = _match_font(span["font"], font_ids, inventory)
                    objects.append(
                        {
                            "id": f"{object_id}-line-{line_index:04d}-span-{span_index:04d}",
                            "kind": "text_fragment",
                            "engine_block": block["number"],
                            "engine_line": line_index,
                            "direction": line["dir"],
                            "writing_mode": line["wmode"],
                            "text": "".join(char["c"] for char in span["chars"]),
                            "font_id": font_id,
                            "font_candidates": candidates,
                            "font_match": match,
                            "source": span,
                        }
                    )
        else:
            objects.append({"id": object_id, "kind": "unhandled", "source": block})
    graphics_file = f"assets/graphics/{identifier}.json"
    _json(
        root / graphics_file,
        {
            "schema_version": 1,
            "paths": page.get_cdrawings(extended=True),
        },
    )
    # Rendering order evidence is separate: rawdict order is NOT paint order.
    paint_log = [
        {"seqno": i, "kind": kind, "bbox": bbox}
        for i, (kind, bbox) in enumerate(page.get_bboxlog())
    ]
    return {
        "schema_version": 1,
        "id": identifier,
        "pdf_page": page.number + 1,
        "label": page.get_label(),
        "media_box": list(page.mediabox),
        "crop_box": list(page.cropbox),
        "display_rect": list(page.rect),
        "rotation": page.rotation,
        "pdf_to_mupdf": list(page.transformation_matrix),
        "rotation_matrix": list(page.rotation_matrix),
        "fonts": references,
        "objects": objects,
        "graphics_file": graphics_file,
        "paint_log": paint_log,
        "warnings": [
            "Engine text groupings are not semantic paragraphs.",
            "Font matches use names, not verified glyph-resource identity.",
            "Paint-log entries are not yet linked to text/image objects.",
            "Annotations, widgets, patterns and complex transparency are not reconstructed.",
        ],
    }


def extract_layout(
    source: Path,
    destination: Path,
    *,
    pages: tuple[int, ...] | None = None,
    export_fonts: bool = False,
) -> Path:
    """Export selected 1-based PDF pages to a new directory; return its manifest.

    Embedded font bytes are opt-in. Callers must establish their right to reuse
    these fonts. No fonts are downloaded, installed or silently substituted.
    """
    try:
        import pymupdf
    except ImportError as error:
        raise RuntimeError("PDF extraction requires doc-lingo[pdf]") from error

    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    # One snapshot is both hashed and parsed, including if the source changes later.
    data = source.read_bytes()
    with pymupdf.open(stream=data, filetype="pdf") as document:
        if not document.is_pdf or document.needs_pass:
            raise ValueError("An unencrypted PDF is required")
        selected = tuple(range(1, len(document) + 1)) if pages is None else pages
        if (
            not selected
            or len(set(selected)) != len(selected)
            or any(type(n) is not int or n < 1 or n > len(document) for n in selected)
        ):
            raise ValueError("Pages must be unique 1-based numbers within the PDF")
        # Keep incomplete extraction private and clean it on ordinary failures.
        with TemporaryDirectory(prefix=".pdf-layout-", dir=destination.parent) as temporary:
            root = Path(temporary) / "book"
            for folder in ("pages", "assets/images", "assets/graphics", "fonts"):
                (root / folder).mkdir(parents=True, exist_ok=True)
            fonts = {}
            page_files = []
            for number in selected:
                result = _page(document, document[number - 1], root, fonts, export_fonts)
                page_file = f"pages/{result['id']}.json"
                _json(root / page_file, result)
                page_files.append({"pdf_page": number, "file": page_file})
            _json(
                root / "manifest.json",
                {
                    "schema_version": 1,
                    "status": "experimental_evidence",
                    "source": {
                        "name": source.name,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "page_count": len(document),
                    },
                    "extractor": {"name": "PyMuPDF", "version": pymupdf.VersionBind},
                    "coordinates": {
                        "space": "unrotated MuPDF page space",
                        "origin": "top-left",
                        "x_direction": "right",
                        "y_direction": "down",
                        "unit": "point",
                        "note": "Use recorded page matrices for PDF-space and display conversion.",
                    },
                    "pages": page_files,
                    "fonts": list(fonts.values()),
                    "grouping": "raw_engine_fragments",
                },
            )
            if destination.exists():
                raise FileExistsError(destination)
            root.rename(destination)
    return destination / "manifest.json"
