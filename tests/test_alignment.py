"""Alignment contracts expose uncertainty and validate exact text coordinates."""

import pytest

from doc_lingo.translation import AlignmentLink, AlignmentResult, TextAligner, TextRange


def test_discontinuous_verb_alignment():
    result = AlignmentResult(
        "She turned off the light.",
        "Sie schaltete das Licht aus.",
        links=(
            AlignmentLink((TextRange(0, 3),), (TextRange(0, 3),)),
            AlignmentLink((TextRange(4, 14),), (TextRange(4, 13), TextRange(24, 27))),
        ),
        unaligned=(TextRange(15, 25),),
    )
    verb = result.links[1]
    assert [result.target[r.start : r.end] for r in verb.target_ranges] == ["schaltete", "aus"]


def test_many_to_many_and_target_reordering():
    result = AlignmentResult(
        "a b c",
        "C A B",
        links=(
            AlignmentLink((TextRange(0, 1), TextRange(2, 3)), (TextRange(2, 3), TextRange(4, 5))),
            AlignmentLink((TextRange(4, 5),), (TextRange(0, 1),)),
        ),
    )
    assert len(result.links) == 2


def test_explicit_uncertainty_and_target_insertions():
    result = AlignmentResult(
        "lost unsure", "new text", unaligned=(TextRange(0, 4),), ambiguous=(TextRange(5, 11),)
    )
    assert not result.links


@pytest.mark.parametrize("source", ["", " \r\n\t"])
def test_empty_or_whitespace_source_needs_no_links(source):
    assert AlignmentResult(source, "new").source == source


def test_unicode_offsets_are_characters():
    result = AlignmentResult(
        "😀ä",
        "ä😀",
        links=(
            AlignmentLink((TextRange(0, 1),), (TextRange(1, 2),)),
            AlignmentLink((TextRange(1, 2),), (TextRange(0, 1),)),
        ),
    )
    assert result.source[result.links[0].source_ranges[0].start : 1] == "😀"


@pytest.mark.parametrize("start,end", [(-1, 2), (1, 1), (2, 1)])
def test_invalid_range(start, end):
    with pytest.raises(ValueError):
        TextRange(start, end)


@pytest.mark.parametrize(
    "source,target",
    [
        ((), (TextRange(0, 1),)),
        ((TextRange(0, 1),), ()),
        ((TextRange(2, 3), TextRange(0, 1)), (TextRange(0, 1),)),
        ((TextRange(0, 2), TextRange(1, 3)), (TextRange(0, 1),)),
    ],
)
def test_invalid_link(source, target):
    with pytest.raises(ValueError):
        AlignmentLink(source, target)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # No status for source content.
        {"unaligned": (TextRange(1, 3),)},  # Leading gap.
        {"unaligned": (TextRange(0, 2),)},  # Trailing gap.
        {"unaligned": (TextRange(0, 4),)},  # Beyond source.
        {"unaligned": (TextRange(0, 3),), "ambiguous": (TextRange(0, 1),)},
        {"links": (AlignmentLink((TextRange(0, 3),), (TextRange(0, 4),)),)},
        {
            "links": (
                AlignmentLink((TextRange(0, 1),), (TextRange(0, 2),)),
                AlignmentLink((TextRange(1, 3),), (TextRange(1, 3),)),
            )
        },
    ],
)
def test_inconsistent_results_are_rejected(kwargs):
    with pytest.raises(ValueError):
        AlignmentResult("abc", "xyz", **kwargs)


def test_protocol_needs_no_inheritance():
    class UncertainAligner:
        def align(self, source: str, target: str) -> AlignmentResult:
            return AlignmentResult(source, target, ambiguous=(TextRange(0, len(source)),))

    aligner: TextAligner = UncertainAligner()
    assert aligner.align("word", "Wort").ambiguous == (TextRange(0, 4),)
