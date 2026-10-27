"""Compose nested paragraph edits through their exact protected frame fragments."""

from doc_lingo.documents.odt.blocks import OdtBlock
from doc_lingo.documents.odt.package import OdtPackageError


def compose_blocks(
    content: bytes, blocks: tuple[OdtBlock, ...], replacements: dict[str, bytes]
) -> bytes:
    """Child text is translated once and patched after parent XML validation.

    Changed parent paragraphs still contain the original opaque frames. Locate
    those exact fragments in source order, then apply child edits inside them.
    Never use source byte offsets directly against a translated parent string.
    """
    children: dict[str | None, list[OdtBlock]] = {None: []}
    parents = []
    for block in blocks:
        while parents and block.start >= parents[-1].end:
            parents.pop()
        if parents and block.end > parents[-1].end:
            raise OdtPackageError("Crossing ODT paragraph ranges")
        parent = parents[-1].segment.id if parents else None
        children[parent].append(block)
        children[block.segment.id] = []
        parents.append(block)

    def patch_region(start, end, nodes, values):
        parts = []
        cursor = start
        for node, value in zip(nodes, values, strict=True):
            parts.extend((content[cursor : node.start], value))
            cursor = node.end
        parts.append(content[cursor:end])
        return b"".join(parts)

    def render(block):
        original = content[block.start : block.end]
        baseline = replacements.get(block.segment.id, original)
        nodes = children[block.segment.id]
        values = [render(node) for node in nodes]
        if not nodes:
            return baseline
        if baseline == original:
            return patch_region(block.start, block.end, nodes, values)
        parts = []
        cursor = 0
        used = 0
        for start, end in block.frames:
            fragment = content[start:end]
            position = baseline.find(fragment, cursor)
            if position < 0:
                raise OdtPackageError("ODT parent frame changed before child reconstruction")
            selected = [
                (node, value)
                for node, value in zip(nodes, values, strict=True)
                if start <= node.start and node.end <= end
            ]
            used += len(selected)
            patched = patch_region(start, end, [n for n, _ in selected], [v for _, v in selected])
            parts.extend((baseline[cursor:position], patched))
            cursor = position + len(fragment)
        if used != len(nodes):
            raise OdtPackageError("ODT nested paragraph is outside protected frames")
        parts.append(baseline[cursor:])
        return b"".join(parts)

    roots = children[None]
    return patch_region(0, len(content), roots, [render(block) for block in roots])
