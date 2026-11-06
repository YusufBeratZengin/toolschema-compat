"""Tests for `check_schema`, `fix_schema`, idempotency, lossy flags, and MCP envelopes."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.fixtures import (
    ALL_TARGET_FIXTURES,
    ANTHROPIC_FIXTURES,
    GEMINI_FIXTURES,
    OPENAI_STRICT_FIXTURES,
)
from toolschema_compat import (
    SUPPORTED_TARGETS,
    check_schema,
    convert_mcp_tools,
    fix_schema,
    is_lossless,
)


def test_minimum_eight_fixtures_per_target() -> None:
    assert len(GEMINI_FIXTURES) >= 8
    assert len(OPENAI_STRICT_FIXTURES) >= 8
    assert len(ANTHROPIC_FIXTURES) >= 8


EXPECTED_FIXTURE_OUTCOMES: dict[tuple[str, str], dict[str, Any]] = {
    # --- GEMINI ---
    ("gemini", "1_mcp_defs_and_ref"): {
        "lossless": True,
        "rules": {"GEMINI_REF_DEFS"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["term"],
                }
            },
            "required": ["query"],
        },
    },
    ("gemini", "2_workspace_type_array"): {
        "lossless": True,
        "rules": {"GEMINI_TYPE_ARRAY"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "calendar_id": {"type": "string", "nullable": True},
                "max_results": {"anyOf": [{"type": "integer"}, {"type": "string"}]},
            },
            "required": ["calendar_id"],
        },
    },
    ("gemini", "3_thclaws_additional_props_and_meta"): {
        "lossless": False,
        "rules": {"GEMINI_UNSUPPORTED_KEYWORD", "GEMINI_ADDITIONAL_PROPERTIES"},
        "deleted": {"additionalProperties"},
        "schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    ("gemini", "4_pydantic_anyof_null_optional"): {
        "lossless": True,
        "rules": {"GEMINI_ANYOF_NULL", "GEMINI_UNSUPPORTED_KEYWORD"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "page_token": {
                    "type": "string",
                    "nullable": True,
                    "description": "Pagination token from previous call.",
                },
                "timeout_ms": {
                    "anyOf": [{"type": "integer"}, {"type": "number"}],
                    "nullable": True,
                },
            },
            "required": ["page_token"],
        },
    },
    ("gemini", "5_const_and_oneof_discriminated"): {
        "lossless": False,
        "rules": {"GEMINI_CONST", "GEMINI_ONEOF"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "api_version": {"type": "string", "enum": ["v1"]},
                "mode": {
                    "anyOf": [
                        {"type": "string", "enum": ["fast", "accurate"]},
                        {"type": "integer"},
                    ]
                },
            },
            "required": ["api_version", "mode"],
        },
    },
    ("gemini", "6_unsupported_regex_and_email_format"): {
        "lossless": False,
        "rules": {"GEMINI_UNSUPPORTED_CONSTRAINT", "GEMINI_UNSUPPORTED_FORMAT"},
        "deleted": {"pattern", "minLength", "maxLength", "format"},
        "schema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "contact_email": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["slug", "contact_email"],
        },
    },
    ("gemini", "7_recursive_tree_node"): {
        "lossless": False,
        "rules": {"GEMINI_REF_DEFS", "GEMINI_REF_CYCLE"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "root": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "parent": {"type": "object", "description": "Parent node"},
                    },
                    "required": ["label"],
                }
            },
            "required": ["root"],
        },
    },
    ("gemini", "8_parameters_json_schema_envelope"): {
        "lossless": True,
        "rules": {"GEMINI_REF_DEFS", "GEMINI_ORPHAN_REQUIRED"},
        "deleted": set(),
        "schema": {
            "name": "list_drive_files",
            "description": "List files using Gemini parametersJsonSchema field.",
            "parametersJsonSchema": {
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "object",
                        "properties": {"folder_id": {"type": "string"}},
                        "required": ["folder_id"],
                    }
                },
                "required": ["folder"],
            },
        },
    },
    # --- OPENAI STRICT ---
    ("openai-strict", "1_prism_missing_additional_props"): {
        "lossless": True,
        "rules": {"OPENAI_STRICT_ADDITIONAL_PROPERTIES"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "coordinates": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                    },
                    "required": ["lat", "lon"],
                    "additionalProperties": False,
                },
            },
            "required": ["location", "coordinates"],
            "additionalProperties": False,
        },
    },
    ("openai-strict", "2_archon_optional_not_in_required"): {
        "lossless": True,
        "rules": {"OPENAI_STRICT_REQUIRED_PROPERTIES"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "include_archived": {"type": ["boolean", "null"]},
                "tag_filter": {
                    "type": ["string", "null"],
                    "enum": ["bug", "feature", None],
                },
            },
            "required": ["project_id", "include_archived", "tag_filter"],
            "additionalProperties": False,
        },
    },
    ("openai-strict", "3_defs_ref_with_siblings"): {
        "lossless": True,
        "rules": {"OPENAI_STRICT_REF_DEFS", "OPENAI_STRICT_ADDITIONAL_PROPERTIES"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "author": {
                    "type": "object",
                    "properties": {"handle": {"type": "string"}},
                    "required": ["handle"],
                    "description": "Primary document author.",
                    "additionalProperties": False,
                }
            },
            "required": ["author"],
            "additionalProperties": False,
        },
    },
    ("openai-strict", "4_openapi_nullable_keyword"): {
        "lossless": True,
        "rules": {"OPENAI_STRICT_NULLABLE_KEYWORD"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "nickname": {"type": ["string", "null"]},
                "role": {
                    "type": ["string", "null"],
                    "enum": ["admin", "viewer", None],
                },
            },
            "required": ["nickname", "role"],
            "additionalProperties": False,
        },
    },
    ("openai-strict", "5_string_and_numeric_constraints"): {
        "lossless": False,
        "rules": {"OPENAI_STRICT_UNSUPPORTED_CONSTRAINT"},
        "deleted": {
            "pattern",
            "minLength",
            "maxLength",
            "format",
            "minimum",
            "maximum",
            "multipleOf",
        },
        "schema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "webhook_url": {"type": "string"},
                "score": {"type": "integer"},
            },
            "required": ["username", "webhook_url", "score"],
            "additionalProperties": False,
        },
    },
    ("openai-strict", "6_oneof_const_and_allof"): {
        "lossless": False,
        "rules": {
            "OPENAI_STRICT_CONST",
            "OPENAI_STRICT_ONEOF",
            "OPENAI_STRICT_ALLOF",
            "OPENAI_STRICT_ADDITIONAL_PROPERTIES",
        },
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["report"]},
                "target": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                "merged": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "string"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                    "additionalProperties": False,
                },
            },
            "required": ["kind", "target", "merged"],
            "additionalProperties": False,
        },
    },
    ("openai-strict", "7_open_map_additional_props_schema"): {
        "lossless": False,
        "rules": {"OPENAI_STRICT_MAP_NARROWED", "OPENAI_STRICT_REQUIRED_PROPERTIES"},
        "deleted": {"additionalProperties"},
        "schema": {
            "type": "object",
            "properties": {
                "headers": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                    "required": [],
                }
            },
            "required": ["headers"],
            "additionalProperties": False,
        },
    },
    ("openai-strict", "8_cyclic_comment_thread_envelope"): {
        "lossless": False,
        "rules": {
            "OPENAI_STRICT_REF_DEFS",
            "OPENAI_STRICT_REF_CYCLE",
            "OPENAI_STRICT_ADDITIONAL_PROPERTIES",
            "OPENAI_STRICT_REQUIRED_PROPERTIES",
        },
        "deleted": set(),
        "schema": {
            "type": "function",
            "function": {
                "name": "post_comment_thread",
                "description": "Create a nested comment thread.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "comment": {
                            "type": "object",
                            "properties": {
                                "body": {"type": "string"},
                                "reply": {
                                    "type": "object",
                                    "properties": {
                                        "parent": {
                                            "type": "object",
                                            "properties": {},
                                            "additionalProperties": False,
                                            "required": [],
                                        }
                                    },
                                    "required": ["parent"],
                                    "additionalProperties": False,
                                },
                            },
                            "required": ["body", "reply"],
                            "additionalProperties": False,
                        }
                    },
                    "required": ["comment"],
                    "additionalProperties": False,
                },
            },
        },
    },
    # --- ANTHROPIC ---
    ("anthropic", "1_missing_root_type_object"): {
        "lossless": True,
        "rules": {"ANTHROPIC_ROOT_OBJECT", "ANTHROPIC_ADDITIONAL_PROPERTIES"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
    },
    ("anthropic", "2_top_level_union_root"): {
        "lossless": False,
        "rules": {"ANTHROPIC_ROOT_OBJECT"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "value": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {"id": {"type": "integer"}},
                            "required": ["id"],
                            "additionalProperties": False,
                        },
                        {
                            "type": "object",
                            "properties": {"slug": {"type": "string"}},
                            "required": ["slug"],
                            "additionalProperties": False,
                        },
                    ]
                }
            },
            "required": ["value"],
            "additionalProperties": False,
        },
    },
    ("anthropic", "3_defs_diamond_refs"): {
        "lossless": True,
        "rules": {"ANTHROPIC_REF_DEFS", "ANTHROPIC_ADDITIONAL_PROPERTIES"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "source_endpoint": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string"},
                        "port": {"type": "integer"},
                    },
                    "required": ["host", "port"],
                    "additionalProperties": False,
                },
                "destination_endpoint": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string"},
                        "port": {"type": "integer"},
                    },
                    "required": ["host", "port"],
                    "additionalProperties": False,
                },
            },
            "required": ["source_endpoint", "destination_endpoint"],
            "additionalProperties": False,
        },
    },
    ("anthropic", "4_openapi_nullable_and_const"): {
        "lossless": True,
        "rules": {"ANTHROPIC_CONST", "ANTHROPIC_NULLABLE_KEYWORD"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "enum": ["https"]},
                "reason": {"type": ["string", "null"]},
            },
            "required": ["protocol"],
            "additionalProperties": False,
        },
    },
    ("anthropic", "5_oneof_and_allof_composition"): {
        "lossless": False,
        "rules": {
            "ANTHROPIC_ONEOF",
            "ANTHROPIC_ALLOF",
            "ANTHROPIC_ADDITIONAL_PROPERTIES",
        },
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {
                "identifier": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                "config": {
                    "type": "object",
                    "properties": {
                        "retries": {"type": "integer"},
                        "verbose": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["identifier"],
            "additionalProperties": False,
        },
    },
    ("anthropic", "6_validation_constraints_pattern_format"): {
        "lossless": False,
        "rules": {"ANTHROPIC_UNSUPPORTED_CONSTRAINT"},
        "deleted": {
            "format",
            "pattern",
            "minLength",
            "minItems",
            "maxItems",
            "uniqueItems",
        },
        "schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["trace_id"],
            "additionalProperties": False,
        },
    },
    ("anthropic", "7_open_object_and_orphan_required"): {
        "lossless": False,
        "rules": {"ANTHROPIC_ORPHAN_REQUIRED", "ANTHROPIC_MAP_NARROWED"},
        "deleted": set(),
        "schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    ("anthropic", "8_recursive_category_definitions"): {
        "lossless": False,
        "rules": {
            "ANTHROPIC_REF_DEFS",
            "ANTHROPIC_REF_CYCLE",
            "ANTHROPIC_ADDITIONAL_PROPERTIES",
        },
        "deleted": set(),
        "schema": {
            "name": "classify_item",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "subcategories": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {},
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["title"],
                        "additionalProperties": False,
                    }
                },
                "required": ["category"],
                "additionalProperties": False,
            },
        },
    },
}


@pytest.mark.parametrize(
    ("target", "fixture_name", "schema"),
    [
        (target, name, schema)
        for target, fixtures in ALL_TARGET_FIXTURES.items()
        for name, schema in fixtures.items()
    ],
)
def test_target_fixtures_detected_fixed_and_idempotent(
    target: str,
    fixture_name: str,
    schema: dict[str, Any],
) -> None:
    original_copy = copy.deepcopy(schema)
    expected = EXPECTED_FIXTURE_OUTCOMES[(target, fixture_name)]

    # 1. Must detect expected compatibility issues on the broken fixture
    issues = check_schema(schema, target)
    assert len(issues) >= 1, f"Expected issues for {target}/{fixture_name}"
    assert schema == original_copy, "check_schema must not mutate input"
    assert {i.rule_id for i in issues} == expected["rules"]

    for issue in issues:
        assert issue.rule_id
        assert issue.path.startswith("$")
        assert issue.source_url.startswith("https://")

    # 2. Must fix all issues in a single call and match independent expected outcome
    fixed1, changes1 = fix_schema(schema, target)
    assert len(changes1) == len(issues)
    assert schema == original_copy, "fix_schema must not mutate input"
    assert is_lossless(changes1) is expected["lossless"]
    assert {c.rule_id for c in changes1} == expected["rules"]
    deleted = {c.deleted_constraint for c in changes1 if c.deleted_constraint}
    assert deleted == expected["deleted"]
    assert fixed1 == expected["schema"]

    for change in changes1:
        assert change.rule_id
        assert change.path.startswith("$")
        assert change.source_url.startswith("https://")

    # 3. Fixed schema must have 0 remaining issues
    remaining_issues = check_schema(fixed1, target)
    assert remaining_issues == []

    # 4. Second application of fix_schema must be strictly idempotent
    fixed2, changes2 = fix_schema(fixed1, target)
    assert changes2 == []
    assert fixed2 == fixed1


@pytest.mark.parametrize("target", SUPPORTED_TARGETS)
def test_cross_target_idempotency_across_all_24_fixtures(target: str) -> None:
    for _, group in ALL_TARGET_FIXTURES.items():
        for _, schema in group.items():
            fixed1, _ = fix_schema(schema, target)
            assert check_schema(fixed1, target) == []
            fixed2, changes2 = fix_schema(fixed1, target)
            assert changes2 == []
            assert fixed2 == fixed1


def test_lossless_vs_lossy_classification() -> None:
    # Syntactic inlining of $defs + $ref in Gemini is lossless
    lossless_schema = GEMINI_FIXTURES["1_mcp_defs_and_ref"]
    _, changes = fix_schema(lossless_schema, "gemini")
    assert is_lossless(changes) is True

    # Stripping regex pattern and email format in Gemini is lossy
    lossy_schema = GEMINI_FIXTURES["6_unsupported_regex_and_email_format"]
    _, lossy_changes = fix_schema(lossy_schema, "gemini")
    assert is_lossless(lossy_changes) is False
    deleted = {c.deleted_constraint for c in lossy_changes if c.deleted_constraint}
    assert {"pattern", "format", "minLength", "maxLength"} <= deleted

    # Overwriting map `additionalProperties: {"type": "string"}` in OpenAI strict is lossy
    map_schema = OPENAI_STRICT_FIXTURES["7_open_map_additional_props_schema"]
    _, map_changes = fix_schema(map_schema, "openai-strict")
    assert is_lossless(map_changes) is False
    assert any(c.deleted_constraint == "additionalProperties" for c in map_changes)


def test_openai_strict_optional_to_nullable_and_required() -> None:
    schema = OPENAI_STRICT_FIXTURES["2_archon_optional_not_in_required"]
    fixed, changes = fix_schema(schema, "openai-strict")
    assert is_lossless(changes) is True
    assert fixed["required"] == ["project_id", "include_archived", "tag_filter"]
    assert fixed["properties"]["include_archived"]["type"] == ["boolean", "null"]
    assert fixed["properties"]["tag_filter"]["type"] == ["string", "null"]
    assert fixed["properties"]["tag_filter"]["enum"] == ["bug", "feature", None]


def test_edge_cases_allof_const_null_and_primitive_root() -> None:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "empty_allof": {"allOf": [], "type": "string"},
            "conflicting_allof": {
                "allOf": [
                    {"type": "string", "minLength": 1},
                    {"type": "integer"},
                ]
            },
            "null_const": {"const": None},
            "bool_const": {"const": True},
            "int_const": {"const": 42},
            "float_const": {"const": 3.14},
            "anyof_const_null": {"anyOf": [{"const": "fixed_val"}, {"type": "null"}]},
            "null_only_anyof": {"anyOf": [{"type": "null"}]},
            "null_only_type_array": {"type": ["null"]},
            "standalone_null_type": {"type": "null"},
        },
        "required": ["null_const"],
    }

    fixed_gemini, changes_gemini = fix_schema(schema, "gemini")
    assert check_schema(fixed_gemini, "gemini") == []
    assert any(c.lossy for c in changes_gemini)
    assert fixed_gemini["properties"]["anyof_const_null"] == {
        "enum": ["fixed_val"],
        "type": "string",
        "nullable": True,
    }

    # Primitive root schema wrapping
    primitive_root: dict[str, Any] = {"type": "string", "pattern": "^[a-z]+$"}
    fixed_root, root_changes = fix_schema(primitive_root, "openai-strict")
    assert fixed_root["type"] == "object"
    assert fixed_root["additionalProperties"] is False
    assert fixed_root["required"] == ["value"]
    assert fixed_root["properties"]["value"] == {"type": "string"}
    assert any(c.lossy for c in root_changes)
    assert check_schema(fixed_root, "openai-strict") == []

    # Empty root `{}` normalization
    empty_root: dict[str, Any] = {"description": "No-arg tool"}
    fixed_empty, empty_changes = fix_schema(empty_root, "openai-strict")
    assert fixed_empty == {
        "description": "No-arg tool",
        "type": "object",
        "properties": {},
        "additionalProperties": False,
        "required": [],
    }
    assert is_lossless(empty_changes) is True
    assert check_schema(fixed_empty, "openai-strict") == []

    # OpenAI strict optional union and type array properties + simple anyOf null collapse
    strict_unions: dict[str, Any] = {
        "type": "object",
        "properties": {
            "simple_anyof_null": {
                "anyOf": [
                    {"type": "string", "enum": ["a", "b"], "description": "Pick one"},
                    {"type": "null"},
                ]
            },
            "complex_anyof_null": {
                "anyOf": [
                    {"type": "object", "properties": {"k": {"type": "string"}}},
                    {"type": "null"},
                ]
            },
            "opt_type_list": {"type": ["string", "integer"]},
            "opt_anyof": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            "opt_untyped": {"description": "Untyped field"},
            "already_nullable_enum": {
                "type": ["string", "null"],
                "enum": ["x", "y"],
            },
        },
        "required": ["simple_anyof_null", "complex_anyof_null"],
    }
    fixed_strict, _ = fix_schema(strict_unions, "openai-strict")
    assert check_schema(fixed_strict, "openai-strict") == []
    assert fixed_strict["properties"]["simple_anyof_null"]["type"] == ["string", "null"]
    assert None in fixed_strict["properties"]["simple_anyof_null"]["enum"]
    assert fixed_strict["properties"]["opt_type_list"]["type"] == [
        "string",
        "integer",
        "null",
    ]
    assert {"type": "null"} in fixed_strict["properties"]["opt_anyof"]["anyOf"]
    assert fixed_strict["properties"]["opt_untyped"]["type"] == ["string", "null"]
    assert None in fixed_strict["properties"]["already_nullable_enum"]["enum"]


def test_mcp_tools_list_and_envelope_conversions() -> None:
    mcp_doc: dict[str, Any] = {
        "tools": [
            {
                "name": "get_weather",
                "description": "Fetch weather for city.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "pattern": "^[A-Za-z ]+$"},
                        "units": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                    "required": ["city"],
                },
            }
        ]
    }

    # Preserve envelope
    fixed_preserve, changes = convert_mcp_tools(mcp_doc, "gemini", envelope="preserve")
    assert "inputSchema" in fixed_preserve["tools"][0]
    assert fixed_preserve["tools"][0]["inputSchema"]["properties"]["units"] == {
        "type": "string",
        "nullable": True,
    }
    assert any(c.deleted_constraint == "pattern" for c in changes)

    # Gemini `parameters` envelope
    fixed_gemini, _ = convert_mcp_tools(mcp_doc, "gemini", envelope="gemini")
    assert "parameters" in fixed_gemini["tools"][0]
    assert fixed_gemini["tools"][0]["name"] == "get_weather"

    # Gemini `parametersJsonSchema` envelope
    fixed_gemini_json, _ = convert_mcp_tools(mcp_doc, "gemini", envelope="gemini-json-schema")
    assert "parametersJsonSchema" in fixed_gemini_json["tools"][0]

    # OpenAI strict function envelope
    fixed_openai, _ = convert_mcp_tools(mcp_doc, "openai-strict", envelope="openai")
    fn_tool = fixed_openai["tools"][0]
    assert fn_tool["type"] == "function"
    assert fn_tool["function"]["strict"] is True
    assert fn_tool["function"]["parameters"]["additionalProperties"] is False

    # Anthropic `input_schema` envelope
    fixed_anthropic, _ = convert_mcp_tools(mcp_doc, "anthropic", envelope="anthropic")
    assert "input_schema" in fixed_anthropic["tools"][0]

    # Single raw schema converted to OpenAI envelope
    raw_openai, _ = convert_mcp_tools(
        {"type": "object", "properties": {"q": {"type": "string"}}},
        "openai-strict",
        envelope="openai",
    )
    assert raw_openai["type"] == "function"
    assert raw_openai["function"]["name"] == "tool_parameters"

    with pytest.raises(ValueError, match="Unsupported envelope"):
        convert_mcp_tools(mcp_doc, "gemini", envelope="unknown-envelope")

    with pytest.raises(TypeError, match="schema must be a dictionary"):
        fix_schema(["not", "a", "dict"], "gemini")  # type: ignore[arg-type]


def test_audit_regressions_idempotency_and_nested_compositions() -> None:
    # 1. Collapsing anyOf with null when inner branch has oneOf / allOf / pattern
    nested_anyof_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "nested_oneof": {
                "anyOf": [
                    {"oneOf": [{"type": "string", "pattern": "^a+$"}, {"type": "integer"}]},
                    {"type": "null"},
                ]
            },
            "nested_allof": {
                "anyOf": [
                    {
                        "allOf": [
                            {"properties": {"x": {"type": "string"}}},
                            {
                                "properties": {
                                    "x": {"description": "merged"},
                                    "y": {"type": "integer"},
                                }
                            },
                        ]
                    },
                    {"type": "null"},
                ]
            },
            "map_without_type": {
                "additionalProperties": {"type": "string"},
            },
            "optional_single_anyof": {
                "anyOf": [{"type": "string"}],
            },
            "optional_int_enum": {
                "enum": [10, 20],
            },
            "dup_type_array": {
                "type": ["string", "string"],
            },
            "multi_type_with_null": {
                "type": ["string", "integer", "null"],
            },
            "explicit_nullable_false": {
                "type": "string",
                "nullable": False,
            },
            "orphan_only_obj": {
                "type": "object",
                "properties": {"valid_key": {"type": "string"}},
                "required": ["missing_key"],
            },
        },
        "required": [
            "nested_oneof",
            "nested_allof",
            "map_without_type",
            "dup_type_array",
            "multi_type_with_null",
            "explicit_nullable_false",
            "orphan_only_obj",
        ],
    }

    for target in SUPPORTED_TARGETS:
        fixed1, _ = fix_schema(nested_anyof_schema, target)
        assert check_schema(fixed1, target) == [], f"Failed single-pass check on {target}"
        fixed2, changes2 = fix_schema(fixed1, target)
        assert changes2 == [], f"Failed idempotency on {target}"
        assert fixed2 == fixed1

    # Verify specific normalized shapes
    fixed_openai, _ = fix_schema(nested_anyof_schema, "openai-strict")
    assert fixed_openai["properties"]["optional_single_anyof"] == {
        "type": ["string", "null"],
    }
    assert fixed_openai["properties"]["optional_int_enum"] == {
        "type": ["integer", "null"],
        "enum": [10, 20, None],
    }
    assert fixed_openai["properties"]["map_without_type"]["type"] == "object"
    assert fixed_openai["properties"]["nested_allof"]["anyOf"][0]["properties"]["x"] == {
        "type": ["string", "null"],
        "description": "merged",
    }

    fixed_gemini, _ = fix_schema(nested_anyof_schema, "gemini")
    assert fixed_gemini["properties"]["nested_allof"]["properties"]["x"] == {
        "type": "string",
        "description": "merged",
    }
    assert fixed_gemini["properties"]["dup_type_array"] == {"type": "string"}
    assert fixed_gemini["properties"]["multi_type_with_null"] == {
        "anyOf": [{"type": "string"}, {"type": "integer"}],
        "nullable": True,
    }
    assert "required" not in fixed_gemini["properties"]["orphan_only_obj"]

    # 2. Nested allOf inside allOf and closed empty objects without silent mutation
    nested_allof_in_branch: dict[str, Any] = {
        "type": "object",
        "properties": {
            "deep": {
                "allOf": [
                    {
                        "allOf": [
                            {"type": "object", "properties": {"k1": {"type": "string"}}},
                            {"type": "object", "properties": {"k2": {"type": "integer"}}},
                        ]
                    }
                ]
            }
        },
        "required": ["deep"],
    }
    for target in SUPPORTED_TARGETS:
        fixed_deep, _ = fix_schema(nested_allof_in_branch, target)
        assert check_schema(fixed_deep, target) == []
        fixed_deep2, changes_deep2 = fix_schema(fixed_deep, target)
        assert changes_deep2 == []
        assert fixed_deep2 == fixed_deep

    closed_anthropic = {"type": "object", "additionalProperties": False}
    fixed_closed_anth, changes_closed_anth = fix_schema(closed_anthropic, "anthropic")
    assert changes_closed_anth == []
    assert fixed_closed_anth == closed_anthropic

    closed_without_props_strict = {
        "type": "object",
        "additionalProperties": False,
        "required": [],
    }
    fixed_closed_strict, changes_closed_strict = fix_schema(
        closed_without_props_strict, "openai-strict"
    )
    assert len(changes_closed_strict) == 1
    assert fixed_closed_strict["properties"] == {}
    assert check_schema(fixed_closed_strict, "openai-strict") == []

    # 3. Tuple items, parent-level allOf merge, combined oneOf+anyOf, and mixed tools list
    advanced_edges: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tuple_arr": {
                "type": "array",
                "items": [{"type": "string", "pattern": "^x$"}, True],
            },
            "parent_and_allof": {
                "type": "object",
                "properties": {"base": {"type": "string"}},
                "required": ["base"],
                "allOf": [
                    "not-a-dict-branch",
                    {"allOf": [], "properties": {"extra": {"type": "integer"}}},
                    {
                        "properties": {"base": {"pattern": "^a$"}},
                        "required": ["extra"],
                    },
                ],
            },
            "combined_oneof_anyof": {
                "anyOf": ["non-dict-branch", {"type": "string"}],
                "oneOf": [{"type": "integer"}],
            },
            "opt_single_anyof_desc": {
                "anyOf": [{"type": "boolean", "description": "Flag desc"}],
            },
        },
        "required": ["tuple_arr", "parent_and_allof", "combined_oneof_anyof"],
    }
    fixed_adv, changes_adv = fix_schema(advanced_edges, "openai-strict")
    assert any(c.lossy for c in changes_adv)
    assert fixed_adv["properties"]["opt_single_anyof_desc"] == {
        "type": ["boolean", "null"],
        "description": "Flag desc",
    }

    mixed_tools_doc: dict[str, Any] = {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "fn_no_desc",
                    "parameters": {"type": "object", "properties": {"a": {"type": "string"}}},
                },
            },
            {"type": "object", "properties": {"raw_tool": {"type": "integer"}}},
            "non_dict_entry",
        ]
    }
    for env in ("gemini", "gemini-json-schema", "openai", "anthropic"):
        converted, _ = convert_mcp_tools(mixed_tools_doc, "gemini", envelope=env)
        assert len(converted["tools"]) == 3
