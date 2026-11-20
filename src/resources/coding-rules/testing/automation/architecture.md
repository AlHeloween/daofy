<!-- @when: When you need to understand the full automated testing architecture and navigate from the top-level entry to each submodule -->
<!-- @chain: after=index.md, before=reference/*.md -->

# Automated Testing Architecture Overview

MCP resource URI: `delphi://automation/architecture`.

## Client Boundary

This architecture description covers the Delphi automation capabilities that Daofy MCP Server provides to external MCP clients. DaofyCoding has its own independent host execution chain; it does not read `delphi://` resources and does not depend on Daofy MCP Server. DaofyCoding's language processing order is: first identify the project and toolchain, then implement within scope, then run the language's corresponding compile/test, and finally call native `automation_run` only when the target surface requires it; non-Delphi projects are verified through explicit steps and `external-driver`.

External clients use this Server's `automate_delphi`, `delphi_rtti`, and resource URIs. If the Server detects DaofyCoding from `initialize.clientInfo.name`, it hides these three tools that already have host replacements and retains Delphi-specific tools such as `delphi_file`/`delphi_project` that do not have same-name host replacements.

```
Large model (brain):  perceive → plan → execute instructions → analyze feedback → adjust strategy
                   ↕          ↕
MCP server (hands/feet):  provide tools to perceive UI state + execute UI operations
```

The large model is responsible for **decision-making and planning**, and MCP tools are responsible for **perception and execution**. The two form a closed loop.

## Architecture Modules

| Module | URI | Description |
|------|-----|------|
| RTTI vs OCR decision matrix | `delphi://automation/rtti-ocr-matrix` | Scenario comparison table for functional verification vs visual completeness verification |
| Planning methodology | `delphi://automation/planning-methodology` | Layered degradation strategy, action sequence specification, failure handling patterns |
| Experience-driven optimization loop | `delphi://automation/experience-loop` | Experience retrieval/saving/fusion mechanism that lets the AI learn from history |
| Code-aware testing | `delphi://automation/code-aware-testing` | Derive test paths and code-derived assertions from DFM/PAS source code |
| RTTI unit testing | `delphi://automation/rtti-test-runner` | Directly test class methods, fixture lifecycle, per-case timeout, and stability statistics |

## Related Workflows

| Document | URI |
|------|-----|
| Complete automated testing workflow | `delphi://automation/workflow` |
| Script generation workflow | `delphi://automation/script-generation-workflow` |
| Capability selection matrix | `delphi://automation/capability-matrix` |
| Script format specification + assertions + cache | `delphi://automation/script-schema` |
| RTTI unit test runner | `delphi://automation/rtti-test-runner` |

## Related References

| Document | URI |
|------|-----|
| UIA command reference | `delphi://automation/uia-commands` |
| Prompt templates | `delphi://automation/prompts` |
| Report format | `delphi://automation/report-schema` |
| Failure repair loop | `delphi://automation/repair-loop` |
| Project integration guide | `delphi://automation/inline-unit` |

