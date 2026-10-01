"""Verify benchmark results and temporary-file cleanup without timing thresholds."""

import json

import pytest

from scripts import benchmark_glossary


def test_benchmark_report_and_cleanup(tmp_path):
    output = tmp_path / "benchmark.json"
    benchmark_glossary.main(["--sizes", "3", "--repeats", "1", "--output", str(output)])
    report = json.loads(output.read_text(encoding="utf-8"))
    result = report["results"][0]
    assert result["entries"] == 3
    assert result["gzip_bytes"] < result["json_bytes"]
    assert set(result["cases"]) == {"no_hits", "near_misses", "late_hit", "dense_hits"}
    assert result["load_build_python_peak_bytes"] > 0
    assert list(tmp_path.iterdir()) == [output]
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        benchmark_glossary.main(["--output", str(output)])
    assert output.read_bytes() == original


def test_benchmark_removes_temporary_inputs_on_failure(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError("Measurement failed")

    monkeypatch.setattr(benchmark_glossary, "measure", fail)
    output = tmp_path / "benchmark.json"
    with pytest.raises(RuntimeError):
        benchmark_glossary.main(["--output", str(output)])
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("options", [["--sizes", "0"], ["--repeats", "0"]])
def test_invalid_measurement_arguments(tmp_path, options):
    with pytest.raises(SystemExit) as error:
        benchmark_glossary.main(["--output", str(tmp_path / "report.json"), *options])
    assert error.value.code == 2
    assert list(tmp_path.iterdir()) == []
