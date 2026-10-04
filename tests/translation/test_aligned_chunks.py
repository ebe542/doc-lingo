"""Chunk pairing and offset merging without inference or downloads."""

import re

import pytest

from doc_lingo import MarkdownReader, MarkdownWriter, translate_document
from doc_lingo.translation.aligned_chunks import translate_aligned_chunks
from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)


class Backend:
    def __init__(self):
        self.calls = []

    def translate(self, text, **kwargs):
        self.calls.append(text)
        return text.upper()


class SmallAligner:
    def fits_input(self, text):
        return len(text.split()) <= 2

    def align(self, source, target):
        return AlignmentResult(
            source,
            target,
            tuple(
                AlignmentLink((TextRange(m.start(), m.end()),), (TextRange(m.start(), m.end()),))
                for m in re.finditer(r"\S+", source)
            ),
        )


def translate(text, backend=None, aligner=None, failures=None):
    return translate_aligned_chunks(
        text,
        backend or Backend(),
        aligner or SmallAligner(),
        source_lang="en",
        target_lang="de",
        on_alignment_failure=lambda: failures.append(True) if failures is not None else None,
    )


def test_offsets_and_separators_survive_chunking():
    backend = Backend()
    source = "one two.\r\nthree four.  five six."
    result = translate(source, backend)
    assert len(backend.calls) == 3
    assert result.source == source
    assert result.target == source.upper()
    for link in result.links:
        a, b = link.source_ranges[0], link.target_ranges[0]
        assert source[a.start : a.end].upper() == result.target[b.start : b.end]


def test_target_offsets_use_actual_translated_lengths():
    class ExpandedBackend(Backend):
        def translate(self, text, **kwargs):
            return "translated " + text

    class ExpandedAligner(SmallAligner):
        def align(self, source, target):
            return AlignmentResult(
                source,
                target,
                (AlignmentLink((TextRange(0, len(source)),), (TextRange(11, len(target)),)),),
            )

    result = translate("one two. three four.", ExpandedBackend(), ExpandedAligner())
    assert result.links[1].source_ranges == (TextRange(9, 20),)
    assert result.links[1].target_ranges == (TextRange(31, 42),)


@pytest.mark.parametrize("wrong_result", [False, True])
def test_one_failed_chunk_does_not_discard_other_links(wrong_result):
    class Failing(SmallAligner):
        def align(self, source, target):
            if source.startswith("three"):
                if wrong_result:
                    return AlignmentResult("x", "y", unaligned=(TextRange(0, 1),))
                raise AlignmentError("target exceeds encoder limit")
            return super().align(source, target)

    failures = []
    result = translate("one two. three four.", aligner=Failing(), failures=failures)
    assert result.target == "ONE TWO. THREE FOUR."
    assert result.unaligned == (TextRange(9, 20),)
    assert len(result.links) == 2
    assert failures == [True]


def test_oversized_indivisible_marker_is_not_split():
    class Tiny(SmallAligner):
        def fits_input(self, text):
            return len(text) <= 4

    backend = Backend()
    translate("DLM0123456789X0Z word", backend, Tiny())
    assert backend.calls == ["DLM0123456789X0Z", "word"]


def test_unbudgeted_aligner_retains_single_call():
    class Unlimited:
        def align(self, source, target):
            return SmallAligner().align(source, target)

    backend = Backend()
    translate("one two three four", backend, Unlimited())
    assert backend.calls == ["one two three four"]


def test_empty_translation_is_rejected():
    class Empty(Backend):
        def translate(self, text, **kwargs):
            return ""

    with pytest.raises(AlignmentError, match="Empty"):
        translate("one two", Empty())


@pytest.mark.parametrize("opening,closing", [("**", "**"), ("[", "](url)")])
def test_entire_scope_survives_missing_word_links(tmp_path, opening, closing):
    class Unresolved(SmallAligner):
        def align(self, source, target):
            return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))

    source = tmp_path / "source.md"
    source.write_text(opening + "one two. three four." + closing, encoding="utf-8")
    output = tmp_path / "output.md"
    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Unresolved(),
        on_issue=issues.append,
    )
    assert output.read_text(encoding="utf-8") == opening + "ONE TWO. THREE FOUR." + closing
    assert not issues


def test_marker_and_original_content_survive_chunk_boundaries(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("**one `code(value)` two three four**", encoding="utf-8")
    output = tmp_path / "out.md"
    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=SmallAligner(),
        on_issue=issues.append,
    )
    assert output.read_text(encoding="utf-8") == "**ONE `code(value)` TWO THREE FOUR**"
    assert not issues


@pytest.mark.parametrize("opening,closing", [("**", "**"), ("[", "](url)"), ("<em>", "</em>")])
def test_formatting_spans_chunks_in_active_writer(tmp_path, opening, closing):
    source = tmp_path / "source.md"
    source.write_text(opening + "one two. three four. five six." + closing, encoding="utf-8")
    output = tmp_path / "output.md"
    backend = Backend()
    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        backend,
        output,
        source_lang="en",
        target_lang="de",
        aligner=SmallAligner(),
        on_issue=issues.append,
    )
    assert (
        output.read_text(encoding="utf-8") == opening + "ONE TWO. THREE FOUR. FIVE SIX." + closing
    )
    assert len(backend.calls) == 3
    assert not issues
