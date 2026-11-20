<!-- @when: Test expanding/collapsing/selecting tree controls (TreeView/VirtualStringTree) -->
<!-- @part-of: ui-testing -->

#### E. Tree Navigation

| Element | Content |
|------|------|
| **Goal** | Expand/collapse tree nodes, select leaf nodes |
| **Strategy** | click expand → waitfor child nodes visible → click select leaf → capture |
| **Key commands** | `click` (`@` node targeting), `waitfor`, `capture` |

```json
[
  {"cmd":"goto","target":"TTreeForm"},
  {"cmd":"click","target":"TreeView1@客户管理","note":"click@节点文本展开"},
  {"cmd":"waitfor","target":"TreeView1","prop":"Items.Count","value":"3","timeout":3000},
  {"cmd":"click","target":"TreeView1@张三"},
  {"cmd":"waitfor","target":"PanelDetail","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"rget","target":"EdtDetailName.Text","assert_expr":"actual=='张三'"},
  {"cmd":"capture","target":"tree_selected"},
  {"cmd":"exit"}
]
```

**Pitfall**: `@` node matching is first-match → when node names are duplicated, use the `expand` command to expand the parent node before selecting; virtual tree nodes need to be scrolled before they load.

