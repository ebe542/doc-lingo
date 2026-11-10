"""Mixed overlapping content is assigned by ID, never by rectangle containment."""

import hashlib
import json

import pytest

from doc_lingo.pdf_layout.protected_objects import build_object_plan
from scripts.prepare_pdf_objects import main


@pytest.fixture
def evidence(tmp_path):
    layout = tmp_path / "layout"
    layout.mkdir()

    def save(name, data):
        (layout / name).write_text(json.dumps(data), encoding="utf-8")

    # Formula, image and prose intentionally occupy the same rectangle.
    objects = [
        {"id": key, "kind": kind, "source": {"bbox": [0, 0, 20, 20]}, "text": text}
        for key, kind, text in [
            ("before", "text_fragment", "The constraint "),
            ("formula", "text_fragment", "x²"),
            ("after", "text_fragment", " applies."),
            ("unassigned", "text_fragment", "Other paragraph"),
            ("picture", "image", ""),
        ]
    ]
    save(
        "page.json",
        {
            "schema_version": 1,
            "id": "page-0001",
            "pdf_page": 1,
            "graphics_file": "graphics.json",
            "objects": objects,
        },
    )
    save(
        "graphics.json",
        {
            "schema_version": 1,
            "paths": [{"type": "s", "items": [["l", [0, 0], [20, 20]]], "rect": [0, 0, 20, 20]}],
        },
    )
    save(
        "manifest.json",
        {
            "schema_version": 1,
            "source": {"sha256": "source"},
            "pages": [{"pdf_page": 1, "file": "page.json"}],
        },
    )
    spec = {
        "schema_version": 1,
        "extraction_sha256": hashlib.sha256((layout / "manifest.json").read_bytes()).hexdigest(),
        "objects": [
            {
                "id": "eq",
                "kind": "formula",
                "reason": "Preserve math",
                "members": ["formula", "page-0001-vector-00000"],
            }
        ],
        "flows": [
            {
                "id": "paragraph",
                "parts": [{"text_id": "before"}, {"object_id": "eq"}, {"text_id": "after"}],
            }
        ],
    }
    return layout, spec


def prepare(tmp_path, evidence):
    layout, spec = evidence
    assignments = tmp_path / "assignments.json"
    assignments.write_text(json.dumps(spec), encoding="utf-8")
    return build_object_plan(layout, assignments, tmp_path / "plan.json")


def test_overlap_does_not_claim_prose_or_image(tmp_path, evidence):
    before = {p.name: p.read_bytes() for p in evidence[0].iterdir()}
    plan = json.loads(prepare(tmp_path, evidence).read_text(encoding="utf-8"))
    assert plan["objects"][0]["members"] == ["formula", "page-0001-vector-00000"]
    assert plan["objects"][1]["members"] == ["picture"]
    assert plan["flows"] == evidence[1]["flows"]
    assert plan["unassigned_text_ids"] == ["unassigned"]
    assert plan["unplaced_object_ids"] == ["image:picture"]
    assert plan["inventory"]["before"]["evidence"]["text"] == "The constraint "
    assert all(o["translate"] is False for o in plan["objects"])
    assert before == {p.name: p.read_bytes() for p in evidence[0].iterdir()}
    with pytest.raises(FileExistsError):
        prepare(tmp_path, evidence)


@pytest.mark.parametrize(
    "case",
    [
        "stale",
        "unknown",
        "duplicate",
        "owned_text",
        "repeat_text",
        "unknown_ref",
        "repeat_ref",
        "empty",
        "duplicate_flow",
    ],
)
def test_invalid_assignment_not_published(tmp_path, evidence, case):
    _, s = evidence
    parts = s["flows"][0]["parts"]
    if case == "stale":
        s["extraction_sha256"] = "stale"
    elif case == "unknown":
        s["objects"][0]["members"].append("missing")
    elif case == "duplicate":
        s["objects"][0]["members"].append("formula")
    elif case == "owned_text":
        parts.append({"text_id": "formula"})
    elif case == "repeat_text":
        parts.append({"text_id": "before"})
    elif case == "unknown_ref":
        parts.append({"object_id": "missing"})
    elif case == "repeat_ref":
        parts.append({"object_id": "eq"})
    elif case == "empty":
        s["objects"][0]["members"] = []
    else:
        s["flows"].append(s["flows"][0])
    with pytest.raises(ValueError):
        prepare(tmp_path, evidence)
    assert not (tmp_path / "plan.json").exists()


def test_cli_completes_and_refuses_existing_file(tmp_path, evidence, capsys):
    layout, spec = evidence
    path = tmp_path / "assignment.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    args = [str(layout), "--assignments", str(path), "--output", str(tmp_path / "plan.json")]
    assert main(args) == 0
    assert "plan complete" in capsys.readouterr().out
    assert main(args) == 1
    assert "preparation failed" in capsys.readouterr().err
