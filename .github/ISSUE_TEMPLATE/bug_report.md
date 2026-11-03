---
name: Bug Report
about: Report a schema compatibility bug or unexpected transformation
title: "[Bug]: "
labels: ["bug"]
assignees: []
---

## Target Provider
Which target was used? (`gemini`, `openai-strict`, or `anthropic`)

## Minimal Input Schema
Please provide a minimal synthetic JSON Schema (no secrets or personal data) that reproduces the issue:

```json
{
  "type": "object",
  "properties": {}
}
```

## Current Behavior
What did `toolschema-compat check` or `toolschema-compat fix` produce?

## Expected Behavior
What should the output schema or issue report look like, and what is the official provider documentation or error message?
