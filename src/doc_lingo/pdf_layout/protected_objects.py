"""Object ownership and explicit text flows, independent of geometric overlap."""

import hashlib
import json
from pathlib import Path

from .preview import _load


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_object_plan(layout, assignments, destination):
    """Write a source-bound intermediate; do not render or translate its objects."""
    layout, assignments, destination = map(Path, (layout, assignments, destination))
    if destination.exists():
        raise FileExistsError(destination)
    manifest = _load(layout, "manifest.json")
    spec = json.loads(assignments.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("Object assignments must be a JSON object")
    digest = _hash(layout / "manifest.json")
    if spec.get("schema_version") != 1 or spec.get("extraction_sha256") != digest:
        raise ValueError("Object assignments must match the extraction manifest SHA-256")
    inventory, pages = {}, []
    for ref in manifest["pages"]:
        page = _load(layout, ref["file"])
        if page["pdf_page"] != ref["pdf_page"]:
            raise ValueError("Page does not match extraction manifest")
        graphics = _load(layout, page["graphics_file"])
        pages.append(
            {
                "pdf_page": page["pdf_page"],
                "file": ref["file"],
                "sha256": _hash(layout / ref["file"]),
                "graphics_file": page["graphics_file"],
                "graphics_sha256": _hash(layout / page["graphics_file"]),
            }
        )
        entries = [
            (o["id"], o["kind"], o)
            for o in page["objects"]
            if o["kind"] in {"text_fragment", "image"}
        ]
        entries += [
            (f"{page['id']}-vector-{i:05d}", "vector", path)
            for i, path in enumerate(graphics["paths"])
        ]
        for key, kind, evidence in entries:
            if key in inventory:
                raise ValueError(f"Duplicate source object ID: {key}")
            inventory[key] = {"kind": kind, "pdf_page": page["pdf_page"], "evidence": evidence}

    objects, owners = {}, {}
    if not isinstance(spec.get("objects", []), list) or not isinstance(spec.get("flows", []), list):
        raise ValueError("Objects and flows must be lists")
    for obj in spec.get("objects", []):
        if not isinstance(obj, dict):
            raise ValueError("Protected object must be a JSON object")
        key, members = obj.get("id"), obj.get("members")
        if (
            not isinstance(key, str)
            or not key
            or key in objects
            or key.startswith("image:")
            or not isinstance(obj.get("kind"), str)
            or not obj["kind"]
            or not isinstance(obj.get("reason"), str)
            or not obj["reason"].strip()
            or not isinstance(members, list)
            or not members
        ):
            raise ValueError("Protected objects require unique IDs, kind, reason and members")
        for member in members:
            if not isinstance(member, str) or member not in inventory or member in owners:
                raise ValueError(f"Unknown or multiply owned source object: {member}")
            owners[member] = key
        if len({inventory[m]["pdf_page"] for m in members}) != 1:
            raise ValueError(f"Protected object {key} spans pages")
        objects[key] = {**obj, "translate": False}
    # Images are already identifiable objects; overlap never claims nearby text.
    for member, item in inventory.items():
        if item["kind"] == "image" and member not in owners:
            key = "image:" + member
            if key in objects:
                raise ValueError(f"Reserved automatic image ID: {key}")
            objects[key] = {
                "id": key,
                "kind": "image",
                "reason": "Extracted image object",
                "members": [member],
                "translate": False,
            }
            owners[member] = key

    used_text, placed, flow_ids = set(), set(), set()
    flows = spec.get("flows", [])
    for flow in flows:
        if not isinstance(flow, dict) or not isinstance(flow.get("parts"), list):
            raise ValueError("Flow must have a list of parts")
        key = flow.get("id")
        if not isinstance(key, str) or not key or key in flow_ids or not flow.get("parts"):
            raise ValueError("Flows require unique IDs and nonempty parts")
        flow_ids.add(key)
        for part in flow["parts"]:
            if not isinstance(part, dict) or any(not isinstance(v, str) for v in part.values()):
                raise ValueError("Flow references must be strings")
            if set(part) == {"text_id"}:
                member = part["text_id"]
                if (
                    member not in inventory
                    or inventory[member]["kind"] != "text_fragment"
                    or member in owners
                    or member in used_text
                ):
                    raise ValueError(f"Invalid, protected or repeated flow text: {member}")
                used_text.add(member)
            elif set(part) == {"object_id"}:
                member = part["object_id"]
                if member not in objects or member in placed:
                    raise ValueError(f"Unknown or repeated protected object reference: {member}")
                placed.add(member)
            else:
                raise ValueError("Flow parts require exactly text_id or object_id")
    result = {
        "schema_version": 1,
        "kind": "pdf_object_plan",
        "source": manifest["source"],
        "extraction_sha256": digest,
        "assignments_sha256": _hash(assignments),
        "pages": pages,
        "inventory": inventory,
        "objects": list(objects.values()),
        "flows": flows,
        "unassigned_text_ids": [
            key
            for key, item in inventory.items()
            if item["kind"] == "text_fragment" and key not in owners and key not in used_text
        ],
        "unplaced_object_ids": [key for key in objects if key not in placed],
        "unassigned_vector_ids": [
            key for key, item in inventory.items() if item["kind"] == "vector" and key not in owners
        ],
    }
    # All validation/serialization precedes publication. No existing file is replaced.
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    return destination
