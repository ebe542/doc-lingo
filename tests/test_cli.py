"""Check the public CLI contract and protect documents during scaffolding."""

from importlib.metadata import version

import pytest

from doc_lingo.interfaces.cli import main


@pytest.mark.parametrize("option", ["--help", "--version"])
def test_information_exits_successfully(option, capsys):
    with pytest.raises(SystemExit) as error:
        main([option])
    assert error.value.code == 0
    output = capsys.readouterr().out
    assert "doc-lingo" in output
    assert ("--target-lang" if option == "--help" else version("doc-lingo")) in output


def test_translation_is_explicitly_unavailable(tmp_path, capsys):
    document = tmp_path / "slides.odp"
    document.write_bytes(b"original document")
    with pytest.raises(SystemExit) as error:
        main([str(document), "--target-lang", "de"])
    assert error.value.code == 2
    assert "not implemented yet" in capsys.readouterr().err
    assert document.read_bytes() == b"original document"
    assert list(tmp_path.iterdir()) == [document]


@pytest.mark.parametrize("arguments", [[], ["slides.odp"], ["--target-lang", "de"]])
def test_translation_requires_file_and_target_language(arguments):
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
