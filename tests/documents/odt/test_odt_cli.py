"""ODT CLI behavior with generated packages and no model loading."""

import json
from zipfile import ZipFile

import pytest

from doc_lingo.interfaces import cli
from doc_lingo.translation.alignment import AlignmentResult, TextRange


@pytest.fixture
def fake_backend(monkeypatch):
    class Backend:
        def translate(self, text, **kwargs):
            return text.replace("Example", "Beispiel")

    monkeypatch.setattr(cli, "MarianBackend", Backend)
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)


@pytest.mark.parametrize("aligned", [False, True])
def test_subset_outputs_skipped_diagnostics(
    odt_factory, fake_backend, monkeypatch, capsys, aligned
):
    source = odt_factory()
    destination = source.with_name("sample.de.odt")
    arguments = [str(source), "--target-lang", "de"]
    if aligned:

        class Aligner:
            def align(self, source, target):
                return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))

        monkeypatch.setattr(cli.AwesomeAlignAdapter, "load", lambda path: Aligner())
        arguments += ["--aligner", "awesome", "--alignment-model", "fake-checkpoint"]
    with pytest.raises(SystemExit) as error:
        cli.main(arguments)
    assert error.value.code == 3
    with ZipFile(source) as original, ZipFile(destination) as translated:
        assert b"Beispiel" in translated.read("content.xml")
        assert b"Cell one" in translated.read("content.xml")
        assert original.read("Pictures/pixel.png") == translated.read("Pictures/pixel.png")
    issues = [
        json.loads(line)
        for line in destination.with_name(destination.name + ".issues.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    skipped = [issue for issue in issues if issue["action"] == "skipped_content"]
    assert [issue["segment_id"] for issue in skipped] == ["5", "6"]
    assert all(issue["page"] is None for issue in skipped)
    captured = capsys.readouterr()
    assert "Partially translated document" in captured.out
    assert "2 unsupported text blocks skipped" in captured.err
    assert "Segments translated:" in captured.err
    if aligned:
        assert "Alignment path statistics" in captured.err


def test_fully_supported_odt_exits_successfully(odt_factory, fake_backend, tmp_path):
    xml = b"""<o:document-content xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
      xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
      <o:body><o:text><t:p>Example</t:p><t:p/></o:text></o:body></o:document-content>"""
    source = odt_factory(updates={"content.xml": xml})
    destination = tmp_path / "custom.odt"
    cli.main([str(source), "--target-lang", "de", "--output", str(destination)])
    assert destination.exists()
    assert not destination.with_name(destination.name + ".issues.jsonl").exists()


def test_invalid_package_rejected_before_models(tmp_path, monkeypatch, capsys):
    source = tmp_path / "bad.odt"
    source.write_bytes(b"not a zip")
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)
    monkeypatch.setattr(cli, "MarianBackend", lambda: pytest.fail("must not load"))
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--target-lang", "de"])
    assert error.value.code == 1
    assert "Invalid or unsupported ODT" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == [source]


def test_existing_destination_untouched(odt_factory, monkeypatch, tmp_path):
    source = odt_factory()
    destination = tmp_path / "existing.odt"
    destination.write_bytes(b"keep")
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)
    monkeypatch.setattr(cli, "MarianBackend", lambda: pytest.fail("must not load"))
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--target-lang", "de", "--output", str(destination)])
    assert error.value.code == 1
    assert destination.read_bytes() == b"keep"
    assert not destination.with_name(destination.name + ".issues.jsonl").exists()


def test_peripheral_and_unknown_inline_text_are_reported(odt_factory):
    from doc_lingo.documents.odt.diagnostics import skipped_text_issues

    office = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    text = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    content = f'''<o:document-content xmlns:o="{office}" xmlns:t="{text}">
      <o:body><o:text><t:p>Hello <t:unknown>world</t:unknown></t:p>
      <t:p><t:unknown/></t:p></o:text></o:body></o:document-content>'''.encode()
    styles = f'''<o:document-styles xmlns:o="{office}" xmlns:t="{text}">
      <o:master-styles><t:p>Header</t:p><t:p/></o:master-styles></o:document-styles>'''.encode()
    source = odt_factory(updates={"content.xml": content, "styles.xml": styles})
    issues = skipped_text_issues(source)
    assert [(issue.segment_id, issue.original) for issue in issues] == [
        ("1", "Hello world"),
        ("styles.xml:1", "Header"),
    ]
    assert issues[1].diagnostics is not None
    assert issues[1].diagnostics.stage == "odt_inventory"


def test_odt_output_extension_rejected_before_processing(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "MarianBackend", lambda: pytest.fail("must not load"))
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                str(tmp_path / "source.odt"),
                "--target-lang",
                "de",
                "--output",
                str(tmp_path / "output.txt"),
            ]
        )
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


def test_existing_odt_issue_report_is_never_overwritten(odt_factory, tmp_path, monkeypatch):
    source = odt_factory()
    report = tmp_path / "sample.de.odt.issues.jsonl"
    report.write_bytes(b"keep previous diagnostics\n")
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)
    monkeypatch.setattr(cli, "MarianBackend", lambda: pytest.fail("must not load"))
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--target-lang", "de"])
    assert error.value.code == 1
    assert report.read_bytes() == b"keep previous diagnostics\n"
    assert not (tmp_path / "sample.de.odt").exists()
