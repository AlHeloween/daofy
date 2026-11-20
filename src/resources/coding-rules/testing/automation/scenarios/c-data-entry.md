<!-- @when: Fill in form fields (text box/drop-down/date picker) and submit -->
<!-- @part-of: ui-testing -->

#### C. Form Data Entry

| Element | Content |
|------|------|
| **Goal** | Fill in form fields (text box/drop-down/date picker) and submit |
| **Strategy** | type text → click drop-down option → click submit → waitfor result → rget verify write |
| **Key commands** | `type`, `click` (including `@` option click), `waitfor`, `rget` |

```json
[
  {"cmd":"goto","target":"TEditCustomerForm"},
  {"cmd":"type","target":"EdtName","text":"张三"},
  {"cmd":"type","target":"EdtPhone","text":"13800138000"},
  {"cmd":"click","target":"cbCity@北京","note":"下拉框选项点击: ControlName@ItemCaption"},
  {"cmd":"click","target":"BtnSave"},
  {"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"保存成功","timeout":5000},
  {"cmd":"rget","target":"EdtName.Text","assert_expr":"actual=='张三'","note":"验证回填"},
  {"cmd":"capture","target":"form_saved"},
  {"cmd":"exit"}
]
```

**Pitfall**: Field validation before saving may pop up a prompt box → use `msgscan` to detect it before continuing; for date pickers, use `type` + text rather than clicking the calendar.

