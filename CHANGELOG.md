# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-03

### Added
- Versioned TOML compatibility rule sets (`src/toolschema_compat/rules/*.toml`) for `gemini`, `openai-strict`, and `anthropic`, with official documentation/issue URLs and `NEEDS_SOURCE` annotations for undocumented provider limits.
- Acyclic `$ref`, `$defs`, and `definitions` resolver (`toolschema_compat.resolve`) with cycle truncation and sibling keyword preservation.
- Idempotent schema auditor and transformer (`check_schema`, `fix_schema`, `convert_mcp_tools`, `is_lossless`) supporting raw JSON Schemas, MCP `tools/list` files, Gemini `parameters` / `parametersJsonSchema` envelopes, OpenAI `function` envelopes, and Anthropic `input_schema` envelopes.
- Structured reporting (`CheckReport`, `FixReport`) with `lossy: true` telemetry and explicit `deleted_constraints` tracking (`pattern`, `format`, numeric bounds, etc.).
- CLI (`toolschema-compat check`, `toolschema-compat fix`, `toolschema-compat rules`) with `--target`, `--format`, `--output`, `--report`, `--envelope`, and `--fail-on-lossy` flags.
- Test suite with 24 real-world-derived provider fixtures (8 per target) and >90% branch coverage.
