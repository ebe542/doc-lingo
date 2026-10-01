"""Check CLI translation and errors without GPU inference."""

from importlib.metadata import version

import pytest

from doc_lingo import SegmentMismatchError, TranslationError
from doc_lingo.interfaces import cli
from doc_lingo.interfaces.cli import main


@pytest.mark.parametrize("option", ["--help", "--version"])
def test_information_exits_successfully(option, capsys):
    with pytest.raises(SystemExit) as error:
        main([option])
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "doc-lingo" in output
    assert ("--target-lang" if option == "--help" else version("doc-lingo")) in output


def test_unsupported_format_is_rejected(tmp_path, capsys):
    document = tmp_path / "slides.odp"
    document.write_bytes(b"original document")
    with pytest.raises(SystemExit) as error:
        main([str(document), "--target-lang", "de"])
    assert error.value.code == 2
    assert "Only .txt" in capsys.readouterr().err
    assert document.read_bytes() == b"original document"
    assert list(tmp_path.iterdir()) == [document]


@pytest.mark.parametrize("arguments", [[], ["slides.odp"], ["--target-lang", "de"]])
def test_translation_requires_file_and_target_language(arguments):
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2


@pytest.mark.parametrize("explicit_output", [False, True])
@pytest.mark.parametrize("selection", [None, "marian", "qwen"])
def test_txt_translation(tmp_path, monkeypatch, capsys, explicit_output, selection):
    source = tmp_path / "book.txt"
    source.write_bytes(b"Hello\r\n\r\nWorld")
    destination = tmp_path / ("custom.txt" if explicit_output else "book.de.txt")
    calls = []

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            calls.append((source_lang, target_lang))
            return text.replace("Hello", "Hallo").replace("World", "Welt")

    selected_class = "HuggingFaceBackend" if selection == "qwen" else "MarianBackend"
    other_class = "MarianBackend" if selection == "qwen" else "HuggingFaceBackend"
    monkeypatch.setattr(cli, selected_class, Backend)
    monkeypatch.setattr(cli, other_class, lambda: pytest.fail("Wrong backend constructed"))
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)
    arguments = [str(source), "--target-lang", "de"]
    if selection:
        arguments += ["--backend", selection]
    if explicit_output:
        arguments += ["--output", str(destination)]
    main(arguments)
    assert destination.read_bytes() == b"Hallo\r\n\r\nWelt"
    assert source.read_bytes() == b"Hello\r\n\r\nWorld"
    assert calls == [("en", "de"), ("en", "de")]
    output = capsys.readouterr()
    assert str(destination) in output.out
    assert "Preparing translation" in output.err
    assert "Segments translated: 1 | Type: paragraph" in output.err
    assert "Segments translated: 2 | Type: paragraph" in output.err
    assert "Elapsed:" in output.err
    assert "Hallo" not in output.err


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (FileExistsError(), "Output already exists"),
        (FileNotFoundError(), "does not exist"),
        (PermissionError(), "Permission denied"),
        (UnicodeError(), "valid UTF-8"),
        (SegmentMismatchError(), "do not match"),
        (TranslationError("CUDA is unavailable"), "CUDA is unavailable"),
        (OSError(), "Document I/O failed"),
    ],
)
def test_expected_failures_exit_one(monkeypatch, capsys, failure, message):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cli, "translate_document", fail)
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)
    with pytest.raises(SystemExit) as error:
        main(["book.txt", "--target-lang", "de"])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert message in output.err
    assert not output.out


def test_invalid_output_extension(capsys):
    with pytest.raises(SystemExit) as error:
        main(["book.txt", "--target-lang", "de", "--output", "book.odp"])
    assert error.value.code == 2
    assert "Output must" in capsys.readouterr().err


@pytest.mark.parametrize("options", [[], ["--backend", "marian"], ["--backend", "unknown"]])
def test_invalid_backend_request_has_no_side_effects(tmp_path, monkeypatch, capsys, options):
    monkeypatch.setattr(cli, "load_dotenv", lambda **kw: pytest.fail("Environment loaded"))
    monkeypatch.setattr(cli, "MarianBackend", lambda: pytest.fail("Model constructed"))
    with pytest.raises(SystemExit) as error:
        main([str(tmp_path / "book.txt"), "--target-lang", "en", *options])
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())
    assert not capsys.readouterr().out


def test_qwen_same_language_retains_text_without_loading_model(tmp_path, monkeypatch):
    source = tmp_path / "book.txt"
    source.write_bytes(b"Hello\r\n")
    monkeypatch.setattr(cli, "load_dotenv", lambda **kw: None)
    monkeypatch.setattr(cli.HuggingFaceBackend, "_load", lambda self: pytest.fail("Model loaded"))
    main([str(source), "--target-lang", "en", "--backend", "qwen"])
    assert (tmp_path / "book.en.txt").read_bytes() == source.read_bytes()
