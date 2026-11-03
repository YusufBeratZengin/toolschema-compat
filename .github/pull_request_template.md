## Summary
- Briefly describe the changes introduced in this pull request.

## Verification & Rule Sources
- [ ] Every added/modified provider rule includes an official documentation or issue `source_url` in `src/toolschema_compat/rules/*.toml`.
- [ ] Undocumented provider limits are marked `NEEDS_SOURCE` rather than guessed.
- [ ] Transformations are idempotent (`fix_schema(fixed, target)` produces no further changes).
- [ ] `bash scripts/check.sh` passes locally (ruff, mypy, pytest with >=85% coverage).
- [ ] No personal data, credentials, or real secrets are included in fixtures or tests.
