<!-- @when: When you need to execute parameterized tests on white-box/gray-box Delphi methods, or replace DUnitX's execution and reporting capabilities -->
<!-- @chain: after=workflow.md, before=report-schema.md -->

# RTTI Unit Test Runner

MCP resource URI: `delphi://automation/rtti-test-runner`.

`automate_delphi(action="test")` is used to directly test Delphi class methods. It targets white-box/gray-box testing,
using RTTI to complete instance creation, parameter binding, method invocation, assertions, fixture lifecycle, and structured reports;
UI user paths should still use `action="gui"`, and do not use RTTI calls to impersonate black-box tests.

## 1. TestHost Integration

The project must reference `DaofyAutomation.Base` and the corresponding VCL/FMX automation units, and call
`AutoStart` when the process starts. The runner resolves `className` in the order: fixture, explicitly registered class,
`TRttiContext.FindType`, `FindClass`. Classes already in the RTTI type pool with compatible constructors can be used directly without calling
`RegisterTestClass`; in this case `className` uses the RTTI fully qualified name, e.g. `Tests.TCalculator`.

Classes referenced only by test JSON strings may be trimmed from the executable by the Delphi smart linker. Use `RegisterTestClass` only when
the type cannot be discovered by RTTI, needs explicit keeping alive, or needs a custom alias:

```pascal
initialization
  TAutomationProcessorBase.RegisterTestClass(
    TCalculator,
    'Tests.TCalculator');

finalization
  TAutomationProcessorBase.UnregisterTestClass('Tests.TCalculator');
```

Register a fixture when per-case setup/teardown is required:

```pascal
function SetupCalculator: TValue;
begin
  Result := TValue.From<TObject>(TCalculator.Create);
end;

procedure TearDownCalculator(const AValue: TValue);
begin
  if AValue.IsObject then
    AValue.AsObject.Free;
end;

initialization
  TAutomationProcessorBase.RegisterFixture(
    'Tests.TCalculator', SetupCalculator, TearDownCalculator);

finalization
  TAutomationProcessorBase.UnregisterFixture('Tests.TCalculator');
```

Both directly discovered classes and explicitly registered classes are selected by the runner, which calls the constructor; for fixtures, setup returns an object or value,
and teardown always executes independently after the test ends. Exceptions in the setup, construction, test, and teardown phases are recorded separately.

## 2. MCP Invocation

The `test` action submits a background task to avoid long tests filling up the MCP request channel:

```python
submitted = automate_delphi(
    action="test",
    app_path=r"C:\Tests\TestHost.exe",
    test_timeout=30,
    keep_alive=True,
    tests=[
        {
            "id": "add",
            "className": "Tests.TCalculator",
            "method": "Add",
            "params": [1, 2],
            "expected": "3"
        },
        {
            "id": "invalid-input",
            "className": "Tests.TCalculator",
            "method": "Parse",
            "params": ["bad"],
            "expected_exception": "EConvertError",
            "expected_message": "invalid"
        }
    ]
)

async_task(action="status", task_id=submitted["task_id"], long_poll_seconds=10)
result = async_task(action="result", task_id=submitted["task_id"])
```

> **⚠️ Polling recommendation**: For slow tasks (such as automated tests), prefer polling with `action="result"` instead of `action="status"` + `long_poll_seconds`.
> `action="result"` immediately returns the current status (zero wait) and does not block the MCP channel.
> `action="status"` + `long_poll_seconds` blocks waiting for a progress change; if the task does not complete for a long time, it may cause the client to time out.

## 3. Test Case Fields

| Field | Required | Description |
|------|------|------|
| `id` / `name` | No | Stable identifier and display name, passed through to the result unchanged |
| `target` | Choose one of two | GUI control name; mutually exclusive with `className` |
| `className` | Choose one of two | Class name (see lookup order below); mutually exclusive with `target` |
| `method` | Yes | RTTI method name |
| `params` | No | JSON array of method parameters; also accepts a JSON string parsable as an array |
| `constructor_params` | No | JSON array of constructor parameters for directly discovered or explicitly registered classes; when omitted, binds the parameterless constructor |
| `expected` | No | Exact string assertion on the return value; empty string is allowed |
| `expected_exception` | No | Exception class name that should be thrown during the test phase; mutually exclusive with `expected` |
| `expected_message` | No | Text that the exception message should contain, case-insensitive; requires `expected_exception` |
| `assert_expr` | No | Python expression; the variable `actual` is the return value string; mutually exclusive with `expected`/`expected_exception` |
| `visibility` | No | Overrides global RTTI visibility, e.g. `private,protected,public,published` |
| `timeout` | No | Overrides the timeout in seconds for this case; must be a finite positive number |

### className Lookup Order (Highest to Lowest Priority)

1. **RegisterTestClass registration name** (e.g. `'Agent.EditEngineV3Test'`) — looks up the dictionary via `GetTestClass`; most stable and will not be trimmed by the linker
2. **TRttiContext.FindType fully qualified name** (e.g. `'Tests.TCalculator'`) — must be discoverable by RTTI, and the class must be an instance type
3. **FindClass** (Delphi VCL class name) — limited to classes derived from `TComponent`

> ⚠️ **Do not pass the bare class name from Delphi source code** (e.g. `TEditEngineV3Test`). You must pass one of the three forms above.
> Prefer using the `RegisterTestClass` registration name, because it does not depend on RTTI linking and will not be trimmed by the smart linker.

### Assertion Mode Mutual Exclusion Rules

The three assertion modes are **mutually exclusive**; each case can select only one:

| Mode | Field | Executed by | Semantics |
|------|------|--------|------|
| Exact match | `expected` | Delphi | `result.ToString = expected` |
| Exception match | `expected_exception` | Delphi | When `phase=test`, exception class name + message match |
| Python expression | `assert_expr` | Python | `eval(assert_expr, actual=return_value)` |

> ❌ **Forbidden combination**: `assert_expr` overrides the `assert` field on the Delphi side. If
> `expected` and `assert_expr` are set at the same time, the Delphi exact-match result will be silently overridden by the Python expression,
> causing the confusing `result=PASS` + `assert=fail`. The validation layer rejects this combination.

`assert_expr` executes as a standard Python expression in the MCP service process and can use Python built-in capabilities;
only run trusted test definitions. Natural-language descriptions should be placed in `name` or external test descriptions, not written into the expression.

## 4. RTTI Binding Rules

- Supports integer, Int64, Boolean/enum, floating-point, string, character, and class `nil` parameters.
- Parameters not yet supported, such as `var/out`, record, dynamic array, and interface, will report an explicit error and will not guess the binding.
- Overloads are selected by parameter count and type; multiple compatible overloads return `ambiguous overload`.
- Same-signature methods in the inheritance chain returned by RTTI are de-duplicated; constructors prefer the version declared on the most derived type.
- `expected` currently performs an exact comparison against the Delphi `TValue.ToString` result; use
  `assert_expr` for complex comparisons and tolerances.

## 5. Lifecycle and Timeout

Each test executes through an independent `run_tests` request:

1. Validate the complete suite; invalid input will not start TestHost.
2. Start or reuse the process, and wait for the automation endpoint derived from the PID (Windows NamedPipe; POSIX Unix Domain Socket).
3. setup/construct the instance, bind and invoke the method.
4. Execute the Delphi-side `expected` / expected-exception assertions.
5. Execute teardown independently; a teardown failure will not override the original test exception.
6. Execute `assert_expr` on the Python side and aggregate stable statistics.

The default `test_timeout=30` seconds can be overridden by each case's `timeout`. When a transport read reaches the deadline, TestHost is terminated,
and the next case automatically starts a new process. Timeout results include an `ms` field (actual elapsed time) and a `timeout_sec`
field (timeout threshold), making it easy to distinguish "stuck" from "genuinely slow". `keep_alive=true` is the default for the test action;
when false is passed, the transport connection is closed and TestHost is terminated after the suite completes.

Only exceptions with `phase=test` can satisfy `expected_exception`. setup, construction, and teardown exceptions are always
errors; wrong exception type, message mismatch, or no expected exception thrown count as assertion failure.

## 6. Result Structure

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
      "id": "invalid-input",
      "status": "ok",
      "exception_class": "EConvertError",
      "exception_message": "invalid value",
      "assert": "pass"
    }
  ],
  "raw_responses": []
}
```

- `passed`: The method completed and all declared assertions passed.
- `failed`: The method completed execution, but the return value, Python expression, or expected-exception assertion failed.
- `errors`: Startup, transport, setup/construction, unexpected test exception, or teardown error.
- `status`: `ok` when all tests pass; otherwise `failed`.
- `raw_responses`: Retains the original Delphi protocol responses for diagnosing statistics or encoding issues.

## 7. Model-Oriented Generation Workflow

1. Read the target class source code and enumerate normal, boundary, and exception paths.
2. For pure business methods, prioritize generating `action="test"` cases; for user-visible flows, generate GUI black-box scripts.
3. Classes discoverable by RTTI and having a compatible constructor can be used directly; use `RegisterTestClass` when keeping alive/aliasing is needed, and use
   `RegisterFixture` when setup/teardown is needed.
4. Use JSON primitives to construct parameterized data; declare `expected_exception` for exception paths.
5. Compile TestHost, submit the task, and poll `async_task`.
6. Fix errors first, then handle assertion failures; after fixing, rerun the complete suite.

