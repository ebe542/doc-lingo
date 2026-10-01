"""Shared conversion from word-pair graphs to exact character ranges."""

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)


def alignment_from_pairs(
    source: str, target: str, source_ranges: list[TextRange], target_ranges: list[TextRange], pairs
) -> AlignmentResult:
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for a, b in pairs:
        if not (0 <= a < len(source_ranges) and 0 <= b < len(target_ranges)):
            raise AlignmentError("Aligner returned an invalid word index")
        adjacency.setdefault((0, a), set()).add((1, b))
        adjacency.setdefault((1, b), set()).add((0, a))
    seen: set[tuple[int, int]] = set()
    links = []
    for node in sorted(adjacency):
        if node in seen:
            continue
        component = set()
        pending = [node]
        while pending:
            item = pending.pop()
            if item in component:
                continue
            component.add(item)
            pending.extend(adjacency[item] - component)
        seen.update(component)
        links.append(
            AlignmentLink(
                tuple(source_ranges[i] for side, i in sorted(component) if side == 0),
                tuple(target_ranges[i] for side, i in sorted(component) if side == 1),
            )
        )
    return AlignmentResult(
        source,
        target,
        tuple(links),
        tuple(span for i, span in enumerate(source_ranges) if (0, i) not in seen),
    )
