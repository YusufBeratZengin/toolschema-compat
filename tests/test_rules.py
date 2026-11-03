"""Tests for provider rule TOML loading, source URLs, and NEEDS_SOURCE metadata."""

from __future__ import annotations

import pytest

from toolschema_compat.rules import (
    SUPPORTED_TARGETS,
    UNVERIFIED_STATUS,
    load_all_rules,
    load_rules,
    normalize_target,
)


def test_supported_targets_present() -> None:
    assert SUPPORTED_TARGETS == ("gemini", "openai-strict", "anthropic")
    all_rules = load_all_rules()
    assert set(all_rules.keys()) == set(SUPPORTED_TARGETS)


@pytest.mark.parametrize("target", SUPPORTED_TARGETS)
def test_every_rule_has_valid_https_source_url_and_date(target: str) -> None:
    ruleset = load_rules(target)
    assert ruleset.target == target
    assert ruleset.primary_source.startswith("https://")
    assert len(ruleset.last_verified) == 10  # YYYY-MM-DD
    assert len(ruleset.rules) >= 10

    for rule in ruleset.rules:
        assert rule.id
        assert rule.category
        assert rule.description
        assert rule.source_url.startswith("https://")
        assert len(rule.last_verified) == 10
        assert rule.verification_status in {"verified", UNVERIFIED_STATUS}


@pytest.mark.parametrize("target", SUPPORTED_TARGETS)
def test_unverified_limits_marked_needs_source(target: str) -> None:
    ruleset = load_rules(target)
    unverified = ruleset.unverified_rules()
    assert len(unverified) >= 1
    for rule in unverified:
        assert rule.verification_status == UNVERIFIED_STATUS
        assert "NEEDS_SOURCE" in rule.description


def test_normalize_target_variations_and_invalid() -> None:
    assert normalize_target("  GEMINI ") == "gemini"
    assert normalize_target("openai_strict") == "openai-strict"
    assert normalize_target("Anthropic") == "anthropic"

    with pytest.raises(ValueError, match="Unsupported target"):
        normalize_target("unknown-provider")
