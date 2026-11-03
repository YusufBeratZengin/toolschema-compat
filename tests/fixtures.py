"""Real-world-derived tool JSON Schema fixtures (8+ per provider target, zero secrets)."""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# GEMINI FIXTURES (8 schemas derived from gemini-cli#13326, workspace_mcp#1099, thClaws#172)
# ---------------------------------------------------------------------------
GEMINI_FIXTURES: dict[str, dict[str, Any]] = {
    "1_mcp_defs_and_ref": {
        "type": "object",
        "properties": {
            "query": {"$ref": "#/$defs/SearchQuery"},
        },
        "required": ["query"],
        "$defs": {
            "SearchQuery": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["term"],
            }
        },
    },
    "2_workspace_type_array": {
        "type": "object",
        "properties": {
            "calendar_id": {"type": ["string", "null"]},
            "max_results": {"type": ["integer", "string"]},
        },
        "required": ["calendar_id"],
    },
    "3_thclaws_additional_props_and_meta": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.com/schemas/tool.json",
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "default": "status",
                "examples": ["status", "info"],
            }
        },
        "required": ["command"],
        "additionalProperties": False,
    },
    "4_pydantic_anyof_null_optional": {
        "type": "object",
        "properties": {
            "page_token": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
                "description": "Pagination token from previous call.",
            },
            "timeout_ms": {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "number"},
                    {"type": "null"},
                ]
            },
        },
        "required": ["page_token"],
    },
    "5_const_and_oneof_discriminated": {
        "type": "object",
        "properties": {
            "api_version": {"const": "v1"},
            "mode": {
                "oneOf": [
                    {"type": "string", "enum": ["fast", "accurate"]},
                    {"type": "integer"},
                ]
            },
        },
        "required": ["api_version", "mode"],
    },
    "6_unsupported_regex_and_email_format": {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "pattern": "^[a-z0-9-]+$",
                "minLength": 2,
                "maxLength": 50,
            },
            "contact_email": {
                "type": "string",
                "format": "email",
            },
            "created_at": {
                "type": "string",
                "format": "date-time",
            },
        },
        "required": ["slug", "contact_email"],
    },
    "7_recursive_tree_node": {
        "type": "object",
        "properties": {
            "root": {"$ref": "#/$defs/TreeNode"},
        },
        "required": ["root"],
        "$defs": {
            "TreeNode": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "parent": {"$ref": "#/$defs/TreeNode", "description": "Parent node"},
                },
                "required": ["label"],
            }
        },
    },
    "8_parameters_json_schema_envelope": {
        "name": "list_drive_files",
        "description": "List files using Gemini parametersJsonSchema field.",
        "parametersJsonSchema": {
            "type": "object",
            "properties": {
                "folder": {"$ref": "#/$defs/FolderSpec"},
            },
            "required": ["folder", "missing_orphan_key"],
            "$defs": {
                "FolderSpec": {
                    "type": "object",
                    "properties": {
                        "folder_id": {"type": "string"},
                    },
                    "required": ["folder_id"],
                }
            },
        },
    },
}

# ---------------------------------------------------------------------------
# OPENAI STRICT FIXTURES (8 schemas derived from prism#940, Archon#1843, OpenAI docs)
# ---------------------------------------------------------------------------
OPENAI_STRICT_FIXTURES: dict[str, dict[str, Any]] = {
    "1_prism_missing_additional_props": {
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
            },
        },
        "required": ["location", "coordinates"],
    },
    "2_archon_optional_not_in_required": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "include_archived": {"type": "boolean"},
            "tag_filter": {"type": "string", "enum": ["bug", "feature"]},
        },
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "3_defs_ref_with_siblings": {
        "type": "object",
        "properties": {
            "author": {
                "$ref": "#/$defs/Author",
                "description": "Primary document author.",
            },
        },
        "required": ["author"],
        "additionalProperties": False,
        "$defs": {
            "Author": {
                "type": "object",
                "properties": {
                    "handle": {"type": "string"},
                },
                "required": ["handle"],
            }
        },
    },
    "4_openapi_nullable_keyword": {
        "type": "object",
        "properties": {
            "nickname": {
                "type": "string",
                "nullable": True,
            },
            "role": {
                "type": "string",
                "enum": ["admin", "viewer"],
                "nullable": True,
            },
        },
        "required": ["nickname", "role"],
        "additionalProperties": False,
    },
    "5_string_and_numeric_constraints": {
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "pattern": "^[a-zA-Z0-9_]+$",
                "minLength": 3,
                "maxLength": 20,
            },
            "webhook_url": {
                "type": "string",
                "format": "uri",
            },
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "multipleOf": 5,
            },
        },
        "required": ["username", "webhook_url", "score"],
        "additionalProperties": False,
    },
    "6_oneof_const_and_allof": {
        "type": "object",
        "properties": {
            "kind": {"const": "report"},
            "target": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "integer"},
                ]
            },
            "merged": {
                "allOf": [
                    {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
                    {"type": "object", "properties": {"b": {"type": "integer"}}, "required": ["b"]},
                ]
            },
        },
        "required": ["kind", "target", "merged"],
        "additionalProperties": False,
    },
    "7_open_map_additional_props_schema": {
        "type": "object",
        "properties": {
            "headers": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            }
        },
        "required": ["headers"],
        "additionalProperties": False,
    },
    "8_cyclic_comment_thread_envelope": {
        "type": "function",
        "function": {
            "name": "post_comment_thread",
            "description": "Create a nested comment thread.",
            "parameters": {
                "type": "object",
                "properties": {
                    "comment": {"$ref": "#/$defs/Comment"},
                },
                "required": ["comment"],
                "$defs": {
                    "Comment": {
                        "type": "object",
                        "properties": {
                            "body": {"type": "string"},
                            "reply": {"$ref": "#/$defs/ReplyThread"},
                        },
                        "required": ["body", "reply"],
                    },
                    "ReplyThread": {
                        "type": "object",
                        "properties": {
                            "parent": {"$ref": "#/$defs/Comment"},
                        },
                        "required": ["parent"],
                    },
                },
            },
        },
    },
}

# ---------------------------------------------------------------------------
# ANTHROPIC FIXTURES (8 schemas derived from Claude tool use & structured outputs)
# ---------------------------------------------------------------------------
ANTHROPIC_FIXTURES: dict[str, dict[str, Any]] = {
    "1_missing_root_type_object": {
        "properties": {
            "ticker": {"type": "string"},
        },
        "required": ["ticker"],
    },
    "2_top_level_union_root": {
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
    },
    "3_defs_diamond_refs": {
        "type": "object",
        "properties": {
            "source_endpoint": {"$ref": "#/$defs/Endpoint"},
            "destination_endpoint": {"$ref": "#/$defs/Endpoint"},
        },
        "required": ["source_endpoint", "destination_endpoint"],
        "additionalProperties": False,
        "$defs": {
            "Endpoint": {
                "type": "object",
                "properties": {
                    "host": {"type": "string"},
                    "port": {"type": "integer"},
                },
                "required": ["host", "port"],
            }
        },
    },
    "4_openapi_nullable_and_const": {
        "type": "object",
        "properties": {
            "protocol": {"const": "https"},
            "reason": {"type": "string", "nullable": True},
        },
        "required": ["protocol"],
        "additionalProperties": False,
    },
    "5_oneof_and_allof_composition": {
        "type": "object",
        "properties": {
            "identifier": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "integer"},
                ]
            },
            "config": {
                "allOf": [
                    {"type": "object", "properties": {"retries": {"type": "integer"}}},
                    {"type": "object", "properties": {"verbose": {"type": "boolean"}}},
                ]
            },
        },
        "required": ["identifier"],
        "additionalProperties": False,
    },
    "6_validation_constraints_pattern_format": {
        "type": "object",
        "properties": {
            "trace_id": {
                "type": "string",
                "format": "uuid",
                "pattern": "^[0-9a-f-]{36}$",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "maxItems": 10,
                "uniqueItems": True,
            },
        },
        "required": ["trace_id"],
        "additionalProperties": False,
    },
    "7_open_object_and_orphan_required": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name", "non_existent_field", "name"],
        "additionalProperties": True,
    },
    "8_recursive_category_definitions": {
        "name": "classify_item",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"$ref": "#/definitions/Category"},
            },
            "required": ["category"],
            "definitions": {
                "Category": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "subcategories": {
                            "type": "array",
                            "items": {"$ref": "#/definitions/Category"},
                        },
                    },
                    "required": ["title"],
                }
            },
        },
    },
}

ALL_TARGET_FIXTURES: dict[str, dict[str, dict[str, Any]]] = {
    "gemini": GEMINI_FIXTURES,
    "openai-strict": OPENAI_STRICT_FIXTURES,
    "anthropic": ANTHROPIC_FIXTURES,
}
