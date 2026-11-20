<!-- @when: DCC compile error; need to locate the cause and fix -->
<!-- @chain: before=binary-search-isolation.md, after=hypothesis-driven-debugging.md -->

### 8.8 DCC Compile Error Classification and Decoding

#### 8.8.1 Documentation Knowledge Base Search (Preferred)
The Delphi CHM documentation contains 1,278 DCC error/warning HTML files (875 EXXXX + 20 FXXXX + W/H series).
```python
# Build once, then you can search
delphi_kb(action="build", kb_type="document", async_mode=true)

# Look up a specific error number
delphi_kb(query="E2003", kb_type="document", search_type="semantic")
delphi_kb(query="F2613 unit not found", kb_type="document", search_type="semantic")
```

#### 8.8.2 Error Level Quick Reference
| Level | Prefix | Strategy |
|------|------|------|
| Fatal | Fxxxx | Fix path/config first |
| Error | Exxxx | Read error line → query documentation KB → fix |
| Warning | Wxxxx | Assess impact; known ones can be ignored |
| Hint | Hxxxx | Handle during cleanup; skip during debugging |

#### 8.8.3 Common DCC Error Quick-Reference Table
| Error No. | Common cause | Solution direction |
|--------|---------|---------|
| E2003 | Missing uses / spelling error | Check uses + case |
| E2010 | Type mismatch | Check assignment/parameter types |
| E2029 | Syntax structure error | Check parentheses/semicolons/begin..end |
| E2037 | Using '.' on a non-object type | Check variable type declaration |
| E2066 | Missing semicolon on previous line | Trace back to end of previous line |
| E2251 | Ambiguous overload match | Explicit type cast |
| E2506 | Stale DCU cache | Full rebuild or delete .dcu |
| F2613 | Search path does not contain target unit | Check DCC_UnitSearchPath |

#### 8.8.4 Handling Flow
```
Failure
 ├─ ① Classify severity: Fatal first → Errors main → Warnings deferred
 ├─ ② Single-file/full build: if an incremental build errors, clean first then full build; few → compile_file; many → first Error
 ├─ ③ Error localization:
 │   1. delphi_kb(query="{error number}", kb_type="document")
 │   2. delphi_kb(query="{keyword}", kb_type="document")
 │   3. Compare with quick-reference table + read source context
 │   4. delphi_kb(search_type="function") to look up API
 └─ ④ Difficult cases: binary-search isolation → search experience base → intervene after 3 failures
```

#### 8.8.5 Incremental Cache Issues
- `.dcu`/`.map`/`.dres` cache corruption causes ghost errors
- Symptoms: still reports the same error after a fix, or points to deleted code
- Solution: clear cache and full rebuild (close IDE first on Windows)


