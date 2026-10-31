"""Translate plain Markdown review blocks with protected content markers."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from doc_lingo.documents.models import TextSegment
from doc_lingo.review.jobs import ReviewBlock, ReviewJob
from doc_lingo.review.markdown import (
    create_markdown_job,
    locate_protected,
    markdown_blocks,
    validate_protected,
)
from doc_lingo.translation.issues import (
    RecoverableTranslationError,
    TranslationDiagnostics,
    TranslationIssue,
    issue_details,
    issue_sink,
    retain_original,
)
from doc_lingo.translation.model_input import prepare_model_input
from doc_lingo.translation.protocols import TranslationBackend


def _translate_block(block: ReviewBlock, backend, source_lang, target_lang) -> str:
    assert block.source_info is not None
    protected = block.source_info.protected
    segment = TextSegment(
        block.id,
        block.original,
        block.type,
        tuple(sorted(locate_protected(protected, block.original))),
    )
    prepared = prepare_model_input(segment.translation_input())
    if prepared.text is None:
        return block.original
    failures = []
    token = issue_sink.set(lambda original, reason: failures.append(reason))
    try:
        try:
            translated = backend.translate(
                prepared.text, source_lang=source_lang, target_lang=target_lang
            )
        except RecoverableTranslationError as error:
            failures.append(str(error))
            translated = ""
    finally:
        issue_sink.reset(token)
    if failures:
        return retain_original(
            block.original,
            "Backend recovery during review preparation; source retained",
            diagnostics=TranslationDiagnostics(translated, "review_preparation", tuple(failures)),
        )
    restored = prepared.restore_content(translated)
    try:
        validate_protected(protected, restored)
    except ValueError:
        return retain_original(
            block.original,
            "Protected review content is ambiguous; source retained",
            diagnostics=TranslationDiagnostics(
                restored, "review_preparation", ("ambiguous_content",)
            ),
        )
    return restored


def translate_markdown_job(
    source: str | Path,
    backend: TranslationBackend,
    *,
    source_lang: str,
    target_lang: str,
    on_progress: Callable[[int, str], None] | None = None,
    on_issue: Callable[[TranslationIssue], None] | None = None,
) -> ReviewJob:
    """Prepare a snapshot-backed job without projecting document formatting.

    Only protected visible contents receive markers. Markers may move but must
    survive exactly once. Recoverable failures retain the complete plain block
    when a callback is supplied; calls without a callback remain strict.
    """
    source = Path(source)
    data = source.read_bytes()
    blocks = markdown_blocks(data)
    with TemporaryDirectory(prefix="doc-lingo-review-source-") as directory:
        snapshot = Path(directory) / source.name
        snapshot.write_bytes(data)

        def proposals():
            paragraph = 0
            for number, block in enumerate(blocks, 1):
                paragraph += block.type == "paragraph"

                def report(original, reason, block=block, number=number, paragraph=paragraph):
                    if on_issue is not None:
                        on_issue(
                            TranslationIssue(
                                original,
                                reason,
                                block.id,
                                block.type,
                                number,
                                paragraph if block.type == "paragraph" else None,
                                diagnostics=issue_details.get(),
                            )
                        )

                token = issue_sink.set(report if on_issue is not None else None)
                try:
                    text = _translate_block(block, backend, source_lang, target_lang)
                finally:
                    issue_sink.reset(token)
                if on_progress is not None:
                    on_progress(number, block.type)
                yield TextSegment(block.id, text, block.type)

        job = create_markdown_job(
            snapshot, proposals(), source_lang=source_lang, target_lang=target_lang
        )
        job.verify_source(source)
        return job
