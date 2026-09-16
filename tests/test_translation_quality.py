"""Validate the quality fixture and runner using an offline substitute backend."""

import json

import pytest

from doc_lingo import TranslationError
from scripts import evaluate_translation_quality as runner
from scripts.evaluate_translation_quality import DEFAULT_SUITE, evaluate_suite, load_suite


def test_committed_suite_has_ten_unique_examples():
    suite = load_suite(DEFAULT_SUITE)
    assert len(suite["examples"]) == 10
    assert any(example.get("known_limitation") for example in suite["examples"])


@pytest.mark.parametrize("invalid", ["schema", "duplicate", "criteria", "source"])
def test_invalid_suite_is_rejected(tmp_path, invalid):
    suite = load_suite(DEFAULT_SUITE)
    if invalid == "schema":
        suite["schema_version"] = 99
    elif invalid == "duplicate":
        suite["examples"].append(suite["examples"][0])
    elif invalid == "criteria":
        suite["examples"][0]["criteria"] = []
    else:
        suite["examples"][0]["source"] = None
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite), encoding="utf-8")
    with pytest.raises(ValueError):
        load_suite(path)


@pytest.mark.parametrize("fail_first", [False, True])
def test_runner_records_outputs_without_assigning_quality_pass(tmp_path, fail_first):
    suite = load_suite(DEFAULT_SUITE)
    calls = []

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            calls.append(text)
            if fail_first and len(calls) == 1:
                raise TranslationError("secret diagnostic")
            assert (source_lang, target_lang) == ("en", "de")
            return text

    output = tmp_path / "run"
    report = evaluate_suite(suite, Backend(), output, metadata={"model": "test substitute"})
    assert report["complete"]
    assert len(report["results"]) == 10
    for index, result in enumerate(report["results"]):
        if fail_first and index == 0:
            assert result["verdict"] == "blocked"
            assert result["actual"] is None
            assert result["error"] == "TranslationError"
        else:
            assert result["verdict"] == "pending"
            assert result["actual"] == result["source"]
        assert result["reference"] == suite["examples"][index]["reference"]
    assert any("preserve its paragraph structure" in text for text in calls)
    assert len(calls) > 10  # Multi-segment examples exercise the real reader/service/writer.
    assert list(output.iterdir()) == [output / "report.json"]
    assert "secret diagnostic" not in (output / "report.json").read_text(encoding="utf-8")
    assert json.loads((output / "report.json").read_text(encoding="utf-8")) == report
    with pytest.raises(FileExistsError):
        evaluate_suite(suite, Backend(), output, metadata={})


def test_unexpected_failure_preserves_completed_results_and_cleans_temp(tmp_path):
    suite = load_suite(DEFAULT_SUITE)

    class Backend:
        calls = 0

        def translate(self, text, *, source_lang, target_lang):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("Programming error")
            return text

    output = tmp_path / "run"
    with pytest.raises(RuntimeError):
        evaluate_suite(suite, Backend(), output, metadata={})
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert not report["complete"]
    assert len(report["results"]) == 1
    assert list(output.iterdir()) == [output / "report.json"]


@pytest.mark.parametrize("selection", [None, "qwen", "marian"])
def test_runner_selects_backend_with_marian_default(tmp_path, monkeypatch, selection):
    backends = {"qwen": object(), "marian": object()}
    monkeypatch.setattr(runner, "HuggingFaceBackend", lambda: backends["qwen"])
    monkeypatch.setattr(runner, "MarianBackend", lambda: backends["marian"])
    monkeypatch.setattr(runner, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "runtime_metadata", lambda backend: {"test": True})
    calls = []

    def evaluate(suite, backend, output, *, metadata):
        calls.append(backend)
        return {"results": []}

    monkeypatch.setattr(runner, "evaluate_suite", evaluate)
    arguments = ["--output", str(tmp_path / "run")]
    if selection is not None:
        arguments += ["--backend", selection]
    runner.main(arguments)
    assert calls == [backends[selection or "marian"]]


@pytest.mark.parametrize(
    "backend,source,target",
    [
        ("marian", "de", "en"),
        ("marian", "en", "en"),
        ("qwen", "en", "fr"),
    ],
)
def test_runner_rejects_languages_before_runtime(
    tmp_path, monkeypatch, capsys, backend, source, target
):
    suite = load_suite(DEFAULT_SUITE)
    suite.update(source_lang=source, target_lang=target)
    monkeypatch.setattr(runner, "load_suite", lambda path: suite)
    monkeypatch.setattr(runner, "load_dotenv", lambda *a, **kw: pytest.fail("Environment loaded"))
    monkeypatch.setattr(runner, "runtime_metadata", lambda b: pytest.fail("Runtime loaded"))
    output = tmp_path / "report"
    with pytest.raises(SystemExit) as error:
        runner.main(["--backend", backend, "--output", str(output)])
    assert error.value.code == 2
    assert "supports only" in capsys.readouterr().err
    assert not output.exists()
