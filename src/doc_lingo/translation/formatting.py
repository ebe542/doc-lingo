"""Project formatting scopes using exact alignment coordinates, without rendering."""

from dataclasses import dataclass
from typing import Literal

from doc_lingo.translation.alignment import AlignmentLink, AlignmentResult, TextRange


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
    source_ranges: tuple[TextRange, ...] = ()

    def diagnostic(self) -> str:
        """Positions refer to prepared alignment input, not original Markdown."""
        positions = ", ".join(f"[{r.start},{r.end})" for r in self.source_ranges)
        return f"{self.identity}: {self.reason}" + (
            f"; alignment_source_ranges={positions}" if positions else ""
        )


@dataclass(frozen=True)
class FormattingProjection:
    formatting: tuple[ProjectedFormatting, ...]
    issues: tuple[FormattingIssue, ...]


def _overlaps(left: TextRange, right: TextRange) -> bool:
    return left.start < right.end and right.start < left.end


def _scope_evidence(alignment: AlignmentResult, scope: TextRange):
    """Use complete call boundaries locally; never modify raw word evidence."""
    units = []
    for unit in alignment.units:
        if not (scope.start <= unit.source.start and unit.source.end <= scope.end):
            continue
        # A marker or word link crossing a call boundary contradicts treating
        # that call as an isolated structural unit. Keep the strict word policy.
        touching = [
            link
            for link in alignment.links
            if any(_overlaps(span, unit.source) for span in link.source_ranges)
            or any(_overlaps(span, unit.target) for span in link.target_ranges)
        ]
        if any(
            span.start < boundary.start or span.end > boundary.end
            for link in touching
            for ranges, boundary in (
                (link.source_ranges, unit.source),
                (link.target_ranges, unit.target),
            )
            for span in ranges
        ):
            continue
        units.append(unit)
    links = [
        link
        for link in alignment.links
        if not any(_overlaps(span, unit.source) for span in link.source_ranges for unit in units)
    ]
    links.extend(AlignmentLink((unit.source,), (unit.target,)) for unit in units)
    unresolved = []
    for span in (*alignment.unaligned, *alignment.ambiguous):
        cursor = span.start
        for unit in units:
            cut = unit.source
            if cut.end <= cursor or cut.start >= span.end:
                continue
            if cursor < cut.start:
                unresolved.append(TextRange(cursor, cut.start))
            cursor = min(span.end, cut.end)
        if cursor < span.end:
            unresolved.append(TextRange(cursor, span.end))
    # Subtracting complete units can leave separators inside a broad unresolved
    # range. Whitespace requires no word correspondence; retain every actual
    # character (including punctuation) and its original coordinate.
    content_ranges = []
    for span in unresolved:
        text = alignment.source[span.start : span.end]
        if text.strip():
            start = span.start + len(text) - len(text.lstrip())
            end = span.start + len(text.rstrip())
            content_ranges.append(TextRange(start, end))
    return links, content_ranges


def project_formatting(
    alignment: AlignmentResult,
    scopes: tuple[FormattingScope, ...],
    *,
    complete_segment: bool = False,
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
        if (
            complete_segment
            and alignment.source[source.start : source.end].strip()
            and not alignment.source[: source.start].strip()
            and not alignment.source[source.end :].strip()
            and alignment.target.strip()
        ):
            start = len(alignment.target) - len(alignment.target.lstrip())
            end = len(alignment.target.rstrip())
            projected.append(ProjectedFormatting(scope, (TextRange(start, end),)))
            continue
        evidence, unresolved = _scope_evidence(alignment, source)
        links = [
            link for link in evidence if any(_overlaps(source, span) for span in link.source_ranges)
        ]
        uncertain = any(_overlaps(source, span) for span in unresolved)
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
            affected = (
                tuple(
                    sorted(
                        {
                            TextRange(max(source.start, span.start), min(source.end, span.end))
                            for span in unresolved
                            if _overlaps(source, span)
                        }
                    )
                )
                if uncertain
                else tuple(sorted({span for link in links for span in link.source_ranges}))
                if crossing
                else (source,)
            )
            issues.append(FormattingIssue(scope.identity, "dropped", reason, affected))
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
