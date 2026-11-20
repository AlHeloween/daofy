<!-- @when: an automated test failed and its cause must be analysed, repaired and retried -->
<!-- @chain: after=report-schema.md -->

# Failure Repair Loop

Run this procedure when `report.first_failure` is not null.

MCP resource URI: `delphi://automation/repair-loop`.

## Steps

1. Stop the automated steps that depend on it.
2. Classify the failure type from `report.first_failure.signal`.
3. Gather additional evidence:
   - Target/control problem → `formsum`/`dumpstate`
   - Unexpected dialog → `msgscan`
   - Visual evidence → `capture`
   - Property/method mismatch → `rinspect`
4. Decide whether the problem lies in the script or in the product code.
5. Script problem → update the cached script and rerun.
6. Code problem → switch to coding mode, edit the Delphi file with `delphi_file`, compile with `delphi_project`, then rerun the automation.
7. Store the stabilised incident-recovery knowledge in `experience`.

## Script vs. Code Decision

| Verdict | Typical scenario |
|------|---------|
| **Script problem** | A control was renamed but behaves correctly; the `assert_expr` expected value is wrong; the timeout is too short (the evidence shows the application is still making progress) |
| **Code problem** | The behaviour the source intends does not happen; a required control is never created; a UI property holds the wrong value after the correct event fires; valid input raises an error dialog |

## Final Output Format

```markdown
**Automation Test Result**
Passed: N/M, elapsed Xs
Execution mode: gui|console

**First Failure**
Step #, command, target, signal, actual value, expected value

**Solution**
Script fix or code fix, with specific files/steps.

**Verification**
Compile result and rerun result.
```