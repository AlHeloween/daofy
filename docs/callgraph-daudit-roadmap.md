# Callgraph Semantic Enhancement Roadmap (based on daudit)

**Plan Status**: Roadmap  
**Plan Date**: 2026-07-04  
**Scope**: `callgraph` / `callgraph_impact` / `callgraph_select_tests` / `callgraph_boundary_check` / `callgraph_refactor_check` / `callgraph_orphan_candidates` / `callgraph_explain_exception`, as well as the subsequent fusion of daudit AST/semantic analysis results into the call graph.  
**Prerequisite**: To be implemented after daudit AST parsing, project-level symbol index, reference tracing and incremental cache are stable.

Related documents:

- `docs/ast-audit-engine-spec.md`: daudit AST, semantic analysis, audit rules and KB integration specification.
- `docs/callgraph-enhancement-plan.md`: current binary direct-call callgraph, use-layer commands and Win64 support records.
- `docs/stacktrace-migration-plan.md`: `StackTrace.pas` runtime diagnostics, MAPDATA, tokenization and callgraph facade migration records.

## 1. Background

The current callgraph can already return forward, reverse, path, impact analysis and use-layer diagnostic results based on MAPDATA and `.text` direct `E8 rel32` scanning in `StackTrace.pas`. This capability is suitable for confirming "direct call edges that actually exist in the compiled artifact", but it cannot fully cover high-level semantics in Delphi source code:

- DFM event binding, Action binding, and runtime event assignment.
- Virtual methods, interface calls, callbacks, anonymous methods, message dispatch, and RTTI/reflection calls.
- Member calls such as `Obj.Save` that require tracing the receiver type.
- Property getter/setter, constructor/destructor, `inherited`, overload/default parameters, and other source-level semantics.

Therefore the subsequent direction is not to expand `StackTrace.pas` into a disassembler, but, after daudit is completed, to use AST/semantic analysis as the primary graph source; the existing binary scanning is retained as the "compile confirmation layer" and runtime diagnostic supplement.

## 2. Goals

1. Establish a multi-source semantic call graph: AST, DFM, MAPDATA/binary, RTTI, runtime observation, and optional LLM assistance are all normalized into the same graph model.
2. Make all call edges carry source, evidence, confidence, and failure semantics, avoiding mistaking candidate edges for definite calls.
3. After daudit stabilizes, upgrade impact analysis, test selection, boundary audit, refactor check, orphan candidates, and exception explanation to the semantic graph.
4. Keep the existing `cmd=callgraph` default behavior compatible; the semantic graph is gradually enabled through explicit `sources` / `mode` or new wrappers.

## 3. Non-goals

1. Do not implement full disassembly, vtable recovery, or interface dispatch recovery in `StackTrace.pas`.
2. Do not claim that all dynamic targets can be precisely resolved when there is no runtime evidence.
3. Do not use an LLM to directly generate a high-confidence call graph; an LLM can only serve as an ambiguity interpreter or candidate ranker.
4. Do not rewrite the current verified binary callgraph path before the daudit AST is stable.

## 4. daudit Dependency Order

| Dependency phase | daudit capability | callgraph content that can advance |
|----------|-------------|----------------------|
| D0 | Single-file AST JSON stable, basic routine/class/interface/record/property/field nodes complete | Define the semantic call graph schema and establish an adapter from AST nodes to callgraph nodes |
| D1 | Scope, uses, type binding, method ownership, and basic overload resolution available | Generate direct procedure/function call, same-class method call, `Self.Xxx`, and `inherited` edges |
| D2 | Project-level index and incremental cache stable, cross-unit references resolvable | Establish a full-project semantic graph cache, supporting stable mapping from file/line to routine |
| D3 | Reference tracing output can distinguish identifier, member access, property access, constructor, and assignment | Support receiver tracing for `Obj.Save`, property getter/setter, and runtime event assignment |
| D4 | DFM parsing or a DFM event binding table available | Merge `OnClick=Handler`, Action/OnExecute, and Form/Frame entry edges |
| D5 | Inheritance chain, interface implementation, and virtual method override relationships stable | Generate virtual/interface candidate edges and narrow the candidate set by static receiver type |
| D6 | Audit rules and reference graph reusable at the MCP layer | Use the semantic graph to drive impact analysis, test selection, boundary audit, and refactor check |

## 5. Graph Model

### 5.1 Nodes

Call graph nodes uniformly represent "executable entries", rather than only binary symbols:

- `routine`: global procedure/function.
- `method`: class/record/interface method.
- `constructor` / `destructor`.
- `property_accessor`: entry after normalizing getter/setter.
- `event_handler`: handler bound by DFM or runtime event.
- `message_handler`: `message WM_*` or message map entry.
- `anonymous_callback`: anonymous method, callback parameters, timer/thread callback and other candidate entries.
- `external_symbol`: RTL/VCL/third-party/system API.

### 5.2 Edges

Each edge contains at least:

| Field | Description |
|------|------|
| `from` / `to` | Normalized node ID, preferably `unit.scope.name(signature)` |
| `edge_kind` | `direct_call`, `method_call`, `property_access`, `constructor_call`, `event_binding`, `runtime_event_assignment`, `virtual_candidate`, `interface_candidate`, `callback_candidate`, `message_dispatch`, `reflection_candidate`, `binary_confirmed`, `runtime_observed` |
| `sources` | `ast`, `dfm`, `binary`, `mapdata`, `rtti`, `runtime_stack`, `runtime_trace`, `llm` |
| `confidence` | `exact`, `high`, `medium`, `low`, `candidate` |
| `evidence` | File, line, column, AST node id, DFM object/property, callsite address, runtime frame, etc. |
| `resolution` | Receiver type, overload selection, inheritance chain, interface implementation candidates, unresolved reason |
| `warnings` | `ambiguous_receiver`, `dynamic_dispatch`, `missing_dfm`, `missing_unit`, `binary_not_confirmed`, `llm_only`, etc. |

High-confidence edges must have reviewable evidence. Edges without evidence can only enter the candidate set and cannot affect conclusions such as "safe to refactor".

## 6. Multi-source Fusion Strategy

| Source | Purpose | Confidence rules |
|------|------|------------|
| daudit AST | Primary graph source, parses source calls, types, scopes, references | direct call uniquely resolved to `exact/high`; unclear receiver is `candidate` |
| DFM | UI entries, design-time events, Action bindings | handler exists and signature matches is `exact/high`; missing source is `medium` and records warning |
| MAPDATA/binary | Compile confirmation, third-party/DCU, exception address mapping | when matched with an AST edge promoted to `binary_confirmed`; standalone direct call found is `medium/high` |
| RTTI | Published methods, type lists, partial method address assistance | used to narrow candidates, does not alone mark virtual calls as exact |
| runtime stack/trace | Exception stack, real paths observed during test runs | observed edge is `runtime_observed`, can raise confidence of related candidates |
| LLM | Ambiguity explanation, candidate ranking, source code semantic supplementation | advisory only; without AST/DFM/runtime evidence must not enter high/exact |

Conflict handling:

1. AST exact + binary confirmed: definite edge.
2. AST exact but binary not confirmed: keep as a source edge, mark `binary_not_confirmed`, possibly caused by inline, optimization, an uncompiled path, or a missing map.
3. binary direct call with no AST edge: keep as a compiled edge, mark `source_unresolved`, for third-party/DCU/compiler-generated code.
4. DFM handler with no AST routine: keep the entry node, mark `handler_not_found`, for project repair or path checking.
5. Multiple-candidate dynamic edges: keep all as candidates; path queries can by default be configured whether to include them.

## 7. Implementation Milestones

### R0 - Schema and Compatibility Layer

Goal: first settle the graph model without changing current callgraph default behavior.

Tasks:

- Define the semantic graph JSON schema and edge confidence rules.
- Add an adapter to the current binary callgraph, mapping direct-call edges to the new schema.
- Add `sources` / `confidence_min` / `include_candidates` parameter design at the Python layer, but keep the old behavior by default.
- Add schema golden tests to ensure old responses and new semantic responses can coexist.

Acceptance:

- Existing `callgraph`, `callgraph_path`, and `callgraph_impact` tests do not regress.
- In the new schema, every edge has `sources`, `confidence`, and `evidence`.

### R1 - AST Static Call Graph

Goal: use the daudit AST project index as the main source to generate a source-level direct graph.

Tasks:

- Build the node table from daudit routine/entity/ref output.
- Parse global function calls, same-unit method calls, `Self.Xxx`, `ClassName.Xxx`, constructor/destructor, and `inherited`.
- Support basic overload selection; when unable to select uniquely, output candidates and the reason.
- For file/line input, prioritize locating by daudit routine range, no longer relying only on map line numbers.

Acceptance:

- fixture covers global call, method call, constructor, destructor, overload, inherited.
- For the same fixture, the AST graph and binary direct-call graph can cross-confirm.

### R2 - DFM / Action / Event Entries

Goal: add UI entries to the graph, solving the problem that current pure binary scanning cannot know entry sources.

Tasks:

- Parse `OnXxx = Handler` in `.dfm` / `.fmx`.
- Parse common entry bindings such as `TAction.OnExecute`, ActionList, menus, and toolbars.
- Identify runtime event assignments from AST: `Obj.OnXxx := Handler`.
- Build event bindings as `event_binding` or `runtime_event_assignment` edges.

Acceptance:

- QLangEditor design-time event entry coverage reaches 95% or above.
- When a DFM handler is missing, output a structured warning and do not silently drop the edge.

### R3 - Receiver Type Tracing

Goal: improve the resolvable ratio for member calls such as `Obj.Save`.

Tasks:

- Trace the declaration types of local variables, parameters, fields, `Self`, and `Result`.
- Identify simple construction assignments: `Obj := TProject.Create`, factory return type, `as` type conversion.
- When handling `with`, property chains, generic containers, and default properties, output candidates and uncertainty reasons.
- Establish explicit edges for property getter/setter.

Acceptance:

- fixture covers locals/params/fields/Self/Result/constructor/factory/property.
- QLangEditor business call chain high-confidence coverage reaches 85% or above.

### R4 - Dynamic Dispatch Candidates

Goal: provide "explainable candidates" for virtual methods, interfaces, callbacks, messages, and reflection, without false reporting them as definite edges.

Tasks:

- Generate `virtual_candidate` based on inheritance chain and override table.
- Generate `interface_candidate` based on interface implementation table.
- Identify common patterns of callback parameters, anonymous methods, thread/timer/message handlers.
- Identify `message WM_*` dispatch entries.
- Generate `reflection_candidate` for RTTI/published methods and reflection paths such as `MethodAddress`.

Acceptance:

- Every dynamic candidate must carry the candidate set, source, confidence, and reason for not being precisely resolved.
- When `refactor_check` encounters dynamic candidates, it cannot give a "safe" conclusion, only downgrade to manual confirmation.

### R5 - Fusion and Confidence Engine

Goal: combine AST, DFM, binary, RTTI, and runtime into a unified graph and provide stable filtering for the use layer.

Tasks:

- Implement edge merge: merge multi-source evidence for the same from/to/kind.
- Implement `confidence_min`, `include_candidates`, `source_filter`.
- `callgraph_path` supports finding paths by confidence, excluding low-confidence candidates by default.
- `callgraph_diff` compares by stable node ID by default, with address changes only as additional evidence changes.

Acceptance:

- High-confidence paths do not contain LLM edges without evidence or low-confidence dynamic candidates.
- diff does not produce large noise due to recompilation address changes.

### R6 - Use-layer Upgrade

Goal: let existing U1-U8 commands consume the semantic graph rather than only the direct-call graph.

Tasks:

- `callgraph_impact`: prioritize AST file/line location and semantic callers.
- `callgraph_select_tests`: introduce DFM/UI entries, Action entries, and candidate path explanations.
- `callgraph_boundary_check`: upgrade from prefix rules to unit/class/category/namespace rules.
- `callgraph_refactor_check`: output exact/high/candidate layered risks.
- `callgraph_orphan_candidates`: include DFM, runtime event, RTTI, and dynamic candidates, reducing false positives.
- `callgraph_explain_exception`: use exception stack addresses to reconnect to the semantic graph, distinguishing real runtime paths and static reachable paths.

Acceptance:

- Every use command has tests for "only look at high-confidence" and "include candidates".
- An incomplete graph can only output risks and pending confirmation items; it cannot output absolute safety conclusions.

### R7 - QLangEditor Validation Baseline

Goal: use `C:\user\qlang\editor` as a real project baseline to verify the actual value of the semantic graph.

Baseline goals:

- UI/DFM entry coverage: >= 95%.
- Project business call chain high-confidence coverage: >= 85%.
- high-confidence + candidate coverage: >= 90%.
- All unresolved items must have cause classification.
- Semantic graph construction and incremental refresh time must be recordable, avoiding uncontrollable overhead during black-box testing.

Key use cases:

- `actNewProjectExecute` downstream path.
- `SaveIfModified` upstream callers and dirty-close/save related script selection.
- Business call chains of `actSmartTranslateExecute`, `actTranslateCurrentExecute`.
- Runtime event assignments related to `SourceResEditor`.
- Mapping from Action/menu/toolbar entries to handlers.

### R8 - Incremental Cache and CI Integration

Goal: make the semantic graph usable long-term for audit and regression, without requiring full parsing every time.

Tasks:

- graph cache layered by file hash, daudit version, MAPDATA id, compiler target.
- Support incremental refresh from changed file -> affected graph partition.
- Output a semantic graph snapshot in CI, supporting PR diff.
- Degrade graph construction failure to a structured diagnostic, without blocking the basic compile/automation flow.

Acceptance:

- After modifying a single `.pas`, only refresh the related unit and dependency edges.
- snapshot can be used for `callgraph_diff`, and path safety follows `snapshots_dir` constraints.

## 8. Test Matrix

| Layer | Test content |
|------|----------|
| daudit fixture | AST JSON golden, routine range, refs, types, inheritance, interface impl |
| graph builder | node normalization, edge merge, confidence calculation, unresolved classification |
| DFM fixture | OnClick, OnExecute, ActionList, Frame, missing handler |
| type tracing fixture | locals, params, fields, Self, Result, constructor, factory, property |
| dynamic fixture | virtual/interface/callback/anonymous/message/reflection candidate |
| binary confirmation | merge AST edges with MAPDATA/binary direct-call edges |
| Python protocol | parameter validation, old behavior compatibility, new schema response, error degradation |
| QLangEditor smoke | Win32/Win64 Debug, key entries and business link coverage |

## 9. Risks and Constraints

| Risk | Handling strategy |
|------|----------|
| daudit AST output is not yet stable | R0 only does schema and adapter; R1 onward depends on daudit golden tests |
| Dynamic dispatch misjudgment | Default to candidate, do not enter high-confidence paths; the use layer must display risk |
| DFM and source out of sync | A missing DFM handler or signature mismatch must output a warning |
| `with` / overload / generics causing ambiguity | Output candidates and unresolved reason; do not guess a unique target |
| LLM results are not reproducible | Only for explanation and candidate ranking; do not write into the high-confidence graph |
| Large project performance | Project-level cache, incremental refresh, edge limit, filtering by source/confidence |
| Compatibility with the current callgraph | Keep binary direct-call behavior by default; semantic graph explicitly enabled |

## 10. Definition of Done

After subsequent daudit completion, this roadmap is complete only when all of the following are satisfied:

1. `callgraph` can return the unified schema in explicit semantic mode, and the old mode remains compatible.
2. AST, DFM, binary, and runtime sources can fuse into the same node/edge model.
3. All edges have evidence, confidence, and source; high-confidence edges have no unsupported items.
4. Dynamic dispatch, callbacks, and reflection are only output as candidates unless confirmed by runtime evidence.
5. U1-U8 use-layer commands can work by confidence and can explain unresolved.
6. QLangEditor validation reaches the R7 coverage goals, and Win32/Win64 smoke results are recorded.
7. Full Python tests and related Delphi fixture compile/run tests pass.

## 11. Suggested Execution Order

1. After daudit D0-D2 are stable, implement R0-R1 first, ensuring the schema, node ID, and AST direct graph are usable.
2. After daudit D4 is available, implement R2, prioritizing UI/DFM entries, because this benefits black-box automation and test selection the most.
3. After daudit D3/D5 are stable, implement R3-R4, gradually improving member call and dynamic candidate coverage.
4. After completing R5, upgrade U1-U8, avoiding inconsistent confidence logic implemented separately in each use layer.
5. Finally use QLangEditor and fixture projects for R7/R8 closure, stabilizing performance, cache, CI snapshot, and diff reports.