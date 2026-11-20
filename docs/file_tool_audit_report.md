# file_tool Tool Interface Audit Report

**Project**: Daofy for Delphi
**Audit scope**: `src/tools/file_tool.py` (1494 lines) and the call chain in `src/server.py`
**Audit date**: 2026-06-18
**Audit method**: line-by-line code review + cross-file call tracing

---

## Preliminary Notes

`file_tool` is registered in MCP as `delphi_file` (the old name `file_tool` is retained as an alias).
Hereafter, `file_tool` collectively refers to `src/tools/file_tool.py`.

---

## Audit Conclusion (One Sentence)

**The code quality is good, there are no security vulnerabilities, and the interface design is reasonable. One minor bug and three code quality suggestions were found.**

---

## Findings List

| # | Type | Severity | Description |
|---|------|--------|------|
| 1 | Bug | Minor | `handle_read` clears the dirty flag early |
| 2 | Quality | Suggestion | Redundant TOCTOU pattern in `_release_*_lock` |
| 3 | Quality | Suggestion | Misleading variable names `s0_1`/`e0_1` in overlap detection |
| 4 | Quality | Suggestion | `project_path` parameter of `_validate_path` is unused |

---

## Detailed Analysis

### 1. [Bug/Minor] `handle_read` Clears the Dirty Flag Early

**Location**: `file_tool.py:327-333`

```python
# Clear dirty flag on read: the AI has re-read the latest line numbers
_clear_dirty(file_path)                           # ← clear first

# Acquire read permission (multiple readers, single writer: multiple reads can be concurrent; no reads during writes)
read_lock_err = _acquire_read_lock(file_path)     # ← acquire lock afterward
if read_lock_err:
    return _wrap_error(read_lock_err)             # lock failed, but dirty flag has already been cleared
```

**Problem**: If read lock acquisition fails (the file is being written), the dirty flag has already been cleared early. The next time `write` is called on that file, the dirty check (`_check_dirty`) will pass (the dirty flag does not exist), but the AI has not actually successfully read the latest line numbers of the file.

**Trigger condition**: This occurs only in multi-threaded concurrent scenarios—one thread is writing to this file while another thread calls `read` at the same time. Single-threaded (MCP serial calls) will not trigger it.

**Suggested fix**:
```python
# Acquire the read lock first
read_lock_err = _acquire_read_lock(file_path)
if read_lock_err:
    return _wrap_error(read_lock_err)

# After confirming that reading is allowed, clear the dirty flag
_clear_dirty(file_path)
```

---

### 2. [Suggestion] Redundant Pattern in `_release_read_lock` / `_release_write_lock`

**Location**: `file_tool.py:421-466`

```python
def _release_read_lock(file_path: str) -> None:
    normalized = os.path.abspath(file_path)
    with _file_rw_dict_lock:                          # look up entry
        entry = _file_rw_locks.get(normalized)
        if entry is None:
            return
    with entry["lock"]:                               # modify counts
        entry["readers"] = max(0, entry["readers"] - 1)
```

**Problem**:

`_release_read_lock` and `_release_write_lock` use `_file_rw_dict_lock` to protect the entry lookup, release that lock, and then acquire `entry["lock"]`. There is a TOCTOU window between the two operations. Although entries are never deleted and this pattern will not cause a data race (the `entry` reference is always valid), the code can be more concise:

**Suggested fix**:
```python
def _release_read_lock(file_path: str) -> None:
    entry = _get_rw_entry(file_path)       # already protected internally by _file_rw_dict_lock
    with entry["lock"]:
        entry["readers"] = max(0, entry["readers"] - 1)
```

The behavior is completely equivalent, more concise, and eliminates the TOCTOU code smell.

The same applies to `_release_write_lock`.

---

### 3. [Suggestion] Misleading Variable Names in Overlap Detection

**Location**: `file_tool.py:686-698`

```python
for i in range(len(validated_edits) - 1):
    s0_1, e0_1, _, _, _, _ = validated_edits[i]
    s1_0, _, _, _, _, _ = validated_edits[i + 1]
```

The format of each element in `validated_edits` is `(s_0, e_0, c, desc, s_1, e_1)`:
- Index 0: `s_0` (0-indexed start)
- Index 1: `e_0` (0-indexed exclusive end, or None)
- Index 4: `s_1` (1-indexed start)
- Index 5: `e_1` (1-indexed inclusive end)

The `_1` suffix in the variable names `s0_1` and `e0_1` suggests 1-indexed, but they are actually the 0-indexed `s_0` and `e_0`. The `_0` suffix in `s1_0` suggests 0-indexed, but it can also easily be ambiguous with "the 0th element of the 1st edit".

**Logic analysis**: The actual calculation is correct (`s1_0 < e0_1` is the correct non-overlap condition), but reading this code requires looking twice to confirm. The variable names could be more self-explanatory.

**Suggestion**:
```python
for i in range(len(validated_edits) - 1):
    curr_s_0, curr_e_0, _, _, _, _ = validated_edits[i]
    next_s_0, _, _, _, _, _ = validated_edits[i + 1]
    if curr_e_0 is None:
        return _wrap_error(...)
    if next_s_0 < curr_e_0:
        return _wrap_error(...)
```

---

### 4. [Suggestion] `project_path` Parameter of `_validate_path` Has No Effect

**Location**: `file_tool.py:49-72`

```python
def _validate_path(file_path: str, project_path: Optional[str] = None) -> Optional[str]:
```

The `project_path` parameter is accepted but never used in the function body. Both `handle_write` (line 558) and `handle_uses` (line 1300) pass `project_path`, but it has no effect.

The comment says "keep the parameter signature for compatibility", but callers pass a value, which easily makes people mistakenly believe there is a project root restriction. If you want to preserve future extensibility, it is recommended to:

1. Change to `**kwargs` to avoid caller misunderstanding; or
2. At least add a comment saying "`project_path` is currently unused"; or
3. Implement a project root whitelist (reference below):

```python
def _validate_path(file_path: str, project_path: Optional[str] = None) -> Optional[str]:
    """校验文件路径安全性"""
    if '\0' in file_path:
        return "路径包含 null 字节"
    try:
        resolved = os.path.abspath(os.path.realpath(file_path))
    except (OSError, ValueError) as e:
        return "路径解析失败: %s" % str(e)

    # System sensitive directory protection
    for sensitive_dir in _SYSTEM_SENSITIVE_DIRS:
        try:
            resolved_relative = os.path.relpath(resolved, sensitive_dir)
            if not resolved_relative.startswith('..'):
                return "路径位于系统敏感目录中: %s" % sensitive_dir
        except ValueError:
            pass

    # If project_path is passed, restrict within its directory
    if project_path:
        try:
            proj_resolved = os.path.abspath(os.path.realpath(project_path))
            proj_dir = proj_resolved if os.path.isdir(proj_resolved) else os.path.dirname(proj_resolved)
            rel = os.path.relpath(resolved, proj_dir)
            if rel.startswith('..'):
                return "路径不在项目目录内"
        except (OSError, ValueError):
            pass   # Do not block when project_path parsing fails

    return None
```

---

## Self-correction of Previous Report

The following three items were originally marked "Serious" and are now corrected to "Misjudgment":

| Original conclusion | Reason | Correction |
|--------|------|------|
| Path traversal attack vulnerability | `os.path.realpath()` already resolves `..`; the caller is an AI Agent, not an external user | Not a vulnerability |
| Encoding detection information disclosure | Error messages are only returned to the calling Agent, not broadcast | Not a security issue |
| Dirty flag lacks persistence | Process-level guardrail; resetting the session after restart is correct behavior | Design is correct |

---

## Checklist

| Dimension | Conclusion |
|------|------|
| Interface parameter validation | Complete (type/range/overlap/required fields) |
| Error handling | Returns `dict` within the function; the upper layer uniformly converts to `CallToolResult` |
| Return value consistency | Uniform `{status, message}` format |
| Encoding handling | Encoding detection + fallback chain + BOM preservation, logically consistent |
| Concurrency safety | Non-blocking RWLock, no deadlocks, release paths fully covered by try/finally |
| Dirty flag protection | Mechanism is reasonable; only one minor bug with early clearing |
| Path safety | No null bytes, no system sensitive directories, no path traversal |
| Logging | Key paths have logger.debug/warning |
| Documentation consistency | README is basically consistent with the code; the `allow_dirty` parameter can be added |

---

## Suggested Priority

1. **Optional**: Fix the early `_clear_dirty` clearing (item 1), to prevent line number misalignment in edge cases
2. **Optional**: Simplify the `_release_*_lock` implementation (item 2), eliminating the TOCTOU smell
3. **Optional**: Add project_path restriction to `_validate_path` (item 4), defense in depth
4. **Optional**: Optimize the variable names in overlap detection (item 3), improving readability
5. **Optional**: Add `allow_dirty` parameter documentation to README

