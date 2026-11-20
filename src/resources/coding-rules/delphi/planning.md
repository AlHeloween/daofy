<!-- @when: Before new features, public interface changes, large-scale modifications, cross-module fixes, package/project structure adjustments, data format/cache/rendering/performance path refactoring, complete requirements clarification and solution review first -->
<!-- @chain: after=index.md, before=workflow.md -->

## P0 Upfront Planning and Review

Before coding new features or making large-scale modifications, you must complete P0 planning and review. **Modifications that skip this step and go straight to coding will most likely need rework.**

The goal of P0 is not to write beautiful documentation, but to make the solution executable, verifiable, and rollback-capable. Content not yet confirmed in the plan must be marked as "To be confirmed" and must not be disguised as decided.

### P0.0 Trigger Conditions

The following situations must enter P0 first and must not go directly to coding:

| Trigger | Description |
|--------|------|
| New feature/large-scale modification | Adds user-visible capabilities, refactors core processes, modifies across multiple modules |
| Public interface changes | Changes to types, function signatures, events, configuration items, protocols, DFM/serialization formats |
| Package/project structure adjustments | Changes to dpr/dproj/dpk/groupproj, design-time/runtime packages, dependency chains, or installation methods |
| Data format/cache policy changes | Changes to persistence formats, cache keys, cache eviction, compatible migration, index semantics |
| Rendering/performance path refactoring | Changes to drawing backends, asynchronous flows, batching, performance-critical paths, resource lifecycles |
| Cross-module bug fixes | The fix point affects callers, callees, tests, documentation, or user workflows |
| Automated testing | When automated UI/interface test scenarios need to be written for features, or test infrastructure needs to be added/modified (inline-unit, script caching, fix loop) |

Cases where P0 can be skipped: pure comments, spelling, small local fixes with no behavior change. If unsure, treat as requiring P0.

#### Definition of Non-trivial Plan

A "non-trivial plan" means a plan that hits any trigger condition in P0.0, or a plan for which it cannot be confirmed whether it hits P0.0. When a trigger condition is hit, P0 must be followed; when P0.0 is not hit and it is confirmed to be only a pure comment, spelling, or small local fix with no behavior change, it can be considered a trivial change and P0 can be skipped.

If a change obviously needs a plan but does not hit P0.0, it means the P0.0 trigger conditions have omissions; you should first supplement the trigger conditions, and then handle it as a non-trivial plan.

### P0.S Plan Status

Plan documents must explicitly mark their status:

| Status | Meaning |
|------|------|
| Draft | First draft, cannot be implemented |
| Audit feedback draft | Audited but has blockers or items to be confirmed, cannot be implemented |
| Implementable draft | Passed P0.4, can enter the coding workflow |
| In progress | Coding has started according to the plan, and status and checklist items must be synchronized |
| Verified | Implementation, testing, documentation synchronization, and cleanup are complete |

Status can only be updated based on actual audit results. When there are unresolved technical routes, unconfirmed dependencies, or unknown compatibility impacts, it must not be marked as "Implementable draft".

### P0.1 Requirements Clarification

Understand explicit requirements and identify implicit requirements:

| Checklist item | Description |
|--------|------|
| 📋 Explicit requirements | What the user explicitly says they want to do |
| 🔍 Implicit requirements | Constraints the user does not mention but that are implied (compatibility, performance, security, error handling) |
| 🔲 Boundary scope | What this feature will not do? Explicit exclusions |
| 📐 Inputs/outputs | Input data, output artifacts, side effects of the feature |
| ❓ Assumptions/to be confirmed | Unverified assumptions, questions that need user confirmation, prerequisites of external dependencies |
| ⚡ Performance requirements | Performance budget: expected latency (p50/p95/p99), throughput (QPS), upper limit of memory increment, startup time increment, upper limit of resource consumption |
| 🎯 Performance scenarios | Typical/extreme performance scenarios to be verified: data volume, concurrency, operation frequency, duration |
| 🔒 Security requirements | Data sensitivity level, authentication/authorization model, input validation rules, transport/storage encryption requirements, audit log requirements |
| 📊 Observability requirements | Runtime health metrics, key-path duration statistics, error/exception diagnosability requirements, log level and sampling strategy |
| 📖 Documentation requirements | Do user-visible behavior changes require updates to help documentation/changelog/release notes? Is a migration guide needed? |

**Output**: A requirements list (1-2 sentences per item), used as the verification basis for all subsequent steps. Items to be confirmed must be listed separately and must not be mixed into "decided".

### P0.2 Impact Analysis

Identify the modules that need to be modified to implement this requirement, **with special attention to chain reactions of the modification**:

| Analysis item | Description |
|--------|------|
| 📁 Files to modify | Specific file paths and approximate modification points (new functions/modified logic/changed interfaces) |
| 🔗 Dependency chain | Impact scope of callees/callers/data flow (direct relationships) |
| 💥 Chain reactions | **Cascading impacts** caused by interface signature changes, behavior semantics changes, data format/protocol changes. <br>Example: change a function signature → all callers need synchronous modification → callers of callers cascade and break; <br>change return value format → parsing logic of all consumers becomes invalid; <br>change configuration key name → all readers report errors |
| ⚠️ Risk points | Unfamiliar APIs, changes that may break existing behavior |
| ⚡ Performance impact | Hot paths involved in the change, changes in resource consumption (CPU/memory/IO/network), changes in GC/allocation frequency, bottleneck prediction under high load |
| 🔒 Security impact | Data plane/permission plane involved in the change, external input entry points, network communication paths, sensitive data storage/transport paths |
| 📖 Documentation impact | Are there user-visible changes to user operation flows, configuration items, UI copy, or API behavior? Do release notes or migration guides need to be updated? |
| 📋 Test impact | Do existing tests need to be updated? Do new tests need to be added? |
| 🧾 Dirty state/IDE state | Are there uncommitted changes, IDE-open buffers, DFM/designer risks, or user changes that need protection? |

**Output**: An impact scope table (file list + risk marks + chain reaction chain), as the basis for solution design.

#### P0.2.1 Source Verification

A non-trivial plan must be based on real source code, not just memory or speculation. At minimum verify:

- Real types, functions, events, properties, enums, package dependencies, and call sites.
- Real test projects, demos, documentation, and build entry points.
- License, version, platform, and deployment requirements of external libraries or third-party code.
- When Delphi source/DFM/project files are involved, prefer Daofy's Delphi-specific tools (such as `delphi_file` / `delphi_project`); do not bypass dirty-marking, backup, and formatting protection.

**Output**: A list of source-backed evidence, stating file paths, symbol names, or line number anchors. A plan without source verification can only be a draft.

### P0.3 Solution Design

Based on the requirements list and impact scope, design the technical solution:

| Design item | Description |
|--------|------|
| 🏗 Overall approach | A one-sentence summary of the solution |
| 🔧 Technology selection | Which APIs/design patterns/tools to use, with reasons; no either-or choices that affect implementation may remain |
| ⚡ Performance design | Algorithm complexity analysis of key paths, cache/resource pool reuse strategy, async/batch design, lazy loading/preloading trade-offs, memory allocation planning and object lifecycle management |
| 📊 Observability | Whether new performance instrumentation, duration statistics, counters, memory snapshots, or debug logs are needed; exception detection and alerting methods |
| 🔒 Security design | Input validation and sanitization scheme, permission check point design, encryption strategy (transport/storage), anti-injection/anti-tampering measures, audit log strategy |
| 📖 Documentation plan | List of documents to update (help documentation, changelog, release notes, migration guide), with owner and delivery time for each |
| 🧹 Technical debt tracking | Known workarounds/hacks/TODOs in the solution, marked as technical debt items; estimated repayment effort; whether there is already a repayment plan or schedule |
| 🧪 Test strategy | Test level allocation (unit/integration/E2E/manual), test case ideas for key scenarios, automation coverage targets, regression verification scope; <br>if automated testing is involved, first refer to `get_coding_rules(section="automation")` (`resources/coding-rules/testing/automation/`) for methodology, scenario templates, and command reference |
| 📐 Interfaces/data structures | New types, function signatures, data structure definitions; explain compatibility and migration methods |
| 🧩 Subtask breakdown | Break implementation into subtasks that can be executed and verified independently |
| 🔄 Interaction with existing code | How to connect to existing modules? Interface-compatible or breaking change? |
| ✅ Acceptance criteria | Completion criteria, verification commands, manual verification items, and pass conditions for each stage |
| ↩️ Rollback/migration | How to roll back on failure? How to migrate breaking changes? Are compatibility shims needed? |

**Output**: A design solution (including subtask list, acceptance criteria, and rollback/migration plan), reviewable by P0.4.

### P0.4 Solution Self-review

Self-review the P0.3 solution; after finding risks, **modify the solution first and do not rush to code**:

| # | Review item | Description |
|---|--------|------|
| 1 | 🔴 Requirements coverage | Does the solution cover all explicit + implicit requirements in P0.1? Any omissions? |
| 2 | 🔴 Source verification | Is the solution based on real source code, real call chains, real package/project files, and real test entry points? |
| 3 | 🔴 Existing pattern matching | Does the solution conform to the codebase's existing design patterns and naming conventions? |
| 4 | 🔴 Chain reactions | Will the modification cause cascading breakage through interface signatures, behavior semantics, or data formats? <br>Has the complete propagation chain (A→B→C) been traced? Are there compatibility shims or a phased migration plan? |
| 5 | 🟡 Risk controllable | Do the risk points marked in P0.2 already have countermeasures? |
| 6 | 🟡 Interface compatibility | Will the new interface break existing callers? Is there a smooth transition plan? |
| 7 | 🟡 Boundary handling | Have boundary scenarios such as null values/exceptions/concurrency/timeouts/resource release/permissions/missing dependencies been considered? |
| 8 | 🟡 Security compliance | Does the solution meet the security requirements defined in P0.1? Are there risks of injection, privilege escalation, or data leakage? <br>Is sensitive data protected by encryption during transport/storage? Are there sufficient audit logs for traceability? |
| 9 | 🟡 Performance meets target | Does the solution meet the performance budget defined in P0.1? Is there algorithm complexity degradation on key paths (e.g., O(n)→O(n²))? <br>Are there uncontrolled memory allocations, unnecessary IO, or repeated calculations? Are there countermeasures under high load? |
| 10 | 🟡 Observability complete | Are there duration statistics/instrumentation on key paths? Do exceptions have clear error context for diagnosis? <br>Are log levels reasonable? Can operations quickly locate problems after launch? |
| 11 | 🟡 Documentation synchronized | Are there corresponding documentation updates for user-visible changes? Are release notes/migration guides/changelogs in place? |
| 12 | 🟢 Test complete | Does the test strategy cover key scenarios? Are there clear automation test targets and regression verification paths? |
| 13 | 🟢 Technical debt controllable | Does the solution introduce acceptable debt? Do new workarounds/hacks have TODO markers and repayment plans? <br>Has it avoided long-term unmaintainable architectural compromises for short-term speed? |
| 14 | 🟢 Subtasks reasonable | Is the subtask breakdown granular enough to be independently executed, verified, and rolled back? |

#### P0.4.1 Hard Failure Conditions

If any of the following occurs, the review conclusion must be "Fail", and return to P0.3 to revise:

- No specific file paths, symbols, or call chains; only concepts are described.
- The technical route still has either-or choices or items to be confirmed that affect implementation.
- The semantics of fallback, error handling, resource lifecycle, cache invalidation, or compatible migration are undefined.
- Public interfaces, data formats, package dependencies, or persistence formats will change, but there is no migration/compatibility/rollback plan.
- The acceptance criteria and verification commands/methods for each stage are not defined.
- Third-party libraries, licenses, platforms, or deployment are involved, but there is no review conclusion.
- User changes, Daofy tool dirty-marking/backup boundaries, or DFM/designer state would be overwritten, but there is no protection plan.
- Tests can only rely on "it should look fine"; there is no executable verification path.
- Performance-critical paths are involved but no performance budget is defined (at least latency or resource consumption upper limits), and the solution cannot prove there will be no regression.
- Security-sensitive changes involving user data, permission models, network communication, or external input are involved, but there is no security design or security review conclusion.
- User-visible interfaces/behavior/configuration change, but there is no corresponding documentation update plan or release notes.

**Review conclusion**:
- ✅ **Pass** → Mark the plan as "Implementable draft" and enter P0.P
- ❌ **Fail** → Mark the plan as "Audit feedback draft", return to P0.3 to revise the solution, and review again

### P0.P Pass → Enter ① Execution

After the solution passes, execute according to the standard coding workflow:

```
get_coding_rules(section="workflow")    # Enter ① Environment check
```

Before entering coding, confirm again: the plan status is "Implementable draft", the current workspace/IDE state has been checked, and there are no unresolved items to be confirmed.

### P0.R Fail → Return to P0.3

When the solution fails, **do not code directly**. Revise the solution according to the problems pointed out in the review, then return to P0.4 for review. Repeat this loop until the solution passes.

> **Experience**: Spending 5 minutes thinking at the solution stage usually saves 30 minutes of rework after coding. Design defects found in the P0 stage cost 1/10 of post-coding fixes.

