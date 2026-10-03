"""Active Markdown path with deterministic CPU-free backend and aligner doubles."""

import json
import re

import pytest

from doc_lingo import MarkdownReader, MarkdownWriter, translate_document
from doc_lingo.interfaces import cli
from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)
from doc_lingo.translation.issues import RecoverableTranslationError


class Backend:
    def translate(self, text, **kwargs):
        assert "**" not in text and "](url)" not in text
        return "Schalte Gerät aus."


class Aligner:
    def align(self, source, target):
        vocabulary = {"Turn": "Schalte", "off": "aus", "device": "Gerät", ".": "."}
        links = []
        for match in re.finditer(r"\w+|[^\w\s]", source):
            word = vocabulary[match.group()]
            start = target.index(word)
            links.append(
                AlignmentLink(
                    (TextRange(match.start(), match.end()),), (TextRange(start, start + len(word)),)
                )
            )
        return AlignmentResult(source, target, tuple(links))


@pytest.mark.parametrize(
    "wrapper,closing,action",
    [
        ('<strong class="important">', "</strong>", "formatting_split"),
        ('<em title="Keep English">', "</em>", "formatting_split"),
        (
            '<a href="https://example.org/?a=1&amp;b=2" title="Keep English">',
            "</a>",
            "formatting_expanded",
        ),
    ],
)
@pytest.mark.parametrize("block", [False, True])
def test_html_alignment_preserves_exact_attributes(tmp_path, wrapper, closing, action, block):
    prefix = '<div class="outer"><p>' if block else ""
    suffix = "</p></div>" if block else ""
    original = prefix + wrapper + "Turn off" + closing + " device." + suffix
    source = tmp_path / "source.md"
    source.write_text(original, encoding="utf-8", newline="\n")
    output = tmp_path / "out.md"
    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Aligner(),
        on_issue=issues.append,
    )
    expected = (
        wrapper + "Schalte Gerät aus" + closing + "."
        if action == "formatting_expanded"
        else wrapper + "Schalte" + closing + " Gerät " + wrapper + "aus" + closing + "."
    )
    assert output.read_text(encoding="utf-8") == prefix + expected + suffix
    assert [issue.action for issue in issues] == [action]


@pytest.mark.parametrize("prefix", ["# ", "## ", "- ", "1. ", "> "])
@pytest.mark.parametrize("ending", ["\n\n", "\r\n\r\n"])
def test_block_envelope_stays_outside_models(tmp_path, prefix, ending):
    class InspectBackend(Backend):
        def translate(self, text, **kwargs):
            assert text == "Turn off device."
            return super().translate(text, **kwargs)

    source = tmp_path / "source.md"
    source.write_bytes((prefix + "**Turn off** device." + ending).encode())
    output = tmp_path / "out.md"
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        InspectBackend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Aligner(),
        on_issue=lambda issue: None,
    )
    assert output.read_bytes() == (prefix + "**Schalte** Gerät **aus**." + ending).encode()


def test_multiline_item_accepts_removed_softbreak(tmp_path):
    class FailedAligner:
        def align(self, source, target):
            raise AlignmentError("no alignment")

    source = tmp_path / "source.md"
    original = "- Turn off\n  device.\n"
    source.write_text(original, encoding="utf-8", newline="\n")
    output = tmp_path / "out.md"
    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=FailedAligner(),
        on_issue=issues.append,
    )
    retained = [issue for issue in issues if issue.action == "retained_original"]
    assert not retained
    assert output.read_bytes() == "- Schalte Gerät aus.\n".encode()


@pytest.mark.parametrize(
    "original,target,allowed",
    [
        ("One\ntwo.", "Eins zwei.", True),
        ("One two.", "Eins\nzwei.", True),
        ("One  \ntwo.", "Eins zwei.", False),
        ("One\\\ntwo.", "Eins zwei.", False),
        ("One two.", "Eins  \nzwei.", False),
        ("One two.", "Eins\n\nzwei.", False),
        ("- One two.", "- Eins\n- zwei.", False),
        ("One two.", "# Eins zwei.", False),
    ],
)
def test_aligned_validation_relaxes_only_softbreaks(original, target, allowed):
    from doc_lingo.documents.markdown._parser import _MarkdownSegment
    from doc_lingo.documents.markdown.aligned import AlignedMarkdownSegment, aligned_errors
    from doc_lingo.translation.formatting import FormattingProjection
    from doc_lingo.translation.formatting_bridge import RestoredFormatting

    source = _MarkdownSegment("x", original)
    evidence = RestoredFormatting(target, FormattingProjection((), ()))
    translated = AlignedMarkdownSegment("x", target, restored=evidence)
    errors = aligned_errors(source, translated)
    assert (not errors) == allowed
    if allowed:
        assert source.validation_errors(target)  # Legacy validation stays strict.


def test_aligned_table_cell_still_rejects_newline():
    from doc_lingo.documents.markdown._parser import _MarkdownSegment

    source = _MarkdownSegment("x", "One two", type="table_cell")
    assert source.validation_errors("Eins\nzwei", allow_softbreaks=True) == (
        "markdown_table_cell_boundary_changed",
    )


@pytest.mark.parametrize(
    "source,expected,action",
    [
        ("**Turn off** device.", "**Schalte** Gerät **aus**.", "formatting_split"),
        ("[Turn off](url) device.", "[Schalte Gerät aus](url).", "formatting_expanded"),
    ],
)
def test_complete_service_and_writer(tmp_path, source, expected, action):
    path = tmp_path / "source.md"
    path.write_text(source, encoding="utf-8")
    output = tmp_path / "out.md"
    issues = []
    translate_document(
        MarkdownReader(path),
        MarkdownWriter(path),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Aligner(),
        on_issue=issues.append,
    )
    assert output.read_text(encoding="utf-8") == expected
    assert issues[0].action == action
    assert issues[0].segment_number == issues[0].paragraph_number == 1


@pytest.mark.parametrize("failure", ["alignment", "mismatch", "empty", "structure", "recovery"])
def test_recovery_paths(tmp_path, failure):
    class TestBackend(Backend):
        def translate(self, text, **kwargs):
            if failure == "empty":
                return ""
            if failure == "structure":
                return "# New heading"
            if failure == "recovery":
                raise RecoverableTranslationError("local failure")
            return super().translate(text, **kwargs)

    class TestAligner(Aligner):
        def align(self, source, target):
            if failure == "mismatch":
                return AlignmentResult("x", "y", unaligned=(TextRange(0, 1),))
            raise AlignmentError("encoder limit")

    path = tmp_path / "source.md"
    original = "**Turn off** device."
    path.write_text(original, encoding="utf-8")
    output = tmp_path / "out.md"
    issues = []
    translate_document(
        MarkdownReader(path),
        MarkdownWriter(path),
        TestBackend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=TestAligner(),
        on_issue=issues.append,
    )
    expected = "Schalte Gerät aus." if failure in ("alignment", "mismatch") else original
    assert output.read_text(encoding="utf-8") == expected
    assert issues


def test_cli_loads_explicit_model_and_logs_formatting_warning(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.md"
    source.write_text("**Turn off** device.", encoding="utf-8")
    monkeypatch.setattr(cli, "MarianBackend", Backend)
    calls = []

    def load(path):
        calls.append(path)
        return Aligner()

    monkeypatch.setattr(cli.AwesomeAlignAdapter, "load", load)
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                str(source),
                "--target-lang",
                "de",
                "--aligner",
                "awesome",
                "--alignment-model",
                "local-model",
            ]
        )
    assert error.value.code == 3
    assert calls == ["local-model"]
    assert "0 original text units retained" in capsys.readouterr().err
    report = source.with_name("source.de.md.issues.jsonl")
    assert json.loads(report.read_text(encoding="utf-8"))["action"] == "formatting_split"


@pytest.mark.parametrize(
    "filename,options",
    [
        ("x.md", ["--aligner", "awesome"]),
        ("x.md", ["--alignment-model", "model"]),
        ("x.txt", ["--aligner", "awesome", "--alignment-model", "model"]),
    ],
)
def test_invalid_cli_selection(filename, options):
    with pytest.raises(SystemExit) as error:
        cli.main([filename, "--target-lang", "de", *options])
    assert error.value.code == 2


def test_opaque_input_bypasses_models_and_html_uses_legacy_path():
    from doc_lingo.documents.markdown._parser import _MarkdownSegment
    from doc_lingo.documents.models import TextSegment
    from doc_lingo.translation.aligned_markdown import translate_aligned

    kwargs = dict(source_lang="en", target_lang="de", report=lambda *a, **k: None)
    assert translate_aligned(TextSegment("x", "text"), None, None, **kwargs) is None
    assert translate_aligned(_MarkdownSegment("x", "<div>text</div>"), None, None, **kwargs) is None
    source = _MarkdownSegment("x", "`code`", protected_spans=((0, 6),))
    assert translate_aligned(source, None, None, **kwargs).text == source.text


def test_writer_evidence_requires_matching_markdown_source():
    from doc_lingo.documents.markdown.aligned import AlignedMarkdownSegment, accepts_aligned
    from doc_lingo.documents.models import TextSegment

    assert not accepts_aligned(TextSegment("x", "x"), AlignedMarkdownSegment("x", "x"))


def test_missing_protected_marker_retains_original(tmp_path):
    class FailedAligner:
        def align(self, source, target):
            raise AlignmentError("no correspondence")

    source = tmp_path / "source.md"
    source.write_text("Use `code` now.", encoding="utf-8")
    output = tmp_path / "out.md"
    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=FailedAligner(),
        on_issue=issues.append,
    )
    assert output.read_text(encoding="utf-8") == "Use `code` now."
    assert issues[-1].action == "retained_original"
