# Dirty Flag Protection Examples (v2026.06.12+)

## Problem

After write/format/uses, the file is marked **dirty**. Before writing again, you must first read (to clear the dirty flag) or provide `old_content` to verify the matched range.

## Ways to Continue Writing

- Call `read` (automatically clears the dirty flag)
- Provide a non-empty `old_content` for each edit
- `write(dry_run=True)` previews only (does not clear the dirty flag)
- `write(allow_dirty=True)` (at your own risk)

## Compact Output Format

- **read**: `# encoding: utf-8, 1-indexed [1, 200]`
- **write**: `[5, 10] → [5, 13] edit #0` + `- / +` diff, with an `Unchanged:` line appended at the end
- **dry_run**: same as above but marked `dry_run: true` (does not output the `Unchanged:` line)
- **uses**: `wrote: added System.SysUtils in interface, [2, 3] → [2, 4]`

## Correct Flow

```
1. read → get current line numbers + clear dirty flag
2. write(edits=[...]) → write changes
3. If another modification is needed → must read before write
```

## Incorrect Flow

```
1. write(edits=[...]) → file becomes dirty
2. write(edits=[...]) → ❌ dirty flag protection rejects the write
```