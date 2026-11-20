<!-- @when: Consecutive attempts fail or a problem cannot be solved independently -->
<!-- @chain: before=six-step-method.md -->

### 8.1 Human Intervention Trigger Conditions

When any condition is met, you **must proactively stop trying and request human intervention**:

| Priority | Condition | Example |
|--------|------|------|
| 🔴 P0 | 3+ consecutive fix attempts all fail | Compile error unresolved after 3 attempts |
| 🔴 P0 | The error cause points to closed-source code/environment the AI cannot access | Third-party closed-source DLL crash |
| 🔴 P1 | Design decision requiring human confirmation | Architecture change, API compatibility trade-off |
| 🟡 P2 | Error information incomplete, root cause cannot be determined | AV with no call stack |
| 🟡 P2 | Need access to external restricted resources | Corporate internal Git, VPN |
| 🟡 P2 | 2+ feasible solutions, unsure which is better | Multiple equivalent fix paths |
| 🟡 P2 | Two consecutive essentially identical solutions | Only changing parameters/order and trying again |
| 🟡 P2 | Forcing guesses when information is insufficient | Error has no path, AI guesses a path to try |
| 🟡 P2 | Same tool fails twice in a row | Still calling same tool without changing approach |
| 🟢 P3 | Problem is simple but environment does not match | User's local registry/DLL differences |

> **Exception**: AI coding errors (obvious bugs/missing references) are not in scope for intervention; keep fixing.

**Supplementary details**:
- **Ambiguity in solution choice**: Do not default to choosing one. List options and rationale within 1 round and request a human choice
- **Do not guess when information is insufficient**: First try to complete the information; if still insufficient, ask the user; after 2 consecutive wrong guesses → intervene
- **Change direction after consecutive same-tool failures**: If the same tool fails twice in a row, first check whether the wrong tool is being used, then change direction
- **Verify abnormal results**: When success is reported but the result is clearly unreasonable, cross-validate

**Priority interaction**:
- P2 (same tool twice) triggers first → change direction → if it still fails for 3+ total → enter P0
- P2 (insufficient information) after 2 wrong guesses → enter P0
- P2 resolved after changing direction → no need to reach P0


