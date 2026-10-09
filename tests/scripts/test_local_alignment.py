"""Local review proposals preserve the baseline and reject unsafe repairs."""

from dataclasses import replace

import pytest

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)
from scripts.local_alignment import evaluate_local


def baseline():
    return AlignmentResult(
        "a user guide b",
        "A Manual B",
        (
            AlignmentLink((TextRange(0, 1),), (TextRange(0, 1),)),
            AlignmentLink((TextRange(7, 12),), (TextRange(2, 8),)),
            AlignmentLink((TextRange(13, 14),), (TextRange(9, 10),)),
        ),
        (TextRange(2, 6),),
    )


CASE = {"scopes": [{"id": "focus", "source": [2, 12]}]}


class Adapter:
    def __init__(self):
        self.calls = []

    def align(self, source, target):
        self.calls.append((source, target))
        return AlignmentResult(
            source,
            target,
            (AlignmentLink((TextRange(0, 4), TextRange(5, 10)), (TextRange(0, 6),)),),
        )


def test_candidate_preserves_raw_evidence_and_exact_window():
    original = baseline()
    adapter = Adapter()
    row = evaluate_local(adapter, original, CASE)[0]
    assert adapter.calls == [("user guide", "Manual")]
    assert row["calls"] == 1
    assert row["status"] == "candidate"
    assert row["window"] == {"source": {"start": 2, "end": 12}, "target": {"start": 2, "end": 8}}
    assert original == baseline()


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("unresolved", "still_unresolved"),
        ("mismatch", "mismatched_text"),
        ("error", "failed"),
        ("changed", "changed_existing_links"),
    ],
)
def test_one_attempt_rejects_invalid_or_incomplete_results(mode, reason):
    class Broken(Adapter):
        def align(self, source, target):
            self.calls.append((source, target))
            if mode == "error":
                raise AlignmentError("failed")
            if mode == "mismatch":
                return AlignmentResult("x", "y", unaligned=(TextRange(0, 1),))
            if mode == "unresolved":
                return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))
            return AlignmentResult(
                source,
                target,
                (
                    AlignmentLink((TextRange(0, 4),), (TextRange(0, 3),)),
                    AlignmentLink((TextRange(5, 10),), (TextRange(3, 6),)),
                ),
            )

    adapter = Broken()
    row = evaluate_local(adapter, baseline(), CASE)[0]
    assert row["reason"] == reason
    assert row["status"] in ("rejected", "error")
    assert len(adapter.calls) == 1


def test_protected_case_never_calls_model():
    row = evaluate_local(None, baseline(), {**CASE, "markers": ["DLMX0Z"]})[0]
    assert row["reason"] == "protected_case"
    assert row["calls"] == 0


def test_missing_anchor_skips_without_inference():
    result = baseline()
    result = replace(result, links=result.links[1:], unaligned=(TextRange(0, 6),))
    row = evaluate_local(None, result, CASE)[0]
    assert row["reason"] == "missing_anchors"


def test_crossing_source_group_skips_without_inference():
    result = AlignmentResult(
        "a user guide b",
        "A Manual B",
        (
            AlignmentLink((TextRange(0, 1), TextRange(7, 12)), (TextRange(0, 8),)),
            AlignmentLink((TextRange(13, 14),), (TextRange(9, 10),)),
        ),
        (TextRange(2, 6),),
    )
    assert evaluate_local(None, result, CASE)[0]["reason"] == "crossing_source_boundary"


def test_new_overlapping_link_is_rejected():
    case = {
        "scopes": [
            {"id": "focus", "source": [2, 12], "link_target": "first"},
            {"id": "inner", "source": [7, 12], "link_target": "second"},
        ]
    }
    assert evaluate_local(Adapter(), baseline(), case)[0]["reason"] == "projection_conflict"


def test_default_evaluation_does_not_request_local_calls():
    from scripts.evaluate_alignment import evaluate_case

    class Full:
        def align(self, source, target):
            assert (source, target) == (baseline().source, baseline().target)
            return baseline()

    case = {**CASE, "source": baseline().source, "target": baseline().target}
    assert evaluate_case(Full(), case)["local_reviews"] == []


def test_evaluation_reports_proposal_without_replacing_baseline():
    from scripts.evaluate_alignment import evaluate_case

    class Full(Adapter):
        def align(self, source, target):
            if source == baseline().source:
                return baseline()
            return super().align(source, target)

    adapter = Full()
    case = {**CASE, "source": baseline().source, "target": baseline().target}
    row = evaluate_case(adapter, case, local_review=True)
    assert row["alignment"] == row["raw_alignment"]
    assert row["local_reviews"][0]["status"] == "candidate"
    assert len(adapter.calls) == 1


def test_reordered_anchors_skip_without_inference():
    original = baseline()
    result = replace(
        original,
        links=(
            replace(original.links[0], target_ranges=(TextRange(9, 10),)),
            original.links[1],
            replace(original.links[2], target_ranges=(TextRange(0, 1),)),
        ),
    )
    assert evaluate_local(None, result, CASE)[0]["reason"] == "empty_or_reordered_window"
