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

    # 1. Must detect at least one compatibility issue on the broken fixture
    issues = check_schema(schema, target)
    assert len(issues) >= 1, f"Expected issues for {target}/{fixture_name}"
    assert schema == original_copy, "check_schema must not mutate input"

    for issue in issues:
        assert issue.rule_id
        assert issue.path.startswith("$")
        assert issue.source_url.startswith("https://")

    # 2. Must fix all issues in a single call
    fixed1, changes1 = fix_schema(schema, target)
    assert len(changes1) == len(issues)
    assert schema == original_copy, "fix_schema must not mutate input"

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
