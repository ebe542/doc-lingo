"""CLI review workflows run with deterministic backends, never model downloads."""

import json

import pytest

from doc_lingo.interfaces import cli, review_cli
from doc_lingo.review import load_job, translate_text_job
from doc_lingo.review.jobs import ReviewJobError
from doc_lingo.translation.issues import retain_original
from doc_lingo.translation.protocols import TranslationError


class Backend:
    def translate(self, text, **kwargs):
        return text.replace("Hello", "Hallo").replace("World", "Welt")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.txt"
    path.write_bytes(b"\xef\xbb\xbfHello.\r\n\r\n- World.\r\n")
    return path


def prepare(source, output, *extra):
    cli.main(
        [
            "review",
            "prepare",
            str(source),
            "--target-lang",
            "de",
            "--output-dir",
            str(output),
            *extra,
        ]
    )


def test_prepare_edit_finalize_without_model_reload(source, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(review_cli, "MarianBackend", Backend)
    monkeypatch.setattr(review_cli, "load_dotenv", lambda **kw: None)
    directory = tmp_path / "review"
    prepare(source, directory)
    assert sorted(p.name for p in directory.iterdir()) == ["job.zip", "review.txt"]
    job = load_job(directory / "job.zip")
    assert job.source == source.read_bytes()
    assert job.source_name == "source.txt"
    assert job.blocks[0].proposal == "Hallo.\r\n"
    assert "Segments translated: 2" in capsys.readouterr().err
    review = directory / "review.txt"
    text = review.read_text(encoding="utf-8")
    first, second = text.split("=== Block 2 ===", 1)
    second = second.replace("--- Correction ---\n\n", "--- Correction ---\nMeine Welt.\n", 1)
    review.write_text(first + "=== Block 2 ===" + second, encoding="utf-8", newline="\n")

    def forbidden(*args, **kwargs):
        pytest.fail("Finalization must not load configuration or models")

    monkeypatch.setattr(review_cli, "MarianBackend", forbidden)
    monkeypatch.setattr(review_cli, "HuggingFaceBackend", forbidden)
    monkeypatch.setattr(review_cli, "load_dotenv", forbidden)
    output = tmp_path / "final.txt"
    cli.main(
        [
            "review",
            "finalize",
            str(directory / "job.zip"),
            str(review),
            "--output",
            str(output),
            "--original",
            str(source),
        ]
    )
    assert output.read_bytes() == b"\xef\xbb\xbfHallo.\r\n\r\n- Meine Welt.\r\n"
    assert "Review finalization complete" in capsys.readouterr().out
    assert not list(tmp_path.glob(".doc-lingo-*"))


def test_recovery_publishes_review_and_separate_diagnostics(source, tmp_path, monkeypatch):
    class Recovering:
        def translate(self, text, **kwargs):
            return retain_original(text, "Cannot translate this unit")

    monkeypatch.setattr(review_cli, "MarianBackend", Recovering)
    monkeypatch.setattr(review_cli, "load_dotenv", lambda **kw: None)
    directory = tmp_path / "review"
    with pytest.raises(SystemExit) as error:
        prepare(source, directory)
    assert error.value.code == 3
    job = load_job(directory / "job.zip")
    assert all(b.original == b.proposal for b in job.blocks)
    assert len((directory / "issues.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert (directory / "review.txt").exists()


@pytest.mark.parametrize(
    "kind", ["existing", "missing", "format", "language", "encoding", "glossary"]
)
def test_prepare_preflight_avoids_model_loading(source, tmp_path, monkeypatch, kind):
    monkeypatch.setattr(review_cli, "MarianBackend", lambda: pytest.fail("must not load"))
    output = tmp_path / "review"
    extra = []
    if kind == "existing":
        output.mkdir()
        (output / "keep").write_bytes(b"keep")
    elif kind == "missing":
        source.unlink()
    elif kind == "format":
        source = source.with_suffix(".odt")
    elif kind == "language":
        extra = ["--target-lang", "en"]
    elif kind == "encoding":
        source.write_bytes(b"\xff")
    else:
        extra = ["--glossary", str(tmp_path / "missing.json")]
    with pytest.raises(SystemExit) as error:
        prepare(source, output, *extra)
    assert error.value.code in (1, 2)
    if kind == "existing":
        assert (output / "keep").read_bytes() == b"keep"
    else:
        assert not output.exists()


def test_qwen_prepare_and_unreadable_dotenv(source, tmp_path, monkeypatch):
    monkeypatch.setattr(review_cli, "HuggingFaceBackend", Backend)

    def unreadable(**kwargs):
        raise OSError("unreadable")

    monkeypatch.setattr(review_cli, "load_dotenv", unreadable)
    prepare(source, tmp_path / "review", "--backend", "qwen")
    assert (tmp_path / "review/job.zip").is_file()


@pytest.mark.parametrize("stage", ["translate", "export", "publish"])
def test_failures_do_not_publish_incomplete_job(source, tmp_path, monkeypatch, stage):
    monkeypatch.setattr(review_cli, "MarianBackend", Backend)
    monkeypatch.setattr(review_cli, "load_dotenv", lambda **kw: None)

    def fail(*args, **kwargs):
        raise TranslationError("failed")

    if stage == "translate":
        monkeypatch.setattr(review_cli, "translate_text_job", fail)
    elif stage == "export":
        monkeypatch.setattr(review_cli, "export_review_txt", fail)
    else:
        real_link = review_cli.os.link
        published = 0

        def fail_publication(source, target):
            nonlocal published
            if target.parent == tmp_path / "review":
                published += 1
                if published == 2:
                    raise OSError("publication failed")
            return real_link(source, target)

        monkeypatch.setattr(review_cli.os, "link", fail_publication)
    with pytest.raises(SystemExit) as error:
        prepare(source, tmp_path / "review")
    assert error.value.code == 1
    assert not (tmp_path / "review").exists()
    assert not list(tmp_path.glob(".doc-lingo-*"))


def test_job_creation_detects_source_change(source):
    class Changing:
        def translate(self, text, **kwargs):
            source.write_bytes(b"changed")
            return text

    with pytest.raises(ReviewJobError, match="changed"):
        translate_text_job(source, Changing(), source_lang="en", target_lang="de")


@pytest.mark.parametrize("command", [[], ["prepare"], ["finalize"]])
def test_review_help_does_not_load_configuration(monkeypatch, command):
    monkeypatch.setattr(review_cli, "load_dotenv", lambda **kw: pytest.fail("no dotenv"))
    with pytest.raises(SystemExit) as error:
        cli.main(["review", *command, "--help"])
    assert error.value.code == 0


def test_finalize_rejects_existing_output_and_wrong_extension(tmp_path):
    output = tmp_path / "out.txt"
    output.write_bytes(b"keep")
    for target, code in ((output, 1), (tmp_path / "out.odt", 2)):
        with pytest.raises(SystemExit) as error:
            cli.main(["review", "finalize", "missing.zip", "missing.odt", "--output", str(target)])
        assert error.value.code == code
    assert output.read_bytes() == b"keep"


@pytest.mark.parametrize("language", ["de", "en"])
def test_glossary_is_applied_or_rejected_before_translation(
    source, tmp_path, monkeypatch, language
):
    glossary = tmp_path / "glossary.json"
    glossary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_lang": "en",
                "target_lang": language,
                "entries": [{"source": "World", "mode": "translate", "target": "Erde"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_cli, "load_dotenv", lambda **kw: None)
    output = tmp_path / "review"
    if language == "en":
        monkeypatch.setattr(review_cli, "MarianBackend", lambda: pytest.fail("must not load"))
        with pytest.raises(SystemExit) as error:
            prepare(source, output, "--glossary", str(glossary))
        assert error.value.code == 1
        assert not output.exists()
    else:
        monkeypatch.setattr(review_cli, "MarianBackend", Backend)
        prepare(source, output, "--glossary", str(glossary))
        assert "Erde" in load_job(output / "job.zip").blocks[1].proposal
