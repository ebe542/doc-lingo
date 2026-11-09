"""Run inside Scribus (Python 3.8 compatible) to create an editable SLA from a plan."""

import hashlib
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile


def _base(name):
    return re.sub(r"^[A-Z]{6}\+", "", name).casefold()


def _asset(root, name, hashes):
    path = (root / name).resolve()
    if root.resolve() not in path.parents or name not in hashes:
        raise ValueError("Asset outside plan or absent from manifest")
    if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
        raise ValueError(f"Changed asset: {name}")
    return path


def _resolve_fonts(scribus, plan):
    available = set(scribus.getFontNames())
    metadata = {row[0]: row for row in scribus.getXFontNames() if row[0] in available}
    resolved, log = {}, []
    for page in plan["pages"]:
        for frame in page["texts"]:
            for run in frame["runs"]:
                choice = run["choice"]
                if choice:
                    name = choice["scribus_name"]
                    if name not in available:
                        raise ValueError(f"Font unavailable in Scribus: {name}")
                    if choice["kind"] == "original" and (
                        name not in metadata or _base(metadata[name][2]) != _base(run["pdf_font"])
                    ):
                        raise ValueError(f"Original font name mismatch: {name}")
                else:
                    matches = [
                        name
                        for name, row in metadata.items()
                        if _base(row[2]) == _base(run["pdf_font"])
                    ]
                    if len(matches) != 1:
                        raise ValueError(f"Choose a Scribus font explicitly for {run['pdf_font']}")
                    name = matches[0]
                resolved[(page["pdf_page"], frame["id"], run["start"])] = name
                entry = {
                    "page": page["pdf_page"],
                    "block": frame["id"],
                    "original": run["pdf_font"],
                    "scribus_name": name,
                    "kind": choice["kind"] if choice else "original",
                    "reason": choice["reason"] if choice else "Unique available PostScript name",
                }
                if entry not in log:
                    log.append(entry)
    return resolved, log


def import_plan(scribus, plan_file):
    """Preflight fonts/assets, then create a new document; preserve existing documents."""
    plan_file = Path(plan_file)
    root = plan_file.parent
    output = root / "layout.sla"
    report = root / "export-report.json"
    readable = root / "export-report.md"
    if any(path.exists() for path in (output, report, readable)):
        raise FileExistsError("Export outputs already exist; use a fresh preparation directory")
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    if (
        plan.get("schema_version") != 1
        or plan.get("kind") != "scribus_layout_plan"
        or not plan.get("pages")
    ):
        raise ValueError("Unsupported or empty Scribus plan")
    resolved, font_log = _resolve_fonts(scribus, plan)
    assets = {}
    for page in plan["pages"]:
        for graphic in page["graphics"]:
            assets[graphic["file"]] = _asset(root, graphic["file"], plan["assets"])
    width, height = plan["pages"][0]["size"]
    if not scribus.newDocument(
        (width, height),
        (0, 0, 0, 0),
        scribus.PORTRAIT if height >= width else scribus.LANDSCAPE,
        1,
        scribus.UNIT_POINTS,
        scribus.PAGE_1,
        0,
        len(plan["pages"]),
    ):
        raise RuntimeError("Scribus could not create a document")
    issues = list(plan["issues"])
    for layer in ("Images", "Vectors", "Text"):
        scribus.createLayer(layer)
        scribus.setLayerLocked(layer, False)
    overflow_count = 0
    for index, page in enumerate(plan["pages"], 1):
        scribus.gotoPage(index)
        for graphic in page["graphics"]:
            x0, y0, x1, y1 = graphic["bbox"]
            path = str(assets[graphic["file"]])
            if graphic["kind"] == "vector":
                scribus.setActiveLayer("Vectors")
                vx, vy = graphic.get("placement_origin", [x0, y0])
                scribus.placeSVG(path, vx, vy)
            else:
                scribus.setActiveLayer("Images")
                name = scribus.createImage(x0, y0, x1 - x0, y1 - y0, graphic["id"])
                scribus.loadImage(path, name)
                scribus.setScaleImageToFrame(True, False, name)
        scribus.setActiveLayer("Text")
        for frame in page["texts"]:
            x0, y0, x1, y1 = frame["bbox"]
            name = scribus.createText(x0, y0, x1 - x0, y1 - y0, frame["id"])
            scribus.setText(frame["text"], name)
            scribus.setTextDistances(0, 0, 0, 0, name)
            scribus.setFirstLineOffset(scribus.FLOP_REALGLYPHHEIGHT, name)
            style = "dl-" + frame["id"]
            scribus.createParagraphStyle(
                name=style,
                linespacingmode=0,
                linespacing=frame["line_spacing"],
                firstindent=frame["first_indent"],
                gapbefore=0,
                gapafter=0,
                alignment=0,
            )
            scribus.setParagraphStyle(style, name)
            if frame["runs"]:
                first = frame["runs"][0]
                scribus.setFont(resolved[(page["pdf_page"], frame["id"], first["start"])], name)
                scribus.setFontSize(first["size"], name)
            for run in frame["runs"]:
                scribus.selectText(run["start"], run["length"], name)
                scribus.setFont(resolved[(page["pdf_page"], frame["id"], run["start"])], name)
                scribus.setFontSize(run["size"], name)
                color = run["color"]
                color_name = "dl-color-" + str(color)
                scribus.defineColorRGB(
                    color_name, (color >> 16) & 255, (color >> 8) & 255, color & 255
                )
                scribus.setTextColor(color_name, name)
            scribus.selectText(0, 0, name)
            if scribus.textOverflows(name):
                overflow_count += 1
                issues.append(
                    f"Page {page['pdf_page']}, {frame['id']}: text overflow; "
                    "adjust frame or typography."
                )
    # Scribus remains open for manual inspection even if publication fails.
    temporary = None
    try:
        with NamedTemporaryFile(dir=root, suffix=".sla", delete=False) as stream:
            temporary = Path(stream.name)
        scribus.saveDocAs(str(temporary))
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink()
    data = {
        "schema_version": 1,
        "source": plan["source"],
        "font_choices": font_log,
        "issues": issues,
        "manual_review": "pending",
        "summary": {
            "overflow_frames": overflow_count,
            "font_replacements": len(
                {
                    (_base(item["original"]), item["scribus_name"])
                    for item in font_log
                    if item["kind"] == "replacement"
                }
            ),
        },
    }
    with report.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    with readable.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(
            "# Scribus export review\n\nManual review: pending.\n\n"
            + _summary_text(data["summary"])
            + "\n\n## Font choices\n\n"
        )
        for item in font_log:
            stream.write(
                f"- Page {item['page']}, {item['block']}: {item['original']} -> "
                f"{item['scribus_name']} ({item['kind']}); {item['reason']}\n"
            )
        stream.write("\n## Issues\n\n" + "\n".join("- " + issue for issue in issues) + "\n")
    scribus.closeDoc()
    scribus.openDoc(str(output))
    return output


def _summary_text(summary):
    return (
        f"Text frames with overflow: {summary['overflow_frames']}\n"
        f"Distinct font replacements: {summary['font_replacements']}"
    )


def main():
    try:
        import scribus
    except ImportError:
        print("Run inside Scribus: Script > Execute Script")
        return 1
    path = scribus.fileDialog("Choose doc-lingo plan.json", "JSON (*.json)")
    if not path:
        return 0
    try:
        result = import_plan(scribus, path)
        report = result.parent / "export-report.md"
        data = json.loads((result.parent / "export-report.json").read_text(encoding="utf-8"))
    except Exception as error:
        scribus.messageBox("Layout export failed", str(error))
        return 1
    scribus.messageBox(
        "Layout export complete - review required",
        str(result)
        + "\n\n"
        + _summary_text(data["summary"])
        + "\n\nReport: "
        + str(report)
        + "\nManual review remains required, even when no overflow is detected.",
    )
    return 0


if __name__ == "__main__":
    main()
