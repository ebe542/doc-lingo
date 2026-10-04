"""Translate known source chunks and merge local alignments into segment offsets."""

from collections.abc import Callable

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    BudgetedTextAligner,
    TextAligner,
    TextRange,
)
from doc_lingo.translation.chunks import split_text
from doc_lingo.translation.protocols import TranslationBackend


def translate_aligned_chunks(
    source: str,
    backend: TranslationBackend,
    aligner: TextAligner,
    *,
    source_lang: str,
    target_lang: str,
    on_alignment_failure: Callable[[], None],
) -> AlignmentResult:
    """Keep markers indivisible and retain local uncertainty when alignment fails.

    The source budget determines paired translation calls; target sentences are
    never split independently or matched by index. Oversized indivisible words
    still reach the translator, whose own recovery policy applies. Target-side
    overflow loses only that chunk's alignment, without retranslating content.
    Formatting projection and content restoration happen after merging. Memory
    is bounded by one document segment, not by the entire document.
    """

    def fits(text: str) -> bool:
        if not isinstance(aligner, BudgetedTextAligner):
            return True
        # split_text uses whitespace boundaries: do not cut a marker or word.
        if not any(char.isspace() for char in text.strip()):
            return True
        return aligner.fits_input(text)

    source_offset = target_offset = 0
    targets = []
    links = []
    unaligned = []
    ambiguous = []

    def shift(ranges: tuple[TextRange, ...], offset: int) -> tuple[TextRange, ...]:
        return tuple(TextRange(span.start + offset, span.end + offset) for span in ranges)

    chunks = split_text(source, fits)
    try:
        for text, separator in chunks:
            target = (
                backend.translate(text, source_lang=source_lang, target_lang=target_lang)
                if text
                else ""
            )
            if text.strip() and not target.strip():
                raise AlignmentError("Empty aligned translation")
            try:
                local = aligner.align(text, target)
                if local.source != text or local.target != target:
                    raise AlignmentError("Aligner returned mismatched text")
            except AlignmentError:
                local = AlignmentResult(
                    text, target, unaligned=(TextRange(0, len(text)),) if text else ()
                )
                on_alignment_failure()
            links.extend(
                AlignmentLink(
                    shift(link.source_ranges, source_offset),
                    shift(link.target_ranges, target_offset),
                )
                for link in local.links
            )
            unaligned.extend(shift(local.unaligned, source_offset))
            ambiguous.extend(shift(local.ambiguous, source_offset))
            targets.append(target + separator)
            source_offset += len(text) + len(separator)
            target_offset += len(target) + len(separator)
    finally:
        chunks.close()
    return AlignmentResult(
        source, "".join(targets), tuple(links), tuple(unaligned), tuple(ambiguous)
    )
