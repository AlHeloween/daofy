<!-- @when: When automated UI/Console testing is needed for a Delphi program -->
<!-- @chain: after=../ui.md -->

## ⚙ Automated Testing Architecture — Perceive · Plan · Execute · Feedback Loop

Automated testing documentation is located uniformly under `resources/coding-rules/testing/automation/` and is divided into three layers by responsibility:

```
resources/coding-rules/testing/automation/
├── index.md                 ← This file, main entry
├── architecture.md          ← Top-level methodology (RTTI/OCR decision matrix, perceive-execute-verify loop, code-aware testing)
├── reference/               ← Framework reference docs
│   ├── workflow.md          — Automated testing workflow overview
│   ├── rtti-test-runner.md  — White-box/gray-box RTTI unit tests, fixtures, timeouts, and reports
│   ├── script-schema.md     — Script format, command list, parameter descriptions
│   ├── script-generation-workflow.md — AI script generation workflow
│   ├── report-schema.md     — Report structure, first_failure handling
│   ├── repair-loop.md       — Failure signal classification → repair → retry loop
│   └── inline-unit.md       — In-process automation unit and cross-platform transport protocol
└── scenarios/               ← Scenario templates (A-O, with strategy descriptions and reusable JSON)
    ├── base.md, a-smoke.md … o-control-rebuild.md, checklist.md
```

### File Index

| File | @when applicable scenario | Description |
|------|---------------|------|
| [architecture.md](architecture.md) | Understanding RTTI/OCR decisions, the perceive-plan-execute loop, and code-aware methodology | Top-level automation architecture |
| [reference/workflow.md](reference/workflow.md) | When performing automated testing for the first time | Automated testing workflow overview |
| [reference/rtti-test-runner.md](reference/rtti-test-runner.md) | When directly testing Delphi class methods or replacing DUnitX execution capability | RTTI test integration, registration, assertions, timeouts, and reporting |
| [reference/inline-unit.md](reference/inline-unit.md) | When you need to understand in-process automation units and NamedPipe/Unix Socket transport | Inline automation unit documentation |
| [reference/script-schema.md](reference/script-schema.md) | When writing `automate_delphi` script commands | Script format, command list, parameter descriptions |
| [reference/script-generation-workflow.md](reference/script-generation-workflow.md) | When generating automation scripts from Delphi source code | AI script generation workflow |
| [reference/report-schema.md](reference/report-schema.md) | When analyzing automated test reports | Report structure, first_failure handling |
| [reference/repair-loop.md](reference/repair-loop.md) | When automated test failures need repair | Classify failure signals → repair → retry loop |

### UI Test Scenarios (A-O)

Scenario files are located in `scenarios/` and contain strategy descriptions and reusable JSON templates:

| Scenario | File | Description |
|------|------|------|
| Infrastructure (enablement) | [scenarios/base.md](scenarios/base.md) | Pre-check/enablement process (4 steps)/communication architecture/protocol/keep_alive/failure recovery |
| A. Smoke test | [scenarios/a-smoke.md](scenarios/a-smoke.md) | Program startup and main form verification |
| B. Login flow | [scenarios/b-login.md](scenarios/b-login.md) | Credential input and login state switching |
| C. Form data entry | [scenarios/c-data-entry.md](scenarios/c-data-entry.md) | Form filling and submit/save |
| D. Grid row operations | [scenarios/d-grid.md](scenarios/d-grid.md) | List row create/read/update/delete |
| E. Tree navigation | [scenarios/e-tree-navigation.md](scenarios/e-tree-navigation.md) | Tree node expand/collapse/select |
| F. Search/filter | [scenarios/f-search.md](scenarios/f-search.md) | Search hits and no-result handling |
| G. Modal dialogs | [scenarios/g-modal-dialogs.md](scenarios/g-modal-dialogs.md) | Confirmation dialog/file dialog |
| H. Multi-step wizard | [scenarios/h-wizard.md](scenarios/h-wizard.md) | Wizard step switching |
| I. Context menu | [scenarios/i-context-menu.md](scenarios/i-context-menu.md) | Context menu popup and menu item selection |
| J. DirectUI popups | [scenarios/j-directui.md](scenarios/j-directui.md) | IFileDialog/TTaskDialog/uia.xxx commands |
| K. Text completeness | [scenarios/k-text-completeness.md](scenarios/k-text-completeness.md) | OCR detects truncation/ellipsis/DPI |
| L. Layout alignment | [scenarios/l-layout.md](scenarios/l-layout.md) | After static layout audit, runtime left alignment/spacing/overlap/DPI detection |
| M. Control targeting strategy | [scenarios/m-control-targeting.md](scenarios/m-control-targeting.md) | Coordinate calibration/DPI factor |
| N. Wait strategy | [scenarios/n-wait-strategy.md](scenarios/n-wait-strategy.md) | Conditional waits instead of fixed delays |
| O. Control rebuild safety | [scenarios/o-control-rebuild.md](scenarios/o-control-rebuild.md) | Wait for control rebuild after Rescan |
| Checklist | [scenarios/checklist.md](scenarios/checklist.md) | 27 black-box test quality gates |

Entry file: [testing/ui.md](../ui.md) (`## ⑧ Automated UI Interaction Testing`)

### Related Tools

```python
automate_delphi(action="auto", app_path="App.exe", script=[...])
automate_delphi(action="gui",  app_path="App.exe", script=[...])
automate_delphi(action="console", app_path="Tool.exe", input="Y\n", expect="Continue?")
automate_delphi(action="test", app_path="TestHost.exe", tests=[...])
```

> For the detailed command list, protocol format, and examples, see `reference/script-schema.md`.
> For RTTI unit tests and fixture integration, see `reference/rtti-test-runner.md`.
> For the AI script generation workflow, see `reference/script-generation-workflow.md`.
> For the repair loop, see `reference/repair-loop.md`.
> For UI test scenario templates, see the A-O files under the `scenarios/` directory.

