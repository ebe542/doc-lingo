"""Rendering tests use fixed projections without model dependencies."""

from dataclasses import replace

import pytest

from doc_lingo.documents.html.text import HtmlText
from doc_lingo.documents.markdown.layout import inline_source_layout
from doc_lingo.documents.markdown.rendering import markdown_scopes, render_markdown
from doc_lingo.documents.source_layout import SourceLayout, SourceRange
from doc_lingo.translation.alignment import TextRange
from doc_lingo.translation.formatting import (
    FormattingIssue,
    FormattingProjection,
    ProjectedFormatting,
)
from doc_lingo.translation.formatting_bridge import RestoredFormatting


def fixture(source, target, spans):
    layout = inline_source_layout(source, {}, HtmlText(source))
    scopes = markdown_scopes(layout)
    projection = FormattingProjection(
        tuple(
            ProjectedFormatting(scope, tuple(TextRange(*span) for span in ranges))
            for scope, ranges in zip(scopes, spans, strict=True)
        ),
        (),
    )
    return layout, RestoredFormatting(target, projection)


def test_split_emphasis():
    layout, result = fixture("**turned off**", "schaltete das Gerät aus", [((0, 9), (20, 23))])
    rendered = render_markdown(layout, result)
    assert rendered.text == "**schaltete** das Gerät **aus**"
    assert not rendered.issues


def test_expanded_link_keeps_exact_destination_and_title():
    layout, result = fixture(
        '[turned off](https://example.org/a?q=1 "Title")', "schaltete das Gerät aus", [((0, 23),)]
    )
    rendered = render_markdown(layout, result)
    assert rendered.text == '[schaltete das Gerät aus](https://example.org/a?q=1 "Title")'
    assert not rendered.issues


def test_nested_equal_target_ranges():
    layout, result = fixture("**[word](url)**", "Wort", [((0, 4),), ((0, 4),)])
    assert render_markdown(layout, result).text == "**[Wort](url)**"


def test_crossing_scopes_drop_both():
    layout, result = fixture("**one** *two*", "eins zwei drei", [((0, 9),), ((5, 14),)])
    rendered = render_markdown(layout, result)
    assert rendered.text == result.text
    assert len(rendered.issues) == 2
    assert all(issue.reason == "conflicting_markdown_ranges" for issue in rendered.issues)


def test_overlapping_links_are_defensively_rejected():
    layout, result = fixture("[one](a) [two](b)", "eins zwei", [((0, 9),), ((5, 9),)])
    assert render_markdown(layout, result).text == result.text


def test_unsupported_html_wrapper_is_reported():
    layout, result = fixture("<div>one</div>", "eins", [((0, 4),)])
    rendered = render_markdown(layout, result)
    assert rendered.text == "eins"
    assert rendered.issues[0].reason == "unsupported_markdown_wrapper"


def test_invalid_delimiter_flanking_retains_translation():
    layout, result = fixture("_word_", "abc", [((1, 2),)])
    result = replace(
        result,
        projection=replace(
            result.projection, issues=(FormattingIssue("0", "split", "discontinuous_target"),)
        ),
    )
    rendered = render_markdown(layout, result)
    assert rendered.text == "abc"
    assert [issue.action for issue in rendered.issues] == ["dropped"]
    assert rendered.issues[0].reason == "markdown_wrapper_validation"


def test_multiple_sentences_and_protected_text_are_preserved():
    layout, result = fixture("**one. two.**", "Eins. Zwei. `x`", [((0, 11),)])
    assert render_markdown(layout, result).text == "**Eins. Zwei.** `x`"


def test_invalid_scope_and_ranges_rejected():
    layout, result = fixture("**one**", "eins", [((0, 4),)])
    item = result.projection.formatting[0]
    bad = replace(item, scope=replace(item.scope, identity="unknown"))
    with pytest.raises(ValueError, match="source layout"):
        render_markdown(layout, replace(result, projection=FormattingProjection((bad,), ())))
    for spans in ((TextRange(0, 5),), (TextRange(1, 3), TextRange(2, 4))):
        bad = replace(item, target_ranges=spans)
        with pytest.raises(ValueError, match="target ranges"):
            render_markdown(layout, replace(result, projection=FormattingProjection((bad,), ())))


def test_empty_layout_and_empty_inner_scope():
    assert markdown_scopes(SourceLayout("<b></b>", (SourceRange(0, 3, 3, 7),))) == ()
    rendered = render_markdown(
        SourceLayout("plain"), RestoredFormatting("Text", FormattingProjection((), ()))
    )
    assert rendered.text == "Text"
    assert not rendered.issues


def test_nested_html_and_markdown_wrappers():
    layout, result = fixture(
        '<strong title="Original">*word*</strong>', "Wort", [((0, 4),), ((0, 4),)]
    )
    rendered = render_markdown(layout, result)
    assert rendered.text == '<strong title="Original">*Wort*</strong>'
    assert not rendered.issues


def test_html_link_is_classified_and_conflicts_with_markdown_link():
    layout, result = fixture(
        '<a href="one">word</a> [other](two)', "eins zwei", [((0, 9),), ((5, 9),)]
    )
    assert all(scope.link_target is not None for scope in markdown_scopes(layout))
    rendered = render_markdown(layout, result)
    assert rendered.text == "eins zwei"
    assert len(rendered.issues) == 2


def test_raw_html_does_not_interpret_markdown_text():
    layout = SourceLayout("<em>word</em>", (SourceRange(0, 4, 8, 13),))
    scope = markdown_scopes(layout)[0]
    result = RestoredFormatting(
        "*Wort*", FormattingProjection((ProjectedFormatting(scope, (TextRange(0, 6),)),), ())
    )
    assert render_markdown(layout, result, raw_html=True).text == "<em>*Wort*</em>"


@pytest.mark.parametrize(
    "text",
    [
        "<code>word</code>",
        '<span translate="no">word</span>',
        "<span hidden>word</span>",
        "<pre>word</pre>",
    ],
)
def test_excluded_html_has_no_projectable_scope(text):
    assert not markdown_scopes(HtmlText(text).source_layout())
