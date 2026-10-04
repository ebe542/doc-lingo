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
        on_alignment_failure=lambda details: (
            failures.append(details) if failures is not None else None
        ),
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
        def fits_input(self, text):
            return len(text.removeprefix("translated ").split()) <= 2

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
    assert len(failures) == 1
    assert "chunk=2" in failures[0]
    assert "alignment_source_range=[9,20)" in failures[0]
    assert any(item.startswith("cause=") for item in failures[0])


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


def test_registered_standalone_marker_bypasses_models_and_keeps_spacing():
    from doc_lingo.translation.alignment_statistics import AlignmentStatistics

    class TrimmedBackend(Backend):
        def translate(self, text, **kwargs):
            assert "DLMX2Z" not in text
            return super().translate(text, **kwargs).strip()

    backend = TrimmedBackend()
    stats = AlignmentStatistics()
    result = translate_aligned_chunks(
        "one two.\r\n DLMX2Z",
        backend,
        SmallAligner(),
        source_lang="en",
        target_lang="de",
        protected_tokens=("DLMX2Z",),
        statistics=stats,
        on_alignment_failure=lambda details: pytest.fail(str(details)),
    )
    assert result.target == "ONE TWO.\r\n DLMX2Z"
    assert backend.calls == ["one two."]
    assert stats.protected_units == 1
    assert stats.translation_calls == stats.alignment_calls == 1
    assert stats.alignment_failures == 0
    assert result.links[-1].source_ranges == (TextRange(11, 17),)


def test_unregistered_marker_like_text_is_translated():
    backend = Backend()
    translate("DLMX2Z", backend)
    assert backend.calls == ["DLMX2Z"]


def test_only_registered_markers_need_no_model_calls():
    result = translate_aligned_chunks(
        "DLMX0Z DLMX1Z",
        None,
        None,
        source_lang="en",
        target_lang="de",
        protected_tokens=("DLMX0Z", "DLMX1Z"),
        on_alignment_failure=lambda details: pytest.fail(str(details)),
    )
    assert result.target == result.source


def test_source_reserve_and_statistics(monkeypatch):
    from doc_lingo.translation import aligned_chunks
    from doc_lingo.translation.alignment_statistics import AlignmentStatistics

    class Reserved(SmallAligner):
        def fits_source(self, text):
            return len(text.split()) <= 2

        def fits_input(self, text):
            return len(text.split()) <= 4

    ticks = iter(range(100))
    monkeypatch.setattr(aligned_chunks, "perf_counter", lambda: next(ticks))
    stats = AlignmentStatistics()
    backend = Backend()
    translate_aligned_chunks(
        "one two three four",
        backend,
        Reserved(),
        source_lang="en",
        target_lang="de",
        statistics=stats,
        on_alignment_failure=lambda details: pytest.fail(str(details)),
    )
    assert backend.calls == ["one two", "three four"]
    assert stats.translation_calls == stats.alignment_calls == 2
    assert stats.translation_seconds == stats.alignment_seconds == 2
    assert stats.planning_seconds == 3


def test_failure_timing_is_recorded(monkeypatch):
    from doc_lingo.translation import aligned_chunks
    from doc_lingo.translation.alignment_statistics import AlignmentStatistics

    class Broken(Backend):
        def translate(self, text, **kwargs):
            raise RuntimeError("failed")

    ticks = iter(range(100))
    monkeypatch.setattr(aligned_chunks, "perf_counter", lambda: next(ticks))
    stats = AlignmentStatistics()
    with pytest.raises(RuntimeError, match="failed"):
        translate_aligned_chunks(
            "one two",
            Broken(),
            SmallAligner(),
            source_lang="en",
            target_lang="de",
            statistics=stats,
            on_alignment_failure=lambda details: None,
        )
    assert stats.translation_calls == 1
    assert stats.translation_seconds == 1
    assert stats.alignment_calls == 0


def test_target_budget_failure_has_side_and_global_coordinates():
    class Expanded(Backend):
        def translate(self, text, **kwargs):
            return text + " additional words"

    failures = []
    result = translate("one two", Expanded(), failures=failures)
    assert result.target == "one two additional words"
    assert "cause=Target chunk exceeds alignment encoder budget" in failures[0]
    assert "alignment_source_range=[0,7)" in failures[0]
    assert "alignment_target_range=[0,24)" in failures[0]


@pytest.mark.parametrize(
    "source_text,expected",
    [
        ("start **one two. three four.** end", "START **ONE TWO. THREE FOUR.** END"),
        (
            "start **one two. *three four.* five six.** end",
            "START **ONE TWO. *THREE FOUR.* FIVE SIX.** END",
        ),
        (
            'start [one two. three four.](https://example.org/a "First") middle '
            '[five six. seven eight.](https://example.org/b "Second") end',
            'START [ONE TWO. THREE FOUR.](https://example.org/a "First") MIDDLE '
            '[FIVE SIX. SEVEN EIGHT.](https://example.org/b "Second") END',
        ),
        (
            'start <strong class="keep">one two. <em>three four.</em> five six.</strong> end',
            'START <strong class="keep">ONE TWO. <em>THREE FOUR.</em> FIVE SIX.</strong> END',
        ),
    ],
)
def test_partial_and_nested_scopes_span_real_chunk_calls(tmp_path, source_text, expected):
    source = tmp_path / "source.md"
    source.write_text(source_text, encoding="utf-8", newline="\n")
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
    assert output.read_text(encoding="utf-8") == expected
    assert len(backend.calls) > 1
    assert all(len(part.split()) <= 2 for part in backend.calls)
    assert not issues


def test_unresolved_partial_scope_does_not_drop_separate_link(tmp_path):
    class MissingWord(SmallAligner):
        def align(self, source, target):
            result = super().align(source, target)
            kept, missing = [], []
            for link in result.links:
                span = link.source_ranges[0]
                if source[span.start : span.end] == "three":
                    missing.append(span)
                else:
                    kept.append(link)
            return AlignmentResult(source, target, tuple(kept), unaligned=tuple(missing))

    source = tmp_path / "source.md"
    source.write_text(
        "start **one two. three four.** middle [five six.](url) end", encoding="utf-8", newline="\n"
    )
    output = tmp_path / "output.md"
    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=MissingWord(),
        on_issue=issues.append,
    )
    assert (
        output.read_text(encoding="utf-8")
        == "START ONE TWO. THREE FOUR. MIDDLE [FIVE SIX.](url) END"
    )
    assert len(issues) == 1
    assert issues[0].action == "formatting_dropped"
    # Positions are in the complete prepared input, not in the local chunk.
    assert "alignment_source_ranges=[15,20)" in issues[0].diagnostics.validation_errors[0]


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
