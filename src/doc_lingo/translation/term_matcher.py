"""Leftmost, longest glossary matching without a giant regex alternation."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


def character_key(character: str) -> str:
    """Fold one character, preserving source offsets and sharp-s boundaries.

    The special I variants match the previous Unicode IGNORECASE behavior.
    A multi-character fold remains one trie edge: sharp s does not become two s's.
    """
    return "i" if character in "İı" else character.casefold()


def word_character(character: str) -> bool:
    return character.isalnum() or character == "_"


@dataclass(slots=True)
class _Node:
    children: dict[str, "_Node"] = field(default_factory=dict)
    entry: int | None = None


class TermMatcher:
    """Shared prefixes take one path; each source start visits at most a term length.

    Worst-case search is O(text length * longest term length), not a guarantee
    of linear time for adversarial overlapping terms. No loop over all entries
    is performed at each position. Matches keep exact original character offsets.
    """

    def __init__(self, terms: Iterable[str]) -> None:
        self._root = _Node()
        for index, term in enumerate(terms):
            if not term:
                raise ValueError("Empty glossary term")
            node = self._root
            for character in term:
                key = character_key(character)
                if key not in node.children:
                    node.children[key] = _Node()
                node = node.children[key]
            if node.entry is not None:
                raise ValueError("Glossary terms have equivalent case-insensitive spelling")
            node.entry = index

    def finditer(self, text: str) -> Iterator[tuple[int, int, int]]:
        start = 0
        while start < len(text):
            if start and word_character(text[start - 1]):
                start += 1
                continue
            node = self._root
            end = start
            best = None
            while end < len(text):
                child = node.children.get(character_key(text[end]))
                if child is None:
                    break
                node = child
                end += 1
                if node.entry is not None and (end == len(text) or not word_character(text[end])):
                    best = (start, end, node.entry)
            if best is None:
                start += 1
            else:
                yield best
                start = best[1]
