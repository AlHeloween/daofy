<!-- @when: Test right-click menu (ContextMenu/PopupMenu) pop-up and menu item selection -->
<!-- @part-of: ui-testing -->

#### I. Context Menu

| Element | Content |
|------|------|
| **Goal** | Right-click the target to pop up ContextMenu, then select a menu item |
| **Strategy** | rclick target → waitfor menu visible → click menu item → verify |
| **Key commands** | `rclick`, `waitfor`, `click` (`@` menu item) |

```json
[
  {"cmd":"rclick","target":"DBGrid1"},
  {"cmd":"waitfor","target":"TPopupMenu","prop":"Handle","value":"True","timeout":2000},
  {"cmd":"click","target":"@Edit","note":"@text matches menu item"},
  {"cmd":"waitfor","target":"TEditDialog","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"rget","target":"EdtValue.Text","assert_expr":"len(actual)>0"},
  {"cmd":"capture","target":"context_menu_edit"},
  {"cmd":"exit"}
]
```

**Pitfall**: Right-clicking different rows/columns may pop up different menus → first `goto`/`click` to select a specific row before `rclick`; multi-level submenus use `@TopLevelMenu>>SubMenu` path targeting (if applicable).

