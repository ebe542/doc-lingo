"""Grouping rules are checked independently of a particular PDF book."""

import pytest

from doc_lingo.pdf_layout.grouping import group_page


def fragment(identifier, text, x, y, right, *, line=0, block=0, size=10, direction=(1, 0)):
    return {
        "id": identifier,
        "kind": "text_fragment",
        "text": text,
        "engine_line": line,
        "engine_block": block,
        "direction": direction,
        "writing_mode": 0,
        "source": {"bbox": [x, y - size, right, y], "origin": [x, y], "size": size},
    }


def group(*fragments):
    return group_page({"id": "page-0001", "pdf_page": 1, "objects": list(fragments)})


def test_style_fragments_form_line_and_paragraph_without_losing_provenance():
    result = group(
        fragment("a", "First", 10, 20, 30),
        fragment("b", "line", 33, 20, 100),
        fragment("c", "Second line", 10, 33, 100, line=1),
    )
    assert len(result["lines"]) == 2
    assert result["blocks"][0]["text"] == "First line\nSecond line"
    assert result["blocks"][0]["fragment_ids"] == ["a", "b", "c"]
    assert result["blocks"][0]["bbox"] == [10, 10, 100, 33]


@pytest.mark.parametrize(
    "change",
    [
        {"y": 45},
        {"size": 16},
        {"x": 30},
        {"block": 1},
        {"text": "- New item"},
        {"text": "2. Next item"},
        {"direction": (0, 1)},
    ],
)
def test_paragraph_boundaries_are_conservative(change):
    params = {"identifier": "b", "text": "Second", "x": 10, "y": 33, "right": 100, "line": 1}
    params.update(change)
    result = group(fragment("a", "First", 10, 20, 100), fragment(**params))
    assert len(result["blocks"]) == 2


def test_column_gap_is_not_joined_even_with_same_engine_line():
    result = group(fragment("a", "Left", 10, 20, 100), fragment("b", "Right", 150, 20, 240))
    assert len(result["lines"]) == len(result["blocks"]) == 2


def test_indented_first_line_and_hyphenation_are_preserved():
    result = group(
        fragment("a", "inspira-", 22, 20, 100), fragment("b", "tion", 10, 33, 60, line=1)
    )
    assert len(result["blocks"]) == 1
    assert result["blocks"][0]["text"] == "inspira-\ntion"


def test_short_final_line_ends_paragraph():
    result = group(
        fragment("a", "Long line", 10, 20, 100),
        fragment("b", "End.", 10, 33, 50, line=1),
        fragment("c", "New paragraph", 10, 46, 100, line=2),
    )
    assert [b["fragment_ids"] for b in result["blocks"]] == [["a", "b"], ["c"]]


def test_existing_spaces_and_adjacent_style_changes_are_not_modified():
    result = group(
        fragment("a", "some", 10, 20, 30),
        fragment("b", "thing ", 30, 20, 50),
        fragment("c", "else", 53, 20, 80),
    )
    assert result["blocks"][0]["text"] == "something else"


def test_rotated_fragments_stay_separate():
    result = group(
        fragment("a", "One", 10, 20, 30, direction=(0, 1)),
        fragment("b", "Two", 10, 30, 30, direction=(0, 1)),
    )
    assert len(result["blocks"]) == 2


def test_empty_page_and_duplicate_ids():
    assert group()["blocks"] == []
    part = fragment("a", "Text", 10, 20, 100)
    with pytest.raises(ValueError, match="Duplicate"):
        group(part, part)


def test_symbol_marker_is_separate_and_list_continuation_crosses_engine_block():
    marker = fragment("bullet", "\uf0a1", 8, 20, 13, size=8.5)
    marker["source"]["font"] = "Wingdings2"
    result = group(
        marker,
        fragment("a", "Item starts", 20, 20, 100),
        fragment("b", "and continues", 20, 33, 100, block=1),
        fragment("c", "to its end.", 20, 46, 65, block=1, line=1),
    )
    assert [block["kind"] for block in result["blocks"]] == ["list_marker", "list_item_candidate"]
    item = result["blocks"][1]
    assert item["text"] == "Item starts\nand continues\nto its end."
    assert item["marker_ids"] == ["bullet"]
    assert item["fragment_ids"] == ["a", "b", "c"]
    assert [fid for block in result["blocks"] for fid in block["fragment_ids"]] == [
        "bullet",
        "a",
        "b",
        "c",
    ]


def test_separate_letters_on_same_baseline_form_one_caption():
    result = group(
        fragment("server", "Server", 313.214, 127.39, 335.939, size=9),
        fragment("odel", "odel", 344.534, 127.39, 359.51, line=1, size=9),
        fragment("space", " ", 359.51, 127.39, 365.773, line=1, size=9),
        fragment("ettings", "ettings", 365.773, 127.39, 389.947, line=1, size=9),
        fragment("M", "M", 338.243, 127.39, 344.534, line=2, size=9),
        fragment("S", "S", 361.814, 127.39, 365.774, line=3, size=9),
        fragment("rest", "match the loaded model.", 313.214, 136.891, 400.892, line=4, size=9),
    )
    assert len(result["blocks"]) == 1
    assert result["blocks"][0]["text"] == "Server Model Settings\nmatch the loaded model."
    assert result["blocks"][0]["fragment_ids"] == [
        "server",
        "M",
        "odel",
        "space",
        "S",
        "ettings",
        "rest",
    ]


def test_list_items_do_not_merge_with_next_marker_or_indented_paragraph():
    result = group(
        fragment("m1", "•", 5, 20, 10),
        fragment("a", "First item", 20, 20, 100),
        fragment("m2", "•", 5, 33, 10, block=1),
        fragment("b", "Next item", 20, 33, 100, block=1),
        fragment("c", "New paragraph", 32, 46, 100, block=2),
    )
    assert [b["kind"] for b in result["blocks"]] == [
        "list_marker",
        "list_item_candidate",
        "list_marker",
        "list_item_candidate",
        "single_line",
    ]


def test_non_marker_private_character_is_preserved_as_text():
    part = fragment("a", "\uf0a1", 10, 20, 15)
    part["source"]["font"] = "CustomTextFont"
    assert group(part)["blocks"][0]["kind"] == "single_line"


def test_first_line_indent_is_explicit_layout_metadata():
    result = group(
        fragment("a", "First", 22, 20, 100), fragment("b", "Second", 10, 33, 100, line=1)
    )
    assert result["blocks"][0]["layout"] == {"line_lefts": [22, 10], "first_line_indent": 12}
