"""Plain-text review round trips and strict boundary validation without models."""

from dataclasses import replace

import pytest

from doc_lingo import PlainTextReader
from doc_lingo.review import (
    ReviewJobError,
    create_text_job,
    export_review_txt,
    finalize_text_review,
    import_review_txt,
)


def setup_review(tmp_path, data=b"\xef\xbb\xbfHello.\r\n\r\n- World.\r\n"):
    source = tmp_path / "source.txt"
    source.write_bytes(data)
    with PlainTextReader(source).iter_segments() as values:
        proposals = [
            replace(s, text=s.text.replace("Hello", "Hallo").replace("World", "Welt"))
            for s in values
        ]
    job = create_text_job(source, proposals, source_lang="en", target_lang="de")
    review = tmp_path / "review.txt"
    export_review_txt(job, review)
    return job, source, review


def test_export_acceptance_and_finalization_preserve_structure(tmp_path):
    job, source, review = setup_review(tmp_path)
    data = review.read_bytes()
    assert data.startswith(b"doc-lingo-review: 1\n")
    assert b"\r" not in data
    assert b"Page:" not in data
    assert b"- World" not in data  # Source list prefixes are metadata, not review payload.
    assert [s.text for s in import_review_txt(job, review)] == [b.proposal for b in job.blocks]
    output = tmp_path / "out.txt"
    finalize_text_review(job, review, output, original=source)
    assert output.read_bytes() == b"\xef\xbb\xbfHallo.\r\n\r\n- Welt.\r\n"
    assert review.read_bytes() == data


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_editor_correction_bom_reordering_and_multiline(tmp_path, newline):
    job, _, review = setup_review(tmp_path)
    text = review.read_text(encoding="utf-8")
    header, blocks = text.split("=== Block 1 ===", 1)
    first, second = blocks.split("=== Block 2 ===", 1)
    second = second.replace(
        "--- Correction ---\n\n", "--- Correction ---\nMeine Welt.\nNoch eine Zeile.\n"
    )
    text = header + "=== Block 2 ===" + second + "=== Block 1 ===" + first
    review.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", newline).encode("utf-8"))
    values = import_review_txt(job, review)
    assert values[0].text == job.blocks[0].proposal
    assert values[1].text == "Meine Welt.\nNoch eine Zeile."
    output = tmp_path / "out.txt"
    finalize_text_review(job, review, output)
    assert output.read_bytes() == (b"\xef\xbb\xbfHallo.\r\n\r\n- Meine Welt.\nNoch eine Zeile.\r\n")


@pytest.mark.parametrize(
    "text",
    [
        "--- Original ---\n--- Translation ---\n--- Correction ---\n=== End Block ===\n",
        "=== Block 5 ===\ndoc-lingo-review: 1\n\\path\n\\\\double\n",
        "Unicode Grüße 🙂 <b>literal</b> # text **stars** X0Z.\n",
        "No final newline",
        "One.\rTwo.\r",
        "One.\n\n\n",
    ],
)
def test_literal_controls_backslashes_and_whitespace_round_trip(tmp_path, text):
    job, _, review = setup_review(tmp_path, text.encode("utf-8"))
    assert [s.text for s in import_review_txt(job, review)] == [b.proposal for b in job.blocks]


def test_escaped_correction_controls_and_backslashes(tmp_path):
    job, _, review = setup_review(tmp_path)
    text = review.read_text(encoding="utf-8").replace(
        "--- Correction ---\n\n", "--- Correction ---\n\\--- Original ---\n\\\\path\n", 1
    )
    review.write_text(text, encoding="utf-8", newline="\n")
    assert import_review_txt(job, review)[0].text == "--- Original ---\n\\path"


@pytest.mark.parametrize(
    "old,new",
    [
        ("doc-lingo-review: 1", "doc-lingo-review: 99"),
        ("Job-ID: ", "Different-ID: "),
        ("Source: source.txt", "Source: other.txt"),
        ("=== Block 2 ===", "=== Block 1 ==="),
        ("=== Block 2 ===", "=== Block 999 ==="),
        ("Hello.", "Changed reference."),
        ("Hallo.", "Changed proposal."),
        ("--- Original ---", "--- Translation ---"),
        ("--- Correction ---\n\n", "--- Correction ---\n"),
        ("--- Correction ---\n\n", "--- Correction ---\n\\invalid\n"),
        ("--- Correction ---\n\n", "--- Correction ---\n=== Block 42 ===\n"),
    ],
)
def test_invalid_review_rejected_before_output(tmp_path, old, new):
    job, _, review = setup_review(tmp_path)
    text = review.read_text(encoding="utf-8").replace(old, new, 1)
    review.write_text(text, encoding="utf-8", newline="\n")
    output = tmp_path / "out.txt"
    with pytest.raises(ReviewJobError):
        finalize_text_review(job, review, output)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["missing", "truncated", "outside", "encoding"])
def test_incomplete_or_unassigned_text_rejected(tmp_path, kind):
    job, _, review = setup_review(tmp_path)
    data = review.read_bytes()
    if kind == "missing":
        data = data.split(b"=== Block 2 ===")[0]
    elif kind == "truncated":
        data = data[: data.rfind(b"=== End Block ===")]
    elif kind == "outside":
        data += b"unassigned text"
    else:
        data = b"\xff"
    review.write_bytes(data)
    with pytest.raises(ReviewJobError):
        import_review_txt(job, review)


def test_empty_job_and_whitespace_correction(tmp_path):
    job, _, review = setup_review(tmp_path, b"")
    assert import_review_txt(job, review) == ()
    review.unlink()
    job, _, review = setup_review(tmp_path)
    text = review.read_text(encoding="utf-8").replace(
        "--- Correction ---\n\n", "--- Correction ---\n \t\n\n"
    )
    review.write_text(text, encoding="utf-8", newline="\n")
    assert [s.text for s in import_review_txt(job, review)] == [b.proposal for b in job.blocks]


def test_source_label_control_characters_do_not_break_structure(tmp_path):
    job, _, review = setup_review(tmp_path)
    job = replace(job, source_name="line\nname\t.txt")
    review.unlink()
    export_review_txt(job, review)
    assert "Source: line\\nname\\t.txt" in review.read_text(encoding="utf-8")
    assert len(import_review_txt(job, review)) == 2


def test_no_overwrite_size_limits_and_failed_publication(tmp_path, monkeypatch):
    from doc_lingo.review import text as module

    job, _, review = setup_review(tmp_path)
    before = review.read_bytes()
    with pytest.raises(FileExistsError):
        export_review_txt(job, review)
    assert review.read_bytes() == before
    output = tmp_path / "new.txt"
    real_limit = module.MAX_REVIEW_BYTES
    monkeypatch.setattr(module, "MAX_REVIEW_BYTES", 1)
    with pytest.raises(ReviewJobError, match="size limit"):
        export_review_txt(job, output)
    with pytest.raises(ReviewJobError, match="size limit"):
        import_review_txt(job, review)
    monkeypatch.setattr(module, "MAX_REVIEW_BYTES", real_limit)

    def fail(*args):
        raise OSError("publication failed")

    monkeypatch.setattr(module.os, "link", fail)
    with pytest.raises(OSError):
        export_review_txt(job, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-*"))


def test_finalization_refuses_changed_source_and_existing_output(tmp_path):
    job, source, review = setup_review(tmp_path)
    output = tmp_path / "out.txt"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        finalize_text_review(job, review, output)
    assert output.read_bytes() == b"keep"
    output.unlink()
    source.write_bytes(b"changed")
    with pytest.raises(ReviewJobError, match="changed"):
        finalize_text_review(job, review, output, original=source)
    assert not output.exists()


def test_finalization_failure_cleans_snapshot_and_keeps_review(tmp_path, monkeypatch):
    from doc_lingo.documents.plain_text import writer

    job, _, review = setup_review(tmp_path)
    before = review.read_bytes()

    def fail(*args):
        raise OSError("publication failed")

    monkeypatch.setattr(writer.os, "link", fail)
    output = tmp_path / "out.txt"
    with pytest.raises(OSError):
        finalize_text_review(job, review, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-*"))
    assert review.read_bytes() == before


def test_empty_job_finalization_needs_no_external_source(tmp_path):
    job, source, review = setup_review(tmp_path, b"")
    source.unlink()
    output = tmp_path / "out.txt"
    finalize_text_review(job, review, output)
    assert output.read_bytes() == b""
