# Testing Documentation Navigation

Automated testing documentation is located uniformly under `coding-rules/testing/` and is divided into three layers by responsibility:

```
coding-rules/testing/
├── index.md                    ← This file (navigation entry)
├── ui.md                       ← ⑧ UI automated testing (entry, command classification, scenario index)
├── console.md                  ← ⑨ Console interaction verification
└── automation/                 ← Detailed automated testing documentation
    ├── index.md                ← Automated documentation overview
    ├── architecture.md         ← Architecture methodology (perceive → plan → execute → feedback)
    ├── scenarios/              ← Test scenario templates (A-O + checklist)
    │   ├── base.md             ← Communication protocol + test quality red lines
    │   ├── a-smoke.md ~ o-control-rebuild.md
    │   └── checklist.md        ← 27 black-box test quality gates
    └── reference/              ← Technical reference
        ├── script-schema.md    ← Script format specification
        ├── script-generation-workflow.md ← Script generation workflow
        ├── capability-matrix.md ← Capability selection matrix
        ├── workflow.md         ← Complete workflow
        └── ...                 ← Other reference documents
```

## Entry Selection

| Scenario | Entry file |
|------|---------|
| First time learning about automated testing | [ui.md](ui.md) (⑧ UI automated testing) |
| Writing test scripts | [automation/reference/script-schema.md](automation/reference/script-schema.md) |
| Choosing a test strategy | [automation/reference/capability-matrix.md](automation/reference/capability-matrix.md) |
| Generating test scripts | [automation/reference/script-generation-workflow.md](automation/reference/script-generation-workflow.md) |
| Console program testing | [console.md](console.md) (⑨ Console interaction verification) |
| Understanding test quality standards | [automation/scenarios/base.md](automation/scenarios/base.md) § Test Quality Red Lines |

