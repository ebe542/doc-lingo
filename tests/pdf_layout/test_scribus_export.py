"""Real synthetic evidence preparation; Scribus calls checked with an API fake."""

import json
import sys
from pathlib import Path

import pymupdf
import pytest

from doc_lingo.pdf_layout import extract_layout
from doc_lingo.pdf_layout.grouping import group_layout
from doc_lingo.pdf_layout.scribus_graphics import _path, vector_svg
from doc_lingo.pdf_layout.scribus_plan import _text_frame, prepare_scribus
from scripts.import_scribus_layout import import_plan
from scripts.import_scribus_layout import main as import_main
from scripts.prepare_scribus_layout import main


@pytest.fixture
def inputs(tmp_path):
    source, layout, groups = tmp_path / "input.pdf", tmp_path / "layout", tmp_path / "groups"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=300, height=400)
        page.insert_text((30, 50), "Hello", fontname="helv", fontsize=12)
        page.insert_text((61, 50), " world", fontname="hebo", fontsize=12)
        page.draw_rect((20, 100, 80, 130), color=(1, 0, 0), fill=(0, 1, 0))
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 2), False)
        pix.clear_with(100)
        page.insert_image((30, 160, 90, 190), stream=pix.tobytes("png"))
        pdf.save(source)
    extract_layout(source, layout)
    group_layout(layout, groups)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fonts": {
                    "Helvetica": {
                        "scribus_name": "Example Regular",
                        "kind": "replacement",
                        "reason": "Test",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return source, layout, groups, mapping


class Scribus:
    PORTRAIT, LANDSCAPE, UNIT_POINTS, PAGE_1, FLOP_REALGLYPHHEIGHT = 0, 1, 0, 0, 0

    def __init__(self):
        self.calls = []

    def getFontNames(self):
        return ["Example Regular", "Helvetica Bold"]

    def getXFontNames(self):
        return [
            ("Example Regular", "Example", "Example", 0, 0, "example.ttf"),
            ("Helvetica Bold", "Helvetica", "Helvetica-Bold", 0, 0, "bold.ttf"),
        ]

    def newDocument(self, *args):
        self.calls.append(("newDocument", args))
        return True

    def createText(self, *args):
        self.calls.append(("createText", args))
        return args[-1]

    createImage = createText

    def textOverflows(self, name):
        return True

    def saveDocAs(self, path):
        Path(path).write_text("fake SLA; real Scribus requires manual review", encoding="utf-8")

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name, args))


def test_prepare_and_import_records_fonts_assets_and_overflows(inputs, tmp_path):
    destination = tmp_path / "out"
    source, layout, groups, mapping = inputs
    before = {str(p): p.read_bytes() for p in layout.rglob("*") if p.is_file()}
    plan_path = prepare_scribus(source, layout, groups, mapping, destination)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["pages"][0]["texts"]
    assert {g["kind"] for g in plan["pages"][0]["graphics"]} == {"image", "vector"}
    assert all((destination / asset).exists() for asset in plan["assets"])
    scribus = Scribus()
    output = import_plan(scribus, plan_path)
    assert output.is_file()
    report = json.loads((destination / "export-report.json").read_text(encoding="utf-8"))
    assert any("overflow" in issue for issue in report["issues"])
    assert report["summary"] == {
        "overflow_frames": len(plan["pages"][0]["texts"]),
        "font_replacements": 1,
    }
    assert {entry["kind"] for entry in report["font_choices"]} == {"original", "replacement"}
    assert any(call[0] == "placeSVG" for call in scribus.calls)
    assert any(call[0] == "setFont" for call in scribus.calls)
    assert scribus.calls[-1] == ("openDoc", (str(output),))
    assert before == {str(p): p.read_bytes() for p in layout.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        import_plan(scribus, plan_path)
    with pytest.raises(FileExistsError):
        prepare_scribus(*inputs, destination)
    assert not list(tmp_path.glob(".scribus-plan-*"))


def test_missing_font_fails_before_document_creation(inputs, tmp_path):
    plan = prepare_scribus(*inputs, tmp_path / "out")
    scribus = Scribus()
    scribus.getFontNames = lambda: []
    with pytest.raises(ValueError, match="Font unavailable"):
        import_plan(scribus, plan)
    assert not scribus.calls
    assert not (plan.parent / "layout.sla").exists()


@pytest.mark.parametrize("overflow", [False, True])
def test_completion_shows_overflows_replacements_and_report(
    inputs, tmp_path, monkeypatch, overflow
):
    plan_path = prepare_scribus(*inputs, tmp_path / "out")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    # Repeated use of a replacement in another frame must not inflate the count.
    duplicate = dict(plan["pages"][0]["texts"][0], id="duplicate-frame")
    plan["pages"][0]["texts"].append(duplicate)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    scribus = Scribus()
    scribus.fileDialog = lambda *args: str(plan_path)
    scribus.textOverflows = lambda name: overflow
    monkeypatch.setitem(sys.modules, "scribus", scribus)
    assert import_main() == 0
    title, message = scribus.calls[-1][1]
    expected = len(plan["pages"][0]["texts"]) if overflow else 0
    assert "review required" in title
    assert f"Text frames with overflow: {expected}" in message
    assert "Distinct font replacements: 1" in message
    assert str(plan_path.parent / "export-report.md") in message
    assert "Manual review remains required" in message
    readable = (plan_path.parent / "export-report.md").read_text(encoding="utf-8")
    assert f"Text frames with overflow: {expected}" in readable


def test_changed_asset_fails_before_document_creation(inputs, tmp_path):
    path = prepare_scribus(*inputs, tmp_path / "out")
    plan = json.loads(path.read_text(encoding="utf-8"))
    (path.parent / next(iter(plan["assets"]))).write_bytes(b"changed")
    scribus = Scribus()
    with pytest.raises(ValueError, match="Changed asset"):
        import_plan(scribus, path)
    assert not scribus.calls


@pytest.mark.parametrize("changed", ["source", "page", "mapping", "groups"])
def test_stale_evidence_rejected(inputs, tmp_path, changed):
    source, layout, groups, mapping = inputs
    if changed == "source":
        source.write_bytes(source.read_bytes() + b"\n")
    elif changed == "page":
        page = layout / "pages/page-0001.json"
        page.write_bytes(page.read_bytes() + b"\n")
    elif changed == "mapping":
        mapping.write_text('{"schema_version": 99}', encoding="utf-8")
    else:
        manifest = layout / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        prepare_scribus(*inputs, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_vector_commands_and_clipping():
    items = [
        ["l", [0, 0], [10, 0]],
        ["c", [10, 0], [12, 1], [15, 2], [20, 0]],
        ["re", [2, 2, 4, 4], -1],
        ["qu", [[0, 0], [2, 0], [0, 2], [2, 2]]],
    ]
    assert "C 12 1 15 2 20 0" in _path(items)
    svg = vector_svg(
        {"items": items, "fill": [1, 0, 0]},
        [{"items": [["re", [0, 0, 10, 10], 1]], "even_odd": True}],
        [0, 0, 20, 20],
    )
    assert b"clipPath" in svg and b"evenodd" in svg and b"#ff0000" in svg
    with pytest.raises(ValueError, match="Unsupported"):
        _path([["unknown"]])


def test_uncertain_font_requires_explicit_source_assignment():
    obj = {
        "text": "A",
        "font_id": None,
        "font_candidates": ["f1"],
        "source": {"font": "Short", "size": 10},
    }
    line = {"text": "A", "fragment_ids": ["a"], "size": 10, "horizontal": True}
    block = {
        "id": "b",
        "line_ids": ["line"],
        "fragment_ids": ["a"],
        "bbox": [0, 0, 10, 10],
        "layout": {"first_line_indent": 2},
    }
    fonts = {"f1": {"pdf_name": "ABCDEF+Original"}}
    with pytest.raises(ValueError, match="uncertain"):
        _text_frame(block, {"line": line}, {"a": obj}, fonts, {})
    frame = _text_frame(
        block, {"line": line}, {"a": obj}, fonts, {"fragment_fonts": {"Short": "Original"}}
    )
    assert frame["first_indent"] == 2
    assert frame["runs"][0]["pdf_font"] == "ABCDEF+Original"


def test_prepare_cli(inputs, tmp_path, capsys):
    source, layout, groups, mapping = inputs
    args = [
        str(source),
        "--layout",
        str(layout),
        "--groups",
        str(groups),
        "--font-map",
        str(mapping),
        "--output",
        str(tmp_path / "out"),
    ]
    assert main(args) == 0
    assert "plan complete" in capsys.readouterr().out
    assert main(args) == 1
    assert "preparation failed" in capsys.readouterr().err
