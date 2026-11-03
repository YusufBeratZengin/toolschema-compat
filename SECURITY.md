# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Security Design

- `toolschema-compat` operates purely on in-memory JSON structures and local files using the Python standard library.
- It makes **zero network requests** when resolving `$ref` pointers; external URIs (e.g., `https://...`) are never fetched and are safely flagged as unresolvable references.
- Recursive `$ref` cycles are bounded by ancestor-spine tracking to prevent denial-of-service via infinite recursion (`RecursionError` / memory exhaustion).

## Reporting a Vulnerability

If you discover a security vulnerability (for example, a crafted JSON Schema input that causes unbounded resource consumption), please report it privately via [GitHub Security Advisories](https://github.com/YusufBeratZengin/toolschema-compat/security/advisories/new) rather than opening a public issue.

We will acknowledge receipt within 72 hours and work with you on a fix and coordinated disclosure.
