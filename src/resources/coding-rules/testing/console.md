<!-- @when: After a console program compiles successfully, stdin/stdout interaction verification is required -->
<!-- @chain: before=human-collab.md, after=ui.md -->

## ⑨ Console Program Interaction Verification

Console-type programs use `automate_delphi` console mode for stdin/stdout interaction. **No Delphi-side changes are required.**

`action="auto"` automatically detects the PE header Subsystem; you can also explicitly use `action="console"`.

### Tool Invocation
```python
automate_delphi(app_path="Tool.exe", input="Y\n", expect="Continue?")
automate_delphi(action="console", app_path="Deploy.exe", args=["--silent"], timeout=60)
```

### Communication Mode
```
Python                               Console Delphi
  ── Popen(stdin=PIPE, stdout=PIPE) → begin..end starts
  ── proc.stdin.write("input\n")    → ReadLn receives
  ←── proc.stdout.read()            ← WriteLn outputs
  ←── proc.wait(timeout=5)          ← exit
```

### Step-by-step Interaction (keep_alive)
```python
proc = subprocess.Popen([exe_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
proc.stdin.write(b"Y\n"); proc.stdin.flush()
while True:
    line = proc.stdout.readline()
    if not line: break
    if b"Continue?" in line: proc.stdin.write(b"N\n"); proc.stdin.flush(); break
proc.wait(timeout=5)
```

### Notes
| Note | Description |
|--------|------|
| Timeout control | `communicate(timeout=...)` must be set |
| Pipe buffering | For large output, use `readline()` to read line by line |
| stderr | Recommend merging into `STDOUT` |
| exit code | Use `proc.returncode` to determine normal exit |
| Encoding | Windows console is usually gbk |

---

### Test Quality Red Lines

The 6 veto red lines (no skip-style passing, assertions verify specific state, screenshots must have verification, external dependency degradation paths, execution time matching, runtime evidence support) see [`automation/scenarios/base.md` § Test Quality Red Lines`](automation/scenarios/base.md#测试质量红线).