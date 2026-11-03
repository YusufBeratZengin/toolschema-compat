"""Structured issue and transformation reporting models and formatters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Issue:
    """Compatibility violation detected by `check_schema`."""

    rule_id: str
    path: str
    message: str
    source_url: str
    lossy: bool = False
    keyword: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize issue to a JSON-compatible dictionary."""
        data: dict[str, Any] = {
            "rule_id": self.rule_id,
            "path": self.path,
            "message": self.message,
            "lossy": self.lossy,
            "source_url": self.source_url,
        }
        if self.keyword is not None:
            data["keyword"] = self.keyword
        return data


@dataclass(frozen=True, slots=True)
class Change:
    """Single transformation applied by `fix_schema`."""

    rule_id: str
    path: str
    action: str
    message: str
    lossy: bool
    source_url: str
    deleted_constraint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize change to a JSON-compatible dictionary."""
        data: dict[str, Any] = {
            "rule_id": self.rule_id,
            "path": self.path,
            "action": self.action,
            "message": self.message,
            "lossy": self.lossy,
            "source_url": self.source_url,
        }
        if self.deleted_constraint is not None:
            data["deleted_constraint"] = self.deleted_constraint
        return data


@dataclass(frozen=True, slots=True)
class CheckReport:
    """Summary report for `check_schema` / `check` command."""

    target: str
    issues: tuple[Issue, ...]

    @property
    def compatible(self) -> bool:
        """Return True when no compatibility issues were found."""
        return len(self.issues) == 0

    @property
    def issue_count(self) -> int:
        """Total number of issues detected."""
        return len(self.issues)

    @property
    def lossy_issue_count(self) -> int:
        """Number of issues whose automatic fix is lossy."""
        return sum(1 for issue in self.issues if issue.lossy)

    def to_dict(self) -> dict[str, Any]:
        """Convert check report to a dictionary."""
        return {
            "target": self.target,
            "compatible": self.compatible,
            "issue_count": self.issue_count,
            "lossy_issue_count": self.lossy_issue_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_json(self, indent: int = 2) -> str:
        """Format check report as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_text(self) -> str:
        """Format check report as human-readable terminal text."""
        if self.compatible:
            return f"[OK] target={self.target}: compatible (0 issues)"

        lines = [
            f"[FAIL] target={self.target}: {self.issue_count} issue(s) found "
            f"({self.lossy_issue_count} require lossy fix)"
        ]
        for idx, issue in enumerate(self.issues, start=1):
            lossy_tag = " [lossy]" if issue.lossy else ""
            lines.append(
                f"  {idx}. [{issue.rule_id}]{lossy_tag} {issue.path}: {issue.message} "
                f"(source: {issue.source_url})"
            )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class FixReport:
    """Summary report for `fix_schema` / `fix` command with lossy telemetry."""

    target: str
    changes: tuple[Change, ...]
    schema: Any = None

    @property
    def changed(self) -> bool:
        """Return True if at least one change was applied."""
        return len(self.changes) > 0

    @property
    def change_count(self) -> int:
        """Total number of applied changes."""
        return len(self.changes)

    @property
    def lossy_changes(self) -> tuple[Change, ...]:
        """All changes marked with `lossy=True`."""
        return tuple(change for change in self.changes if change.lossy)

    @property
    def lossy_count(self) -> int:
        """Count of lossy changes."""
        return len(self.lossy_changes)

    @property
    def lossy(self) -> bool:
        """Return True if any applied change narrows or drops validation semantics."""
        return self.lossy_count > 0

    @property
    def lossless(self) -> bool:
        """Return True if no applied change was lossy."""
        return self.lossy_count == 0

    @property
    def deleted_constraints(self) -> list[str]:
        """Ordered unique list of validation constraint keywords removed during fix."""
        seen: dict[str, None] = {}
        for change in self.changes:
            if change.deleted_constraint is not None:
                seen[change.deleted_constraint] = None
        return list(seen.keys())

    def to_dict(self, include_schema: bool = False) -> dict[str, Any]:
        """Convert fix report to a JSON-compatible dictionary."""
        data: dict[str, Any] = {
            "target": self.target,
            "changed": self.changed,
            "change_count": self.change_count,
            "lossy": self.lossy,
            "lossless": self.lossless,
            "lossy_count": self.lossy_count,
            "deleted_constraints": self.deleted_constraints,
            "changes": [change.to_dict() for change in self.changes],
        }
        if include_schema and self.schema is not None:
            data["schema"] = self.schema
        return data

    def to_json(self, indent: int = 2, include_schema: bool = False) -> str:
        """Format fix report as a JSON string."""
        return json.dumps(
            self.to_dict(include_schema=include_schema),
            indent=indent,
            ensure_ascii=False,
        )

    def to_text(self) -> str:
        """Format fix report as human-readable terminal text."""
        if not self.changed:
            return f"[OK] target={self.target}: 0 changes needed (lossless=true)"

        status = "lossy=true" if self.lossy else "lossless=true"
        lines = [
            f"[FIXED] target={self.target}: {self.change_count} change(s) applied "
            f"({self.lossy_count} lossy, {status})"
        ]
        if self.deleted_constraints:
            joined = ", ".join(self.deleted_constraints)
            lines.append(f"  Deleted constraints: {joined}")
        for idx, change in enumerate(self.changes, start=1):
            lossy_tag = " [lossy: true]" if change.lossy else " [lossy: false]"
            lines.append(
                f"  {idx}. [{change.rule_id}]{lossy_tag} {change.path}: {change.message} "
                f"(source: {change.source_url})"
            )
        return "\n".join(lines)


def build_check_report(target: str, issues: list[Issue]) -> CheckReport:
    """Create a `CheckReport` from a target and list of `Issue` objects."""
    return CheckReport(target=target, issues=tuple(issues))


def build_fix_report(
    target: str,
    changes: list[Change],
    schema: Any = None,
) -> FixReport:
    """Create a `FixReport` from a target, list of `Change` objects, and fixed schema."""
    return FixReport(target=target, changes=tuple(changes), schema=schema)
