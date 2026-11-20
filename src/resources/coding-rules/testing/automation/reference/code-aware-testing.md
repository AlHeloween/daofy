<!-- @when: a test path must be derived from source analysis, or code-derived assertions are needed -->

# Code-Aware Testing

MCP resource URI: `delphi://automation/code-aware-testing`.

## H1. Core Idea

The AI's advantage is not simulating clicks — it is **reading the code**. The source code is the best test specification there is.

Code-aware testing adds a code-analysis stage **upstream** of the perceive → plan → execute → verify loop.

## H2. Code-Analysis Workflow

### Step 1: Locate the target code

```python
delphi_kb(query="TNewCustomerForm", search_type="class", kb_type="project")
delphi_file(action="read", file_path="UnitNewCustomer.pas")
delphi_file(action="read", search_type="class", type_name="TNewCustomerForm")
```

### Step 2: Analyse the DFM (control structure)

Extract each control's name, type, event bindings and key properties, then emit a control map for the planning stage to use.

### Step 3: Analyse the PAS (event handlers)

| Code pattern | Testing implication |
|---------|---------|
| `if edtName.Text = '' then` | Test the empty-value path and verify the dialog |
| `try ... except ... end` | Trigger the exception and verify the degradation behaviour |
| `ShowMessage('...')` | msgscan after the operation to verify the dialog text |
| `ModalResult := mrOk/mrCancel` | waitfor the window to close |
| `Insert/Post` | Black-box UI verification; grey-box rcall to verify persistence |
| `Enabled := False` | rget to verify Enabled |
| `lblError.Visible := True` | rget to verify Visible |

### Step 4: Emit the code-analysis report

```
== Code Analysis Report — TNewCustomerForm ==

Control Structure:
| Control Name | Type | Event |
|--------|------|------|
| edtName | TEdit | — |
| btnSave | TButton | btnSaveClick |

Event Handler Analysis:
**btnSaveClick**
1. Validate that edtName.Text is non-empty → if empty, ShowMessage('名称不能为空') + Exit
2. Create TCustomer → read values from controls → Insert DB → ShowMessage('保存成功')
3. ModalResult := mrOk

Derived Test Paths:
| # | Path | Action | Code-Derived Assertion |
|---|------|------|-------------|
| 1 | Success path | Enter valid data → Save | Dialog "保存成功" + window closes |
| 2 | Empty name | edtName='' → Save | Dialog "名称不能为空" |
| 3 | Cancel operation | Any data → Cancel | Window closes, no new DB record |
```

## H3. Code Path → Test Path Mapping

| Code structure | Test paths |
|---------|-----------|
| Sequential code (no branches) | 1 (the success path) |
| `if ... then` | 2 (true + false) |
| `if ... then ... else` | 2 |
| `case X of ... end` | N+1 |
| `try ... except ... end` | 2 (normal + exception) |
| `for/while` | ≥2 (0 iterations + 1 or more) |

Every `if`/`case`/`try` corresponds to at least one automated test operation and assertion.

## H4. Priority of Code-Derived Assertions

1. Pure business-logic methods: `automate_delphi(action="test")`, verified through parameterised input,
   `expected`, `expected_exception` or `assert_expr`.
2. UI state: `rget` checks the property value directly — the most precise and most stable.
3. `waitfor` + `msgscan` — checks the dialog content.
4. `capture` + OCR — visual verification (the fallback).
5. `rcall` invokes a business method — only for single-step grey-box diagnosis; a reusable test belongs in the RTTI test suite.

Read `delphi://automation/rtti-test-runner` first for a pure business-method test. A user-visible interaction
still gets a GUI Black-box script: RTTI being more convenient is no reason to skip the real UI path.

## H5. Integration with the Automation Flow

Insert the code-analysis stage ahead of the existing loop:

```
Stage 0: Code analysis → Stage 1-N: Perceive → Plan → Execute → Verify
```

The output of the code analysis directly guides the choice of steps and the definition of assertions that follow.

