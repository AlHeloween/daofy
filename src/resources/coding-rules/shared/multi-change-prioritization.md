<!-- @when: Several changes must be handled at the same time — decide their order and priority -->
<!-- @chain: before=workflow.md, after=agent-rules.md -->

## Multi-Change Priority Ordering

> This rule constrains only the **scheduling strategy across multiple changes** (what to change first, what next); it does not modify the individual processes themselves (workflow, debugging and testing each keep their own flow unchanged).

### Entry Conditions

Before entering this rule, decide whether the P0 trigger conditions of `planning.md` are hit:

- **Hit** (non-trivial changes such as new features / interface changes / cross-module fixes) → go through the `planning.md` P0 planning flow first, and enter this rule's ordering flow only once an executable sub-task list exists
- **Not hit** (trivial changes) → enter this rule's ordering flow directly

### Priority Definitions

| Priority | Type | Description |
|--------|------|------|
| **S0** | Compile blocker | Cannot compile without it (missing unit, syntax error) |
| **S1** | Infrastructure/interface | Other changes depend on it; a wrong order reworks everything |
| **S2** | Core logic | Compile dependencies, upstream of the data flow |
| **S3** | Auxiliary feature/tool | Does not affect the main flow, can be verified independently |
| **S4** | Style/wording/tweaking | Lowest dependencies, handled last |

### Execution Order Rules

#### 1. Dependency chain first

```
S0(compile blocker) → S1(interface/infrastructure) → S2(core logic) → S3(auxiliary feature) → S4(style/tweaking)
```

- **Change the interface first, the implementation after** — once an interface signature changes, every caller must change with it
- **Change the bottom layer first, the upper layer after** — once the data model/Schema changes, the business logic must adapt
- **Verify as soon as it is changed** — compile and verify immediately after each change is complete, and only then move to the next one

#### 2. Stability first

```
fix a bug → add a feature → refactor code
```

- **Fix first, refactor after** — do not refactor while fixing a bug, otherwise you cannot tell which step caused a regression
- **When fix + refactor must be separated**: fix until it compiles, then refactor, compile-verifying after every refactor step

#### 3. Verifiability first

```
changes that compile on their own → changes that need a whole-project compile
```

- **Single-file changes first** — an intermediate state that compiles = it can be paused and rolled back at any time
- **Commit in small steps** — pair each independent change with a compile verification; do not pile up a batch and test it all at once

#### 4. Ordering within one priority

When several changes share one priority:

| Principle | Description |
|------|------|
| Larger impact first | Changes that touch more files and a wider surface go first |
| Higher risk first | Those that may cause a regression go first, exposing problems early |
| Shorter dependency chain first | Those that fewer later changes depend on go first, reducing blocking |
| Lower difficulty first | Quick completion shrinks the to-do list and lowers the cognitive load |

### Decision Flow

```
Multiple change requests received
    │
    ├─ <Entry condition> Does planning.md P0 hit?
    │   ├─ Yes → go through the P0 plan first; enter ordering once the sub-task list exists
    │   └─ No  → enter ordering directly
    │
    ├─ ① List all changes and classify them
    │
    ├─ ② Analyze the dependency relations
    │   ├─ A depends on B → run B first
    │   └─ A and B are unrelated → order by priority
    │
    ├─ ③ Order by S0~S4
    │
    ├─ ④ Execute one by one + compile-verify
    │   ├─ Pass → continue with the next
    │   ├─ Fail → restore the **newest usable** copy from the three backup sources:
    │   │          · delphi_file __history (auto-backed up on every write; most reliable)
    │   │          · Git commit/stash (if there is a recent commit or stash)
    │   │          · The AI tool's own backup
    │   │          After restoring, fix the problem and re-run
    │   └─ Cause unclear → troubleshoot per the debugging flow (compile.md / debugging rules)
    │
    ├─ ⑤ Full compile confirmation
    │
    └─ ⑥ Final verification (tests pass)
```

### Testing Strategy

- **Tests follow the changes** — verify immediately after each independent change is complete; do not pile up a batch
- **Incremental compile verification** — change A → compile → change B → compile → confirm both A and B pass
- **Full regression run** — once all changes are done, run the full test suite once to confirm there is no regression
- **Regression covers the changed area first** — when full-test resources are limited, cover the changed modules first

### Merging and Splitting Changes

| Scenario | Strategy |
|------|------|
| Two changes touch adjacent lines of the same file | Merge them into one edit, reducing conflict risk |
| One change touches several unrelated modules | Split into independent sub-tasks, verified one by one |
| Two changes are independent and low-risk | May be executed merged, reducing total compiles |
| Two changes are independent but high-risk | Execute separately, verifying only one at a time |

### Change Status Tracking

During one-by-one execution the status of the change list must be maintained:

```
| # | Change description | S-level | Status | Backup method | Notes |
|---|---------|-----|------|---------|------|
| 1 | Fix TForm1 crash | S0 | ✅ Done | git stash | — |
| 2 | Refactor data module | S2 | 🔄 In progress | delphi_file __history | — |
| 3 | Adjust button layout | S4 | ⏳ Pending | — | — |
```

**Status**: ⏳ Pending / 🔄 In progress / ✅ Done / ❌ Failed, rolled back

### Typical Scenarios

#### Scenario A: Fix a bug + add a feature
```
1. Fix the bug (S1/S2) → compile passes
2. Add the feature (S2/S3) → compile passes
3. Full verification
```

#### Scenario B: Change an interface + adapt the callers
```
1. Change the interface definition (S1) → compile fails (expected)
2. Adapt the callers one by one → compile after each adaptation
3. Full compile confirmation
```

#### Scenario C: Refactor + fix a bug
```
1. Fix the bug (no refactoring) → compile passes → confirm the bug is fixed
2. Start refactoring → compile-verify after every step
3. Full verification
```

#### Scenario D: Several independent bug fixes
```
1. Order by impact (fix the largest impact first)
2. Fix them one by one + compile-verify
3. Full compile confirmation
```

#### Scenario E: Cross-module changes
```
1. Confirm the inter-module dependencies
2. Start from the bottom modules (dependencies first)
3. Compile-verify module by module
4. Integration compile confirmation
```

### Forbidden Behaviors

| ❌ Forbidden | Reason |
|---------|------|
| Refactoring while fixing a bug | Cannot tell which step caused the regression |
| Piling up a batch of changes and testing them together | When something breaks, you cannot locate which change caused it |
| Moving to the next change without verifying the interface change | A wrong interface change reworks everything that follows |
| Unordered changes (picking one at random to change) | Raises the rework probability and is not reproducible |

### Related Rule Linkage

- **`planning.md`** — non-trivial changes go through the P0 plan first; enter this rule's ordering once sub-tasks exist
- **Workflow overview** — this rule does not modify any workflow step; it decides only the scheduling order among multiple changes; each change still follows the workflow itself
- **`compile.md` / debugging rules** — when a compile fails and the cause is unclear, troubleshoot per the compile-failure handling flow
- **`delphi_file` backup** — on rollback, take the newest usable version from the three backup sources: `delphi_file __history` (most reliable) > Git commit/stash > the AI tool's own backup