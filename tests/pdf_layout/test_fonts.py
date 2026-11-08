"""Synthetic font metadata fixtures; no installed fonts or model downloads."""

import json
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

from doc_lingo.pdf_layout.fonts import (
    _related_faces,
    font_report,
    read_faces,
    scan_fonts,
    system_font_dirs,
)
from scripts.check_pdf_fonts import main


def make_font(path, name="Example-Regular", style="Regular"):
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in [".notdef", "A"]})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "A": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": "Example",
            "styleName": style,
            "psName": name,
            "fullName": f"Example {style}",
        }
    )
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)
    return path


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "layout"
    root.mkdir()
    write_json(
        root / "manifest.json",
        {
            "schema_version": 1,
            "pages": [{"pdf_page": 1, "file": "page.json"}],
            "fonts": [
                {
                    "id": "font-1",
                    "pdf_name": "ABCDEF+Example-Regular",
                    "embedded": True,
                    "subset_prefix": "ABCDEF",
                }
            ],
        },
    )
    write_json(
        root / "page.json",
        {
            "schema_version": 1,
            "pdf_page": 1,
            "fonts": [{"font_id": "font-1"}],
            "objects": [
                {
                    "kind": "text_fragment",
                    "id": "text-1",
                    "font_id": None,
                    "source": {"font": "Example"},
                    "font_candidates": ["font-1"],
                }
            ],
        },
    )
    return root


def test_real_font_names_cmap_and_collection(tmp_path):
    regular = make_font(tmp_path / "unrelated-filename.ttf")
    bold = make_font(tmp_path / "other.ttf", "Example-Bold", "Bold")
    face = read_faces(regular)[0]
    assert face["postscript_name"] == "Example-Regular"
    assert face["family"] == "Example" and face["style"] == "Regular"
    assert "A" not in face["missing_probe_characters"]
    assert "ä" in face["missing_probe_characters"]
    with TTFont(regular) as first, TTFont(bold) as second:
        collection = TTCollection()
        collection.fonts = [first, second]
        collection.save(tmp_path / "collection.ttc")
    faces = read_faces(tmp_path / "collection.ttc")
    assert [(f["face_index"], f["style"]) for f in faces] == [(0, "Regular"), (1, "Bold")]
    assert all(f["sha256"] == faces[0]["sha256"] for f in faces)


@pytest.mark.parametrize("extension", ["otf", "ttf", "ttc", "otc"])
def test_scan_deduplicates_and_reports_bad_files(tmp_path, extension):
    make_font(tmp_path / "one.ttf")
    (tmp_path / f"bad.{extension}").write_bytes(b"not a font")
    (tmp_path / "skip.txt").write_text("skip", encoding="utf-8")
    faces, errors = scan_fonts([tmp_path, tmp_path, tmp_path / "missing"])
    assert len(faces) == 1
    assert len(errors) == 2


def test_report_keeps_source_and_separates_fragment_uncertainty(layout, tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    make_font(fonts / "font.ttf")
    before = {p.name: p.read_bytes() for p in layout.iterdir()}
    output = tmp_path / "report"
    result = font_report(layout, output, directories=[fonts])
    text = result.read_text(encoding="utf-8")
    data = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert data["fonts"][0]["status"] == "name_match"
    assert data["fonts"][0]["selection"] is None
    assert data["fonts"][0]["pages"] == [1]
    assert len(data["unresolved_fragments"]) == 1
    assert "Regular" in text and "not proof" in text
    assert before == {p.name: p.read_bytes() for p in layout.iterdir()}
    with pytest.raises(FileExistsError):
        font_report(layout, output, directories=[])
    assert not list(tmp_path.glob(".pdf-fonts-*"))


def test_not_found_and_duplicate_named_faces(layout, tmp_path):
    font_report(layout, tmp_path / "empty", directories=[])
    assert (
        json.loads((tmp_path / "empty/report.json").read_text())["fonts"][0]["status"]
        == "not_found_in_scan"
    )
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    make_font(fonts / "one.ttf")
    make_font(fonts / "two.ttf")
    font_report(layout, tmp_path / "duplicates", directories=[fonts])
    data = json.loads((tmp_path / "duplicates/report.json").read_text())
    assert data["fonts"][0]["status"] == "ambiguous"


@pytest.mark.parametrize(
    "kind,name,status",
    [
        ("original", "Example-Regular", "explicit_original"),
        ("replacement", "Example-Bold", "explicit_replacement"),
    ],
)
def test_explicit_mapping_relative_paths(layout, tmp_path, kind, name, status):
    font_report(layout, tmp_path / "initial", directories=[])
    mapping = json.loads((tmp_path / "initial/mapping-template.json").read_text())
    make_font(tmp_path / "chosen.ttf", name)
    mapping["fonts"] = {"font-1": {"file": "chosen.ttf", "face_index": 0, "kind": kind}}
    path = tmp_path / "mapping.json"
    write_json(path, mapping)
    font_report(layout, tmp_path / "mapped", directories=[], mapping=path)
    report = json.loads((tmp_path / "mapped/report.json").read_text())
    assert report["fonts"][0]["status"] == status
    assert report["fonts"][0]["selection"]["face"]["file"] == str(
        (tmp_path / "chosen.ttf").resolve()
    )


@pytest.mark.parametrize(
    "case", ["digest", "unknown", "kind", "index", "missing", "mismatch", "range"]
)
def test_invalid_mapping_never_publishes(layout, tmp_path, case):
    font_report(layout, tmp_path / "initial", directories=[])
    data = json.loads((tmp_path / "initial/mapping-template.json").read_text())
    make_font(tmp_path / "chosen.ttf", "Example-Bold")
    entry = {"file": "chosen.ttf", "face_index": 0, "kind": "replacement"}
    data["fonts"] = {"font-1": entry}
    if case == "digest":
        data["extraction_sha256"] = "stale"
    elif case == "unknown":
        data["fonts"] = {"other": entry}
    elif case == "kind":
        entry["kind"] = "automatic"
    elif case == "index":
        entry["face_index"] = True
    elif case == "missing":
        entry["file"] = "absent.ttf"
    elif case == "mismatch":
        entry["kind"] = "original"
    else:
        entry["face_index"] = 9
    mapping = tmp_path / "mapping.json"
    write_json(mapping, data)
    with pytest.raises(ValueError):
        font_report(layout, tmp_path / "out", directories=[], mapping=mapping)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_standard_search_locations(platform, monkeypatch):
    monkeypatch.setattr("doc_lingo.pdf_layout.fonts.sys.platform", platform)
    assert all(isinstance(p, Path) for p in system_font_dirs())
    assert len(system_font_dirs()) >= 2


def test_cli(layout, tmp_path, capsys):
    args = [str(layout), "--output", str(tmp_path / "out"), "--font-dir", str(tmp_path / "absent")]
    assert main(args) == 0
    assert "report complete:" in capsys.readouterr().out
    assert main(args) == 1
    assert "check failed:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "pdf_name,family,style,reason",
    [
        ("ABCDEF+NewBaskerville-Roman", "New Baskerville", "Regular", "family_and_style_name"),
        ("FranklinGothic-DemiItal", "Franklin Gothic", "Demi Italic", "family_and_style_name"),
        ("Wingdings2", "Wingdings 2", "Regular", "family_and_style_name"),
        ("Example-Bold", "Example", "Italic", "family_only_style_differs"),
        ("Example-BoldCondensed-Bold", "Example", "Bold Condensed", "family_and_style_name"),
    ],
)
def test_family_style_candidates_are_explained(pdf_name, family, style, reason):
    face = {
        "family": family,
        "style": style,
        "postscript_name": "DifferentInternalName",
        "full_name": None,
        "file": "font.ttf",
        "face_index": 0,
    }
    assert _related_faces(pdf_name, [face]) == [{"face": face, "reason": reason}]


def test_family_digits_and_style_mismatches_are_not_ignored():
    face = {
        "family": "Wingdings 3",
        "style": "Regular",
        "postscript_name": None,
        "full_name": None,
        "file": "font.ttf",
        "face_index": 0,
    }
    assert _related_faces("Wingdings2", [face]) == []
    assert _related_faces("", [face]) == []


def test_related_match_is_not_automatically_selected(layout, tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    make_font(fonts / "font.ttf", "Example-Roman")
    output = tmp_path / "related"
    font_report(layout, output, directories=[fonts])
    data = json.loads((output / "report.json").read_text(encoding="utf-8"))
    row = data["fonts"][0]
    assert row["status"] == "family_candidates"
    assert row["selection"] is None and row["candidates"] == []
    assert row["related_candidates"][0]["reason"] == "family_and_style_name"
    assert "unverified, not selected" in (output / "report.md").read_text(encoding="utf-8")
