"""toolschema-compat: Audit and transform tool JSON Schemas across LLM providers."""

from __future__ import annotations

from toolschema_compat.report import (
    Change,
    CheckReport,
    FixReport,
    Issue,
    build_check_report,
    build_fix_report,
)
from toolschema_compat.resolve import check_refs, resolve_json_pointer, resolve_refs
from toolschema_compat.rules import (
    SUPPORTED_TARGETS,
    UNVERIFIED_STATUS,
    RuleDefinition,
    RuleSet,
    TargetPolicy,
    load_all_rules,
    load_rules,
    normalize_target,
)
from toolschema_compat.transform import (
    check_schema,
    convert_mcp_tools,
    fix_schema,
    is_lossless,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "SUPPORTED_TARGETS",
    "UNVERIFIED_STATUS",
    "Change",
    "CheckReport",
    "FixReport",
    "Issue",
    "RuleDefinition",
    "RuleSet",
    "TargetPolicy",
    "build_check_report",
    "build_fix_report",
    "check_refs",
    "check_schema",
    "convert_mcp_tools",
    "fix_schema",
    "is_lossless",
    "load_all_rules",
    "load_rules",
    "normalize_target",
    "resolve_json_pointer",
    "resolve_refs",
]
