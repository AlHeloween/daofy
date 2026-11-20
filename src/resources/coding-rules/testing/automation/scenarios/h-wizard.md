<!-- @when: Test step switching and data passing in multi-step wizards -->
<!-- @part-of: ui-testing -->

#### H. Multi-step Wizard

| Element | Content |
|------|------|
| **Goal** | Complete each wizard step in order |
| **Strategy** | fill step1 → click Next → waitfor step2 → fill step2 → click Finish → verify result |
| **Key commands** | `waitfor` detects step page switch, `rget` verifies data at each step |

```json
[
  {"cmd":"goto","target":"TWizardForm"},
  {"cmd":"type","target":"EdtName","text":"Project A"},
  {"cmd":"click","target":"BtnNext"},
  {"cmd":"waitfor","target":"TWizardForm.PageControl","prop":"ActivePageIndex","value":"1","timeout":3000},
  {"cmd":"type","target":"EdtDescription","text":"Description text"},
  {"cmd":"click","target":"BtnFinish"},
  {"cmd":"waitfor","target":"TResultForm","prop":"Visible","value":"True","timeout":5000},
  {"cmd":"rget","target":"ResultLabel.Caption","assert_expr":"'Success' in actual"},
  {"cmd":"capture","target":"wizard_done"},
  {"cmd":"exit"}
]
```

**Pitfall**: Each wizard step may have asynchronous validation → set `waitfor` timeout long enough; after clicking Finish, if asynchronous processing is not complete (e.g., generating a report), wait for the status bar instead of a Form switch.

