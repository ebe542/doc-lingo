"""Keep manually authored review ranges and marker registries consistent."""

import json
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/alignment"
CASES = json.loads((FIXTURES / "en-de-holdout.json").read_text(encoding="utf-8"))


def test_holdout_is_separate_from_tuning_cases():
    tuning = json.loads((FIXTURES / "en-de-registered.json").read_text(encoding="utf-8"))
    assert len(CASES) == len({case["id"] for case in CASES}) == 30
    assert not {case["id"] for case in CASES} & {case["id"] for case in tuning}
    assert not {case["source"] for case in CASES} & {case["source"] for case in tuning}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_review_ranges_identify_exact_text(case):
    assert case["expected_spans"]
    for expectation in case["expected_spans"]:
        assert expectation["source_ranges"]
        assert expectation["relation"] in ("correspondence", "unaligned")
        assert bool(expectation["target_ranges"]) == (expectation["relation"] == "correspondence")
        for side in ("source", "target"):
            end = 0
            for span in expectation[f"{side}_ranges"]:
                assert end <= span["start"] < span["end"] <= len(case[side])
                assert case[side][span["start"] : span["end"]] == span["text"]
                end = span["end"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_holdout_markers_are_explicit_and_preserved(case):
    pattern = r"DLM[0-9A-F]{32}X[0-9]+Z"
    tokens = case.get("markers", [])
    assert len(tokens) == len(set(tokens))
    for side in ("source", "target"):
        assert sorted(re.findall(pattern, case[side])) == sorted(tokens)
    for token in tokens:
        assert re.fullmatch(re.escape(case["marker_prefix"]) + r"X[0-9]+Z", token)
