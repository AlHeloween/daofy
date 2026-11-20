<!-- @when: Test the login flow (username/password entry, login state transition, failure prompt) -->
<!-- @part-of: ui-testing -->

#### B. Login Flow

| Element | Content |
|------|------|
| **Goal** | Verify username/password entry, login state transition, and failure prompts |
| **Strategy** | type credentials → click login → waitfor state change → rget verification → capture |
| **Key commands** | `goto`, `type`, `click`, `waitfor`, `rget`, `capture` |

```json
[
  {"cmd":"goto","target":"TLoginForm"},
  {"cmd":"type","target":"EdtUserName","text":"admin"},
  {"cmd":"type","target":"EdtPassword","text":"123456"},
  {"cmd":"click","target":"BtnLogin"},
  {"cmd":"waitfor","target":"TMainForm","prop":"Visible","value":"True","timeout":8000},
  {"cmd":"rget","target":"StatusBar.Caption","assert_expr":"'成功' in actual"},
  {"cmd":"capture","target":"login_success"},
  {"cmd":"exit"}
]
```

**Pitfall**: The password box's `PasswordChar` property does not respond to `type` → confirm the target is the edit control itself rather than the displayed text; a login failure MessageBox needs `msgscan` detection.

