# Contributing to toolschema-compat

Thank you for your interest in contributing to `toolschema-compat`!

## Development Setup

`toolschema-compat` requires Python 3.11+ and has zero runtime dependencies.

```bash
git clone https://github.com/YusufBeratZengin/toolschema-compat.git
cd toolschema-compat
python -m venv .venv
# On Linux/macOS:
source .venv/bin/activate
# On Windows (Git Bash):
source .venv/Scripts/activate

pip install -e ".[dev]"
```

## Running Quality Checks

Before opening a pull request, run the full check script from the repository root:

```bash
bash scripts/check.sh
```

This runs:
1. `ruff check src tests` (linting)
2. `ruff format --check src tests` (formatting)
3. `mypy src tests` (strict static type checking)
4. `pytest -q -m "not network" --cov=toolschema_compat --cov-fail-under=85` (unit tests and coverage threshold)

## Adding or Updating Provider Rules

1. **Every rule must have a verifiable source:** Add or update the rule in `src/toolschema_compat/rules/<target>.toml` with an official provider documentation URL or reproducible issue URL in `source_url` and update `last_verified`.
2. **Never guess undocumented limits:** If a provider limit is not officially documented as a fixed value, mark it with `verification_status = "NEEDS_SOURCE"`.
3. **Preserve idempotence:** Ensure `fix_schema(fixed, target)` produces zero additional changes and `check_schema(fixed, target)` returns `[]`.
4. **No secrets or personal data:** All test fixtures must use synthetic example schemas (`example.com`, `foo`, etc.).
