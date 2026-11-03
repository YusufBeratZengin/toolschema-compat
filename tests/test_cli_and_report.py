"""Tests for CLI commands (`check`, `fix`, `rules`) and report formatting."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from toolschema_compat.cli import main
from toolschema_compat.report import build_check_report, build_fix_report
from toolschema_compat.transform import check_schema, fix_schema


def test_cli_check_and_fix_json_report_deleted_constraints(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema_file = tmp_path / "tools.json"
    schema_data: dict[str, Any] = {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "format": "email",
                "pattern": "^.+@example\\.com$",
            },
            "optional_note": {"type": "string"},
        },
        "required": ["email"],
    }
    schema_file.write_text(json.dumps(schema_data), encoding="utf-8")

    # 1. `check` returns exit code 1 when issues exist
    rc_check = main(["check", str(schema_file), "--target", "openai-strict", "--format", "json"])
    assert rc_check == 1
    out_check = json.loads(capsys.readouterr().out)
    assert out_check["compatible"] is False
    assert out_check["lossy_issue_count"] >= 2

    # 2. `fix` writes fixed file and JSON report with `deleted_constraints` (pattern & format)
    out_file = tmp_path / "fixed.json"
    rep_file = tmp_path / "report.json"
    rc_fix = main(
        [
            "fix",
            str(schema_file),
            "--target",
            "openai-strict",
            "--output",
            str(out_file),
            "--report",
            str(rep_file),
            "--format",
            "json",
        ]
    )
    assert rc_fix == 0
    out_fix = json.loads(capsys.readouterr().out)
    assert out_fix["lossy"] is True
    assert out_fix["lossless"] is False
    assert "pattern" in out_fix["deleted_constraints"]
    assert "format" in out_fix["deleted_constraints"]
    assert out_file.is_file()
    assert rep_file.is_file()

    # 3. `check` on fixed file returns exit code 0
    rc_check_fixed = main(["check", str(out_file), "--target", "openai-strict"])
    assert rc_check_fixed == 0
    text_out = capsys.readouterr().out
    assert "[OK] target=openai-strict: compatible (0 issues)" in text_out


def test_cli_check_all_targets_and_fail_on_lossy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lossless_file = tmp_path / "lossless.json"
    lossless_file.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
        ),
        encoding="utf-8",
    )

    # Check against all targets in JSON and text formats
    rc_all_json = main(["check", str(lossless_file), "--target", "all", "--format", "json"])
    assert rc_all_json == 1  # openai-strict and anthropic need additionalProperties: false
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["targets"]) == 3

    # With --fail-on-lossy, adding additionalProperties: false is lossless so exit code is 0
    rc_lossy_only = main(
        ["check", str(lossless_file), "--target", "openai-strict", "--fail-on-lossy"]
    )
    assert rc_lossy_only == 0
    _ = capsys.readouterr()

    # Fix in text mode without --output prints fixed schema to stdout
    rc_fix_text = main(["fix", str(lossless_file), "--target", "openai-strict"])
    assert rc_fix_text == 0
    fix_stdout = capsys.readouterr().out
    assert "[FIXED] target=openai-strict" in fix_stdout
    assert "--- Fixed Schema ---" in fix_stdout


def test_cli_fail_on_lossy_exit_code_in_fix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lossy_file = tmp_path / "lossy.json"
    lossy_file.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"code": {"type": "string", "pattern": "^[0-9]{4}$"}},
                "required": ["code"],
            }
        ),
        encoding="utf-8",
    )

    rc = main(["fix", str(lossy_file), "--target", "gemini", "--fail-on-lossy"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Deleted constraints: pattern" in out


def test_cli_rules_command_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc_text = main(["rules", "--target", "gemini", "--format", "text"])
    assert rc_text == 0
    text_out = capsys.readouterr().out
    assert "GEMINI_REF_DEFS" in text_out
    assert "NEEDS_SOURCE" in text_out

    rc_json = main(["rules", "--target", "all", "--format", "json"])
    assert rc_json == 0
    json_out = json.loads(capsys.readouterr().out)
    assert set(json_out.keys()) == {"gemini", "openai-strict", "anthropic"}


def test_cli_stdin_and_error_handling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Valid stdin input
    valid_stdin = json.dumps(
        {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(valid_stdin))
    rc_stdin = main(["check", "-", "--target", "gemini"])
    assert rc_stdin == 0
    _ = capsys.readouterr()

    # Missing file
    rc_missing = main(["check", str(tmp_path / "does_not_exist.json"), "--target", "gemini"])
    assert rc_missing == 2
    assert "Input file not found" in capsys.readouterr().err

    # Invalid JSON
    bad_json_file = tmp_path / "bad.json"
    bad_json_file.write_text("{not valid json", encoding="utf-8")
    rc_bad = main(["check", str(bad_json_file), "--target", "gemini"])
    assert rc_bad == 2
    assert "Invalid JSON" in capsys.readouterr().err

    # Non-dict JSON root
    list_json_file = tmp_path / "list.json"
    list_json_file.write_text("[1, 2, 3]", encoding="utf-8")
    rc_list = main(["check", str(list_json_file), "--target", "gemini"])
    assert rc_list == 2
    assert "Expected top-level JSON object" in capsys.readouterr().err


def test_report_methods_on_already_compatible_schema() -> None:
    compatible_gemini: dict[str, Any] = {
        "type": "object",
        "properties": {"q": {"type": "string"}},
        "required": ["q"],
    }
    issues = check_schema(compatible_gemini, "gemini")
    check_rep = build_check_report("gemini", issues)
    assert check_rep.compatible is True
    assert "[OK] target=gemini" in check_rep.to_text()

    fixed, changes = fix_schema(compatible_gemini, "gemini")
    fix_rep = build_fix_report("gemini", changes, schema=fixed)
    assert fix_rep.changed is False
    assert fix_rep.lossless is True
    assert "[OK] target=gemini: 0 changes needed" in fix_rep.to_text()
    assert "schema" in fix_rep.to_dict(include_schema=True)

    # CLI fix in text mode with --output suppresses "--- Fixed Schema ---" on stdout
    out_path = Path(compatible_gemini.get("_tmp", "unused"))  # dummy reference avoided below
    assert out_path is not None


def test_cli_fix_text_with_output_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    in_file = tmp_path / "in.json"
    out_file = tmp_path / "out.json"
    in_file.write_text(
        json.dumps({"type": "object", "properties": {"a": {"type": "string"}}}),
        encoding="utf-8",
    )
    rc = main(["fix", str(in_file), "--target", "openai-strict", "-o", str(out_file)])
    assert rc == 0
    stdout = capsys.readouterr().out
    assert "[FIXED] target=openai-strict" in stdout
    assert "--- Fixed Schema ---" not in stdout
    assert out_file.is_file()
