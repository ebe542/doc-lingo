"""Test catalog persistence with the Scribus API represented by a fake."""

import json
import sys
from types import SimpleNamespace

import pytest

from scripts.scribus_font_catalog import export_catalog, main


def api(rows=None):
    return SimpleNamespace(
        scribus_version="1.6.7",
        getFontNames=lambda: ["Example Regular", "Metadata absent"],
        getXFontNames=lambda: (
            rows
            if rows is not None
            else [
                ("Example Regular", "Example", "ExamplePS", 1, 0, "fonts/example.ttf"),
                ("Disabled", "Other", "OtherPS", 0, 0, "fonts/other.ttf"),
            ]
        ),
    )


def test_catalog_preserves_scribus_names_and_separates_export_settings(tmp_path):
    output = tmp_path / "catalog.json"
    assert export_catalog(api(), output) == 2
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["kind"] == "scribus_font_catalog"
    assert data["scribus_version"] == "1.6.7"
    first, second = data["fonts"]
    assert first["scribus_name"] == "Example Regular"
    assert first["postscript_name"] == "ExamplePS"
    assert first["scribus_subset_setting"] is True
    assert second["file"] is None
    assert b"\r\n" not in output.read_bytes()
    assert list(tmp_path.iterdir()) == [output]
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        export_catalog(api(), output)
    assert output.read_bytes() == before


def test_invalid_metadata_is_not_published(tmp_path):
    with pytest.raises(ValueError, match="metadata"):
        export_catalog(api([("invalid",)]), tmp_path / "catalog.json")
    assert list(tmp_path.iterdir()) == []


def test_failed_publication_cleans_temporary_file(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("publication failed")

    monkeypatch.setattr("scripts.scribus_font_catalog.os.link", fail)
    with pytest.raises(OSError, match="publication"):
        export_catalog(api(), tmp_path / "catalog.json")
    assert list(tmp_path.iterdir()) == []


def test_scribus_dialog_success_cancel_and_error(tmp_path, monkeypatch):
    scribus = api()
    messages = []
    scribus.messageBox = lambda *args: messages.append(args)
    scribus.fileDialog = lambda *args, **kwargs: str(tmp_path / "catalog.json")
    monkeypatch.setitem(sys.modules, "scribus", scribus)
    assert main() == 0
    assert messages[-1][0] == "Font catalog complete"
    assert main() == 1
    assert messages[-1][0] == "Font catalog failed"
    scribus.fileDialog = lambda *args, **kwargs: ""
    assert main() == 0
