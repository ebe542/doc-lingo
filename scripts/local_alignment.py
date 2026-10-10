"""Experimental fixed-pair re-alignment; never used by document translation."""

from dataclasses import asdict

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)
from doc_lingo.translation.formatting import FormattingScope, project_formatting


def overlaps(a, b):
    return a.start < b.end and b.start < a.end


def inside(a, b):
    return b.start <= a.start and a.end <= b.end


def review_scope(adapter, result: AlignmentResult, scopes, scope: FormattingScope) -> dict:
    """Try once between adjacent single-range anchors, preserving known links."""
    report = {
        "scope": scope.identity,
        "status": "skipped",
        "reason": None,
        "calls": 0,
        "window": None,
        "local_alignment": None,
        "candidate_alignment": None,
        "projection": None,
    }

    def finish(reason, status="skipped"):
        report.update(reason=reason, status=status)
        return report

    baseline = project_formatting(result, scopes)
    issue = next(
        (i for i in baseline.issues if i.identity == scope.identity and i.action == "dropped"), None
    )
    if issue is None or issue.reason != "unresolved_source":
        return finish("not_unresolved_source")
    # Crossing many-to-many groups cannot be repaired by choosing a substring.
    if any(
        any(overlaps(s, scope.source) for s in link.source_ranges)
        and not all(inside(s, scope.source) for s in link.source_ranges)
        for link in result.links
    ):
        return finish("crossing_source_boundary")
    left = [
        link
        for link in result.links
        if max(s.end for s in link.source_ranges) <= scope.source.start
    ]
    right = [
        link
        for link in result.links
        if min(s.start for s in link.source_ranges) >= scope.source.end
    ]
    if not left or not right:
        return finish("missing_anchors")
    before = max(left, key=lambda link: max(s.end for s in link.source_ranges))
    after = min(right, key=lambda link: min(s.start for s in link.source_ranges))
    if any(
        len(link.source_ranges) != 1 or len(link.target_ranges) != 1 for link in (before, after)
    ):
        return finish("non_unique_anchors")
    if (
        result.source[before.source_ranges[0].end : scope.source.start].strip()
        or result.source[scope.source.end : after.source_ranges[0].start].strip()
    ):
        return finish("unresolved_anchor_gap")
    start, end = before.target_ranges[0].end, after.target_ranges[0].start
    if start >= end or not result.target[start:end].strip():
        return finish("empty_or_reordered_window")
    target_text = result.target[start:end]
    start += len(target_text) - len(target_text.lstrip())
    end -= len(target_text) - len(target_text.rstrip())
    target = TextRange(start, end)
    source = scope.source
    internal, external = [], []
    for link in result.links:
        touches = any(overlaps(s, source) for s in link.source_ranges) or any(
            overlaps(t, target) for t in link.target_ranges
        )
        if touches:
            if not (
                all(inside(s, source) for s in link.source_ranges)
                and all(inside(t, target) for t in link.target_ranges)
            ):
                return finish("conflicting_window_links")
            internal.append(link)
        else:
            external.append(link)
    report["window"] = {"source": asdict(source), "target": asdict(target)}
    report["calls"] = 1
    try:
        local = adapter.align(result.source[source.start : source.end], result.target[start:end])
    except AlignmentError as error:
        return finish(str(error), "error")
    report["local_alignment"] = asdict(local)
    if (
        local.source != result.source[source.start : source.end]
        or local.target != result.target[start:end]
    ):
        return finish("mismatched_text", "rejected")
    if any(local.source[s.start : s.end].strip() for s in (*local.unaligned, *local.ambiguous)):
        return finish("still_unresolved", "rejected")
    shifted = tuple(
        AlignmentLink(
            tuple(
                TextRange(s.start + source.start, s.end + source.start) for s in link.source_ranges
            ),
            tuple(TextRange(t.start + start, t.end + start) for t in link.target_ranges),
        )
        for link in local.links
    )
    # Preserve every existing correspondence, including discontiguous groups.
    for old in internal:
        if not any(
            all(any(inside(s, n) for n in new.source_ranges) for s in old.source_ranges)
            and all(any(inside(t, n) for n in new.target_ranges) for t in old.target_ranges)
            for new in shifted
        ):
            return finish("changed_existing_links", "rejected")

    def remainder(ranges):
        pieces = []
        for span in ranges:
            if not overlaps(span, source):
                pieces.append(span)
            else:
                if span.start < source.start:
                    pieces.append(TextRange(span.start, source.start))
                if span.end > source.end:
                    pieces.append(TextRange(source.end, span.end))
        return tuple(pieces)

    candidate = AlignmentResult(
        result.source,
        result.target,
        tuple(external) + shifted,
        remainder(result.unaligned),
        remainder(result.ambiguous),
    )
    projection = project_formatting(candidate, scopes)
    report["candidate_alignment"] = asdict(candidate)
    report["projection"] = asdict(projection)
    kept = {item.scope.identity: item for item in projection.formatting}
    if scope.identity not in kept or any(
        kept.get(item.scope.identity) != item for item in baseline.formatting
    ):
        return finish("projection_conflict", "rejected")
    return finish("structural_checks_passed_manual_review_required", "candidate")


def evaluate_local(adapter, result, case):
    scopes = tuple(
        FormattingScope(item["id"], TextRange(*item["source"]), item.get("link_target"))
        for item in case.get("scopes", [])
    )
    if case.get("markers"):
        return [
            {"scope": scope.identity, "status": "skipped", "reason": "protected_case", "calls": 0}
            for scope in scopes
        ]
    # Independent proposals against the same baseline, never cascading repairs.
    reviews = [review_scope(adapter, result, scopes, scope) for scope in scopes]
    reject_conflicting_proposals(reviews)
    return reviews


def reject_conflicting_proposals(reviews: list[dict]) -> None:
    """Reject all overlapping candidate windows, independent of review order.

    Disjoint proposals remain independent; this does not apply or merge them.
    Even overlapping optical scopes are deferred until joint validation exists.
    """
    candidates = [row for row in reviews if row["status"] == "candidate"]
    conflicts: dict[str, set[str]] = {}
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if any(
                overlaps(TextRange(**left["window"][side]), TextRange(**right["window"][side]))
                for side in ("source", "target")
            ):
                conflicts.setdefault(left["scope"], set()).add(right["scope"])
                conflicts.setdefault(right["scope"], set()).add(left["scope"])
    for row in candidates:
        if row["scope"] in conflicts:
            row.update(
                status="rejected",
                reason="conflicting_proposals",
                conflicts_with=sorted(conflicts[row["scope"]]),
            )
