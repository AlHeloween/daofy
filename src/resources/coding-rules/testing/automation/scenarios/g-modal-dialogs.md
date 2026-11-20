<!-- @when: Handle modal dialogs such as MessageBox / OpenDialog / confirmation dialogs -->
<!-- @part-of: ui-testing -->

#### G. Modal Dialogs — MessageBox / OpenDialog / Confirmation Dialogs

| Element | Content |
|------|------|
| **Goal** | Operate pop-up dialogs: confirm, cancel, select files |
| **Strategy** | Trigger pop-up action → msgscan detection → dlgclick response → verify subsequent state |
| **Key commands** | `msgscan`, `dlgclick`, `msgclose`, `waitfor` |

```json
[
  {"cmd":"click","target":"BtnDelete"},
  {"cmd":"msgscan","expected":"Delete confirmation dialog","assert_expr":"actual=='OK'","note":"Detected MessageBox returned OK; otherwise NOD"},
  {"cmd":"dlgclick","target":"btnYes","note":"Click 'Yes' in the MessageBox"},
  {"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"Delete succeeded","timeout":5000},
  {"cmd":"rget","target":"DBGrid1.DataSource.DataSet.RecordCount","assert_expr":"int(actual)==0","note":"Confirm the row has been deleted"},
  {"cmd":"capture","target":"dialog_after_delete"},
  {"cmd":"exit"}
]
```

**OpenDialog file selection**:
```json
[
  {"cmd":"click","target":"BtnImport"},
  {"cmd":"waitfor","target":"TOpenDialog","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"dlgfile","target":"C:\\data\\import.xlsx","note":"dlgfile directly writes the file path + Enter"},
  {"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"Import completed","timeout":10000},
  {"cmd":"capture","target":"import_done"},
  {"cmd":"exit"}
]
```

**Pitfall**: `msgscan` only detects MessageBox (`MessageDlg`/`ShowMessage`), not custom Form pop-ups → for custom pop-ups use `waitfor`+`click`; OpenDialog paths use `\\` instead of `/`.

> Detection of modern Windows dialogs (IFileDialog) is described in J0-J2 of [j-directui.md](j-directui.md).

