"""Retain failed text locally while continuing; never conceal fatal failures."""

import json

import pytest

from doc_lingo import RecoverableTranslationError, TranslationError
from doc_lingo.interfaces import cli
from doc_lingo.translation.chunks import translate_chunks
from doc_lingo.translation.issues import issue_sink


def test_oversized_word_and_generation_failure_continue_in_order():
    issues = []
    token = issue_sink.set(lambda text, reason: issues.append((text, reason)))

    def generate(text):
        if text == "bad":
            raise RecoverableTranslationError("Empty translation")
        return text.upper()

    try:
        result = translate_chunks("ok enormousword bad end", lambda s: len(s) <= 4, generate)
    finally:
        issue_sink.reset(token)
    assert result == "OK enormousword bad END"
    assert [text for text, _ in issues] == ["enormousword", "bad"]


@pytest.mark.parametrize("fatal", [False, True])
def test_cli_reports_partial_translation_or_fatal_failure(tmp_path, monkeypatch, capsys, fatal):
    source = tmp_path / "book.txt"
    source.write_bytes(b"Good. Bad.\n\nNext.")
    destination = tmp_path / "book.de.txt"
    report = tmp_path / "book.de.txt.issues.jsonl"

    class Backend:
        def translate(self, text, **kwargs):
            if fatal:
                raise TranslationError("Model unavailable")

            def generate(part):
                if part == "Bad.":
                    raise RecoverableTranslationError("Empty translation")
                return part.upper()

            return translate_chunks(text, lambda part: True, generate)

    monkeypatch.setattr(cli, "MarianBackend", Backend)
    monkeypatch.setattr(cli, "load_dotenv", lambda **kw: None)
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--target-lang", "de"])
    assert issue_sink.get() is None
    if fatal:
        assert error.value.code == 1
        assert not destination.exists()
        assert not report.exists()
    else:
        assert error.value.code == 3
        assert destination.read_bytes() == b"GOOD. Bad.\n\nNEXT."
        issue = json.loads(report.read_text(encoding="utf-8"))
        assert issue["original"] == "Bad."
        assert issue["segment_id"] == "1"
        assert issue["paragraph_number"] == 1
        assert issue["page"] is None
        assert "Partially translated" in capsys.readouterr().out


def test_existing_report_is_never_overwritten(tmp_path, monkeypatch):
    source = tmp_path / "book.txt"
    source.write_bytes(b"Original")
    report = tmp_path / "book.de.txt.issues.jsonl"
    report.write_bytes(b"Existing report")
    monkeypatch.setattr(cli, "load_dotenv", lambda **kw: None)
    monkeypatch.setattr(cli, "MarianBackend", lambda: pytest.fail("Backend constructed"))
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--target-lang", "de"])
    assert error.value.code == 1
    assert report.read_bytes() == b"Existing report"
    assert not (tmp_path / "book.de.txt").exists()
