"""Compare raw/anchored links without optional models or network access."""

import json
import sys
from pathlib import Path

import pytest

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)
from scripts.evaluate_alignment import evaluate_case, main


class GroupingAligner:
    def align(self, source, target):
        return AlignmentResult(
            source,
            target,
            (AlignmentLink((TextRange(0, len(source)),), (TextRange(0, len(target)),)),),
        )


def test_raw_alignment_retained_and_inputs_unchanged():
    case = {
        "source": "Use DLMX0Z",
        "target": "DLMX0Z nutzen",
        "marker_prefix": "DLM",
        "markers": ["DLMX0Z"],
    }
    row = evaluate_case(GroupingAligner(), case, anchor_markers=True)
    assert row["error"] is None
    assert row["raw_alignment"]["source"] == row["alignment"]["source"] == case["source"]
    assert row["raw_alignment"]["target"] == row["alignment"]["target"] == case["target"]
    assert row["alignment"]["links"][0]["source_ranges"] == ({"start": 4, "end": 10},)
    assert row["alignment"]["ambiguous"] == ({"start": 0, "end": 4},)
    assert row["verdict"] == "pending"


def test_marker_failure_keeps_raw_evidence():
    case = {"source": "DLMX0Z", "target": "text", "marker_prefix": "DLM", "markers": ["DLMX0Z"]}
    row = evaluate_case(GroupingAligner(), case, anchor_markers=True)
    assert row["raw_alignment"] is not None
    assert row["alignment"] is None
    assert row["error"]


def test_anchoring_is_optional_and_requires_explicit_registry():
    case = {"source": "DLMX0Z", "target": "DLMX1Z"}
    for enabled in (False, True):
        row = evaluate_case(GroupingAligner(), case, anchor_markers=enabled)
        assert row["alignment"] == row["raw_alignment"]


def test_backend_failure():
    class Failed:
        def align(self, *args):
            raise AlignmentError("Failed")

    row = evaluate_case(Failed(), {"source": "a", "target": "b"})
    assert row["alignment"] is row["raw_alignment"] is None
    assert row["error"] == "Failed"


@pytest.mark.parametrize(
    "extra",
    [
        ["--thresholds", "0.01"],
        ["--backend", "awesome", "--thresholds", "nan"],
        ["--backend", "awesome", "--thresholds", "0.01", "0.01"],
    ],
)
def test_invalid_settings_fail_before_loading(monkeypatch, tmp_path, extra):
    monkeypatch.setattr(
        sys, "argv", ["evaluate_alignment", "--output", str(tmp_path / "out.json"), *extra]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_registered_fixture_keeps_comparison_pairs():
    fixtures = Path(__file__).resolve().parents[1] / "fixtures/alignment"
    old = json.loads((fixtures / "en-de-extended.json").read_text(encoding="utf-8"))
    new = json.loads((fixtures / "en-de-registered.json").read_text(encoding="utf-8"))
    assert [
        {k: v for k, v in case.items() if k not in ("markers", "marker_prefix")} for case in new
    ] == old
    assert [case["id"] for case in new if "markers" in case] == ["marker", "two-markers"]
