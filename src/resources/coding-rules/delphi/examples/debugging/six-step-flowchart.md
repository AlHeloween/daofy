# Six-Step Exception Diagnosis Flowchart

```
        ① Analysis
        Collect information → Identify root cause → Determine problem nature
         ▲                    │  
         │   Audit return (🔴)│  ← Verification return direction
         │   Plan return (🟡) │    (⑥ Failure → back to ①)
         │                    │  
       ┌─┼─────────────────┐
       │ ② Plan             │
       │ Design solution→Compare multiple solutions→Verification criteria │
       └───────────┬────────┘
                   │ Audit return (🟡 boundary/spec)
                   ▼
       ┌───────────────────┐
       │ ③ Audit            │
       │ Review solution item by item with checklist │
       │ ├─ ✅ Pass → Continue │
       │ └─ ❌ Issue → Return to ①②│
       └───────────┬───────┘
                   │
       ┌───────────┴───────┐
       │ ④ Backup           │
       │ __history + WIP commit │
       └───────────┬───────┘
                   │
       ┌───────────┴───────┐
       │ ⑤ Execute          │
       │ Preview→Modify→Format→Compile→commit│
       └───────────┬───────┘
                   ▼
       ┌───────────────────┐
       │ ⑥ Verify           │
       │ Verify per criteria→Clean up→Save experience │
       ├─ ✅ Pass → Done      │
       └─ ❌ Fail → Back to ① Analysis │
```

## Audit Return Loop Rules

- 🔴 Security/root cause missed → Return to ①
- 🟡 Boundary/spec → Return to ②
- Same issue returned 3 times consecutively → Trigger P0 intervention

## Six-Step Inputs and Outputs

| Step | Input | Output |
|------|------|------|
| ① | Exception information | Root cause hypothesis / problem classification |
| ② | Root cause hypothesis | Modification plan / verification criteria |
| ③ | Plan | Audit conclusion (pass/return) |
| ④ | Audit passed | Backup confirmation |
| ⑤ | Backup confirmation | Compile result / commit |
| ⑥ | Compile result | Verification report / experience / retrospective decision |

