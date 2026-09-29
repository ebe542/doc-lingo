"""Run paired format fixtures through real adapters without loading a model."""

import json
from pathlib import Path

import pytest

from scripts.evaluate_translation_quality import evaluate_suite, load_suite

SUITE = Path(__file__).parent / "fixtures/translation_quality/format-comparison.en-de.json"


def test_paired_examples_roundtrip_and_capture_protected_backend_input(tmp_path):
    class Identity:
        def translate(self, text, **kwargs):
            return text

    suite = load_suite(SUITE)
    output = tmp_path / "report"
    report = evaluate_suite(suite, Identity(), output, metadata={"model": "offline identity"})
    assert report["complete"]
    assert len(report["results"]) == 9
    for group in ("classification", "guide", "keep-code"):
        variants = [item for item in report["results"] if item["comparison_id"] == group]
        assert [item["format"] for item in variants] == ["txt", "markdown", "html"]
        for item in variants:
            assert item["actual"] == item["source"]
            assert item["verdict"] == "pending"
            assert not item["issues"]
            assert len(item["backend_inputs"]) == 1
        assert "DLM" not in variants[0]["backend_inputs"][0]
        assert "DLM" in variants[1]["backend_inputs"][0]
        assert "DLM" in variants[2]["backend_inputs"][0]
    assert list(output.iterdir()) == [output / "report.json"]
    assert json.loads((output / "report.json").read_text(encoding="utf-8")) == report


@pytest.mark.parametrize("invalid", ["pdf", None, []])
def test_unsupported_fixture_format_is_rejected(tmp_path, invalid):
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    suite["examples"][0]["format"] = invalid
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite), encoding="utf-8")
    with pytest.raises(ValueError, match="format"):
        load_suite(path)


def test_capture_flag_requires_boolean(tmp_path):
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    suite["capture_backend_input"] = "true"
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite), encoding="utf-8")
    with pytest.raises(ValueError, match="boolean"):
        load_suite(path)


def test_format_comparison_records_recovery_without_assigning_quality_verdict(tmp_path):
    class DroppedMarkers:
        def translate(self, text, **kwargs):
            return "Hallo"

    report = evaluate_suite(load_suite(SUITE), DroppedMarkers(), tmp_path / "report", metadata={})
    results = report["results"]
    assert results[0]["actual"] == "Hallo"
    assert not results[0]["issues"]
    assert results[1]["actual"] == results[1]["source"]
    assert results[1]["issues"][0]["action"] == "retained_original"
    assert results[1]["issues"][0]["diagnostics"]["stage"] == "protected"
    assert all(item["verdict"] == "pending" for item in results)
