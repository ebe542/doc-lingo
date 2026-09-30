"""Explain failed validation without changing source-retention behavior."""

import json
from dataclasses import asdict

import pytest

from doc_lingo import MarkdownReader, MarkdownWriter, TranslationDiagnostics, translate_document
from doc_lingo.documents.html.text import HtmlSegment
from doc_lingo.translation.issues import issue_details, issue_sink, retain_original


def test_failed_structure_records_exact_candidate_and_clears_context(tmp_path):
    source = tmp_path / "source.md"
    source.write_bytes(b"Hello\n\nNext\n")
    destination = tmp_path / "output.md"

    class Backend:
        def translate(self, text, **kwargs):
            return "# Hallo" if text == "Hello" else "Weiter"

    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        destination,
        source_lang="en",
        target_lang="de",
        on_issue=issues.append,
    )
    assert destination.read_bytes() == b"Hello\n\nWeiter\n"
    assert len(issues) == 1
    report = json.loads(json.dumps(asdict(issues[0])))
    assert report["original"] == "Hello\n"
    assert report["action"] == "retained_original"
    assert report["diagnostics"]["attempted_translation"] == "# Hallo\n"
    assert report["diagnostics"]["stage"] == "restored"
    assert any(
        "paragraph_open -> heading_open" in error
        for error in report["diagnostics"]["validation_errors"]
    )
    assert issue_details.get() is None
    assert issue_sink.get() is None


def test_diagnostic_context_resets_even_when_callback_raises():
    details = TranslationDiagnostics("candidate", "restored", ("example",))

    def fail(original, reason):
        assert issue_details.get() == details
        raise RuntimeError("Callback failed")

    token = issue_sink.set(fail)
    try:
        with pytest.raises(RuntimeError, match="Callback failed"):
            retain_original("source", "reason", diagnostics=details)
        assert issue_details.get() is None
    finally:
        issue_sink.reset(token)


def test_html_validation_explains_emptied_element():
    segment = HtmlSegment("1", "Hello <strong>world</strong>.")
    errors = segment.validation_errors("Hallo Welt <strong></strong>.")
    assert errors == ("html_text_emptied: strong[0]",)
    assert segment.repair_translation("Hallo Welt <strong></strong>.") == "Hallo Welt ."
