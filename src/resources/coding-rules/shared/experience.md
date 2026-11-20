<!-- @when: Experience must be saved after a problem is solved; consult the experience base when troubleshooting a difficult problem -->
<!-- @chain: before=maintenance.md, after=human-collab.md -->

## ⑪ Experience Saving — Capture Knowledge in the Experience Base

The `experience` tool persists effective methods into the experience knowledge base, so the next similar case can reuse them directly.

### Scenarios That Must Be Saved

| Scenario | Priority |
|------|--------|
| After a problem was solved with human intervention | 🔴 Must |
| Non-obvious bug fixes | 🔴 Must |
| Compiler/toolchain compatibility issues | 🟡 Recommended |
| Uncommon API usage | 🟡 Recommended |
| A new coding rule was triggered | 🟡 Recommended |

### Saving Flow (search → generalize → save)

```
① search(query=..., tags=...) check whether a similar experience already exists
   exists → ③ update/merge
   none   → ② generalize the problem description (abstract the general scenario, no concrete file names)
            ③ save(problem=..., solution=..., tags=...)
            ④ rebuild_embedding (optional; filled in automatically when the model loads later)
            ⑤ search to verify it can be recalled
```

### Automatic Deduplication Logic

```
save(problem, solution)
 ├─ similarity > 0.85 → merge into the old record automatically (solution concatenated, tags deduplicated, score +0.05)
 ├─ similarity > 0.7  → intercepted with a reminder, merge/update suggested; pass force=true to skip
 └─ similarity ≤ 0.7  → create a new record
```

### Quality Standards
| Dimension | Requirement | Counter-example |
|------|------|------|
| problem | A general scenario that contains the key trigger conditions | `Form1 reports an error` |
| solution | Step-based and reproducible | `tweak the config a bit` |
| tags | 3~5 tags covering several angles | `["bug"]` |

### Periodic Maintenance
- **prune**: value = hit_count × score × time_decay; 30-day half-life decay
- **merge**: merge similar experiences, concatenate problem/solution, deduplicate tags/tools_used
- hit_count ≥ 3 → evaluate promoting it into a coding rule

### Embedding Degradation Strategy
- Model not loaded: save() stores no vector, search() degrades to LIKE
- Model loaded later: the first search() automatically generates the missing vectors
- Manual rebuild: `experience(action="rebuild_embedding")`

