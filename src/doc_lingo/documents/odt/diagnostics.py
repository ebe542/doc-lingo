"""Explicit skipped-text diagnostics for the limited ODT command-line path."""

from pathlib import Path
from xml.etree import ElementTree as ET

from doc_lingo.documents.odt.blocks import TEXT, text_blocks
from doc_lingo.documents.odt.package import inspect_package
from doc_lingo.translation.issues import TranslationDiagnostics, TranslationIssue


def skipped_text_issues(source: Path) -> tuple[TranslationIssue, ...]:
    """Inspect before model loading; empty/protected-only blocks are not failures.

    Segment numbers refer to source XML block occurrences, not translated counts.
    Peripheral text uses part-qualified IDs; page and paragraph numbers are unknown.
    This inventory does not claim complete rendering or text extraction from images.
    """
    package = inspect_package(source)
    blocks = text_blocks(package.content_xml)
    issues = []
    for block in blocks:
        if block.reason not in ("unsupported_container", "inline_content"):
            continue
        if not block.segment.text.strip():
            continue
        issues.append(
            TranslationIssue(
                block.segment.text,
                "Unsupported ODT text retained: " + block.reason,
                block.segment.id,
                block.segment.type,
                int(block.segment.id),
                None,
                action="skipped_content",
                diagnostics=TranslationDiagnostics(None, "odt_inventory", (block.reason,)),
            )
        )
    if package.styles_xml is not None:
        number = len(blocks)
        for index, element in enumerate(
            (
                node
                for node in ET.fromstring(package.styles_xml).iter()
                if node.tag in (f"{{{TEXT}}}p", f"{{{TEXT}}}h")
            ),
            start=1,
        ):
            text = "".join(element.itertext())
            if text.strip():
                issues.append(
                    TranslationIssue(
                        text,
                        "Unsupported ODT peripheral text retained: styles.xml",
                        f"styles.xml:{index}",
                        "peripheral_text",
                        number + index,
                        None,
                        action="skipped_content",
                        diagnostics=TranslationDiagnostics(
                            None, "odt_inventory", ("unsupported_styles_text",)
                        ),
                    )
                )
    return tuple(issues)
