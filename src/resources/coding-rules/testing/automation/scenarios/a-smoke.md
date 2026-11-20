<!-- @when: Verify the program can start, the main form renders, and key controls are in place -->
<!-- @part-of: ui-testing -->

#### A. Smoke Test — Verify the main form starts normally

| Element | Content |
|------|------|
| **Goal** | Confirm the program can start, the main form renders, and key controls are in place |
| **Strategy** | goto main form → rget key control state → capture snapshot → exit |
| **Key commands** | `goto`, `rget`, `capture`, `exit` |

```json
[
  {"cmd":"goto","target":"TMainForm","note":"等主窗体就绪,默认超时5s"},
  {"cmd":"rget","target":"MainForm.Caption","assert_expr":"len(actual)>0","note":"主窗体标题非空"},
  {"cmd":"rget","target":"BtnSearch.Enabled","assert_expr":"actual=='True'","note":"关键按钮可用"},
  {"cmd":"rget","target":"StatusBar.Panels[0].Text","note":"状态栏内容,不断言仅记录"},
  {"cmd":"capture","target":"smoke_main","note":"基线截图"},
  {"cmd":"exit"}
]
```

**Pitfall**: Startup animations/splash screens can cause goto to time out → set timeout to 15s or use `waitfor` to wait for the splash screen to disappear.

