<!-- @when: Human intervention conditions are triggered and complete handover information must be submitted -->
<!-- @chain: after=exception-info-collection.md -->

### 8.4 Human Intervention Handover Checklist

When requesting intervention, the following information is **indispensable**:

```
┌────────────────────────────────────────────┐
│               Human Intervention Request Form │
├────────────────────────────────────────────┤
│ [1] Problem summary                         │
│   Describe the problem in one sentence      │
│                                             │
│ [2] Attempted solutions (list one by one)   │
│   ① What was tried → result → why it failed │
│   ② ...                                     │
│   ③ ...                                     │
│                                             │
│ [3] Exception scene (see 8.3 template)      │
│   ├─ Complete exception message + call stack│
│   ├─ Key variable values                    │
│   └─ Reproduction steps (shortest path from startup to exception) │
│                                             │
│ [4] Environment information                 │
│   ├─ Daofy/Python/OS version                │
│   ├─ Delphi compiler version                │
│   ├─ Project type (VCL/FMX/Console)         │
│   └─ Recent changes (related to the problem)│
│                                             │
│ [5] Expected result                         │
│   What specifically you want the human to do│
│                                             │
│ [6] Minimal reproducible example (MRE)      │
│   If it can be isolated, attach the code    │
└────────────────────────────────────────────┘
```


