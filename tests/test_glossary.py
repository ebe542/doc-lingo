"""Terminology policy and failure handling without model downloads."""

import gzip
import json
import re

import pytest

from doc_lingo import Glossary, GlossaryBackend, GlossaryEntry, TranslationError
from doc_lingo.interfaces import cli
from doc_lingo.translation.issues import issue_sink, retain_original


def test_json_and_gzip_have_identical_rules(tmp_path):
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / "docs/examples/glossary-en-de.json"
    plain = tmp_path / "terms.json"
    packed = tmp_path / "terms.json.gz"
    plain.write_bytes(example.read_bytes())
    packed.write_bytes(gzip.compress(plain.read_bytes(), mtime=0))
    assert Glossary.load(plain) == Glossary.load(packed)
    for path in (plain, packed):
        result = GlossaryBackend(Echo(), Glossary.load(path)).translate(
            "multiclass classification; training data; LLM",
            source_lang="en",
            target_lang="de",
        )
        assert result == (
            "Mehrklassenklassifikation (multiclass classification); "
            "Trainingsdaten (training data); LLM"
        )


@pytest.mark.parametrize("data", [b"not gzip", gzip.compress(b"{}")[:-5], gzip.compress(b"\xff")])
def test_invalid_compressed_glossary(tmp_path, data):
    path = tmp_path / "invalid.json.gz"
    path.write_bytes(data)
    with pytest.raises((ValueError, OSError, UnicodeError)):
        Glossary.load(path)


@pytest.mark.parametrize("value", [None, 12, [], {}])
def test_nonstring_entry_rejected(value):
    with pytest.raises(ValueError):
        Glossary("en", "de", (GlossaryEntry(value, "keep"),))


@pytest.mark.parametrize(
    "source,text", [("Straße", "STRAẞE"), ("index", "İndex"), ("kernel", "Kernel")]
)
def test_unicode_match_resolves_to_the_matching_entry(source, text):
    backend = GlossaryBackend(
        Echo(), Glossary("en", "de", (GlossaryEntry(source, "translate", "Result"),))
    )
    assert backend.translate(text, source_lang="en", target_lang="de") == "Result"


def test_many_repeated_matches_restore_without_cascading():
    entries = tuple(
        GlossaryEntry(f"word{i:04d}", "translate", f"target{i:04d}") for i in range(1000)
    )
    backend = GlossaryBackend(Echo(), Glossary("en", "de", entries))
    source = "word0999 word0000 " * 50
    assert (
        backend.translate(source, source_lang="en", target_lang="de")
        == "Target0999 target0000 " + "target0999 target0000 " * 49
    )


class Echo:
    def translate(self, text, **kwargs):
        return text


@pytest.mark.parametrize(
    "mode,target,expected",
    [
        ("translate", "klassifikation", "Klassifikation"),
        ("annotate", "klassifikation", "Klassifikation (Classification)"),
        ("keep", "", "Classification"),
    ],
)
@pytest.mark.parametrize("leading,trailing", [("", ""), (" \t", "\r\n"), ("", "\n")])
def test_whole_segment_uses_glossary_without_inference(mode, target, expected, leading, trailing):
    class Unused:
        def translate(self, *args, **kwargs):
            pytest.fail("Whole glossary term must not reach the model")

    backend = GlossaryBackend(
        Unused(), Glossary("en", "de", (GlossaryEntry("classification", mode, target),))
    )
    token = issue_sink.set(lambda *args: pytest.fail("Unexpected fallback"))
    try:
        assert (
            backend.translate(
                leading + "Classification" + trailing, source_lang="en", target_lang="de"
            )
            == leading + expected + trailing
        )
    finally:
        issue_sink.reset(token)


@pytest.mark.parametrize("text", ["Classification.", "Classification helps", "Classification RAG"])
def test_partial_segment_still_uses_model(text):
    calls = []

    class Recording:
        def translate(self, text, **kwargs):
            calls.append(text)
            return text

    backend = GlossaryBackend(
        Recording(),
        Glossary(
            "en",
            "de",
            (
                GlossaryEntry("classification", "translate", "Klassifikation"),
                GlossaryEntry("RAG", "keep"),
            ),
        ),
    )
    backend.translate(text, source_lang="en", target_lang="de")
    assert len(calls) == 1


def test_modes_longest_match_boundaries_and_no_cascading():
    glossary = Glossary(
        "en",
        "de",
        (
            GlossaryEntry("learning", "translate", "Lernen"),
            GlossaryEntry("machine learning", "annotate", "maschinelles Lernen"),
            GlossaryEntry("RAG", "keep"),
            GlossaryEntry("classification", "translate", "Klassifikation"),
        ),
    )
    backend = GlossaryBackend(Echo(), glossary)
    assert (
        backend.translate(
            "Machine learning; classification; RAG; unlearning.", source_lang="en", target_lang="de"
        )
        == "Maschinelles Lernen (Machine learning); Klassifikation; RAG; unlearning."
    )
    assert backend.translate("No match.", source_lang="en", target_lang="de") == "No match."
    with pytest.raises(TranslationError, match="languages"):
        backend.translate("RAG", source_lang="de", target_lang="en")


@pytest.mark.parametrize("damage", ["missing", "duplicate", "fallback", "fatal", "extra"])
def test_bad_protection_never_leaks_markers(damage):
    class Broken:
        def translate(self, text, **kwargs):
            marker = re.search(r"DLG[A-F0-9]+X0Z", text).group()
            if damage == "fatal":
                raise TranslationError("Model unavailable")
            if damage == "fallback":
                return retain_original(text, "Unit failed")
            if damage == "extra":
                return text + marker[:-3] + "X99Z"
            return text.replace(marker, "") if damage == "missing" else text + marker

    backend = GlossaryBackend(Broken(), Glossary("en", "de", (GlossaryEntry("RAG", "keep"),)))
    issues = []
    token = issue_sink.set(lambda text, reason: issues.append((text, reason)))
    try:
        if damage == "fatal":
            with pytest.raises(TranslationError, match="Model unavailable"):
                backend.translate("RAG works.", source_lang="en", target_lang="de")
            assert issues == []
        else:
            assert (
                backend.translate("RAG works.", source_lang="en", target_lang="de") == "RAG works."
            )
            assert len(issues) == 1
            assert issues[0][0] == "RAG works."
    finally:
        issue_sink.reset(token)


@pytest.mark.parametrize(
    "entry",
    [
        {"source": "", "mode": "keep"},
        {"source": "term", "mode": "invalid"},
        {"source": "term", "mode": "translate"},
        {"source": "term", "mode": "keep", "target": "unexpected"},
    ],
)
def test_invalid_entries_are_rejected(tmp_path, entry):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {"schema_version": 1, "source_lang": "en", "target_lang": "de", "entries": [entry]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        Glossary.load(path)


@pytest.mark.parametrize("compressed", [False, True])
def test_cli_glossary_is_applied(tmp_path, monkeypatch, compressed):
    source = tmp_path / "source.txt"
    source.write_text("Classification", encoding="utf-8")
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_lang": "en",
                "target_lang": "de",
                "entries": [
                    {"source": "classification", "mode": "translate", "target": "Klassifikation"}
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "MarianBackend", Echo)
    monkeypatch.setattr(cli, "load_dotenv", lambda **kw: None)
    if compressed:
        packed = tmp_path / "glossary.json.gz"
        packed.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
        path = packed
    cli.main([str(source), "--target-lang", "de", "--glossary", str(path)])
    assert (tmp_path / "source.de.txt").read_text(encoding="utf-8") == "Klassifikation"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--target-lang", "de", "--glossary", str(path)])
    assert error.value.code == 2
