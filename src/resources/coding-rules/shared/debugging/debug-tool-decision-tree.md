<!-- @when: Unsure which tool to use to investigate the current problem type -->
<!-- @chain: before=post-mortem.md, after=debug-log.md -->

### 8.11 Debug Tool Selection Decision Tree

| Problem type | ⭐ Primary | ☆ Alternative |
|---------|---------|---------|
| **Compile error** | delphi_project(compile) / compile_file | delphi_file(read) / delphi_kb / experience |
| **Runtime crash** | classify(8.13) → msgscan / StackTrace / delphi_rtti | guide user in IDE / experience |
| **Logic error** | delphi_file(read) / delphi_kb / LSP | automate_delphi(rget/capture) / experience |
| **Environment issue** | check_environment / delphi_project(info) | git diff / experience |

**General principles**:
- Search the experience base before acting: `experience(search, ...)` may give the answer in 30 seconds
- Confirm the API before fixing the code: when unsure about an API, use `delphi_kb` to look up its definition
- Single-file verification first: for compile errors prefer `compile_file`
- Isolate before analyzing: narrow the range with binary search, then analyze in depth


