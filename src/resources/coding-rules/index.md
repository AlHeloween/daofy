<!-- @title: Coding rules navigation (multi-language) -->
<!-- @purpose: Select the corresponding coding rules entry point by programming language. Use get_coding_rules(section=..., language=...). -->

## Coding rules navigation
> Last updated: 2026-07-17 | Version: 1.14.0

Select a programming language to get the corresponding coding rules:

- **Delphi** → `get_coding_rules(language="delphi")` — Embarcadero Delphi coding standards
- **Lazarus/Free Pascal** → `get_coding_rules(language="lazarus")` — Lazarus/FPC coding standards

When `language` is not specified, Delphi rules are returned by default (backward compatible).

Each language entry contains: workflow overview → environment check → API search → coding standards → format → compile → cleanup → review → experience saving

Common rules shared by all languages (Agent operation standards, debugging, experience management) are automatically merged into the returned results.