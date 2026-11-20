<!-- @when: Need automated testing prompt templates -->

# Automated Testing Prompt Templates

The following templates are for the AI to apply directly at each stage of automated testing; replace `{variables}` with actual values.

MCP resource URI: `delphi://automation/prompts`.

## F0. System Role and Thinking Framework

> **Role injection**: Call the MCP prompt `automate-expert-primer` to inject the complete "Delphi UI Automation Testing Expert" role (including the three-layer progressive thinking model + role boundaries); no need to expand it here.
>
> Invocation: `prompts/get automate-expert-primer`, parameters: `app_name`, `project_path`
>
> Role boundary: Used only during the automated testing phase. After testing is complete, the role automatically switches back to Delphi Development Expert.

---

## F1. Test Planning Template

```
== Test Planning ==

**Goal**: {test goal description}
**Preconditions**: {current application state}

**① Retrieve experience**
experience(action="search", query="{scenario keywords}", top_k=3)
- Match found → refer to its tool selection, failure modes, and recovery strategies
- No match → plan according to the default strategy

**② Perceive current state**
- listwnd → confirm the window list
- dumpstate / capture → obtain the UI structure and screenshot
- msgscan → check for residual pop-ups

**③ Plan the step sequence**

| # | Phase | Tool | Target | Expected result | Timeout | Failure handling |
|---|---|------|------|---------|------|---------|
| 1 | perceive | listwnd+dumpstate | Obtain initial state | Main window is open | 5s | Escalate |
| 2 | execute | goto+click | Click button X | Dialog opens | 10s | capture→msgscan→analyse |
| 3 | verify | waitfor+capture | Confirm dialog | Control Y is visible | 5s | Degrade to RTTI |

**④ Execution loop**
Strictly loop perceive→execute→verify for each step; stop on failure.
```

## F2. Single-Step Execution Protocol

Each step must be executed strictly according to the four-stage protocol:

```
┌─ ① Pre-perception ──────────────┐
│ msgscan: check for pop-ups (required before every step) │
│ capture/dumpstate: confirm current state │
│ Confirm the previous step's verification passed │
└────────────────────────────────┘
          ↓
┌─ ② Execute ──────────────────────┐
│ Invoke the target tool/command │
│ Synchronous command → check return code and result │
│ Asynchronous command → record that the operation was sent │
└────────────────────────────────┘
          ↓
┌─ ③ Wait ──────────────────────┐
│ Asynchronous command → wait(500~2000ms) / │
│   waitfor(control, timeout=10000) │
│ Synchronous command → skip waiting │
└────────────────────────────────┘
          ↓
┌─ ④ Verify ──────────────────────┐
│ msgscan: confirm there are no unexpected pop-ups │
│ capture/rget/ocr: confirm the result matches │
│ Match → mark complete, continue to next step │
│ Mismatch → switch to Failure Recovery Template (F3) │
└────────────────────────────────┘
```

**Templated submission**:
```
[Step {N}] phase=perceive|execute|verify
tool={tool} params={params}
expected={expected}
Pre-perception: {msgscan/dumpstate/capture result}
Execution result: {tool return}
Wait result: {waitfor/wait result}
Verification result: {match/mismatch, difference description}
```

## F3. Failure Recovery Template

```
**Failure Recovery — Step {N}**

**Failure signal**: {timeout/error return value/pop-up/OCR mismatch...}
**Expected**: {expected}
**Actual**: {actual}

**① Diagnose**
- capture current state (save screenshot)
- dumpstate to obtain the current control tree
- msgscan to detect pop-ups
- Analyse the cause of the difference: operation did not take effect? pop-up interference? timing issue? control changed?

**② Decide**
| Condition | Recovery strategy |
|------|---------|
| Pop-up interference | msgclick(OK/Cancel) → retry the original operation |
| Control not visible | dumpstate to find an alternative path → correct goto |
| Timeout but no error | Increase waitfor time → retry |
| RTTI available | Black-box first fixes the UI path; grey-box diagnostics may use rcall/rset |
| Deterministic failure | Escalate (record in experience base) |

**③ Recovery execution**
{selected recovery strategy + specific operations}

**④ Learning record**
Save to the experience base:
- problem: "{scenario} — {failure reason}"
- solution: "{recovery strategy} — effective on {application/version}"
- tags: ["automation", "{app_name}", "{failure_type}"]
```

## F4. Experience Saving Template

```
**Experience Save**

**Scenario**: {test case name}
**Application**: {application name/version}
**Execution summary**: Total steps N, succeeded N, failed+recovered N, unrecoverable N, elapsed Xs

**Success patterns** (which tool/command combinations worked well):
- Tool combination: {e.g. "goto+click combined with waitfor is stable"}
- RTTI usage: {e.g. "use rcall for grey-box diagnosis, while black-box scripts keep real UI operations"}

**Failure patterns** (which operations are prone to problems, and how to recover):
- {failure description}: {cause} → {recovery method} → {whether automated recovery is possible}

**Optimisation suggestions**:
1. {suggestion 1}
2. {suggestion 2}

**Save**:
experience(action="save", problem="{scenario keywords}", solution="{core practice}", tags=["automation", "{app_name}"])
```

## F5. MCP Prompt Overview

| Prompt | Purpose | Parameters | Corresponding F section |
|--------|------|------|-----------|
| `automate-expert-primer` | Inject testing expert role | `app_name`, `project_path` | F0 |
| `automate-code-analysis` | Code-aware analysis | `form_name`, `project_path`, `app_path` | H |
| `automate-test-plan` | Complete test planning | `goal`, `app_path`, `project_path` | F1 |
| `automate-step-execute` | Single-step execution protocol | `phase`, `tool`, `target`, `expected` | F2 |
| `automate-failure-recover` | Failure recovery | `signal`, `expected`, `actual` | F3 |
| `automate-save-experience` | Save experience to knowledge base | (none) | F4 |
| `automate-session-end` | End session | `save_experience`, `export_script` | — |

> All prompts are invoked via `prompts/get <prompt_name>`. Some require prerequisite parameters; it is recommended to read the corresponding F section before invoking.

