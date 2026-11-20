<!-- @when: Test add, select, edit, and delete row operations in lists/grids -->
<!-- @part-of: ui-testing -->

#### D. List/Grid Row Operations

| Element | Content |
|------|------|
| **Goal** | Add, select, edit, and delete list rows, and verify data changes |
| **Strategy** | click add → fill in → click save → rget first row content verify → click edit/delete → state confirmation |
| **Key commands** | `rget` read cell, `click` select row, `waitfor` confirm state |

```json
[
  {"cmd":"goto","target":"TGridForm"},
  {"cmd":"rget","target":"DBGrid1.Columns[0].Title.Caption","note":"读表头,确认网格类型"},
  {"cmd":"click","target":"BtnAddRow"},
  {"cmd":"waitfor","target":"TEditDialog","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"type","target":"EdtValue","text":"新数据"},
  {"cmd":"click","target":"BtnOK"},
  {"cmd":"waitfor","target":"TGridForm","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"rget","target":"DBGrid1.DataSource.DataSet.RecordCount","assert_expr":"int(actual)>0"},
  {"cmd":"capture","target":"grid_after_add"},
  {"cmd":"exit"}
]
```

**Pitfall**: DBGrid row numbers change after additions/deletions → use DataSet.RecNo to locate rows instead of assuming row numbers; handle the confirmation dialog before deletion with `msgscan`+`dlgclick`.

