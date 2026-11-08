"""Local font evidence and explicit selections; never install or substitute fonts."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from .extract import _base_name, _json
from .preview import _load

PROBE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789ÄÖÜäöüßẞ"
EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}


def system_font_dirs():
    """Common font locations, not proof of registration with a layout application."""
    home = Path.home()
    if sys.platform == "win32":
        return [
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
            Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
            / "Microsoft/Windows/Fonts",
        ]
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library/Fonts"]
    return [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".fonts",
        Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "fonts",
    ]


def read_faces(path):
    """Read names and a limited Unicode probe, including collection face indexes."""
    from fontTools.ttLib import TTCollection, TTFont

    path = Path(path).resolve()
    collection = path.suffix.lower() in {".ttc", ".otc"}
    # Own the handle before invoking constructors: malformed fonts can fail
    # before a TTFont/TTCollection instance exists to close it.
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        stream.seek(0)
        owner = TTCollection(stream, lazy=True) if collection else TTFont(stream, lazy=True)
        try:
            faces = owner.fonts if isinstance(owner, TTCollection) else [owner]
            result = []
            for index, font in enumerate(faces):
                names = font["name"]
                cmap = font.getBestCmap()
                result.append(
                    {
                        "file": str(path),
                        "face_index": index,
                        "sha256": digest,
                        "postscript_name": names.getDebugName(6),
                        "family": names.getBestFamilyName(),
                        "style": names.getBestSubFamilyName(),
                        "full_name": names.getDebugName(4),
                        "variable": "fvar" in font,
                        "missing_probe_characters": None
                        if cmap is None
                        else "".join(
                            char
                            for char in PROBE
                            if not cmap.get(ord(char)) or cmap[ord(char)] == ".notdef"
                        ),
                    }
                )
            return result
        finally:
            owner.close()


def scan_fonts(directories):
    """Return faces plus all directory/file errors without hiding incomplete scans."""
    faces, errors, seen = [], [], set()
    for directory in directories:
        directory = Path(directory).expanduser().resolve()
        if not directory.is_dir():
            errors.append({"path": str(directory), "error": "Directory missing or inaccessible"})
            continue

        def walk_error(error):
            errors.append({"path": str(error.filename), "error": str(error)})

        for parent, dirs, files in os.walk(directory, onerror=walk_error):
            dirs.sort()
            for name in sorted(files):
                path = (Path(parent) / name).resolve()
                if path.suffix.lower() not in EXTENSIONS or path in seen:
                    continue
                seen.add(path)
                try:
                    faces.extend(read_faces(path))
                except Exception as error:
                    # A damaged third-party font must not hide the remaining inventory.
                    errors.append({"path": str(path), "error": f"{type(error).__name__}: {error}"})
    return faces, errors


def _same_name(pdf_name, face):
    return _base_name(pdf_name).casefold() == (face["postscript_name"] or "").casefold()


def _name_parts(name):
    """Conservative naming heuristic, not a font identity or metric comparison."""
    compact = re.sub(r"[\s_-]+", "", _base_name(name or "")).casefold()
    traits = {}
    suffixes = (
        ("semibold", "weight", "demi"),
        ("demibold", "weight", "demi"),
        ("condensed", "width", "condensed"),
        ("extended", "width", "extended"),
        ("regular", "weight", "regular"),
        ("oblique", "slant", "italic"),
        ("italic", "slant", "italic"),
        ("normal", "weight", "regular"),
        ("roman", "weight", "regular"),
        ("light", "weight", "light"),
        ("black", "weight", "black"),
        ("heavy", "weight", "heavy"),
        ("bold", "weight", "bold"),
        ("demi", "weight", "demi"),
        ("book", "weight", "book"),
        ("cond", "width", "condensed"),
        ("ital", "slant", "italic"),
    )
    while compact:
        for suffix, dimension, value in suffixes:
            if compact.endswith(suffix):
                traits[dimension] = value
                compact = compact[: -len(suffix)]
                break
        else:
            break
    return compact, (
        traits.get("weight", "regular"),
        traits.get("width", "normal"),
        traits.get("slant", "upright"),
    )


def _related_faces(pdf_name, faces):
    family, style = _name_parts(pdf_name)
    if not family:
        return []
    candidates = []
    for face in faces:
        names = [face.get("postscript_name"), face.get("full_name")]
        if face.get("family"):
            names.append(face["family"] + "-" + (face.get("style") or ""))
        signatures = [_name_parts(name) for name in names if name]
        related = [
            candidate_style
            for candidate_family, candidate_style in signatures
            if candidate_family == family
        ]
        if related:
            same_style = style in related
            candidates.append(
                {
                    "face": face,
                    "reason": "family_and_style_name"
                    if same_style
                    else "family_only_style_differs",
                }
            )
    return sorted(
        candidates,
        key=lambda c: (
            c["reason"] != "family_and_style_name",
            c["face"]["file"],
            c["face"]["face_index"],
        ),
    )


def _selection(mapping_file, digest, known_ids):
    if mapping_file is None:
        return {}
    mapping_file = Path(mapping_file)
    data = json.loads(mapping_file.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("extraction_sha256") != digest:
        raise ValueError("Font mapping does not match the extraction")
    selections = data.get("fonts")
    if not isinstance(selections, dict) or set(selections) - known_ids:
        raise ValueError("Font mapping contains invalid or unknown font IDs")
    result = {}
    for identifier, entry in selections.items():
        if not isinstance(entry, dict) or entry.get("kind") not in {"original", "replacement"}:
            raise ValueError(f"{identifier}: mapping kind must be original or replacement")
        index = entry.get("face_index", 0)
        if type(index) is not int or index < 0 or not isinstance(entry.get("file"), str):
            raise ValueError(f"{identifier}: invalid file or face_index")
        path = Path(entry["file"]).expanduser()
        if not path.is_absolute():
            path = mapping_file.parent / path
        try:
            faces = read_faces(path)
        except Exception as error:
            raise ValueError(f"{identifier}: cannot read selected font: {error}") from error
        if index >= len(faces):
            raise ValueError(f"{identifier}: collection face_index out of range")
        result[identifier] = {"kind": entry["kind"], "face": faces[index]}
    return result


def _cell(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace("|", "&#124;")
        .replace("\n", " ")
    )


def font_report(layout: Path, destination: Path, *, directories=None, mapping=None) -> Path:
    """Write machine-readable evidence, a readable report and an empty mapping template."""
    layout, destination = Path(layout), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    manifest = _load(layout, "manifest.json")
    digest = hashlib.sha256((layout / "manifest.json").read_bytes()).hexdigest()
    selections = _selection(mapping, digest, {f["id"] for f in manifest["fonts"]})
    directories = system_font_dirs() if directories is None else list(directories)
    faces, errors = scan_fonts(directories)
    pages = {f["id"]: set() for f in manifest["fonts"]}
    unresolved = []
    page_hashes = []
    for reference in manifest["pages"]:
        page = _load(layout, reference["file"])
        if page["pdf_page"] != reference["pdf_page"]:
            raise ValueError("Page evidence does not match manifest")
        page_hashes.append(
            {
                "file": reference["file"],
                "sha256": hashlib.sha256((layout / reference["file"]).read_bytes()).hexdigest(),
            }
        )
        for ref in page["fonts"]:
            pages[ref["font_id"]].add(page["pdf_page"])
        for obj in page["objects"]:
            if obj["kind"] == "text_fragment" and obj["font_id"] is None:
                unresolved.append(
                    {
                        "page": page["pdf_page"],
                        "fragment_id": obj["id"],
                        "name": obj["source"]["font"],
                        "candidates": obj["font_candidates"],
                    }
                )
    rows = []
    for font in manifest["fonts"]:
        matches = [face for face in faces if _same_name(font["pdf_name"], face)]
        related = _related_faces(font["pdf_name"], faces) if not matches else []
        chosen = selections.get(font["id"])
        if (
            chosen
            and chosen["kind"] == "original"
            and not _same_name(font["pdf_name"], chosen["face"])
        ):
            raise ValueError(
                f"{font['id']}: different PostScript name; declare replacement explicitly"
            )
        status = (
            "explicit_" + chosen["kind"]
            if chosen
            else "name_match"
            if len(matches) == 1
            else "ambiguous"
            if matches
            else "family_candidates"
            if related
            else "not_found_in_scan"
        )
        rows.append(
            {
                "font_id": font["id"],
                "pdf_name": font["pdf_name"],
                "embedded": font["embedded"],
                "subset_prefix": font["subset_prefix"],
                "pages": sorted(pages[font["id"]]),
                "status": status,
                "candidates": matches,
                "related_candidates": related,
                "selection": chosen,
            }
        )
    report = {
        "schema_version": 1,
        "extraction_sha256": digest,
        "page_hashes": page_hashes,
        "directories": [str(Path(p).expanduser().resolve()) for p in directories],
        "probe": PROBE,
        "faces_scanned": len(faces),
        "scan_errors": errors,
        "fonts": rows,
        "unresolved_fragments": unresolved,
    }
    text = [
        "# PDF font report",
        "",
        "Local file discovery is not proof that Scribus has registered a font. "
        "A PostScript-name match identifies a named face, not identical font metrics or version.",
        "",
        "Page numbers below are PDF resource references, which can include unused fonts. "
        "Missing means not found in the scanned locations, not absent from the computer.",
        "",
        "| PDF font / ID | Pages | Status | Embedded / subset |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        text.append(
            "| "
            + " | ".join(
                _cell(v)
                for v in (
                    row["pdf_name"] + " / " + row["font_id"],
                    ", ".join(map(str, row["pages"])),
                    row["status"],
                    f"{row['embedded']} / {bool(row['subset_prefix'])}",
                )
            )
            + " |"
        )
    for row in rows:
        text += ["", f"## {_cell(row['font_id'])}: {_cell(row['pdf_name'])}", ""]
        listed = [row["selection"]["face"]] if row["selection"] else row["candidates"]
        for face in listed:
            missing = face["missing_probe_characters"]
            coverage = (
                _cell(missing if missing is not None else "unknown Unicode mapping") or "none"
            )
            text.append(
                f"- {_cell(face['family'])} / {_cell(face['style'])}; "
                f"file: {_cell(face['file'])}; face index: {face['face_index']}; "
                f"missing probe characters: {coverage}; "
                f"variable font: {face['variable']}."
            )
        if not listed:
            text.append("No exact PostScript-name match found.")
        if row["related_candidates"]:
            text += ["", "Possible family/style matches — unverified, not selected:", ""]
            for candidate in row["related_candidates"]:
                face = candidate["face"]
                text.append(
                    f"- {_cell(face['family'])} / {_cell(face['style'])}; "
                    f"PostScript: {_cell(face['postscript_name'])}; "
                    f"reason: {candidate['reason']}; file: {_cell(face['file'])}; "
                    f"face index: {face['face_index']}."
                )
    text += [
        "",
        "## Unresolved text-fragment font assignments",
        "",
        f"{len(unresolved)} fragments remain uncertain. "
        "File availability does not resolve PDF identity.",
        "",
    ]
    for item in unresolved:
        text.append(
            f"- Page {item['page']}: {_cell(item['name'])} "
            f"({_cell(item['fragment_id'])}); candidates: {_cell(', '.join(item['candidates']))}."
        )
    text += ["", "## Scan scope and errors", ""]
    text.extend(f"- Directory: {_cell(p)}" for p in report["directories"])
    text.extend(f"- {_cell(e['path'])}: {_cell(e['error'])}" for e in errors)
    text += [
        "",
        "The character probe is limited; it does not prove full German, mathematical or "
        "technical character coverage. Embedded subsets are not assumed to be complete. "
        "No fonts were downloaded, installed or substituted. Raw extraction remains unchanged.",
        "",
    ]
    with TemporaryDirectory(prefix=".pdf-fonts-", dir=destination.parent) as temporary:
        root = Path(temporary) / "report"
        root.mkdir()
        _json(root / "report.json", report)
        _json(
            root / "mapping-template.json",
            {
                "schema_version": 1,
                "extraction_sha256": digest,
                "fonts": {},
            },
        )
        (root / "report.md").write_text("\n".join(text), encoding="utf-8", newline="\n")
        if destination.exists():
            raise FileExistsError(destination)
        root.rename(destination)
    return destination / "report.md"
