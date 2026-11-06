"""Command-line interface for `toolschema-compat`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from toolschema_compat.report import (
    CheckReport,
    FixReport,
    build_check_report,
    build_fix_report,
)
from toolschema_compat.rules import SUPPORTED_TARGETS, load_all_rules, load_rules
from toolschema_compat.transform import check_schema, convert_mcp_tools

TARGET_CHOICES: tuple[str, ...] = (*SUPPORTED_TARGETS, "all")
ENVELOPE_CHOICES: tuple[str, ...] = (
    "preserve",
    "gemini",
    "gemini-json-schema",
    "openai",
    "anthropic",
)


def _read_json_input(source: str) -> dict[str, Any]:
    """Load JSON dictionary from a file path or `-` (stdin)."""
    try:
        if source == "-":
            raw_text = sys.stdin.read()
        else:
            file_path = Path(source)
            if not file_path.is_file():
                raise FileNotFoundError(f"Input file not found: {source}")
            raw_text = file_path.read_text(encoding="utf-8")
        parsed = json.loads(raw_text)
    except FileNotFoundError as exc:
        raise ValueError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in '{source}': {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Expected top-level JSON object in '{source}', got {type(parsed).__name__}"
        )
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolschema-compat",
        description=(
            "Audit and safely transform tool (function calling) JSON Schemas for "
            "Gemini, OpenAI strict, and Anthropic with explicit lossy-change reporting."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # `check` command
    check_parser = subparsers.add_parser(
        "check",
        help="Audit a JSON Schema or MCP tools/list file against provider compatibility rules.",
    )
    check_parser.add_argument(
        "input",
        help="Path to JSON Schema / MCP tools.json file, or '-' for stdin.",
    )
    check_parser.add_argument(
        "-t",
        "--target",
        required=True,
        choices=TARGET_CHOICES,
        help="Target provider subset ('gemini', 'openai-strict', 'anthropic', or 'all').",
    )
    check_parser.add_argument(
        "-f",
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    check_parser.add_argument(
        "--fail-on-lossy",
        action="store_true",
        help="Exit non-zero only if issues require a lossy transformation.",
    )

    # `fix` command
    fix_parser = subparsers.add_parser(
        "fix",
        help="Transform a JSON Schema or MCP tools/list file for the target provider.",
    )
    fix_parser.add_argument(
        "input",
        help="Path to JSON Schema / MCP tools.json file, or '-' for stdin.",
    )
    fix_parser.add_argument(
        "-t",
        "--target",
        required=True,
        choices=SUPPORTED_TARGETS,
        help="Target provider subset ('gemini', 'openai-strict', 'anthropic').",
    )
    fix_parser.add_argument(
        "-o",
        "--output",
        help="Write the transformed JSON schema to this file path.",
    )
    fix_parser.add_argument(
        "-r",
        "--report",
        help="Write the structured JSON transformation report to this file path.",
    )
    fix_parser.add_argument(
        "-f",
        "--format",
        choices=("text", "json"),
        default="text",
        help="Stdout report format (default: text).",
    )
    fix_parser.add_argument(
        "--envelope",
        choices=ENVELOPE_CHOICES,
        default="preserve",
        help=(
            "Output tool envelope format ('preserve', 'gemini', 'gemini-json-schema', "
            "'openai', 'anthropic')."
        ),
    )
    fix_parser.add_argument(
        "--fail-on-lossy",
        action="store_true",
        help="Exit with code 1 if any applied transformation is marked lossy: true.",
    )

    # `rules` command
    rules_parser = subparsers.add_parser(
        "rules",
        help="Display provider compatibility rules and their official documentation sources.",
    )
    rules_parser.add_argument(
        "-t",
        "--target",
        choices=TARGET_CHOICES,
        default="all",
        help="Target provider to inspect (default: all).",
    )
    rules_parser.add_argument(
        "-f",
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )

    return parser


def _handle_check(args: argparse.Namespace) -> int:
    schema = _read_json_input(args.input)
    targets = SUPPORTED_TARGETS if args.target == "all" else (args.target,)

    reports: list[CheckReport] = []
    for target in targets:
        issues = check_schema(schema, target)
        reports.append(build_check_report(target, issues))

    if args.format == "json":
        if len(reports) == 1:
            print(reports[0].to_json())
        else:
            payload = {
                "compatible": all(r.compatible for r in reports),
                "targets": [r.to_dict() for r in reports],
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("\n\n".join(r.to_text() for r in reports))

    if args.fail_on_lossy:
        return 1 if any(r.lossy_issue_count > 0 for r in reports) else 0
    return 0 if all(r.compatible for r in reports) else 1


def _handle_fix(args: argparse.Namespace) -> int:
    out_path = Path(args.output) if args.output else None
    rep_path = Path(args.report) if args.report else None
    if (
        out_path is not None
        and rep_path is not None
        and out_path.expanduser().resolve() == rep_path.expanduser().resolve()
    ):
        raise ValueError(
            f"--output and --report must point to different file paths, got '{args.output}'."
        )

    schema = _read_json_input(args.input)
    fixed_schema, changes = convert_mcp_tools(
        schema,
        args.target,
        envelope=args.envelope,
    )
    report: FixReport = build_fix_report(args.target, changes, schema=fixed_schema)

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(fixed_schema, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if rep_path is not None:
        rep_path.parent.mkdir(parents=True, exist_ok=True)
        rep_path.write_text(
            report.to_json(indent=2, include_schema=False) + "\n",
            encoding="utf-8",
        )

    if args.format == "json":
        include_schema = not bool(args.output)
        print(report.to_json(indent=2, include_schema=include_schema))
    else:
        print(report.to_text())
        if not args.output:
            print("\n--- Fixed Schema ---")
            print(json.dumps(fixed_schema, indent=2, ensure_ascii=False))

    if args.fail_on_lossy and report.lossy:
        return 1
    return 0


def _handle_rules(args: argparse.Namespace) -> int:
    rulesets = load_all_rules() if args.target == "all" else {args.target: load_rules(args.target)}
    if args.format == "json":
        payload = {
            target: {
                "provider": rs.provider,
                "schema_version": rs.schema_version,
                "last_verified": rs.last_verified,
                "primary_source": rs.primary_source,
                "secondary_sources": list(rs.secondary_sources),
                "rules": [
                    {
                        "id": r.id,
                        "category": r.category,
                        "description": r.description,
                        "lossy": r.lossy,
                        "source_url": r.source_url,
                        "last_verified": r.last_verified,
                        "verification_status": r.verification_status,
                    }
                    for r in rs.rules
                ],
            }
            for target, rs in rulesets.items()
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        blocks: list[str] = []
        for target, rs in rulesets.items():
            lines = [
                f"Target: {target} ({rs.provider})",
                f"Version: {rs.schema_version} (verified: {rs.last_verified})",
                f"Primary source: {rs.primary_source}",
            ]
            for r in rs.rules:
                status = (
                    f" [{r.verification_status}]" if r.verification_status != "verified" else ""
                )
                lines.append(
                    f"  - {r.id}{status} (lossy={str(r.lossy).lower()}): {r.description}\n"
                    f"    Source: {r.source_url}"
                )
            blocks.append("\n".join(lines))
        print("\n\n".join(blocks))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning process exit code."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "check":
            return _handle_check(args)
        if args.command == "fix":
            return _handle_fix(args)
        if args.command == "rules":
            return _handle_rules(args)
        return 2  # pragma: no cover
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
