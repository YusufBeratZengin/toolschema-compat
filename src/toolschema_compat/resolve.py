"""Acyclic JSON Schema `$ref`, `$defs`, and `definitions` resolution and inlining."""

from __future__ import annotations

import copy
from typing import Any

from toolschema_compat.report import Change, Issue
from toolschema_compat.rules import RuleSet


def unescape_json_pointer(token: str) -> str:
    """Unescape a single RFC 6901 JSON Pointer reference token."""
    return token.replace("~1", "/").replace("~0", "~")


def resolve_json_pointer(root: dict[str, Any], ref: str) -> dict[str, Any] | None:
    """Resolve a local JSON Pointer (`#/...`) against the root schema dictionary.

    Returns a deep copy of the referenced dictionary, or `None` if the pointer is
    external, malformed, or does not resolve to a mapping.
    """
    if not isinstance(ref, str) or not ref.startswith("#"):
        return None
    if ref == "#":
        return copy.deepcopy(root)
    if not ref.startswith("#/"):
        return None

    parts = [unescape_json_pointer(p) for p in ref[2:].split("/")]
    current: Any = root
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                return None
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            return None

    if isinstance(current, dict):
        return copy.deepcopy(current)
    return None


def _detect_ref_cycle(
    root: dict[str, Any],
    ref: str,
    seen: frozenset[str],
) -> bool:
    """Check whether following `ref` leads to a cycle in `$ref` targets."""
    if ref == "#" or ref in seen:
        return True
    target = resolve_json_pointer(root, ref)
    if target is None:
        return False
    return _node_has_cycle(root, target, seen | {ref})


def _node_has_cycle(
    root: dict[str, Any],
    node: Any,
    seen: frozenset[str],
) -> bool:
    """Recursively inspect a resolved node for cyclic `$ref` chains."""
    if isinstance(node, dict):
        ref_val = node.get("$ref")
        if isinstance(ref_val, str) and _detect_ref_cycle(root, ref_val, seen):
            return True
        for key, value in node.items():
            if key in ("$defs", "definitions", "$ref"):
                continue
            if _node_has_cycle(root, value, seen):
                return True
    elif isinstance(node, list):
        for item in node:
            if _node_has_cycle(root, item, seen):
                return True
    return False


def check_refs(
    schema: dict[str, Any],
    ruleset: RuleSet,
) -> list[Issue]:
    """Inspect a schema for `$ref`, `$defs`, and `definitions` issues without mutating it."""
    if not ruleset.policy.inline_refs and not ruleset.policy.strip_defs:
        return []

    issues: list[Issue] = []
    ref_rule = ruleset.rule_for("ref_defs")
    cycle_rule = ruleset.rule_for("ref_cycle")

    def _walk(node: Any, path: str, active_refs: frozenset[str]) -> None:
        if isinstance(node, dict):
            for defs_key in ("$defs", "definitions"):
                if defs_key in node and ruleset.policy.strip_defs:
                    issues.append(
                        Issue(
                            rule_id=ref_rule.id,
                            path=f"{path}.{defs_key}",
                            message=(
                                f"`{defs_key}` is not supported by target `{ruleset.target}`; "
                                "inline references instead."
                            ),
                            source_url=ref_rule.source_url,
                            lossy=False,
                            keyword=defs_key,
                        )
                    )

            ref_val = node.get("$ref")
            if "$ref" in node:
                ref_path = f"{path}.$ref"
                if not isinstance(ref_val, str):
                    issues.append(
                        Issue(
                            rule_id=cycle_rule.id,
                            path=ref_path,
                            message="`$ref` value must be a string JSON Pointer.",
                            source_url=cycle_rule.source_url,
                            lossy=True,
                            keyword="$ref",
                        )
                    )
                else:
                    resolved = resolve_json_pointer(schema, ref_val)
                    if resolved is None:
                        issues.append(
                            Issue(
                                rule_id=cycle_rule.id,
                                path=ref_path,
                                message=(
                                    f"Unresolvable or external `$ref` ('{ref_val}') "
                                    "cannot be inlined losslessly."
                                ),
                                source_url=cycle_rule.source_url,
                                lossy=True,
                                keyword="$ref",
                            )
                        )
                    elif _detect_ref_cycle(schema, ref_val, active_refs):
                        issues.append(
                            Issue(
                                rule_id=cycle_rule.id,
                                path=ref_path,
                                message=(
                                    f"Cyclic `$ref` ('{ref_val}') detected; "
                                    "recursive reference must be truncated."
                                ),
                                source_url=cycle_rule.source_url,
                                lossy=True,
                                keyword="$ref",
                            )
                        )
                    else:
                        issues.append(
                            Issue(
                                rule_id=ref_rule.id,
                                path=ref_path,
                                message=(
                                    f"`$ref` ('{ref_val}') must be inlined for `{ruleset.target}`."
                                ),
                                source_url=ref_rule.source_url,
                                lossy=False,
                                keyword="$ref",
                            )
                        )
                        _walk(resolved, path, active_refs | {ref_val})

            for key, value in node.items():
                if key in ("$defs", "definitions", "$ref"):
                    continue
                _walk(value, f"{path}.{key}", active_refs)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                _walk(item, f"{path}[{idx}]", active_refs)

    _walk(schema, "$", frozenset())
    return issues


def resolve_refs(
    schema: dict[str, Any],
    ruleset: RuleSet,
) -> tuple[dict[str, Any], list[Change]]:
    """Inline local `$ref` pointers acyclically and strip `$defs`/`definitions`.

    Guarantees termination on direct, mutual, or root (`#`) recursion by replacing
    the back-edge with a fallback object schema and recording a `lossy=True` change.
    """
    root_copy = copy.deepcopy(schema)
    if not ruleset.policy.inline_refs and not ruleset.policy.strip_defs:
        return root_copy, []

    changes: list[Change] = []
    ref_rule = ruleset.rule_for("ref_defs")
    cycle_rule = ruleset.rule_for("ref_cycle")

    def _transform(node: Any, path: str, active_refs: frozenset[str]) -> Any:
        if isinstance(node, list):
            return [
                _transform(item, f"{path}[{idx}]", active_refs) for idx, item in enumerate(node)
            ]

        if not isinstance(node, dict):
            return node

        current = dict(node)

        # Strip $defs / definitions at this level if configured
        if ruleset.policy.strip_defs:
            for defs_key in ("$defs", "definitions"):
                if defs_key in current:
                    del current[defs_key]
                    changes.append(
                        Change(
                            rule_id=ref_rule.id,
                            path=f"{path}.{defs_key}",
                            action="removed_defs",
                            message=(
                                f"Removed `{defs_key}` container after inlining local references."
                            ),
                            lossy=False,
                            source_url=ref_rule.source_url,
                        )
                    )

        # Resolve $ref if present
        if "$ref" in current and ruleset.policy.inline_refs:
            ref_val = current.pop("$ref")
            siblings = {k: v for k, v in current.items() if k not in ("$defs", "definitions")}
            ref_path = f"{path}.$ref"

            if not isinstance(ref_val, str):
                fallback: dict[str, Any] = {"type": "object", **siblings}
                changes.append(
                    Change(
                        rule_id=cycle_rule.id,
                        path=ref_path,
                        action="replaced_unresolvable_ref",
                        message="Replaced non-string `$ref` with fallback object schema.",
                        lossy=True,
                        source_url=cycle_rule.source_url,
                    )
                )
                return _transform(fallback, path, active_refs)

            if ref_val == "#" or ref_val in active_refs:
                fallback = {"type": "object"}
                if "description" in siblings:
                    fallback["description"] = siblings["description"]
                changes.append(
                    Change(
                        rule_id=cycle_rule.id,
                        path=ref_path,
                        action="truncated_cyclic_ref",
                        message=(
                            f"Truncated cyclic `$ref` ('{ref_val}') to object stub "
                            "to prevent infinite recursion."
                        ),
                        lossy=True,
                        source_url=cycle_rule.source_url,
                    )
                )
                return fallback

            resolved = resolve_json_pointer(root_copy, ref_val)
            if resolved is None:
                fallback = {"type": "object"}
                if "description" in siblings:
                    fallback["description"] = siblings["description"]
                changes.append(
                    Change(
                        rule_id=cycle_rule.id,
                        path=ref_path,
                        action="replaced_unresolvable_ref",
                        message=(
                            f"Replaced unresolvable `$ref` ('{ref_val}') "
                            "with fallback object schema."
                        ),
                        lossy=True,
                        source_url=cycle_rule.source_url,
                    )
                )
                return fallback

            merged = dict(resolved)
            for k, v in siblings.items():
                merged[k] = v

            changes.append(
                Change(
                    rule_id=ref_rule.id,
                    path=ref_path,
                    action="inlined_ref",
                    message=f"Inlined `$ref` ('{ref_val}') into `{path}`.",
                    lossy=False,
                    source_url=ref_rule.source_url,
                )
            )
            return _transform(merged, path, active_refs | {ref_val})

        # Recursively transform child values
        result: dict[str, Any] = {}
        for key, value in current.items():
            if key in ("$defs", "definitions"):
                result[key] = value
                continue
            if key == "properties" and isinstance(value, dict):
                props: dict[str, Any] = {}
                for prop_name, prop_schema in value.items():
                    props[prop_name] = _transform(
                        prop_schema,
                        f"{path}.properties.{prop_name}",
                        active_refs,
                    )
                result[key] = props
            else:
                result[key] = _transform(value, f"{path}.{key}", active_refs)
        return result

    transformed = _transform(root_copy, "$", frozenset())
    assert isinstance(transformed, dict)
    return transformed, changes
