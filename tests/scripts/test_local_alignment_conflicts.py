"""Controlled proposal conflicts and explicit limits of structural evidence."""

from copy import deepcopy

import pytest

from doc_lingo.translation.alignment import AlignmentLink, AlignmentResult, TextRange
from scripts.local_alignment import evaluate_local, reject_conflicting_proposals


def link(source, target):
    return AlignmentLink((TextRange(source, source + 1),), (TextRange(target, target + 1),))


class Exact:
    def __init__(self):
        self.calls = []

    def align(self, source, target):
        self.calls.append((source, target))
        return AlignmentResult(source, target, (link(0, 0),))


@pytest.mark.parametrize("reverse", [False, True])
def test_neighboring_retries_remain_independent(reverse):
    baseline = AlignmentResult(
        "a x b y c",
        "A X B Y C",
        (link(0, 0), link(4, 4), link(8, 8)),
        (TextRange(2, 3), TextRange(6, 7)),
    )
    scopes = [
        {"id": "first", "source": [2, 3], "link_target": "first-url"},
        {"id": "second", "source": [6, 7], "link_target": "second-url"},
    ]
    adapter = Exact()
    rows = evaluate_local(adapter, baseline, {"scopes": scopes[::-1] if reverse else scopes})
    assert len(adapter.calls) == 2
    assert all(row["status"] == "candidate" and row["calls"] == 1 for row in rows)
    for row in rows:
        # Each candidate leaves the other problem unresolved; no cascading repair.
        expected = {"start": 6, "end": 7} if row["scope"] == "first" else {"start": 2, "end": 3}
        assert row["candidate_alignment"]["unaligned"] == (expected,)
    assert baseline.unaligned == (TextRange(2, 3), TextRange(6, 7))


@pytest.mark.parametrize("side", ["source", "target"])
@pytest.mark.parametrize("reverse", [False, True])
def test_overlapping_windows_reject_every_participant(side, reverse):
    rows = [
        {
            "scope": "a",
            "status": "candidate",
            "window": {"source": {"start": 0, "end": 2}, "target": {"start": 0, "end": 2}},
        },
        {
            "scope": "b",
            "status": "candidate",
            "window": {"source": {"start": 3, "end": 5}, "target": {"start": 3, "end": 5}},
        },
        {
            "scope": "c",
            "status": "candidate",
            "window": {"source": {"start": 8, "end": 9}, "target": {"start": 8, "end": 9}},
        },
    ]
    rows[1]["window"][side] = {"start": 1, "end": 4}
    if reverse:
        rows.reverse()
    reject_conflicting_proposals(rows)
    by_id = {row["scope"]: row for row in rows}
    for identity, other in (("a", "b"), ("b", "a")):
        assert by_id[identity]["status"] == "rejected"
        assert by_id[identity]["reason"] == "conflicting_proposals"
        assert by_id[identity]["conflicts_with"] == [other]
    assert by_id["c"]["status"] == "candidate"


def test_adjacent_windows_are_not_overlaps():
    rows = [
        {
            "scope": str(start),
            "status": "candidate",
            "window": {side: {"start": start, "end": start + 2} for side in ("source", "target")},
        }
        for start in (0, 2)
    ]
    original = deepcopy(rows)
    reject_conflicting_proposals(rows)
    assert rows == original


def test_overlapping_optical_scopes_are_deferred_in_actual_review():
    baseline = AlignmentResult("a x b", "A X B", (link(0, 0), link(4, 4)), (TextRange(2, 3),))
    rows = evaluate_local(
        Exact(),
        baseline,
        {"scopes": [{"id": "bold", "source": [2, 3]}, {"id": "italic", "source": [2, 3]}]},
    )
    assert all(row["reason"] == "conflicting_proposals" for row in rows)
    assert all(row["candidate_alignment"] is not None for row in rows)


def test_consistently_wrong_repeated_anchors_are_not_detected_as_linguistic_errors():
    # Deliberately swapped occurrence identities: a structural validator has no
    # independent linguistic evidence to identify this internally consistent lie.
    baseline = AlignmentResult(
        "a x b a x b",
        "A X B A X B",
        (link(0, 6), link(4, 10), link(6, 0), link(10, 4)),
        (TextRange(2, 3), TextRange(8, 9)),
    )
    row = evaluate_local(Exact(), baseline, {"scopes": [{"id": "first", "source": [2, 3]}]})[0]
    assert row["status"] == "candidate"
    assert row["reason"] == "structural_checks_passed_manual_review_required"
    assert row["window"]["target"] == {"start": 8, "end": 9}
