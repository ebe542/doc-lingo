"""Known formatting does not become markers; opaque sentence content does."""

import pytest

from doc_lingo.documents import TextSegment
from doc_lingo.documents.markdown import MarkdownReader
from doc_lingo.translation.issues import RecoverableTranslationError, issue_sink
from doc_lingo.translation.markers import marker_prefix
from doc_lingo.translation.model_input import prepare_model_input


def test_formatting_removed_and_code_marked(tmp_path):
    path = tmp_path / "source.md"
    path.write_text("Keep **this call**: `model.predict(data)`.", encoding="utf-8")
    with MarkdownReader(path).iter_segments() as segments:
        prepared = prepare_model_input(next(segments).translation_input())
    assert len(prepared.markers) == 1
    marker = prepared.markers[0].token
    assert prepared.text == f"Keep this call: {marker}."
    assert prepared.restore_content(f"Diesen Aufruf beibehalten: {marker}.") == (
        "Diesen Aufruf beibehalten: `model.predict(data)`."
    )


def test_fully_protected_content_bypasses_model():
    segment = TextSegment("1", "code", protected_spans=((0, 4),))
    prepared = prepare_model_input(segment.translation_input())
    assert prepared.text is None
    assert prepared.markers == ()
    assert prepared.restore_content("") == "code"


def test_whitespace_needs_no_marker():
    prepared = prepare_model_input(
        TextSegment("1", "text\n", protected_spans=((4, 5),)).translation_input()
    )
    assert prepared.text == "text\n"
    assert prepared.markers == ()
    assert prepared.restore_content("Text\n") == "Text\n"


def make_input():
    return prepare_model_input(
        TextSegment("1", "Use a and b.", protected_spans=((4, 5), (10, 11))).translation_input()
    )


def test_content_markers_may_move():
    prepared = make_input()
    first, second = (item.token for item in prepared.markers)
    assert prepared.restore_content(f"Nutze {second} und {first}.") == "Nutze b und a."


@pytest.mark.parametrize("failure", ["missing", "duplicate", "unexpected", "damaged", "empty"])
def test_invalid_markers_retain_original_and_report(failure):
    prepared = make_input()
    first, second = (item.token for item in prepared.markers)
    variants = {
        "missing": f"Nutze {first}.",
        "duplicate": f"Nutze {first} {first} {second}.",
        "unexpected": f"Nutze {first} {second} {prepared.prefix}X99Z.",
        "damaged": f"Nutze {first.lower()} {second}.",
        "empty": f"{first} {second}",
    }
    issues = []
    token = issue_sink.set(lambda original, reason: issues.append((original, reason)))
    try:
        assert prepared.restore_content(variants[failure]) == "Use a and b."
    finally:
        issue_sink.reset(token)
    assert len(issues) == 1


def test_missing_marker_is_strict_without_issue_sink():
    with pytest.raises(RecoverableTranslationError):
        make_input().restore_content("Nutze etwas.")


def test_marker_namespace_does_not_collide_with_literal_source():
    existing = marker_prefix("", namespace="DLM") + "X0Z"
    text = existing + " code"
    prepared = prepare_model_input(
        TextSegment(
            "1", text, protected_spans=((len(existing) + 1, len(text)),)
        ).translation_input()
    )
    assert prepared.prefix not in text
    assert prepared.text is not None
    assert prepared.restore_content(prepared.text) == text


def test_reader_omits_standalone_code_block(tmp_path):
    path = tmp_path / "source.md"
    path.write_text("```python\nmodel.predict(data)\n```\n", encoding="utf-8")
    with MarkdownReader(path).iter_segments() as segments:
        assert list(segments) == []
