"""Provider compatibility rule definitions loaded from versioned TOML files."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

SUPPORTED_TARGETS: tuple[str, ...] = ("gemini", "openai-strict", "anthropic")

# NEEDS_SOURCE: Provider-side numeric complexity limits (maximum schema nesting depth,
# maximum property count per tool, and grammar compilation token budgets) are not
# published as fixed constants across all provider model versions. They are recorded
# with verification_status="NEEDS_SOURCE" in the TOML rule definitions and never guessed.
UNVERIFIED_STATUS = "NEEDS_SOURCE"


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    """Single compatibility rule backed by an official documentation or issue URL."""

    id: str
    category: str
    description: str
    source_url: str
    last_verified: str
    lossy: bool
    verification_status: str = "verified"


@dataclass(frozen=True, slots=True)
class TargetPolicy:
    """Executable transformation policy for a specific provider target."""

    inline_refs: bool
    strip_defs: bool
    disallow_type_array: bool
    nullable_style: str  # "openapi_nullable" | "type_array"
    collapse_anyof_null: bool
    convert_const_to_enum: bool
    convert_oneof_to_anyof: bool
    merge_allof: bool
    require_root_object: bool
    require_additional_properties_false: bool
    disallow_additional_properties: bool
    require_all_properties_in_required: bool
    clean_orphan_required: bool
    allowed_formats: tuple[str, ...]
    strip_metadata_keywords: tuple[str, ...]
    strip_validation_constraints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleSet:
    """Complete rule set and policy for a provider target."""

    target: str
    provider: str
    schema_version: str
    last_verified: str
    primary_source: str
    secondary_sources: tuple[str, ...]
    notes: str
    policy: TargetPolicy
    rules: tuple[RuleDefinition, ...]
    rules_by_category: dict[str, RuleDefinition]

    def rule_for(self, category: str) -> RuleDefinition:
        """Return the rule metadata associated with a rule category."""
        return self.rules_by_category[category]

    def unverified_rules(self) -> tuple[RuleDefinition, ...]:
        """Return rules marked with NEEDS_SOURCE (undocumented provider limits)."""
        return tuple(r for r in self.rules if r.verification_status == UNVERIFIED_STATUS)


def normalize_target(target: str) -> str:
    """Validate and normalize a provider target identifier."""
    normalized = target.strip().lower().replace("_", "-")
    if normalized not in SUPPORTED_TARGETS:
        supported = ", ".join(SUPPORTED_TARGETS)
        raise ValueError(f"Unsupported target '{target}'. Supported targets: {supported}")
    return normalized


@lru_cache(maxsize=16)
def load_rules(target: str) -> RuleSet:
    """Load the TOML rule file for the specified target."""
    normalized = normalize_target(target)
    toml_path = Path(__file__).with_name(f"{normalized}.toml")
    if not toml_path.is_file():
        raise FileNotFoundError(f"Rule file not found for target '{normalized}': {toml_path}")

    raw: dict[str, Any] = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    raw_policy: dict[str, Any] = raw["policy"]

    policy = TargetPolicy(
        inline_refs=bool(raw_policy["inline_refs"]),
        strip_defs=bool(raw_policy["strip_defs"]),
        disallow_type_array=bool(raw_policy["disallow_type_array"]),
        nullable_style=str(raw_policy["nullable_style"]),
        collapse_anyof_null=bool(raw_policy["collapse_anyof_null"]),
        convert_const_to_enum=bool(raw_policy["convert_const_to_enum"]),
        convert_oneof_to_anyof=bool(raw_policy["convert_oneof_to_anyof"]),
        merge_allof=bool(raw_policy["merge_allof"]),
        require_root_object=bool(raw_policy["require_root_object"]),
        require_additional_properties_false=bool(raw_policy["require_additional_properties_false"]),
        disallow_additional_properties=bool(raw_policy["disallow_additional_properties"]),
        require_all_properties_in_required=bool(raw_policy["require_all_properties_in_required"]),
        clean_orphan_required=bool(raw_policy["clean_orphan_required"]),
        allowed_formats=tuple(str(x) for x in raw_policy.get("allowed_formats", [])),
        strip_metadata_keywords=tuple(
            str(x) for x in raw_policy.get("strip_metadata_keywords", [])
        ),
        strip_validation_constraints=tuple(
            str(x) for x in raw_policy.get("strip_validation_constraints", [])
        ),
    )

    rules_list: list[RuleDefinition] = []
    by_category: dict[str, RuleDefinition] = {}
    for entry in raw.get("rules", []):
        rule = RuleDefinition(
            id=str(entry["id"]),
            category=str(entry["category"]),
            description=str(entry["description"]),
            source_url=str(entry["source_url"]),
            last_verified=str(entry["last_verified"]),
            lossy=bool(entry["lossy"]),
            verification_status=str(entry.get("verification_status", "verified")),
        )
        rules_list.append(rule)
        by_category[rule.category] = rule

    return RuleSet(
        target=str(raw["target"]),
        provider=str(raw["provider"]),
        schema_version=str(raw["schema_version"]),
        last_verified=str(raw["last_verified"]),
        primary_source=str(raw["primary_source"]),
        secondary_sources=tuple(str(s) for s in raw.get("secondary_sources", [])),
        notes=str(raw.get("notes", "")).strip(),
        policy=policy,
        rules=tuple(rules_list),
        rules_by_category=by_category,
    )


def load_all_rules() -> dict[str, RuleSet]:
    """Load rule sets for all supported targets."""
    return {target: load_rules(target) for target in SUPPORTED_TARGETS}
