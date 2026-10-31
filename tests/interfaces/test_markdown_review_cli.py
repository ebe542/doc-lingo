"""Markdown review CLI uses fake translation/alignment, never model downloads."""

import json

import pytest

from doc_lingo.interfaces import cli, review_cli
from doc_lingo.review import load_job
from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)


class Backend:
    def translate(self, text, **kwargs):
        return text.replace("Hello", "Hallo")


@pytest.fixture(autouse=True)
def fake_runtime(monkeypatch):
    monkeypatch.setattr(review_cli, "load_dotenv", lambda **kw: None)
    monkeypatch.setattr(review_cli, "MarianBackend", Backend)
    monkeypatch.setattr(review_cli, "HuggingFaceBackend", Backend)


def prepare(tmp_path, text="Read **Hello**.\n", extra=()):
    source = tmp_path / "source.md"
    source.write_text(text, encoding="utf-8", newline="\n")
    root = tmp_path / "review"
    cli.main(
        ["review", "prepare", str(source), "--target-lang", "de", "--output-dir", str(root), *extra]
    )
    return source, root


def finalize(root, output, *extra):
    cli.main(
        [
            "review",
            "finalize",
            str(root / "job.zip"),
            str(root / "review.txt"),
            "--output",
            str(output),
            *extra,
        ]
    )


def test_prepare_edit_finalize_without_loading_models(tmp_path, monkeypatch, capsys):
    source, root = prepare(tmp_path, "# Hello\n\nCall `predict()`.\n")
    job = load_job(root / "job.zip")
    assert job.document_format == "md" and job.schema_version == 2
    assert job.blocks[0].proposal == "Hallo"
    assert job.blocks[1].proposal == "Call predict()."
    assert sorted(p.name for p in root.iterdir()) == ["job.zip", "review.txt"]
    text = (root / "review.txt").read_text(encoding="utf-8")
    assert "`predict()`" not in text and "DLM" not in text
    first, second = text.split("=== Block 2 ===", 1)
    second = second.replace(
        "--- Correction ---\n\n", "--- Correction ---\nBitte predict() aufrufen.\n"
    )
    (root / "review.txt").write_text(
        first + "=== Block 2 ===" + second, encoding="utf-8", newline="\n"
    )

    def forbidden(*args, **kwargs):
        pytest.fail(
            "Finalization must not load translators, configuration or an unrequested aligner"
        )

    monkeypatch.setattr(review_cli, "MarianBackend", forbidden)
    monkeypatch.setattr(review_cli, "HuggingFaceBackend", forbidden)
    monkeypatch.setattr(review_cli, "load_dotenv", forbidden)
    monkeypatch.setattr(review_cli.AwesomeAlignAdapter, "load", forbidden)
    output = tmp_path / "final.md"
    finalize(root, output, "--original", str(source))
    assert output.read_text(encoding="utf-8") == "# Hallo\n\nBitte `predict()` aufrufen\\.\n"
    assert not output.with_name(output.name + ".issues.jsonl").exists()
    messages = capsys.readouterr()
    assert "Segments translated: 2" in messages.err
    assert "Review finalization complete" in messages.out
    assert not list(tmp_path.glob(".doc-lingo-*"))


def test_formatting_warnings_publish_document_and_report(tmp_path, capsys):
    _, root = prepare(tmp_path)
    output = tmp_path / "final.md"
    with pytest.raises(SystemExit) as error:
        finalize(root, output)
    assert error.value.code == 3
    assert output.read_text(encoding="utf-8") == "Read Hallo\\.\n"
    report = output.with_name(output.name + ".issues.jsonl")
    rows = [json.loads(row) for row in report.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["action"] == "formatting_dropped"
    assert rows[0]["segment_id"] == "1"
    assert rows[0]["diagnostics"]["attempted_translation"] == "Read Hallo."
    assert "Review finalization complete" in capsys.readouterr().out


def test_optional_aligner_is_used_only_for_finalization(tmp_path, monkeypatch):
    calls = []

    class Aligner:
        def align(self, source, target):
            calls.append((source, target))
            return AlignmentResult(
                source,
                target,
                (AlignmentLink((TextRange(5, 10),), (TextRange(5, 10),)),),
                (TextRange(0, 5), TextRange(10, 11)),
            )

    model = tmp_path / "model"
    model.mkdir()
    loads = []

    def load(path):
        loads.append(path)
        return Aligner()

    monkeypatch.setattr(review_cli.AwesomeAlignAdapter, "load", load)
    _, root = prepare(tmp_path)
    assert loads == []
    output = tmp_path / "final.md"
    finalize(root, output, "--aligner", "awesome", "--alignment-model", str(model))
    assert loads == [str(model)]
    assert calls == [("Read Hello.", "Read Hallo.")]
    assert output.read_text(encoding="utf-8") == "Read **Hallo**\\.\n"


@pytest.mark.parametrize("text", ["Use <b>Hello</b> now.", "Use `model` and `model`."])
def test_unsupported_markdown_is_rejected_before_runtime(tmp_path, monkeypatch, text):
    monkeypatch.setattr(review_cli, "load_dotenv", lambda **kw: pytest.fail("no dotenv"))
    monkeypatch.setattr(review_cli, "MarianBackend", lambda: pytest.fail("no backend"))
    with pytest.raises(SystemExit) as error:
        prepare(tmp_path, text)
    assert error.value.code == 1
    assert not (tmp_path / "review").exists()


def test_missing_markers_retain_source_and_continue(tmp_path, monkeypatch):
    class Missing:
        def translate(self, text, **kwargs):
            return "Code lost." if "DLM" in text else text.replace("Hello", "Hallo")

    monkeypatch.setattr(review_cli, "MarianBackend", Missing)
    with pytest.raises(SystemExit) as error:
        prepare(tmp_path, "Call `predict()`.\n\nHello.\n")
    assert error.value.code == 3
    root = tmp_path / "review"
    job = load_job(root / "job.zip")
    assert [b.proposal for b in job.blocks] == ["Call predict().", "Hallo."]
    rows = [
        json.loads(row) for row in (root / "issues.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1 and rows[0]["original"] == "Call predict()."


@pytest.mark.parametrize(
    "kind", ["extension", "pair", "missing_model", "original", "review", "report"]
)
def test_finalize_preflight_avoids_aligner_loading(tmp_path, monkeypatch, kind):
    source, root = prepare(tmp_path)
    model = tmp_path / "model"
    model.mkdir()
    output = tmp_path / "final.md"
    extra = ["--aligner", "awesome", "--alignment-model", str(model)]
    if kind == "extension":
        output = output.with_suffix(".txt")
    elif kind == "pair":
        extra = ["--aligner", "awesome"]
    elif kind == "missing_model":
        model.rmdir()
    elif kind == "original":
        source.write_bytes(b"changed")
        extra += ["--original", str(source)]
    elif kind == "review":
        (root / "review.txt").write_bytes(b"invalid")
    else:
        output.with_name(output.name + ".issues.jsonl").write_bytes(b"keep")
    monkeypatch.setattr(
        review_cli.AwesomeAlignAdapter, "load", lambda *args: pytest.fail("no load")
    )
    with pytest.raises(SystemExit) as error:
        finalize(root, output, *extra)
    assert error.value.code == (2 if kind in ("extension", "pair") else 1)
    assert not output.exists()
    if kind == "report":
        assert output.with_name(output.name + ".issues.jsonl").read_bytes() == b"keep"


def test_alignment_loader_failure_does_not_publish(tmp_path, monkeypatch):
    _, root = prepare(tmp_path)
    model = tmp_path / "model"
    model.mkdir()

    def fail(path):
        raise AlignmentError("cannot load")

    monkeypatch.setattr(review_cli.AwesomeAlignAdapter, "load", fail)
    output = tmp_path / "final.md"
    with pytest.raises(SystemExit) as error:
        finalize(root, output, "--aligner", "awesome", "--alignment-model", str(model))
    assert error.value.code == 1
    assert not output.exists()
    assert not output.with_name(output.name + ".issues.jsonl").exists()


def test_final_publication_failure_removes_own_report(tmp_path, monkeypatch):
    _, root = prepare(tmp_path)
    output = tmp_path / "final.md"
    real_link = review_cli.os.link

    def fail(source, target):
        if target == output:
            raise OSError("publication failed")
        return real_link(source, target)

    monkeypatch.setattr(review_cli.os, "link", fail)
    with pytest.raises(SystemExit) as error:
        finalize(root, output)
    assert error.value.code == 1
    assert not output.exists()
    assert not output.with_name(output.name + ".issues.jsonl").exists()
    assert (root / "review.txt").exists()
    assert not list(tmp_path.glob(".doc-lingo-*"))


def test_txt_job_rejects_alignment_options(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_bytes(b"Hello.\n")
    root = tmp_path / "review"
    cli.main(["review", "prepare", str(source), "--target-lang", "de", "--output-dir", str(root)])
    model = tmp_path / "model"
    model.mkdir()
    monkeypatch.setattr(
        review_cli.AwesomeAlignAdapter, "load", lambda *args: pytest.fail("no load")
    )
    with pytest.raises(SystemExit) as error:
        finalize(
            root, tmp_path / "out.txt", "--aligner", "awesome", "--alignment-model", str(model)
        )
    assert error.value.code == 2
    assert not (tmp_path / "out.txt").exists()


def test_markdown_glossary_does_not_change_protected_code(tmp_path):
    glossary = tmp_path / "glossary.json"
    glossary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_lang": "en",
                "target_lang": "de",
                "entries": [
                    {"source": "Hello", "mode": "translate", "target": "Grüße"},
                    {"source": "predict", "mode": "translate", "target": "vorhersagen"},
                ],
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    _, root = prepare(tmp_path, "Hello with `predict()`.\n", ("--glossary", str(glossary)))
    proposal = load_job(root / "job.zip").blocks[0].proposal
    assert "Grüße" in proposal
    assert "predict()" in proposal and "vorhersagen" not in proposal
