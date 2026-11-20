---
name: delphi-automation-workflow
description: >-
  Build and run Delphi GUI/console automation tests. Use when AI needs to analyze Delphi source/DFM files,
  generate machine-executable automation scripts, call automate_delphi, generate structured test reports and repair plans,
  then switch to coding mode to fix failures and rerun.
---

<!-- @when: Performing Delphi automation testing for the first time; need to understand the complete workflow -->
<!-- @chain: after=../../ui.md, before=script-generation-workflow.md -->

# Delphi Automation Test Workflow

Complete closed loop: source analysis → script construction → execution → report → repair → rerun.

MCP resource URI: `delphi://automation/workflow`.

## Client Boundary

This resource is provided by Daofy MCP Server to external MCP clients. DaofyCoding built-in
Guidance does not read `delphi://` resources, nor does it depend on Daofy MCP Server; in DaofyCoding
use the host-native `structured_content`, `process`, and `automation_run`, and follow
the processing order of the current language profile. Delphi uses the `daofy-gui`, `windows-uia`, or
`delphi-rtti` provider; Lazarus uses `daofy-gui`/`windows-uia`; other languages use
explicit steps and `external-driver`.

Ordinary external MCP clients can still use `automate_delphi`. When the Server detects that
`initialize.clientInfo.name` is DaofyCoding, it hides `structured_content`, `automate_delphi`, and `delphi_rtti`,
which have been replaced by native host capabilities, to avoid duplicate registration;
`delphi_file` and `delphi_project` remain for clients without host tools of the same name.

## Core Loop

1. Load `delphi://automation/workflow`.
2. First choose the test entry: for pure business-class methods use `action="test"`; for UI user paths use
   `action="gui"`; for console interaction use `action="console"`.
3. For RTTI unit tests, first read `delphi://automation/rtti-test-runner`; for new GUI/console scripts, first read
   `delphi://automation/script-generation-workflow`.
4. Analyze source: read the target `.pas/.dfm`, map branches, exceptions, controls, events, and code-derived assertions.
5. Construct executable tests: RTTI suites use `expected`, `expected_exception`, or
   `assert_expr`; GUI script explanatory text goes in `expected` or `note`.
6. Execute `automate_delphi(action="test"|"auto"|"gui"|"console", ...)`.
7. For the test action, read results via `async_task`; for GUI action, read
   `result.report.first_failure`. Stop dependent steps when a failure exists.
8. Generate a repair plan based on structured results and failure evidence.
9. Switch to coding mode, fix deterministic defects, compile, and rerun the complete suite/script.
10. Save passing test definitions under the project root `Tests\<测试类型>\`,
    and store useful incident recoveries in `experience`.

## Related Documents

- `delphi://automation/script-schema` — required reading before creating or editing scripts.
- `delphi://automation/rtti-test-runner` — required reading when creating or executing RTTI unit test suites.
- `delphi://automation/script-generation-workflow` — required reading when deriving scripts from source.
- `delphi://automation/report-schema` — required reading when interpreting results or generating test reports.
- `delphi://automation/inline-unit` — required reading when integrating a Delphi project with `tools/auto`.
- `delphi://automation/repair-loop` — required reading when a run fails and code needs to be modified.

## Hard Rules

- Do not write natural language in `assert_expr`.
- For RTTI exception paths use `expected_exception`; setup/teardown exceptions must not pass as expected test exceptions.
- Black-box execution steps must not use `rcall`, `rset`, or direct RTTI calls.
- Prefer `rget/waitfor/msgscan` for assertions rather than pure visual checks.
- For collection controls (TCategoryButtons, TListBox, etc.), use title-based clicks
  (`ControlName@ItemCaption`) instead of coordinates. Fall back to
  `ControlName@x,y` only when child items have no stable title.
- Coordinate clicks should use `ControlName@x,y`, unless the newer standalone `x/y` script fields are specifically needed.
- Do not blindly run `dumpstate/formsum` on the startup form (forms containing project-related getters);
  first calibrate with `listwnd`, `capture`, `rinspect`, or targeted `rget`. When using `dumpstate`,
  pass a `props` whitelist (e.g. `props=name,class,caption,enabled`) to avoid triggering problematic
  getters and to control response size.
- When `action="auto"`, use `resolved_action` as authoritative.
- Keep `stop_on_failure=true` unless it is explicitly an exploratory task.
- Use `delphi_file` for Delphi source edits, then compile with `delphi_project`.
- Do not continue subsequent automation steps after a preceding step fails.

