<!-- @when: Test search/filter functionality, including hits, misses, and result list updates -->
<!-- @part-of: ui-testing -->

#### F. Search/Filter

| Element | Content |
|------|------|
| **Goal** | Enter search criteria and verify result list/status changes |
| **Strategy** | type search keyword → waitfor result update → rget result count → capture |
| **Key commands** | `type`, `waitfor`, `rget`, `capture` |

```json
[
  {"cmd":"type","target":"EdtSearch","text":"张三"},
  {"cmd":"waitfor","target":"DBGrid1","prop":"DataSource.DataSet.RecordCount","value":"1","timeout":5000},
  {"cmd":"rget","target":"DBGrid1.DataSource.DataSet.RecordCount","assert_expr":"int(actual)>=1"},
  {"cmd":"capture","target":"search_result"},
  {"cmd":"type","target":"EdtSearch","text":"不存在的关键词","note":"测试无结果场景"},
  {"cmd":"waitfor","target":"DBGrid1","prop":"DataSource.DataSet.RecordCount","value":"0","timeout":5000},
  {"cmd":"rget","target":"StatusBar.Caption","assert_expr":"'无' in actual or '0' in actual"},
  {"cmd":"capture","target":"search_empty"},
  {"cmd":"exit"}
]
```

**Pitfall**: Search input has debounce (300ms–1s) → set waitfor timeout to 5s or more; after clearing the search, wait for the data to recover.