"""Project formatting scopes using exact alignment coordinates, without rendering."""

from dataclasses import dataclass
from typing import Literal

from doc_lingo.translation.alignment import AlignmentResult, TextRange


@dataclass(frozen=True)
class FormattingScope:
    """Adapter-owned identity and source scope in alignment-input coordinates.

    ``link_target=None`` denotes optical formatting; otherwise it is the opaque
    link destination, preserved verbatim. Identity lets the caller recover the
    original wrapper without copying document syntax into this layer.
    """

    identity: str
    source: TextRange
    link_target: str | None = None


@dataclass(frozen=True)
class ProjectedFormatting:
    scope: FormattingScope
    target_ranges: tuple[TextRange, ...]


@dataclass(frozen=True)
class FormattingIssue:
    """Serializable diagnostics without document text or link destinations."""

    identity: str
    action: Literal["dropped", "split", "expanded"]
    reason: str


@dataclass(frozen=True)
class FormattingProjection:
    formatting: tuple[ProjectedFormatting, ...]
    issues: tuple[FormattingIssue, ...]


def _overlaps(left: TextRange, right: TextRange) -> bool:
    return left.start < right.end and right.start < left.end


def project_formatting(
    alignment: AlignmentResult, scopes: tuple[FormattingScope, ...]
) -> FormattingProjection:
    """Drop uncertain scopes, split styles and expand links over their gaps.

    Returned issues are mandatory review/logging data for the caller. This pure
    policy never changes translated text or writes a log file. Whitespace-only
    target gaps join adjacent anchors; other gaps split optical formatting.
    Link conflicts discard every participant, independent of input order.
    Complete coverage is structural evidence, not linguistic confidence.
    """
    identities = [scope.identity for scope in scopes]
    if len(set(identities)) != len(identities):
        raise ValueError("Formatting identities must be unique")
    projected: list[ProjectedFormatting] = []
    issues: list[FormattingIssue] = []
    for scope in scopes:
        source = scope.source
        if source.end > len(alignment.source):
            raise ValueError("Formatting scope exceeds alignment source")
        links = [
            link
            for link in alignment.links
            if any(_overlaps(source, span) for span in link.source_ranges)
        ]
        uncertain = any(
            _overlaps(source, span) for span in (*alignment.unaligned, *alignment.ambiguous)
        )
        crossing = any(
            span.start < source.start or span.end > source.end
            for link in links
            for span in link.source_ranges
        )
        if uncertain or crossing or not links:
            reason = (
                "unresolved_source"
                if uncertain
                else "crossing_source_boundary"
                if crossing
                else "no_target"
            )
            issues.append(FormattingIssue(scope.identity, "dropped", reason))
            continue
        ranges: list[TextRange] = []
        for span in sorted(span for link in links for span in link.target_ranges):
            # Do not consume punctuation, inserted words or unrelated prose.
            if ranges and not alignment.target[ranges[-1].end : span.start].strip():
                ranges[-1] = TextRange(ranges[-1].start, span.end)
            else:
                ranges.append(span)
        if len(ranges) > 1:
            action: Literal["split", "expanded"] = "split"
            if scope.link_target is not None:
                ranges = [TextRange(ranges[0].start, ranges[-1].end)]
                action = "expanded"
            issues.append(FormattingIssue(scope.identity, action, "discontinuous_target"))
        projected.append(ProjectedFormatting(scope, tuple(ranges)))

    conflicts: set[str] = set()
    links = [item for item in projected if item.scope.link_target is not None]
    for index, left in enumerate(links):
        for right in links[index + 1 :]:
            if _overlaps(left.target_ranges[0], right.target_ranges[0]):
                conflicts.update((left.scope.identity, right.scope.identity))
    # Do not claim a successful expansion for a subsequently discarded link.
    issues = [issue for issue in issues if issue.identity not in conflicts]
    issues.extend(
        FormattingIssue(scope.identity, "dropped", "overlapping_links")
        for scope in scopes
        if scope.identity in conflicts
    )
    return FormattingProjection(
        tuple(item for item in projected if item.scope.identity not in conflicts),
        tuple(issues),
    )
