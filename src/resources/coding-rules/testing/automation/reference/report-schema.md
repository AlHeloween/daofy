<!-- @when: When analyzing the test report returned by automate_delphi -->
<!-- @chain: after=script-schema.md, before=repair-loop.md -->

# Automated Test Report Structure

The `report` structure returned by `automate_delphi(action="gui", ...)` is sufficient to drive the repair loop.

MCP resource URI: `delphi://automation/report-schema`.

## Important Fields

```json
{
  "status": "partial",
  "requested_action": "auto",
  "resolved_action": "gui",
  "detected_subsystem": 2,
  "report": {
    "total": 3,
    "passed": 1,
    "failed": 1,
    "skipped": 1,
    "executed": 2,
    "duration_seconds": 6.21,
    "success_rate": "33%",
    "executed_success_rate": "50%",
    "first_failure": {
      "index": 1,
      "phase": "verify",
      "cmd": "rget",
      "target": "BtnSave.Caption",
      "signal": "assertion_failed",
      "expected": "Save button caption is correct",
      "diagnostics": {
        "callgraph": {
          "target": "main.TfrmMain.SaveIfModified",
          "direction": "callers",
          "status": "ok",
          "edge_count": 1,
          "returned_count": 1,
          "truncated": false
        }
      },
      "assertion": {
        "expression": "actual == 'Save'",
        "source": "assert_expr",
        "actual": "Cancel",
        "message": "assert failed: actual == 'Save'  (actual='Cancel')"
      },
      "recommendations": []
    },
    "solution": {
      "status": "requires_fix",
      "next_mode": "coding",
      "summary": "Fix the first deterministic failure, then rerun this script from the failed step.",
      "recommendations": []
    },
    "steps": [
      {"index": 0, "cmd": "goto", "status": "pass"},
      {"index": 1, "cmd": "rget", "status": "fail"},
      {"index": 2, "cmd": "click", "status": "skip"}
    ]
  }
}
```

## RTTI Test Task Results

`automate_delphi(action="test", ...)` first returns `status="submitted"` and `task_id`. The task result obtained through
`async_task(action="result")` does not use the GUI `report` wrapper; its stable fields are as follows:

```json
{
  "status": "failed",
  "total": 4,
  "passed": 1,
  "failed": 2,
  "errors": 1,
  "duration_seconds": 0.475,
  "process_reused": false,
  "results": [
    {
      "index": 0,
      "id": "invalid-input",
      "className": "Tests.TCalculator",
      "method": "Parse",
      "status": "ok",
      "phase": "test",
      "exception_class": "EConvertError",
      "exception_message": "invalid value",
      "assert": "pass"
    }
  ],
  "raw_responses": []
}
```

- `passed`: The method completed and all Delphi/Python assertions passed.
- `failed`: The return value, `assert_expr`, or expected-exception assertion failed.
- `errors`: Startup, transport, setup/construction, unexpected test exception, or teardown failure.
- `phase`: The phase where the error occurred; one of `prepare`, `setup`, `constructor`, `test`, or `teardown`.
- `raw_responses`: Per-case original Delphi protocol responses, for diagnostics only; should not replace the stable statistics fields.

## Failure Signals

| Signal | Response Strategy |
|------|---------|
| `assertion_failed` | Compare the expected behavior derived from source code with the actual UI state |
| `capture_failed` | Check window visibility and the screenshot directory |
| `timeout` | Capture the current UI, check `msgscan/formsum`, and avoid blind retries |
| `target_not_found` | Run `formsum/dumpstate`, update the target name, or fix the missing control |
| `property_not_found` | Run `rinspect` and update the property path |
| `command_error` | Check `response_data`, capture the state, then decide whether to fix the code or the script |
| `skipped` | A preceding step failed; rerun after fixing the first failure |

## Report Output Specification

When presenting results, include:

- The executed app path and `resolved_action`.
- Total passed/failed counts and elapsed time.
- The number of `skipped` (when `stop_on_failure=true` prevented dependent steps).
- The first failure: `cmd`, `target`, `signal`, actual value, evidence.
- If the script enabled `callgraph_diagnostics`: list `diagnostics.callgraph.target`, `direction`, `status`, `edge_count`, `truncated`. A callgraph query failure can only be a warning/secondary diagnostic and must not override the original failure cause.
- Fix plan: adjust the automation script or fix the code.
- The exact next command: rerun the script, compile the project, or switch to the coding rules.