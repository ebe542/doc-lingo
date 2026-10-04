"""Translate known source chunks and merge local alignments into segment offsets."""

from collections.abc import Callable, Iterator
from time import perf_counter

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    BudgetedTextAligner,
    ReservedTextAligner,
    TextAligner,
    TextRange,
)
from doc_lingo.translation.alignment_statistics import AlignmentStatistics
from doc_lingo.translation.chunks import sentence_parts, split_text
from doc_lingo.translation.protocols import TranslationBackend


def translate_aligned_chunks(
    source: str,
    backend: TranslationBackend,
    aligner: TextAligner,
    *,
    source_lang: str,
    target_lang: str,
    on_alignment_failure: Callable[[tuple[str, ...]], None],
    protected_tokens: tuple[str, ...] = (),
    statistics: AlignmentStatistics | None = None,
) -> AlignmentResult:
    """Keep markers indivisible and retain local uncertainty when alignment fails.

    The source budget determines paired translation calls; target sentences are
    never split independently or matched by index. Oversized indivisible words
    still reach the translator, whose own recovery policy applies. Target-side
    overflow loses only that chunk's alignment, without retranslating content.
    Formatting projection and content restoration happen after merging. Memory
    is bounded by one document segment, not by the entire document.
    """

    stats = statistics if statistics is not None else AlignmentStatistics()
    registered = set(protected_tokens)

    def fits(text: str) -> bool:
        if not isinstance(aligner, BudgetedTextAligner):
            return True
        # split_text uses whitespace boundaries: do not cut a marker or word.
        if not any(char.isspace() for char in text.strip()):
            return True
        return (
            aligner.fits_source(text)
            if isinstance(aligner, ReservedTextAligner)
            else aligner.fits_input(text)
        )

    def units() -> Iterator[tuple[str, str, bool]]:
        # Only trusted registry entries qualify. Never guess markers from prose.
        cursor = 0
        pending_start = 0
        for sentence, following in sentence_parts(source):
            words = sentence.split()
            if words and all(word in registered for word in words):
                pending = source[pending_start:cursor]
                core = pending.rstrip()
                consumed = 0
                for text, separator in split_text(core, fits):
                    consumed += len(text) + len(separator)
                    if consumed == len(core):
                        separator += pending[len(core) :]
                    if text or separator:
                        yield text, separator, False
                yield sentence, following, True
                pending_start = cursor + len(sentence) + len(following)
            cursor += len(sentence) + len(following)
        if pending_start < len(source):
            for text, separator in split_text(source[pending_start:], fits):
                yield text, separator, False

    source_offset = target_offset = 0
    targets = []
    links = []
    unaligned = []
    ambiguous = []

    def shift(ranges: tuple[TextRange, ...], offset: int) -> tuple[TextRange, ...]:
        return tuple(TextRange(span.start + offset, span.end + offset) for span in ranges)

    chunks = units()
    try:
        chunk_number = 0
        while True:
            started = perf_counter()
            try:
                text, separator, protected = next(chunks)
            except StopIteration:
                break
            finally:
                stats.planning_seconds += perf_counter() - started
            chunk_number += 1
            if protected:
                target = text
                stats.protected_units += 1
            elif text:
                stats.translation_calls += 1
                started = perf_counter()
                try:
                    target = backend.translate(
                        text, source_lang=source_lang, target_lang=target_lang
                    )
                finally:
                    stats.translation_seconds += perf_counter() - started
            else:
                target = ""
            if text.strip() and not target.strip():
                raise AlignmentError("Empty aligned translation")
            started = perf_counter()
            try:
                if not protected and isinstance(aligner, BudgetedTextAligner):
                    if not aligner.fits_input(text):
                        raise AlignmentError("Source chunk exceeds alignment encoder budget")
                    if not aligner.fits_input(target):
                        raise AlignmentError("Target chunk exceeds alignment encoder budget")
                if protected:
                    local = AlignmentResult(
                        text,
                        target,
                        (AlignmentLink((TextRange(0, len(text)),), (TextRange(0, len(text)),)),),
                    )
                else:
                    stats.alignment_calls += 1
                    local = aligner.align(text, target)
                if local.source != text or local.target != target:
                    raise AlignmentError("Aligner returned mismatched text")
            except AlignmentError as error:
                stats.alignment_failures += 1
                local = AlignmentResult(
                    text, target, unaligned=(TextRange(0, len(text)),) if text else ()
                )
                on_alignment_failure(
                    (
                        f"chunk={chunk_number}",
                        f"alignment_source_range=[{source_offset},{source_offset + len(text)})",
                        f"alignment_target_range=[{target_offset},{target_offset + len(target)})",
                        f"cause={error}",
                    )
                )
            finally:
                stats.alignment_seconds += perf_counter() - started
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
