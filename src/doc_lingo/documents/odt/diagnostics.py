"""Explicit skipped-text diagnostics for the limited ODT command-line path."""

from pathlib import Path

from doc_lingo.documents.odt.blocks import package_blocks
from doc_lingo.documents.odt.package import inspect_package
from doc_lingo.translation.issues import TranslationDiagnostics, TranslationIssue


def skipped_text_issues(source: Path) -> tuple[TranslationIssue, ...]:
    """Inspect before model loading; empty/protected-only blocks are not failures.

    Segment numbers refer to source XML block occurrences, not translated counts.
    Peripheral text uses part-qualified IDs; page and paragraph numbers are unknown.
    This inventory does not claim complete rendering or text extraction from images.
    """
    package = inspect_package(source)
    blocks = package_blocks(package)
    issues = []
    for number, block in enumerate(blocks, start=1):
        if block.reason not in (
            "unsupported_container",
            "inline_content",
            "unsupported_cell_value",
        ):
            continue
        if not block.segment.text.strip():
            continue
        issues.append(
            TranslationIssue(
                block.segment.text,
                "Unsupported ODT text retained: " + block.reason,
                block.segment.id,
                block.segment.type,
                number,
                None,
                action="skipped_content",
                diagnostics=TranslationDiagnostics(None, "odt_inventory", (block.reason,)),
            )
        )
    return tuple(issues)
