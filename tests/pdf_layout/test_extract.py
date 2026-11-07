"""Synthetic PDFs exercise extraction without books, models or font downloads."""

import hashlib
import json

import pymupdf
import pytest

from doc_lingo.pdf_layout import extract_layout
from doc_lingo.pdf_layout.extract import _asset, _fonts, _match_font
from doc_lingo.pdf_layout.preview import _rectangle, create_preview
from scripts.extract_pdf_layout import main
from scripts.preview_pdf_layout import main as preview_main


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=400)
        page.insert_text((30, 50), "Hello world", fontsize=12)
        page.insert_text((30, 70), "Second line", fontsize=12)
        page.draw_rect((20, 20, 250, 100), color=(1, 0, 0))
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 2, 2), False)
        pixmap.clear_with(128)
        image = pixmap.tobytes("png")
        page.insert_image((30, 150, 50, 170), stream=image)
        page.insert_image((80, 150, 100, 170), stream=image)
        page = document.new_page(width=300, height=400)
        page.insert_text((30, 50), "Rotated")
        page.set_rotation(90)
        document.new_page(width=300, height=400)
        document.save(path)
    return path


def test_text_images_paths_fonts_and_provenance(source, tmp_path):
    output = tmp_path / "book"
    manifest_path = extract_layout(source, output)
    manifest = read_json(manifest_path)
    assert manifest["schema_version"] == 1
    assert manifest["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["source"]["page_count"] == 3
    page = read_json(output / manifest["pages"][0]["file"])
    fragments = [obj for obj in page["objects"] if obj["kind"] == "text_fragment"]
    assert [obj["text"] for obj in fragments] == ["Hello world", "Second line"]
    assert fragments[0]["source"]["origin"] == [30.0, 50.0]
    assert fragments[0]["source"]["size"] == 12
    assert fragments[0]["source"]["chars"][0]["c"] == "H"
    assert fragments[0]["font_id"] in {font["id"] for font in manifest["fonts"]}
    assert all(font["replacement"] is None for font in manifest["fonts"])
    assert all(font["system_availability"] == "not_checked" for font in manifest["fonts"])
    images = [obj for obj in page["objects"] if obj["kind"] == "image"]
    assert len(images) == 2
    assert images[0]["file"] == images[1]["file"]
    assert (output / images[0]["file"]).is_file()
    assert "image" not in images[0]["source"]
    assert read_json(output / page["graphics_file"])["paths"]
    assert page["paint_log"]
    assert not list((output / "fonts").iterdir())
    rotated = read_json(output / manifest["pages"][1]["file"])
    assert rotated["rotation"] == 90
    assert rotated["display_rect"] == [0, 0, 400, 300]
    blank = read_json(output / manifest["pages"][2]["file"])
    assert blank["objects"] == []
    assert not list(tmp_path.glob(".pdf-layout-*"))
    assert b"\r\n" not in manifest_path.read_bytes()


def test_selection_and_deterministic_ids(source, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    extract_layout(source, first, pages=(2, 1))
    extract_layout(source, second, pages=(1,))
    assert read_json(first / "manifest.json")["pages"][0]["pdf_page"] == 2
    assert (first / "pages/page-0001.json").read_bytes() == (
        second / "pages/page-0001.json"
    ).read_bytes()


@pytest.mark.parametrize("pages", [(), (0,), (4,), (1, 1), (True,), (1.5,)])
def test_invalid_selection_does_not_publish(source, tmp_path, pages):
    output = tmp_path / "book"
    with pytest.raises(ValueError, match="1-based"):
        extract_layout(source, output, pages=pages)
    assert not output.exists()


def test_existing_output_is_untouched(source, tmp_path):
    output = tmp_path / "book"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        extract_layout(source, output)
    assert marker.read_text(encoding="utf-8") == "keep"
    assert list(output.iterdir()) == [marker]


def test_failure_cleans_staging(source, tmp_path, monkeypatch):
    def fail(*args):
        raise ValueError("broken page")

    monkeypatch.setattr("doc_lingo.pdf_layout.extract._page", fail)
    with pytest.raises(ValueError, match="broken page"):
        extract_layout(source, tmp_path / "book")
    assert not (tmp_path / "book").exists()
    assert not list(tmp_path.glob(".pdf-layout-*"))


def test_password_protected_pdf_is_rejected(tmp_path):
    source = tmp_path / "locked.pdf"
    with pymupdf.open() as document:
        document.new_page()
        document.save(
            source, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader"
        )
    with pytest.raises(ValueError, match="unencrypted"):
        extract_layout(source, tmp_path / "book")
    assert not (tmp_path / "book").exists()


def test_embedded_font_export_is_explicit(tmp_path):
    class Page:
        def get_fonts(self, full):
            return [(12, "ttf", "TrueType", "ABCDEF+Example", "F1", "", 0)]

    class Document:
        def extract_font(self, xref):
            assert xref == 12
            return "Example", "ttf", "TrueType", b"synthetic-font-evidence"

    (tmp_path / "fonts").mkdir()
    inventory = {}
    _fonts(Document(), Page(), tmp_path, inventory, False)
    assert inventory["font-12"]["file"] is None
    inventory = {}
    _fonts(Document(), Page(), tmp_path, inventory, True)
    font = inventory["font-12"]
    assert font["subset_prefix"] == "ABCDEF"
    assert font["base_name"] == "Example"
    assert font["export_status"] == "exported"
    assert (tmp_path / font["file"]).read_bytes() == b"synthetic-font-evidence"


def test_asset_names_do_not_use_document_paths(tmp_path):
    (tmp_path / "fonts").mkdir()
    asset = _asset(tmp_path, "fonts", b"data", "../../outside")
    assert asset.endswith(".bin")
    assert (tmp_path / asset).parent == tmp_path / "fonts"


def test_cli_completion_and_failure(source, tmp_path, capsys):
    output = tmp_path / "book"
    args = [str(source), "--output", str(output), "--pages", "1"]
    assert main(args) == 0
    assert "extraction complete:" in capsys.readouterr().out
    assert main(args) == 1
    assert "extraction failed:" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("name", "names", "expected_id", "expected_candidates", "status"),
    [
        ("ABCDEF+Example", ["Example"], "f0", ["f0"], "name_unique"),
        ("Example", ["Example", "Example"], None, ["f0", "f1"], "unresolved"),
        (
            "NewBaskerville-BoldItali",
            ["NewBaskerville-BoldItalic"],
            None,
            ["f0"],
            "name_prefix_candidate",
        ),
        (
            "HumanistMann521-BoldCond",
            ["HumanistMann521-BoldCondensed", "Other"],
            None,
            ["f0"],
            "name_prefix_candidate",
        ),
        (
            "NewBaskerville-Bold",
            ["NewBaskerville-BoldItalic", "NewBaskerville-BoldCondensed"],
            None,
            ["f0", "f1"],
            "unresolved",
        ),
        ("Arial", ["Arial-Bold"], None, [], "unresolved"),
        (
            "NewBaskerville-Bold",
            ["NewBaskerville-Bold", "NewBaskerville-BoldItalic"],
            "f0",
            ["f0"],
            "name_unique",
        ),
    ],
)
def test_font_candidates_never_silently_resolve_truncated_names(
    name, names, expected_id, expected_candidates, status
):
    inventory = {f"f{i}": {"base_name": value} for i, value in enumerate(names)}
    assert _match_font(name, set(inventory), inventory) == (
        expected_id,
        expected_candidates,
        status,
    )


def test_preview_uses_original_and_preserves_extraction(source, tmp_path):
    layout, output = tmp_path / "layout", tmp_path / "preview"
    extract_layout(source, layout)
    before = {p.relative_to(layout): p.read_bytes() for p in layout.rglob("*") if p.is_file()}
    html = create_preview(source, layout, output).read_text(encoding="utf-8")
    assert "not reconstructed from JSON" in html
    assert "Hello world" in html
    assert 'class="image"' in html
    assert 'class="vector"' in html
    assert 'viewBox="0 0 400.0 300.0"' in html
    assert len(list(output.glob("*.png"))) == 3
    assert before == {
        p.relative_to(layout): p.read_bytes() for p in layout.rglob("*") if p.is_file()
    }
    with pytest.raises(FileExistsError):
        create_preview(source, layout, output)
    assert not list(tmp_path.glob(".pdf-preview-*"))


def test_preview_escapes_text_and_handles_rotation():
    rect = _rectangle(
        [30, 50, 50, 70], pymupdf.Matrix(0, 1, -1, 0, 400, 0), "text", '<script> & "example"'
    )
    assert 'x="330.0" y="30.0"' in rect
    assert "<script>" not in rect
    assert "&lt;script&gt; &amp; &quot;example&quot;" in rect


def test_preview_rejects_changed_source(source, tmp_path):
    layout, output = tmp_path / "layout", tmp_path / "preview"
    extract_layout(source, layout)
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256"):
        create_preview(source, layout, output)
    assert not output.exists()


@pytest.mark.parametrize("change", ["schema", "path", "page"])
def test_preview_rejects_invalid_manifest(source, tmp_path, change):
    layout, output = tmp_path / "layout", tmp_path / "preview"
    extract_layout(source, layout)
    path = layout / "manifest.json"
    manifest = read_json(path)
    if change == "schema":
        manifest["schema_version"] = 999
    elif change == "path":
        manifest["pages"][0]["file"] = "../outside.json"
    else:
        manifest["pages"][0]["pdf_page"] = 2
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        create_preview(source, layout, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".pdf-preview-*"))


def test_preview_cli(source, tmp_path, capsys):
    layout, output = tmp_path / "layout", tmp_path / "preview"
    extract_layout(source, layout, pages=(1,))
    args = [str(source), "--layout", str(layout), "--output", str(output)]
    assert preview_main(args) == 0
    assert "PDF preview complete:" in capsys.readouterr().out
    assert preview_main(args) == 1
    assert "PDF preview failed:" in capsys.readouterr().err
