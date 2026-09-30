"""Collect inline source boundaries using the Markdown parser's own rules."""

from markdown_it import MarkdownIt
from markdown_it.rules_inline.state_inline import StateInline
from markdown_it.token import Token

from doc_lingo.documents.html.text import HtmlText
from doc_lingo.documents.source_layout import SourceLayout, SourceRange


def inline_source_layout(text: str, environment: dict, html: HtmlText) -> SourceLayout:
    """Locate emphasis and explicit link labels without reserializing tokens.

    Token references are retained before the parser joins text tokens. Delimiter
    postprocessing changes them into matched open/close tokens; unmatched marks
    remain literal. Code, images and implicit reference labels stay opaque.
    """
    if not html.safe:
        return SourceLayout(text)
    parser = MarkdownIt("commonmark").enable("strikethrough")
    ranges = list(html.source_layout().ranges)
    markers: list[tuple[int, Token]] = []
    opaque: list[tuple[int, int]] = []

    def instrument(name, rule):
        def wrapped(state: StateInline, silent: bool) -> bool:
            start = state.pos
            count = len(state.delimiters)
            label_end = -1
            if name == "link" and state.src[start : start + 1] == "[":
                label_end = state.md.helpers.parseLinkLabel(state, start, True)
            matched = rule(state, silent)
            if not matched or silent or state.src is not text:
                return matched
            end = state.pos
            if name in ("emphasis", "strikethrough"):
                delimiters = state.delimiters[count:]
                width = 1 if name == "emphasis" else 2
                position = end - width * len(delimiters)
                for delimiter in delimiters:
                    markers.append((position, state.tokens[delimiter.token]))
                    position += width
            elif name == "link":
                if text[label_end + 1 : end] not in ("", "[]"):
                    ranges.append(SourceRange(start, start + 1, label_end, end))
                else:
                    opaque.append((start, end))
            elif name in ("backticks", "image", "autolink"):
                opaque.append((start, end))
            return matched

        return wrapped

    for name, rule in zip(
        parser.get_active_rules()["inline"], parser.inline.ruler.getRules(""), strict=True
    ):
        parser.inline.ruler.at(name, instrument(name, rule))
    parser.inline.parse(text, parser, dict(environment), [])
    stack: list[tuple[int, int]] = []
    for position, token in sorted(markers, key=lambda item: item[0]):
        if token.nesting == 1:
            # Strong tokens occupy the second opening delimiter and the first
            # closing delimiter after markdown-it merges two emphasis pairs.
            start = position - (1 if token.type == "strong_open" else 0)
            stack.append((start, start + len(token.markup)))
        elif token.nesting == -1:
            start, inner_start = stack.pop()
            ranges.append(SourceRange(start, inner_start, position, position + len(token.markup)))
    # Do not interpret Markdown inside excluded HTML, attributes or comments.
    html_wrappers = html.source_layout().ranges
    ranges = [
        item
        for item in ranges
        if not any(a <= item.outer_start and item.outer_end <= b for a, b in opaque)
        and (
            item in html_wrappers
            or any(index in html.editable for index in range(item.inner_start, item.inner_end))
        )
    ]
    try:
        return SourceLayout(
            text, tuple(sorted(ranges, key=lambda item: (item.outer_start, -item.outer_end)))
        )
    except ValueError:
        # Independently valid HTML/Markdown can cross each other's boundaries.
        # Retain that source rather than inventing a nesting relationship.
        return SourceLayout(text)
