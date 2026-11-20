<!-- @when: When AI generates or reviews test cases, check against the quality checklist item by item -->
<!-- @part-of: ui-testing -->

## Appendix: Black-Box Test Authoring Checklist

When AI generates or reviews test cases, check each item in the following checklist one by one:

### Metadata Checklist

| # | Check item | Pass criteria | Check method |
|---|--------|---------|---------|
| 1 | `test_level` correct | Pure black-box (only UI entry points) → `"black-box"`; uses RTTI commands → `"gray-box"` | Check that the command set conforms to the black-box boundary |
| 2 | `goal` describes specifics | State "what operation is tested and what result is verified" | Read the goal field; it should have a clear bidirectional description |
| 3 | `app_path` and `fixture_project` exist | Paths point to executable and prerequisite data project | Check path existence |
| 4 | `source_files` lists the source code under test | List the main pas files involved in this test | Check whether the listed files cover the tested paths |
| 5 | `version` increments | version+1 after each modification | Compare with previous version |

### Structure Checklist

| # | Check item | Pass criteria | Check method |
|---|--------|---------|---------|
| 6 | Step count reasonable | Smoke test 5-15 steps, functional test 15-60 steps | Count steps |
| 7 | Every step has `expected` | 100% of steps have human-readable expected descriptions | grep expected coverage |
| 8 | Key steps have `assert_expr` | Steps that verify state/values must assert | Check assertions after rget/msgscan/capture |
| 9 | Every step has `phase` | Use perceive/execute/verify/wait/rebuild | Check phase field completeness |
| 10 | Time interval after operations | `wait`/`waitfor` after async commands | Check no consecutive async commands without interval |

### Content Checklist (Based on A-O Standards)

| # | Check item | Corresponding scenario | Pass criteria |
|---|--------|---------|---------|
| 11 | Coordinate targeting does not use bare `@x,y` | M1 | Prefer control name/`@text`; must not use only `@x,y` without accompanying calibration |
| 12 | Calibration script exists | M2 | The test suite must have 00-calibration (verify goto + rget + ClientWidth) |
| 13 | Fixed delay changed to conditional wait | N1 | No `{"cmd":"wait","ms":>1000}`; a few very short delays need comments |
| 14 | `goto` wait after control rebuild | O1 | After rescan/reload/switch operations, must use `goto TfrmMain` instead of direct rget |
| 15 | Rebuild steps marked `phase: rebuild` | O2 | Wait/verification steps after rebuild are marked rebuild |
| 16 | File dialog has `uia.xxx` fallback | J0 | Steps involving Open/Save fallback use uia.goto/uia.click as fallback |
| 17 | `msgscan` assertion content is specific | G | `msgscan`'s `assert_expr` must verify text content, not just `actual != 'NOD'` |
| 18 | Every screenshot has corresponding OCR/diff detection | K7 | After capture, Python side performs recognize/detect/diff/color analysis |
| 19 | Verify dirty state after operation | C/F/G | After data change operations, verify `actSaveProject.Enabled` or `Project.Modified` |
| 20 | Variants under different DPI | M3/K4 | Cross-DPI tests use `coord_scale` factor to dynamically calculate coordinates |
| 21 | Boundary scenarios covered | All | Functional cases cover at least the applicable items among normal path, failure/cancel path, key input boundaries, and environment boundaries; for inapplicable items, state the reason in `note` |

### Quality Gates

| # | Check item | Veto |
|---|--------|---------|
| 22 | Functional case has no boundary scenario description | ❌ Veto (except pure startup smoke cases) |
| 23 | `wait ms` exceeds 3000ms without explanation | ❌ Veto |
| 24 | Proportion of steps missing `phase` field >20% | ❌ Veto |
| 25 | No `goto` rebuild wait after rebuild operation | ❌ Veto |
| 26 | `@x,y` coordinates not calibrated in calibration script | ❌ Veto |
| 27 | Test case has no `assert_expr` verification step | ❌ Veto (except pure recording smoke cases) |

### Test Authenticity Gates (Anti-False-Pass)

> The following 6 items are **veto** items. If any one is violated, the test case is unqualified and must be revised and resubmitted.

| # | Check item | Pass criteria | Check method | Veto |
|---|--------|---------|---------|------|
| T1 | No skip-style passing | Must not mix in `Assert(True)` / `assert True` / `assert 1==1` as the only assertion and mark it as passed; when Runtime/component is unavailable, must **explicitly skip and explain the reason**, and must not silently degrade | grep assert content + check execution time | ❌ |
| T2 | Reasonable execution time | Smoke test ≥3 seconds; functional test average per step ≥0.5 seconds; 100 loop operations ≥30 seconds. If below threshold, provide a performance explanation in `note` | Compare step count with total time | ❌ |
| T3 | Assertions verify specific state | `assert_expr` must verify **specific values** (`len(actual)>0`, `actual=='True'`, `FileExists(actual)`, etc.); `assert_expr:"true"` / `assert_expr:"1=1"` / omitting assertions is prohibited | grep assert_expr content | ❌ |
| T4 | Screenshots must have subsequent verification | After `capture`, there must be `recognize`/`detect`/`diff`/`match` or `rget` to verify screenshot content; must not only save without checking | Whether there is a verification command within 3 steps after capture | ❌ |
| T5 | External dependency failure handling | When depending on external components (WebView2/Runtime/COM/DLL), if the component is unavailable, must **explicitly report an error or mark skip**; must not silently do nothing | Check whether there is precondition detection + degradation path | ❌ |
| T6 | Loop operations have intermediate assertions | When looping N operations, assert at least every N/10 iterations or at the first/last/middle, and do not assert only the beginning and end | Check assert distribution in loop steps | ❌ |

**Usage**: AI generates test cases → go through the checklist item by item → mark failed items → revise before resubmitting.