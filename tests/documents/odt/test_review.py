"""Review-script checks using the same synthetic ODT packages as the adapter."""

import json

import pytest

from doc_lingo.translation.protocols import TranslationError
from scripts.evaluate_odt import evaluate_odt, main


class Echo:
    def translate(self, text, **kwargs):
        return text


def test_review_reports_skips_and_member_preservation(odt_factory, tmp_path, capsys):
    source = odt_factory()
    output = tmp_path / "review"
    report = evaluate_odt(source, output, Echo(), None, metadata={"backend": "echo"})
    assert report["complete"]
    assert report["manual_review"] == "pending"
    assert report["processed_segments"] == report["eligible_segments"] == 4
    assert report["source_unchanged"]
    assert "Pictures/pixel.png" in report["unchanged_members"]
    skipped = [row for row in report["blocks"] if row["status"] == "skipped"]
    assert len(skipped) == 3
    assert any(row["source_text"] == "Cell one" for row in skipped)
    assert all(row["page"] is None for row in report["blocks"])
    assert json.loads((output / "report.json").read_text(encoding="utf-8")) == report
    assert (output / "issues.jsonl").read_bytes() == b""
    assert (output / "translated.de.odt").is_file()
    assert "ODT review complete" in capsys.readouterr().out
    assert b"\r\n" not in (output / "report.json").read_bytes()


def test_review_refuses_existing_directory(odt_factory, tmp_path):
    source = odt_factory()
    with pytest.raises(FileExistsError):
        evaluate_odt(source, tmp_path, Echo(), None, metadata={})
    assert not (tmp_path / "report.json").exists()


def test_failed_review_keeps_sanitized_partial_report(odt_factory, tmp_path):
    class Failing:
        def translate(self, text, **kwargs):
            raise TranslationError("private failure details")

    output = tmp_path / "review"
    with pytest.raises(TranslationError):
        evaluate_odt(odt_factory(), output, Failing(), None, metadata={})
    content = (output / "report.json").read_text(encoding="utf-8")
    report = json.loads(content)
    assert report["status"] == "failed"
    assert report["error_type"] == "TranslationError"
    assert not report["complete"]
    assert not report["output_exists"]
    assert "private failure details" not in content


def test_issue_log_is_retained(odt_factory, tmp_path):
    class LostMarkers:
        def translate(self, text, **kwargs):
            return "Text"

    output = tmp_path / "review"
    report = evaluate_odt(odt_factory(), output, LostMarkers(), None, metadata={})
    issues = [json.loads(line) for line in (output / "issues.jsonl").read_text().splitlines()]
    assert report["issue_count"] == len(issues) > 0
    assert any(issue["action"] == "retained_original" for issue in issues)


def test_styles_text_is_explicitly_inventoried(odt_factory, tmp_path):
    styles = b"""<o:document-styles
      xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
      xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
      xmlns:s="urn:oasis:names:tc:opendocument:xmlns:style:1.0">
      <o:master-styles><s:master-page><s:header><t:p>Header</t:p></s:header>
      </s:master-page></o:master-styles></o:document-styles>"""
    report = evaluate_odt(
        odt_factory(updates={"styles.xml": styles}), tmp_path / "review", Echo(), None, metadata={}
    )
    assert report["peripheral_text"][0]["source_text"] == "Header"
    assert report["peripheral_text"][0]["reason"] == "unsupported_styles_text"


def test_main_rejects_missing_checkpoint_before_loading(odt_factory, tmp_path, monkeypatch):
    from scripts import evaluate_odt as module

    monkeypatch.setattr(module, "MarianBackend", lambda: pytest.fail("must not load"))
    with pytest.raises(SystemExit) as error:
        main(
            [
                str(odt_factory()),
                "--alignment-model",
                str(tmp_path / "missing"),
                "--output",
                str(tmp_path / "review"),
            ]
        )
    assert error.value.code == 1
    assert not (tmp_path / "review").exists()
