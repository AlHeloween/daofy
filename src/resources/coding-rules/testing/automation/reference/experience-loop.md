<!-- @when: managing the automated-test experience base, or learning how experience is searched, saved and merged -->

# Experience-Driven Optimisation Loop

MCP resource URI: `delphi://automation/experience-loop`.

Through the search, save and merge capabilities of the `experience` tool, the AI keeps learning from historical tests.

## G1. Optimisation Loop

```
┌─ ① Retrieve experience ──────────────────┐
│ Search historical experience before each test (top_k=3) │
└──────────────┬─────────────────┘
               ↓
┌─ ② Plan the test ──────────────────┐
│ Refer to successful patterns and avoid historical failure patterns │
└──────────────┬─────────────────┘
               ↓
┌─ ③ Execute the test ──────────────────┐
│ On failure → recovery template → record learning │
└──────────────┬─────────────────┘
               ↓
┌─ ④ Save experience ──────────────────┐
│ experience(action="save", ...) │
│ Automatic deduplication: merge when similarity > 0.85 │
└──────────────┬─────────────────┘
               ↓
┌─ ⑤ Periodic merging ──────────────────┐
│ merge similar experience → prune low-value entries │
└──────────────┬─────────────────┘
               ↓
              Back to ①
```

**Key benefits:**
- The same mistake is never made twice
- Successful tool combinations are reused in comparable scenarios
- Experience gathered from many sources converges into team knowledge
- Stale experience is retired automatically

## G2. Experience Search Strategy

| Scenario | Recommended query |
|------|-----------|
| Planning a new test case | "{app name} {feature module} automated test" |
| Recovering from an execution failure | "{app name} {failing operation} failure recovery" |
| Operating a specific control | "{control type} {operation}" |
| Handling a dialog | "{dialog title} {app name}" |

**Flow:** exact query (top_k=3) → fewer than 2 results, widen the query → still fewer than 2, fall back to the default strategy

## G3. Experience Merging

Merge when similar experience accumulates to 5+ entries, or the same failure pattern occurs 3+ times:

1. `experience(search, query="{scenario category}", top_k=20)`
2. `experience(merge, ids=[...], keep="most complete record")`
3. `experience(update, id="merged", ...)` to rewrite it as the abstract practice

**Abstraction rule:** store the general pattern, not the concrete operation details. Let `tags` cover each sub-scenario.