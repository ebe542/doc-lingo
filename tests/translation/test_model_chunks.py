"""Budget checks use prepared marker text and retain original source links."""

import pytest

from doc_lingo.documents import SourceLayout, SourceRange, TextSegment, TranslationInput
from doc_lingo.translation.issues import RecoverableTranslationError, issue_sink
from doc_lingo.translation.model_chunks import split_model_input
from doc_lingo.translation.model_input import prepare_model_input


def prepare(text):
    return prepare_model_input(TextSegment("1", text).translation_input())


def test_fitting_paragraph_stays_whole():
    chunks = list(split_model_input(prepare("First. Second."), lambda text: True))
    assert len(chunks) == 1
    assert chunks[0].text == "First. Second."
    assert chunks[0].source_spans == ((0, 14),)


@pytest.mark.parametrize("source", ["One. Two. Three.", "ä😀 one\r\n two\tthree", "  one two  "])
def test_chunks_fit_and_preserve_source_and_separators(source):
    chunks = list(split_model_input(prepare(source), lambda text: len(text) <= 7))
    assert all(chunk.text is None or len(chunk.text) <= 7 for chunk in chunks)
    assert "".join((chunk.text or "") + chunk.separator for chunk in chunks) == source
    assert "".join(chunk.original for chunk in chunks) == source


def test_one_formatting_range_spans_multiple_units():
    source = "**First. Second.**"
    layout = SourceLayout(source, (SourceRange(0, 2, 16, 18),))
    prepared = prepare_model_input(TranslationInput.from_layout(layout))
    chunks = list(split_model_input(prepared, lambda text: len(text) <= 7))
    assert [chunk.text for chunk in chunks] == ["First.", "Second."]
    assert [chunk.formatting for chunk in chunks] == [(0,), (0,)]
    assert "".join(chunk.original for chunk in chunks) == "First. Second."


def test_marker_is_atomic_and_budgeted_as_model_text():
    source = "Use code now."
    prepared = prepare_model_input(
        TextSegment("1", source, protected_spans=((4, 8),)).translation_input()
    )
    marker = prepared.markers[0].token
    measured = []

    def fits(text):
        measured.append(text)
        return len(text) <= len(marker)

    chunks = list(split_model_input(prepared, fits))
    assert any(marker in text for text in measured)
    assert sum(marker in (chunk.text or "") for chunk in chunks) == 1
    assert "".join(chunk.original for chunk in chunks) == source
    assert next(chunk for chunk in chunks if marker in (chunk.text or "")).source_spans[0] == (4, 8)


def test_oversized_marker_retains_original_and_continues():
    prepared = prepare_model_input(
        TextSegment("1", "Use code now.", protected_spans=((4, 8),)).translation_input()
    )
    issues = []
    token = issue_sink.set(lambda original, reason: issues.append(original))
    try:
        chunks = list(split_model_input(prepared, lambda text: len(text) <= 4))
    finally:
        issue_sink.reset(token)
    assert [chunk.text for chunk in chunks] == ["Use", None, "now."]
    assert issues == ["code "]
    assert chunks[1].original == "code "
    assert chunks[1].separator == ""
    assert prepared.prefix not in chunks[1].original


def test_oversized_word_remains_strict_without_sink():
    with pytest.raises(RecoverableTranslationError):
        list(split_model_input(prepare("oversized"), lambda text: False))


def test_fully_protected_source_never_calls_budget():
    prepared = prepare_model_input(
        TextSegment("1", "code", protected_spans=((0, 4),)).translation_input()
    )

    def fits(text):
        pytest.fail("Protected source must not reach the tokenizer")

    (chunk,) = split_model_input(prepared, fits)
    assert chunk.text is None
    assert chunk.original == "code"


def test_issue_context_is_restored_before_yield_and_on_close():
    def sink(original, reason):
        pass

    token = issue_sink.set(sink)
    iterator = split_model_input(prepare("one two"), lambda text: len(text) <= 3)
    try:
        next(iterator)
        assert issue_sink.get() is sink
        iterator.close()
        assert issue_sink.get() is sink
    finally:
        issue_sink.reset(token)


def test_tokenizer_failure_restores_issue_context():
    def sink(original, reason):
        pytest.fail("Tokenizer errors are not recoverable content errors")

    def fits(text):
        raise RuntimeError("Tokenizer unavailable")

    token = issue_sink.set(sink)
    try:
        with pytest.raises(RuntimeError, match="Tokenizer unavailable"):
            list(split_model_input(prepare("text"), fits))
        assert issue_sink.get() is sink
    finally:
        issue_sink.reset(token)


def test_nonmonotonic_budget_is_checked_for_each_emitted_input():
    accepted = {"one two", "three"}
    chunks = list(split_model_input(prepare("one two three"), lambda text: text in accepted))
    assert [chunk.text for chunk in chunks] == ["one two", "three"]


def test_marker_attached_to_punctuation_is_not_cut():
    prepared = prepare_model_input(
        TextSegment("1", "Use (code).", protected_spans=((5, 9),)).translation_input()
    )
    marker = prepared.markers[0].token
    chunks = list(split_model_input(prepared, lambda text: len(text) <= len(marker) + 3))
    assert [chunk.text for chunk in chunks] == ["Use", f"({marker})."]
    assert "".join(chunk.original for chunk in chunks) == "Use (code)."


def test_multiple_ranges_and_repeated_words_keep_distinct_source_slices():
    source = "**same** *same*"
    layout = SourceLayout(source, (SourceRange(0, 2, 6, 8), SourceRange(9, 10, 14, 15)))
    chunks = list(
        split_model_input(
            prepare_model_input(TranslationInput.from_layout(layout)), lambda text: len(text) <= 4
        )
    )
    assert [chunk.text for chunk in chunks] == ["same", "same"]
    assert [chunk.formatting for chunk in chunks] == [(0,), (1,)]
    assert chunks[0].source_spans == ((2, 6), (8, 9))
    assert chunks[1].source_spans == ((10, 14),)
