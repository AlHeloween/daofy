<!-- @when: planning automated test steps and needing the layered degradation strategy, the action-sequence specification, or the failure-handling patterns -->

# Planning Methodology

MCP resource URI: `delphi://automation/planning-methodology`.

## 1. Layered Degradation Strategy

### Perception Priority
```
① RTTI (rget/rinspect/dumpstate) → microsecond level
② Structured scanning (msgscan/listwnd/dlgscan) → millisecond level
③ OCR visual recognition (capture/ocr) → hundred-millisecond level
```

### Execution Priority
```
Black-box first choice: real UI operations (goto→click/type/key)
Grey-box/white-box: RTTI calls (rcall/rset), used only for fixtures/diagnostics
Compatibility mode: coordinate operations (move+click), DPI-sensitive
```

### Verification Priority
```
① RTTI property verification (rget) —— most precise
② Structured waiting (waitfor/msgscan)
③ Visual verification (capture+OCR) —— fallback
```

## 2. Action-Sequence Planning

Every step explicitly names its phase (perceive/execute/verify), tool, target, expected result and failure handling:

```json
{
  "phase": "perceive | execute | verify",
  "cmd": "rget | click | waitfor",
  "target": "control name.property",
  "expected": "human-readable expectation",
  "assert_expr": "actual == 'expected value'",
  "note": "context derived from source code",
  "timeout": 10000
}
```

## 3. Failure-Handling Patterns

| Signal | Likely cause | Recovery action |
|------|---------|---------|
| waitfor timeout | The control never appears / the action did not take effect | capture → analyse → retry or escalate |
| click returns an error | The control is occluded / Disabled | dumpstate to check Enabled/Visible |
| Unexpected dialog | Business-logic exception | msgscan → msgclick → capture the new state |
| OCR result mismatch | OCR precision is insufficient / the value genuinely differs | Confirm the exact value with rget first |
| RTTI call raises | The object does not exist / the method signature changed | Degrade to goto+click operation |

