"""Tests for acyclic `$ref`, `$defs`, and `definitions` resolution."""

from __future__ import annotations

from typing import Any

from toolschema_compat.resolve import (
    check_refs,
    resolve_json_pointer,
    resolve_refs,
    unescape_json_pointer,
)
from toolschema_compat.rules import load_rules


def test_unescape_json_pointer() -> None:
    assert unescape_json_pointer("a~1b~0c") == "a/b~c"


def test_resolve_json_pointer_cases() -> None:
    root: dict[str, Any] = {
        "$defs": {
            "User/Profile~1": {"type": "object", "properties": {"id": {"type": "string"}}},
            "ListContainer": [{"type": "integer"}],
        }
    }
    assert resolve_json_pointer(root, "#") == root
    assert resolve_json_pointer(root, "#/$defs/User~1Profile~01") == {
        "type": "object",
        "properties": {"id": {"type": "string"}},
    }
    assert resolve_json_pointer(root, "#/$defs/ListContainer/0") == {"type": "integer"}
    assert resolve_json_pointer(root, "#/$defs/ListContainer/99") is None
    assert resolve_json_pointer(root, "#/$defs/ListContainer/not_an_int") is None
    assert resolve_json_pointer(root, "https://example.com/schema.json") is None
    assert resolve_json_pointer(root, "#invalid") is None
    assert resolve_json_pointer(root, "#/$defs/Missing") is None
    assert resolve_json_pointer(root, "#/$defs/User~1Profile~01/type") is None


def test_resolve_refs_direct_and_mutual_cycles_terminate() -> None:
    ruleset = load_rules("gemini")
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "self_ref": {"$ref": "#", "description": "Root self reference"},
            "node_a": {"$ref": "#/$defs/NodeA"},
        },
        "$defs": {
            "NodeA": {
                "type": "object",
                "properties": {
                    "b": {"$ref": "#/$defs/NodeB"},
                },
            },
            "NodeB": {
                "type": "object",
                "properties": {
                    "a": {"$ref": "#/$defs/NodeA", "description": "Back to A"},
                },
            },
        },
    }

    issues = check_refs(schema, ruleset)
    assert any(i.lossy for i in issues)

    fixed, changes = resolve_refs(schema, ruleset)
    assert "$defs" not in fixed
    assert fixed["properties"]["self_ref"] == {
        "type": "object",
        "description": "Root self reference",
    }
    back_edge = fixed["properties"]["node_a"]["properties"]["b"]["properties"]["a"]
    assert back_edge == {"type": "object", "description": "Back to A"}
    assert any(c.action == "truncated_cyclic_ref" and c.lossy for c in changes)


def test_resolve_refs_unresolvable_and_non_string_ref() -> None:
    ruleset = load_rules("gemini")
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "external": {
                "$ref": "https://example.com/external.json#/User",
                "description": "External user",
            },
            "bad_ref": {"$ref": 12345, "description": "Numeric ref"},
            "items_list": [
                {"$ref": "#/$defs/MissingDef"},
            ],
        },
    }

    issues = check_refs(schema, ruleset)
    assert len(issues) == 3
    assert all(i.lossy for i in issues)

    fixed, changes = resolve_refs(schema, ruleset)
    assert fixed["properties"]["external"] == {
        "type": "object",
        "description": "External user",
    }
    assert fixed["properties"]["bad_ref"] == {
        "type": "object",
        "description": "Numeric ref",
    }
    assert fixed["properties"]["items_list"][0] == {"type": "object"}
    assert all(c.lossy for c in changes)


def test_resolve_refs_diamond_reuse_is_lossless() -> None:
    ruleset = load_rules("gemini")
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "primary": {"$ref": "#/$defs/Coord"},
            "secondary": {"$ref": "#/$defs/Coord"},
        },
        "$defs": {
            "Coord": {
                "type": "object",
                "properties": {"x": {"type": "number"}},
            }
        },
    }

    issues = check_refs(schema, ruleset)
    assert len(issues) == 3  # $defs + 2 $ref pointers
    assert all(not i.lossy for i in issues)

    fixed, changes = resolve_refs(schema, ruleset)
    assert "$defs" not in fixed
    assert fixed["properties"]["primary"] == {
        "type": "object",
        "properties": {"x": {"type": "number"}},
    }
    assert fixed["properties"]["secondary"] == {
        "type": "object",
        "properties": {"x": {"type": "number"}},
    }
    assert all(not c.lossy for c in changes)
