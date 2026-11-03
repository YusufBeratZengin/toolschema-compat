"""Core schema compatibility checker and transformer for Gemini, OpenAI strict, and Anthropic."""

from __future__ import annotations

import copy
from typing import Any

from toolschema_compat.report import Change, Issue
from toolschema_compat.resolve import resolve_refs
from toolschema_compat.rules import RuleSet, load_rules

_SCHEMA_ENVELOPE_KEYS: tuple[str, ...] = (
    "inputSchema",
    "input_schema",
    "parametersJsonSchema",
    "parameters",
)


def is_lossless(changes: list[Change] | tuple[Change, ...]) -> bool:
    """Return True if none of the applied changes are marked `lossy=True`."""
    return all(not change.lossy for change in changes)


def _is_null_branch(branch: Any) -> bool:
    """Return True if `branch` represents a `{"type": "null"}` schema branch."""
    if not isinstance(branch, dict):
        return False
    return branch.get("type") == "null" and set(branch.keys()).issubset(
        {"type", "description", "title"}
    )


def _is_simple_type_branch(branch: Any) -> bool:
    """Return True if `branch` is a scalar type branch collapsible into `type: [...]`."""
    if not isinstance(branch, dict):
        return False
    branch_type = branch.get("type")
    if not isinstance(branch_type, str):
        return False
    if branch_type not in {"string", "integer", "number", "boolean"}:
        return False
    disallowed_branch_keys = {"properties", "items", "anyOf", "oneOf", "allOf", "$ref"}
    return not bool(set(branch.keys()) & disallowed_branch_keys)


def _infer_const_type(value: Any) -> str:
    """Infer JSON Schema primitive type string from a Python constant value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def _schema_is_nullable(node: dict[str, Any]) -> bool:
    """Check whether a schema node already permits `null`."""
    if node.get("nullable") is True:
        return True
    node_type = node.get("type")
    if node_type == "null" or (isinstance(node_type, list) and "null" in node_type):
        return True
    any_of = node.get("anyOf")
    return isinstance(any_of, list) and any(_is_null_branch(b) for b in any_of)


def _make_schema_nullable(node: dict[str, Any], nullable_style: str) -> None:
    """Mutate `node` in-place so that it accepts `null` according to `nullable_style`."""
    if _schema_is_nullable(node):
        if "enum" in node and isinstance(node["enum"], list) and None not in node["enum"]:
            node["enum"] = [*node["enum"], None]
        return

    if nullable_style == "openapi_nullable":
        node["nullable"] = True
        return

    # nullable_style == "type_array"
    node_type = node.get("type")
    if isinstance(node_type, str):
        node["type"] = [node_type, "null"]
    elif isinstance(node_type, list):
        if "null" not in node_type:
            node["type"] = [*node_type, "null"]
    elif "anyOf" in node and isinstance(node["anyOf"], list):
        non_null_branches = [b for b in node["anyOf"] if not _is_null_branch(b)]
        if len(non_null_branches) == 1 and _is_simple_type_branch(non_null_branches[0]):
            del node["anyOf"]
            branch_copy = copy.deepcopy(non_null_branches[0])
            scalar_type = str(branch_copy.pop("type"))
            for k, v in branch_copy.items():
                if k not in node:
                    node[k] = v
            node["type"] = [scalar_type, "null"]
        else:
            node["anyOf"] = [*node["anyOf"], {"type": "null"}]
    elif "enum" in node and isinstance(node["enum"], list):
        non_null_vals = [v for v in node["enum"] if v is not None]
        inferred = _infer_const_type(non_null_vals[0]) if non_null_vals else "string"
        node["type"] = [inferred, "null"]
    else:
        node["type"] = ["string", "null"]

    if "enum" in node and isinstance(node["enum"], list) and None not in node["enum"]:
        node["enum"] = [*node["enum"], None]


def _merge_allof_branches(
    parent: dict[str, Any],
    branches: list[Any],
) -> tuple[dict[str, Any], bool]:
    """Merge `allOf` subschemas into `parent`. Returns `(merged_node, is_lossy)`."""
    merged = {k: v for k, v in parent.items() if k != "allOf"}
    merged_props: dict[str, Any] = {}
    if isinstance(merged.get("properties"), dict):
        merged_props.update(copy.deepcopy(merged["properties"]))
    merged_req: list[str] = []
    if isinstance(merged.get("required"), list):
        for r in merged["required"]:
            if isinstance(r, str) and r not in merged_req:
                merged_req.append(r)

    lossy = False
    for branch in branches:
        if not isinstance(branch, dict):
            lossy = True
            continue
        for key, value in branch.items():
            if key == "properties" and isinstance(value, dict):
                for prop_name, prop_val in value.items():
                    if (
                        prop_name in merged_props
                        and isinstance(merged_props[prop_name], dict)
                        and isinstance(prop_val, dict)
                    ):
                        merged_sub, sub_lossy = _merge_allof_branches(
                            merged_props[prop_name],
                            [prop_val],
                        )
                        merged_props[prop_name] = merged_sub
                        if sub_lossy:
                            lossy = True
                    else:
                        merged_props[prop_name] = copy.deepcopy(prop_val)
            elif key == "required" and isinstance(value, list):
                for r in value:
                    if isinstance(r, str) and r not in merged_req:
                        merged_req.append(r)
            elif key not in merged:
                merged[key] = value
            elif merged[key] != value and key not in ("description", "title"):
                lossy = True

    if merged_props:
        merged["properties"] = merged_props
        if "type" not in merged:
            merged["type"] = "object"
    if merged_req:
        merged["required"] = merged_req

    return merged, lossy


def _transform_single_schema(
    schema: dict[str, Any],
    ruleset: RuleSet,
    base_path: str = "$",
) -> tuple[dict[str, Any], list[Change]]:
    """Transform a single JSON Schema dictionary according to `ruleset`."""
    resolved_schema, ref_changes = resolve_refs(schema, ruleset)
    changes: list[Change] = []
    for rc in ref_changes:
        adjusted_path = rc.path if base_path == "$" else f"{base_path}{rc.path[1:]}"
        changes.append(
            Change(
                rule_id=rc.rule_id,
                path=adjusted_path,
                action=rc.action,
                message=rc.message,
                lossy=rc.lossy,
                source_url=rc.source_url,
                deleted_constraint=rc.deleted_constraint,
            )
        )

    policy = ruleset.policy

    def _transform_node(node: Any, path: str, is_root: bool = False) -> Any:
        if isinstance(node, list):
            return [_transform_node(item, f"{path}[{idx}]", False) for idx, item in enumerate(node)]
        if not isinstance(node, dict):
            return node

        current = copy.deepcopy(node)

        # 1. Merge allOf if present
        if "allOf" in current and policy.merge_allof:
            raw_allof = current.get("allOf")
            allof_rule = ruleset.rule_for("allof_merge")
            if isinstance(raw_allof, list) and len(raw_allof) > 0:
                current, allof_lossy = _merge_allof_branches(current, raw_allof)
                changes.append(
                    Change(
                        rule_id=allof_rule.id,
                        path=f"{path}.allOf",
                        action="merged_allof",
                        message="Merged `allOf` subschemas into a single flat schema object.",
                        lossy=allof_lossy,
                        source_url=allof_rule.source_url,
                    )
                )
            else:
                del current["allOf"]
                changes.append(
                    Change(
                        rule_id=allof_rule.id,
                        path=f"{path}.allOf",
                        action="merged_allof",
                        message="Removed empty or invalid `allOf` keyword.",
                        lossy=True,
                        source_url=allof_rule.source_url,
                    )
                )

        # 2. Convert oneOf -> anyOf if configured
        if "oneOf" in current and policy.convert_oneof_to_anyof:
            oneof_val = current.pop("oneOf")
            oneof_rule = ruleset.rule_for("oneof_to_anyof")
            if isinstance(oneof_val, list):
                if "anyOf" in current and isinstance(current["anyOf"], list):
                    current["anyOf"] = [*current["anyOf"], *oneof_val]
                else:
                    current["anyOf"] = oneof_val
            changes.append(
                Change(
                    rule_id=oneof_rule.id,
                    path=f"{path}.oneOf",
                    action="converted_oneof_to_anyof",
                    message=f"Converted `oneOf` to `anyOf` for `{ruleset.target}` compatibility.",
                    lossy=True,
                    source_url=oneof_rule.source_url,
                )
            )

        # 3. Convert const -> single-value enum
        if "const" in current and policy.convert_const_to_enum:
            const_val = current.pop("const")
            const_rule = ruleset.rule_for("const_keyword")
            inferred_type = _infer_const_type(const_val)
            if policy.disallow_type_array and const_val is None:
                current["type"] = "string"
                current["nullable"] = True
                const_lossy = True
            else:
                current["enum"] = [const_val]
                if "type" not in current:
                    current["type"] = inferred_type
                const_lossy = False
            changes.append(
                Change(
                    rule_id=const_rule.id,
                    path=f"{path}.const",
                    action="converted_const_to_enum",
                    message="Converted `const` keyword to single-element `enum`.",
                    lossy=const_lossy,
                    source_url=const_rule.source_url,
                )
            )

        # 4. Handle anyOf null unions BEFORE transforming individual branches
        if "anyOf" in current and isinstance(current["anyOf"], list):
            raw_branches = current["anyOf"]
            null_branches = [b for b in raw_branches if _is_null_branch(b)]
            non_null_branches = [b for b in raw_branches if not _is_null_branch(b)]

            if null_branches:
                if policy.collapse_anyof_null:
                    anyof_rule = ruleset.rule_for("anyof_null")
                    if len(non_null_branches) == 1 and isinstance(non_null_branches[0], dict):
                        del current["anyOf"]
                        branch_copy = copy.deepcopy(non_null_branches[0])
                        for k, v in branch_copy.items():
                            if k not in current:
                                current[k] = v
                        current["nullable"] = True
                        changes.append(
                            Change(
                                rule_id=anyof_rule.id,
                                path=f"{path}.anyOf",
                                action="collapsed_anyof_null",
                                message="Collapsed `anyOf` with `null` into `nullable: true`.",
                                lossy=False,
                                source_url=anyof_rule.source_url,
                            )
                        )
                        return _transform_node(current, path, is_root)
                    elif len(non_null_branches) > 1:
                        current["anyOf"] = [
                            _transform_node(b, f"{path}.anyOf[{i}]", False)
                            for i, b in enumerate(non_null_branches)
                        ]
                        current["nullable"] = True
                        changes.append(
                            Change(
                                rule_id=anyof_rule.id,
                                path=f"{path}.anyOf",
                                action="collapsed_anyof_null",
                                message=(
                                    "Removed `null` branch from `anyOf` and set `nullable: true`."
                                ),
                                lossy=False,
                                source_url=anyof_rule.source_url,
                            )
                        )
                    else:
                        del current["anyOf"]
                        current["type"] = "string"
                        current["nullable"] = True
                        changes.append(
                            Change(
                                rule_id=anyof_rule.id,
                                path=f"{path}.anyOf",
                                action="collapsed_anyof_null",
                                message="Replaced null-only `anyOf` with nullable string schema.",
                                lossy=True,
                                source_url=anyof_rule.source_url,
                            )
                        )
                elif (
                    policy.nullable_style == "type_array"
                    and len(non_null_branches) == 1
                    and _is_simple_type_branch(non_null_branches[0])
                ):
                    nullable_rule = ruleset.rule_for("nullable_keyword")
                    del current["anyOf"]
                    branch_copy = copy.deepcopy(non_null_branches[0])
                    scalar_type = str(branch_copy.pop("type"))
                    for k, v in branch_copy.items():
                        if k not in current:
                            current[k] = v
                    current["type"] = [scalar_type, "null"]
                    if (
                        "enum" in current
                        and isinstance(current["enum"], list)
                        and None not in current["enum"]
                    ):
                        current["enum"] = [*current["enum"], None]
                    changes.append(
                        Change(
                            rule_id=nullable_rule.id,
                            path=f"{path}.anyOf",
                            action="collapsed_anyof_null",
                            message=(
                                f"Collapsed `anyOf` with `null` into "
                                f'`type: ["{scalar_type}", "null"]`.'
                            ),
                            lossy=False,
                            source_url=nullable_rule.source_url,
                        )
                    )
                    return _transform_node(current, path, is_root)
                else:
                    # Transform non-null branches in place while keeping positions
                    current["anyOf"] = [
                        {"type": "null"}
                        if _is_null_branch(b)
                        else _transform_node(b, f"{path}.anyOf[{i}]", False)
                        for i, b in enumerate(raw_branches)
                    ]
            else:
                current["anyOf"] = [
                    _transform_node(b, f"{path}.anyOf[{i}]", False)
                    for i, b in enumerate(raw_branches)
                ]

        # 5. Handle type arrays vs OpenAPI `nullable: true`
        if policy.disallow_type_array:
            if isinstance(current.get("type"), list):
                raw_types = [str(t) for t in current["type"]]
                has_null = "null" in raw_types
                non_null = list(dict.fromkeys(t for t in raw_types if t != "null"))
                type_rule = ruleset.rule_for("type_array")
                if len(non_null) == 1:
                    current["type"] = non_null[0]
                    if has_null:
                        current["nullable"] = True
                    suffix = " with `nullable: true`." if has_null else "."
                    changes.append(
                        Change(
                            rule_id=type_rule.id,
                            path=f"{path}.type",
                            action="converted_type_array",
                            message=(
                                f"Converted `type` array `{raw_types}` "
                                f"to scalar type `{non_null[0]}`{suffix}"
                            ),
                            lossy=False,
                            source_url=type_rule.source_url,
                        )
                    )
                elif len(non_null) > 1:
                    del current["type"]
                    current["anyOf"] = [{"type": t} for t in non_null]
                    if has_null:
                        current["nullable"] = True
                    changes.append(
                        Change(
                            rule_id=type_rule.id,
                            path=f"{path}.type",
                            action="converted_type_array",
                            message=f"Converted multi-type array `{raw_types}` to `anyOf`.",
                            lossy=False,
                            source_url=type_rule.source_url,
                        )
                    )
                else:
                    current["type"] = "string"
                    current["nullable"] = True
                    changes.append(
                        Change(
                            rule_id=type_rule.id,
                            path=f"{path}.type",
                            action="converted_type_array",
                            message='Replaced `type: ["null"]` with nullable string schema.',
                            lossy=True,
                            source_url=type_rule.source_url,
                        )
                    )
            elif current.get("type") == "null":
                anyof_rule = ruleset.rule_for("anyof_null")
                current["type"] = "string"
                current["nullable"] = True
                changes.append(
                    Change(
                        rule_id=anyof_rule.id,
                        path=f"{path}.type",
                        action="converted_type_array",
                        message=(
                            'Replaced standalone `type: "null"` '
                            'with `type: "string", nullable: true`.'
                        ),
                        lossy=True,
                        source_url=anyof_rule.source_url,
                    )
                )
        elif policy.nullable_style == "type_array" and "nullable" in current:
            is_nullable = bool(current.pop("nullable"))
            nullable_rule = ruleset.rule_for("nullable_keyword")
            if is_nullable:
                _make_schema_nullable(current, "type_array")
                msg = 'Converted OpenAPI `nullable` keyword to JSON Schema union with `"null"`.'
            else:
                msg = "Removed unsupported OpenAPI `nullable: false` keyword."
            changes.append(
                Change(
                    rule_id=nullable_rule.id,
                    path=f"{path}.nullable",
                    action="converted_nullable",
                    message=msg,
                    lossy=False,
                    source_url=nullable_rule.source_url,
                )
            )

        # 6. Strip unsupported metadata keywords (lossy = False)
        meta_rule = ruleset.rule_for("unsupported_keywords")
        for meta_key in policy.strip_metadata_keywords:
            if meta_key in current:
                del current[meta_key]
                changes.append(
                    Change(
                        rule_id=meta_rule.id,
                        path=f"{path}.{meta_key}",
                        action="removed_keyword",
                        message=f"Removed unsupported metadata keyword `{meta_key}`.",
                        lossy=False,
                        source_url=meta_rule.source_url,
                    )
                )

        # 7. Strip unsupported validation constraint keywords (lossy = True)
        constraint_rule = ruleset.rule_for("unsupported_constraints")
        for constraint_key in policy.strip_validation_constraints:
            if constraint_key in current:
                del current[constraint_key]
                changes.append(
                    Change(
                        rule_id=constraint_rule.id,
                        path=f"{path}.{constraint_key}",
                        action="removed_constraint",
                        message=f"Removed unsupported validation constraint `{constraint_key}`.",
                        lossy=True,
                        source_url=constraint_rule.source_url,
                        deleted_constraint=constraint_key,
                    )
                )

        # 8. Check format allowlist (e.g., Gemini supports only specific formats)
        if "format" in current and policy.allowed_formats:
            fmt_val = current["format"]
            if not isinstance(fmt_val, str) or fmt_val not in policy.allowed_formats:
                del current["format"]
                fmt_rule = ruleset.rule_for("unsupported_format")
                changes.append(
                    Change(
                        rule_id=fmt_rule.id,
                        path=f"{path}.format",
                        action="removed_constraint",
                        message=(
                            f"Removed unsupported `format` value `{fmt_val!r}` "
                            f"for `{ruleset.target}`."
                        ),
                        lossy=True,
                        source_url=fmt_rule.source_url,
                        deleted_constraint="format",
                    )
                )

        # 9. Recursively transform child schemas (`properties`, `items`)
        if "properties" in current and isinstance(current["properties"], dict):
            new_props: dict[str, Any] = {}
            for prop_name, prop_schema in current["properties"].items():
                new_props[prop_name] = _transform_node(
                    prop_schema,
                    f"{path}.properties.{prop_name}",
                    False,
                )
            current["properties"] = new_props

        if "items" in current:
            current["items"] = _transform_node(current["items"], f"{path}.items", False)

        # 10. Root-level missing `type: "object"` when no conflicting type exists
        if (
            is_root
            and policy.require_root_object
            and "type" not in current
            and "anyOf" not in current
            and "enum" not in current
            and "items" not in current
        ):
            root_rule = ruleset.rule_for("root_object")
            current["type"] = "object"
            if "properties" not in current:
                current["properties"] = {}
            changes.append(
                Change(
                    rule_id=root_rule.id,
                    path=f"{path}.type",
                    action="normalized_root_object",
                    message='Added missing `type: "object"` to root schema.',
                    lossy=False,
                    source_url=root_rule.source_url,
                )
            )

        # 11. Object-level rules: type, required, additionalProperties
        node_type = current.get("type")
        is_object = (
            node_type == "object"
            or (isinstance(node_type, list) and "object" in node_type)
            or "properties" in current
            or "additionalProperties" in current
        )

        if (
            ("properties" in current or "additionalProperties" in current)
            and "type" not in current
            and "anyOf" not in current
        ):
            root_rule = ruleset.rule_for("root_object")
            current["type"] = "object"
            is_object = True
            changes.append(
                Change(
                    rule_id=root_rule.id,
                    path=f"{path}.type",
                    action="normalized_root_object",
                    message='Added missing `type: "object"` to object schema.',
                    lossy=False,
                    source_url=root_rule.source_url,
                )
            )

        # Clean orphan or duplicate entries in `required`
        if policy.clean_orphan_required and "required" in current:
            raw_req = current.get("required")
            props_dict = (
                current["properties"] if isinstance(current.get("properties"), dict) else {}
            )
            if isinstance(raw_req, list):
                valid_req: list[str] = []
                orphans: list[str] = []
                has_duplicates = False
                for item in raw_req:
                    if not isinstance(item, str) or item not in props_dict:
                        orphans.append(str(item))
                    elif item in valid_req:
                        has_duplicates = True
                    else:
                        valid_req.append(item)
                if orphans or has_duplicates:
                    orphan_rule = ruleset.rule_for("orphan_required")
                    if valid_req or policy.require_all_properties_in_required:
                        current["required"] = valid_req
                    else:
                        del current["required"]
                    changes.append(
                        Change(
                            rule_id=orphan_rule.id,
                            path=f"{path}.required",
                            action="removed_orphan_required",
                            message=(
                                "Removed orphan or duplicate `required` keys: "
                                f"{orphans or 'duplicates'}."
                            ),
                            lossy=False,
                            source_url=orphan_rule.source_url,
                        )
                    )

        # Disallow additionalProperties (Gemini)
        if policy.disallow_additional_properties and "additionalProperties" in current:
            add_prop_val = current.pop("additionalProperties")
            add_rule = ruleset.rule_for("additional_properties")
            is_lossy_removal = add_prop_val is False or isinstance(add_prop_val, dict)
            changes.append(
                Change(
                    rule_id=add_rule.id,
                    path=f"{path}.additionalProperties",
                    action="removed_additional_properties",
                    message="Removed `additionalProperties` (unsupported by Gemini Schema).",
                    lossy=is_lossy_removal,
                    source_url=add_rule.source_url,
                    deleted_constraint="additionalProperties" if is_lossy_removal else None,
                )
            )

        # Require additionalProperties: false (OpenAI strict & Anthropic)
        if policy.require_additional_properties_false and is_object:
            if "properties" not in current:
                current["properties"] = {}
            if current.get("additionalProperties") is not False:
                had_explicit_open = (
                    "additionalProperties" in current
                    and current["additionalProperties"] is not False
                )
                prev_val = current.get("additionalProperties")
                current["additionalProperties"] = False
                if had_explicit_open:
                    narrow_rule = ruleset.rule_for("open_object_lossy")
                    changes.append(
                        Change(
                            rule_id=narrow_rule.id,
                            path=f"{path}.additionalProperties",
                            action="added_additional_properties_false",
                            message=(
                                "Overwrote open/map `additionalProperties` "
                                "with `false` for strict mode."
                            ),
                            lossy=True,
                            source_url=narrow_rule.source_url,
                            deleted_constraint=(
                                "additionalProperties" if isinstance(prev_val, dict) else None
                            ),
                        )
                    )
                else:
                    open_rule = ruleset.rule_for("open_object")
                    changes.append(
                        Change(
                            rule_id=open_rule.id,
                            path=f"{path}.additionalProperties",
                            action="added_additional_properties_false",
                            message="Set `additionalProperties: false` on object schema.",
                            lossy=False,
                            source_url=open_rule.source_url,
                        )
                    )

        # Require all properties in `required` (OpenAI strict)
        if (
            policy.require_all_properties_in_required
            and is_object
            and isinstance(current.get("properties"), dict)
        ):
            props_map: dict[str, Any] = current["properties"]
            existing_req: list[str] = (
                [str(r) for r in current["required"]]
                if isinstance(current.get("required"), list)
                else []
            )
            existing_set = set(existing_req)
            missing_props = [k for k in props_map if k not in existing_set]
            req_rule = ruleset.rule_for("optional_properties")

            if missing_props:
                for prop_key in missing_props:
                    prop_schema = props_map[prop_key]
                    if isinstance(prop_schema, dict):
                        _make_schema_nullable(prop_schema, policy.nullable_style)
                    changes.append(
                        Change(
                            rule_id=req_rule.id,
                            path=f"{path}.properties.{prop_key}",
                            action="added_required_nullable",
                            message=(
                                f"Added optional property `{prop_key}` "
                                "to `required` and made it nullable."
                            ),
                            lossy=False,
                            source_url=req_rule.source_url,
                        )
                    )
                current["required"] = list(props_map.keys())
            elif "required" not in current:
                current["required"] = []
                changes.append(
                    Change(
                        rule_id=req_rule.id,
                        path=f"{path}.required",
                        action="added_required_nullable",
                        message="Added empty `required: []` array to strict object schema.",
                        lossy=False,
                        source_url=req_rule.source_url,
                    )
                )

        # 12. Enforce root object requirement when root has a non-object type or top-level union
        if is_root and policy.require_root_object:
            root_type = current.get("type")
            if root_type != "object":
                root_rule = ruleset.rule_for("root_object")
                wrapped_value = copy.deepcopy(current)
                wrapped: dict[str, Any] = {
                    "type": "object",
                    "properties": {"value": wrapped_value},
                    "required": ["value"],
                }
                if policy.require_additional_properties_false:
                    wrapped["additionalProperties"] = False
                current = wrapped
                changes.append(
                    Change(
                        rule_id=root_rule.id,
                        path=path,
                        action="normalized_root_object",
                        message=(
                            "Wrapped non-object root schema into "
                            'a top-level `type: "object"` schema.'
                        ),
                        lossy=True,
                        source_url=root_rule.source_url,
                    )
                )

        return current

    fixed = _transform_node(resolved_schema, base_path, is_root=True)
    assert isinstance(fixed, dict)
    return fixed, changes


def _extract_tool_schema_slot(tool_obj: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Locate the JSON Schema dictionary inside a single tool envelope if present."""
    if (
        tool_obj.get("type") == "function"
        and isinstance(tool_obj.get("function"), dict)
        and isinstance(tool_obj["function"].get("parameters"), dict)
    ):
        return ("function.parameters", tool_obj["function"]["parameters"])

    for key in _SCHEMA_ENVELOPE_KEYS:
        if (
            key in tool_obj
            and isinstance(tool_obj[key], dict)
            and "properties" not in tool_obj
            and tool_obj.get("type") != "object"
        ):
            return (key, tool_obj[key])
    return None


def fix_schema(
    schema: dict[str, Any],
    target: str,
) -> tuple[dict[str, Any], list[Change]]:
    """Transform a tool JSON Schema (or MCP `tools/list` / tool envelope) for `target`.

    Returns `(fixed_schema, changes)` without mutating the input `schema`.
    """
    if not isinstance(schema, dict):
        raise TypeError("schema must be a dictionary")

    ruleset = load_rules(target)
    doc = copy.deepcopy(schema)

    # Case 1: MCP `tools/list` envelope: {"tools": [...]}
    if (
        "tools" in doc
        and isinstance(doc["tools"], list)
        and "properties" not in doc
        and doc.get("type") != "object"
    ):
        all_changes: list[Change] = []
        fixed_tools: list[Any] = []
        for idx, tool_entry in enumerate(doc["tools"]):
            if isinstance(tool_entry, dict):
                slot = _extract_tool_schema_slot(tool_entry)
                if slot is not None:
                    slot_key, inner_schema = slot
                    fixed_inner, tool_changes = _transform_single_schema(
                        inner_schema,
                        ruleset,
                        base_path=f"$.tools[{idx}].{slot_key}",
                    )
                    updated_entry = copy.deepcopy(tool_entry)
                    if slot_key == "function.parameters":
                        updated_entry["function"]["parameters"] = fixed_inner
                    else:
                        updated_entry[slot_key] = fixed_inner
                    fixed_tools.append(updated_entry)
                    all_changes.extend(tool_changes)
                else:
                    fixed_inner, tool_changes = _transform_single_schema(
                        tool_entry,
                        ruleset,
                        base_path=f"$.tools[{idx}]",
                    )
                    fixed_tools.append(fixed_inner)
                    all_changes.extend(tool_changes)
            else:
                fixed_tools.append(tool_entry)
        doc["tools"] = fixed_tools
        return doc, all_changes

    # Case 2: Single tool envelope (MCP `inputSchema`, Gemini `parametersJsonSchema`, etc.)
    slot = _extract_tool_schema_slot(doc)
    if slot is not None:
        slot_key, inner_schema = slot
        fixed_inner, changes = _transform_single_schema(
            inner_schema,
            ruleset,
            base_path=f"$.{slot_key}",
        )
        if slot_key == "function.parameters":
            doc["function"]["parameters"] = fixed_inner
        else:
            doc[slot_key] = fixed_inner
        return doc, changes

    # Case 3: Raw JSON Schema dictionary
    return _transform_single_schema(doc, ruleset, base_path="$")


def check_schema(
    schema: dict[str, Any],
    target: str,
) -> list[Issue]:
    """Audit a tool JSON Schema (or MCP `tools/list` / tool envelope) against `target`.

    Returns a list of `Issue` objects (empty if the schema is fully compatible).
    """
    _, changes = fix_schema(schema, target)
    return [
        Issue(
            rule_id=change.rule_id,
            path=change.path,
            message=change.message,
            source_url=change.source_url,
            lossy=change.lossy,
            keyword=change.deleted_constraint,
        )
        for change in changes
    ]


def convert_mcp_tools(
    document: dict[str, Any],
    target: str,
    *,
    envelope: str = "preserve",
) -> tuple[dict[str, Any], list[Change]]:
    """Transform an MCP `tools/list` document or single tool for `target` and optional `envelope`.

    Supported envelopes:
    - `"preserve"`: Keep the original structure (`inputSchema`, `parameters`, etc.).
    - `"gemini"`: Emit Gemini `FunctionDeclaration` with `parameters`.
    - `"gemini-json-schema"`: Emit Gemini `FunctionDeclaration` with `parametersJsonSchema`.
    - `"openai"`: Emit OpenAI strict tool definition (`type: "function"`, `strict: True`).
    - `"anthropic"`: Emit Anthropic tool definition (`input_schema`).
    """
    valid_envelopes = {"preserve", "gemini", "gemini-json-schema", "openai", "anthropic"}
    if envelope not in valid_envelopes:
        raise ValueError(
            f"Unsupported envelope '{envelope}'. Expected one of: {sorted(valid_envelopes)}"
        )

    fixed_doc, changes = fix_schema(document, target)
    if envelope == "preserve":
        return fixed_doc, changes

    def _re_envelope_tool(tool_obj: dict[str, Any]) -> dict[str, Any]:
        slot = _extract_tool_schema_slot(tool_obj)
        if slot is not None:
            _, inner_schema = slot
            name = str(
                tool_obj.get("name")
                or (
                    tool_obj.get("function", {}).get("name")
                    if isinstance(tool_obj.get("function"), dict)
                    else "unnamed_tool"
                )
            )
            description = str(
                tool_obj.get("description")
                or (
                    tool_obj.get("function", {}).get("description")
                    if isinstance(tool_obj.get("function"), dict)
                    else ""
                )
            )
        else:
            inner_schema = tool_obj
            name = "tool_parameters"
            description = str(tool_obj.get("description", ""))

        if envelope == "gemini":
            out: dict[str, Any] = {"name": name, "parameters": inner_schema}
            if description:
                out["description"] = description
            return out
        if envelope == "gemini-json-schema":
            out = {"name": name, "parametersJsonSchema": inner_schema}
            if description:
                out["description"] = description
            return out
        if envelope == "openai":
            fn_obj: dict[str, Any] = {
                "name": name,
                "strict": True,
                "parameters": inner_schema,
            }
            if description:
                fn_obj["description"] = description
            return {"type": "function", "function": fn_obj}
        # envelope == "anthropic"
        out = {"name": name, "input_schema": inner_schema}
        if description:
            out["description"] = description
        return out

    if (
        "tools" in fixed_doc
        and isinstance(fixed_doc["tools"], list)
        and "properties" not in fixed_doc
        and fixed_doc.get("type") != "object"
    ):
        return (
            {
                **fixed_doc,
                "tools": [
                    _re_envelope_tool(t) if isinstance(t, dict) else t for t in fixed_doc["tools"]
                ],
            },
            changes,
        )
    return _re_envelope_tool(fixed_doc), changes
