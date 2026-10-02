"""Marker identities override guesses without inventing links for nearby prose."""

from dataclasses import replace

import pytest

from doc_lingo.documents import TextSegment
from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)
from doc_lingo.translation.marker_alignment import anchor_content_markers
from doc_lingo.translation.model_input import prepare_model_input


def prepared():
    return prepare_model_input(
        TextSegment("1", "Use a b", protected_spans=((4, 5), (6, 7))).translation_input()
    )


def unresolved(source, target):
    return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))


def test_swapped_markers_are_anchored_by_identity():
    p = prepared()
    a, b = [m.token for m in p.markers]
    source, target = p.text, f"Nutze {b} {a}"
    assert source is not None
    sa, sb = [TextRange(source.index(t), source.index(t) + len(t)) for t in (a, b)]
    ta, tb = [TextRange(target.index(t), target.index(t) + len(t)) for t in (a, b)]
    wrong = AlignmentResult(
        source,
        target,
        (
            AlignmentLink((TextRange(0, 3),), (TextRange(0, 5),)),
            AlignmentLink((sa,), (tb,)),
            AlignmentLink((sb,), (ta,)),
        ),
    )
    fixed = anchor_content_markers(wrong, p)
    assert fixed.links[0] == wrong.links[0]
    assert fixed.links[1:] == (AlignmentLink((sa,), (ta,)), AlignmentLink((sb,), (tb,)))
    assert anchor_content_markers(fixed, p) == fixed


def test_mixed_phrase_becomes_ambiguous_around_exact_markers():
    p = prepared()
    assert p.text is not None
    whole = TextRange(0, len(p.text))
    result = AlignmentResult(p.text, p.text, (AlignmentLink((whole,), (whole,)),))
    fixed = anchor_content_markers(result, p)
    assert len(fixed.links) == 2
    assert fixed.ambiguous[0] == TextRange(0, 4)
    assert fixed.unaligned == ()


def test_markers_are_removed_from_unresolved_statuses():
    p = prepared()
    assert p.text is not None
    result = unresolved(p.text, p.text)
    fixed = anchor_content_markers(result, p)
    assert len(fixed.links) == 2
    assert fixed.unaligned[0] == TextRange(0, 4)
    uncertain = replace(result, unaligned=(), ambiguous=result.unaligned)
    assert anchor_content_markers(uncertain, p).ambiguous == fixed.unaligned


@pytest.mark.parametrize("variant", ["missing", "duplicate", "unknown", "damaged"])
def test_invalid_markers_fail_before_link_changes(variant):
    p = prepared()
    assert p.text is not None
    token = p.markers[0].token
    target = {
        "missing": p.text.replace(token, ""),
        "duplicate": p.text + token,
        "unknown": p.text + p.prefix + "X99Z",
        "damaged": p.text + p.prefix.lower() + "broken",
    }[variant]
    with pytest.raises(AlignmentError):
        anchor_content_markers(unresolved(p.text, target), p)


def test_wrong_source_and_duplicate_registration():
    p = prepared()
    with pytest.raises(AlignmentError, match="source"):
        anchor_content_markers(unresolved("other", "other"), p)
    assert p.text is not None
    with pytest.raises(AlignmentError, match="registered"):
        anchor_content_markers(unresolved(p.text, p.text), replace(p, markers=p.markers * 2))


def test_no_markers_preserves_alignment():
    p = prepare_model_input(TextSegment("1", "text").translation_input())
    result = unresolved("text", "Text")
    assert anchor_content_markers(result, p) == result
