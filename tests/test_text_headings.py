"""Keep conservative TXT heading boundaries independent of model output."""

from doc_lingo import PlainTextReader, PlainTextWriter, translate_document


def test_headings_are_separate_and_list_continuations_stay_together(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text(
        "An introduction ends here.\nClassification\n"
        "Classification models predict whether an input belongs to one of several categories.\n"
        "Unsupervised learning\n"
        "These models identify meaningful patterns within a dataset without labeled examples.\n"
        "\n- A list item.\nGenerative AI\n"
        "This continuation must remain inside the same complete list item for translation.\n",
        encoding="utf-8",
        newline="\n",
    )
    with PlainTextReader(source).iter_segments() as segments:
        extracted = list(segments)
    assert [s.type for s in extracted] == [
        "paragraph",
        "heading",
        "paragraph",
        "heading",
        "paragraph",
        "bullet_item",
    ]
    assert extracted[1].text == "Classification\n"
    assert extracted[3].text == "Unsupervised learning\n"
    assert "Generative AI" in extracted[-1].text
    destination = tmp_path / "copy.txt"
    PlainTextWriter(source).write(destination, extracted)
    assert destination.read_bytes() == source.read_bytes()


def test_collapsed_multiline_translation_is_reflowed(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"A source paragraph wraps across\r\nseveral lines in this document.\r\n")
    text = "Dies ist ein deutlich laengerer uebersetzter Absatz mit vielen weiteren Woertern."

    class Backend:
        def translate(self, text, **kwargs):
            return (
                "Dies ist ein deutlich laengerer uebersetzter Absatz mit vielen weiteren Woertern."
            )

    destination = tmp_path / "translated.txt"
    translate_document(
        PlainTextReader(source),
        PlainTextWriter(source),
        Backend(),
        destination,
        source_lang="en",
        target_lang="de",
    )
    result = destination.read_bytes().decode()
    assert len(result.splitlines()) >= 2
    assert " ".join(result.split()) == text
    assert result.endswith("\r\n")
