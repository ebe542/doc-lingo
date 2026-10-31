"""Reviewed text stays authoritative while Markdown structure is reconstructed."""

from pathlib import Path

import pytest

from doc_lingo import TextSegment
from doc_lingo.review import (
    ReviewJobError,
    create_markdown_job,
    create_text_job,
    export_review_txt,
    finalize_markdown_review,
    markdown_review_segments,
)
from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)


def prepare(tmp_path, original, targets):
    source = tmp_path / "source.md"
    source.write_bytes(original.encode("utf-8"))
    segments = markdown_review_segments(source)
    job = create_markdown_job(
        source,
        [TextSegment(s.id, t, s.type) for s, t in zip(segments, targets, strict=True)],
        source_lang="en",
        target_lang="de",
    )
    review = tmp_path / "review.txt"
    export_review_txt(job, review)
    return job, review, tmp_path / "final.md"


class WordAligner:
    def __init__(self, pairs):
        self.pairs = pairs
        self.calls = []

    def align(self, source, target):
        self.calls.append((source, target))
        links = tuple(
            AlignmentLink(
                (TextRange(source.index(a), source.index(a) + len(a)),),
                (TextRange(target.index(b), target.index(b) + len(b)),),
            )
            for a, b in self.pairs
        )
        unaligned = []
        cursor = 0
        for span in sorted(link.source_ranges[0] for link in links):
            if cursor < span.start:
                unaligned.append(TextRange(cursor, span.start))
            cursor = span.end
        if cursor < len(source):
            unaligned.append(TextRange(cursor, len(source)))
        return AlignmentResult(source, target, links, tuple(unaligned))


def test_unchanged_source_is_byte_exact_and_does_not_align(tmp_path):
    original = (
        "\ufeff# Title ###\r\n\r\n- Read **this** and `code()`.\r\n\r\n```py\r\n# keep\r\n```\r\n"
    )
    job, review, output = prepare(tmp_path, original, ["Title", "Read this and code()."])

    class Forbidden:
        def align(self, *args):
            pytest.fail("Unchanged text must not need alignment")

    assert finalize_markdown_review(job, review, output, aligner=Forbidden()) == ()
    assert output.read_bytes() == original.encode("utf-8")


@pytest.mark.parametrize(
    "source, target, expected",
    [
        ("# Hello ###\r\n", "Hallo", "# Hallo ###\r\n"),
        ("Hello\n=====\n", "Hallo", "Hallo\n=====\n"),
        ("- Hello\n  world.\n", "Hallo Welt.", "- Hallo Welt\\.\n"),
        ("> Hello\n> world.\n", "Hallo\nWelt.", "> Hallo\n> Welt\\.\n"),
        ("1. Hello.\n", "Hallo\nWelt.", "1. Hallo\n   Welt\\.\n"),
        ("**Hello.**\n", "Hallo Welt.", "**Hallo Welt\\.**\n"),
        (
            "Keep `model` unchanged.\n",
            "model unverändert lassen.",
            "`model` unverändert lassen\\.\n",
        ),
        ("Call `` a`b `` now.\n", "Jetzt a`b verwenden.", "Jetzt `` a`b `` verwenden\\.\n"),
        (
            "See [guide] now.\n\n[guide]: /help\n",
            "Jetzt guide lesen.",
            "Jetzt [guide] lesen\\.\n\n[guide]: /help\n",
        ),
        (
            "Mail <a@example.org> now.\n",
            "Jetzt a@example.org schreiben.",
            "Jetzt <a@example.org> schreiben\\.\n",
        ),
        (
            "Plain text.\n",
            "*literal* [text] <tag> & stuff.",
            "\\*literal\\* \\[text\\] \\<tag\\> \\& stuff\\.\n",
        ),
    ],
)
def test_block_shells_protection_and_literal_punctuation(tmp_path, source, target, expected):
    job, review, output = prepare(tmp_path, source, [target])
    assert finalize_markdown_review(job, review, output) == ()
    assert output.read_bytes() == expected.encode("utf-8")
    assert markdown_review_segments(output)[0].text == target


def test_partial_style_uses_reviewed_correction_not_proposal(tmp_path):
    job, review, output = prepare(
        tmp_path, "Read **important** notes.\n", ["Wichtige Notizen lesen."]
    )
    text = review.read_text(encoding="utf-8").replace(
        "--- Correction ---\n\n", "--- Correction ---\nBitte wichtige Hinweise lesen.\n"
    )
    review.write_text(text, encoding="utf-8", newline="\n")
    aligner = WordAligner([("important", "wichtige")])
    assert finalize_markdown_review(job, review, output, aligner=aligner) == ()
    assert aligner.calls == [("Read important notes.", "Bitte wichtige Hinweise lesen.")]
    assert output.read_text(encoding="utf-8") == "Bitte **wichtige** Hinweise lesen\\.\n"


@pytest.mark.parametrize(
    "wrapper, expected, action",
    [
        ("**Turn off**", "**Schalte** das Gerät **aus**\\.\n", "formatting_split"),
        ("[Turn off](/help)", "[Schalte das Gerät aus](/help)\\.\n", "formatting_expanded"),
    ],
)
def test_existing_split_style_and_expanded_link_policy(tmp_path, wrapper, expected, action):
    job, review, output = prepare(tmp_path, wrapper + " device.\n", ["Schalte das Gerät aus."])
    aligner = WordAligner([("Turn", "Schalte"), ("off", "aus"), ("device", "Gerät")])
    issues = finalize_markdown_review(job, review, output, aligner=aligner)
    assert [issue.action for issue in issues] == [action]
    assert output.read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("mode", ["none", "failed", "wrong_text"])
def test_uncertain_formatting_dropped_and_reported(tmp_path, mode):
    job, review, output = prepare(
        tmp_path, "Read **important** notes.\n", ["Wichtige Notizen lesen."]
    )

    class Broken:
        def align(self, source, target):
            if mode == "failed":
                raise AlignmentError("unavailable")
            return AlignmentResult("x", "y", unaligned=(TextRange(0, 1),))

    reported = []
    issues = finalize_markdown_review(
        job, review, output, aligner=None if mode == "none" else Broken(), on_issue=reported.append
    )
    assert list(issues) == reported
    assert [(i.segment_id, i.action) for i in issues] == [("1", "formatting_dropped")]
    assert issues[0].diagnostics.attempted_translation == "Wichtige Notizen lesen."
    assert output.read_text(encoding="utf-8") == "Wichtige Notizen lesen\\.\n"


def test_atomic_publication_and_callback_failure(tmp_path, monkeypatch):
    from doc_lingo.review import markdown_finalize

    job, review, output = prepare(tmp_path, "Read **important** notes.\n", ["Hinweise lesen."])

    def fail(*args):
        raise OSError("failed")

    with pytest.raises(OSError, match="failed"):
        finalize_markdown_review(job, review, output, on_issue=fail)
    assert not output.exists()
    monkeypatch.setattr(markdown_finalize.os, "link", fail)
    with pytest.raises(OSError, match="failed"):
        finalize_markdown_review(job, review, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-review-*"))
    assert review.exists()


def test_existing_output_and_changed_original_rejected(tmp_path):
    job, review, output = prepare(tmp_path, "Hello.\n", ["Hallo."])
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        finalize_markdown_review(job, review, output)
    assert output.read_bytes() == b"keep"
    output.unlink()
    source = tmp_path / "source.md"
    source.write_bytes(b"changed")
    with pytest.raises(ReviewJobError, match="changed"):
        finalize_markdown_review(job, review, output, original=source)
    assert not output.exists()
    finalize_markdown_review(job, review, output)
    assert output.exists()  # External source is optional; snapshot is authoritative.


def test_structure_changing_correction_is_not_published(tmp_path):
    job, review, output = prepare(tmp_path, "Hello.\n", ["Hallo.\n\nNoch ein Absatz."])
    with pytest.raises(ReviewJobError, match="block structure"):
        finalize_markdown_review(job, review, output)
    assert not output.exists()


def test_empty_markdown_and_wrong_job_format(tmp_path):
    job, review, output = prepare(tmp_path, "", [])
    assert finalize_markdown_review(job, review, output) == ()
    assert output.read_bytes() == b""
    source = tmp_path / "empty.txt"
    source.write_bytes(b"")
    txt_job = create_text_job(source, [], source_lang="en", target_lang="de")
    with pytest.raises(ReviewJobError, match="requires a Markdown"):
        finalize_markdown_review(txt_job, review, tmp_path / "wrong.md")


def test_fixture_table_and_excluded_blocks_survive(tmp_path):
    import json

    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "review"
    cases = json.loads((fixtures / "markdown-review.en-de.json").read_text(encoding="utf-8"))
    source = (fixtures / "markdown-review.en.md").read_text(encoding="utf-8")
    targets = [c["correction"] or c["proposal"] for c in cases]
    job, review, output = prepare(tmp_path, source, targets)
    issues = finalize_markdown_review(job, review, output)
    assert [s.text for s in markdown_review_segments(output)] == targets
    result = output.read_text(encoding="utf-8")
    assert "| Schritt | Beschreibung |" in result
    assert "```python\n# This comment is not translated.\nresult = predict(data)\n```" in result
    assert "<!-- This comment also stays in the source snapshot. -->" in result
    assert "title: Metadata stays in the source snapshot" in result
    assert "Vor dem Speichern mit `save()` rufen Sie `predict()` auf\\." in result
    assert issues


def test_hard_break_loss_is_reported(tmp_path):
    job, review, output = prepare(tmp_path, "Hello  \nworld.\n", ["Hallo\nWelt."])
    issues = finalize_markdown_review(job, review, output)
    assert len(issues) == 1
    assert "hard_line_breaks_not_projected" in issues[0].reason
    assert markdown_review_segments(output)[0].text == "Hallo\nWelt."


def test_table_pipe_is_literal_and_multiline_cell_rejected(tmp_path):
    job, review, output = prepare(tmp_path, "| Name |\n| --- |\n| Value |\n", ["Name", "A | B"])
    finalize_markdown_review(job, review, output)
    assert "| A \\| B |" in output.read_text(encoding="utf-8")
    assert markdown_review_segments(output)[1].text == "A | B"
    changed = review.read_text(encoding="utf-8").replace(
        "--- Correction ---\n\n", "--- Correction ---\nTwo\nlines\n", 1
    )
    review.write_text(changed, encoding="utf-8", newline="\n")
    rejected = tmp_path / "rejected.md"
    with pytest.raises(ReviewJobError, match="Block 1: A table cell"):
        finalize_markdown_review(job, review, rejected)
    assert not rejected.exists()


def test_nested_whole_block_styles_need_no_word_alignment(tmp_path):
    job, review, output = prepare(tmp_path, "***Hello.***\n", ["Hallo."])
    assert finalize_markdown_review(job, review, output) == ()
    assert output.read_text(encoding="utf-8") == "***Hallo\\.***\n"
