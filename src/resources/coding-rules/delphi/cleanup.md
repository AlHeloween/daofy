<!-- @when: After review is complete, clean up redundant leftovers in the code -->
<!-- @chain: after=review-guide.md, before=testing/ui.md -->

## ⑦ Cleanup & Verification

- **Backup verification**: `delphi_file(action="write")` automatically backs up to `__history` by default; use `delphi_file(action="backup", backup_action="list", file_path=...)` to confirm
- **Tidy up**: Delete unused variables/imports/functions/classes (delete directly, no confirmation needed)
- **Legacy dead code**: Mark with deprecation comments and leave for manual cleanup
- **Encoding**: Preserve the original encoding; after modification, run `delphi_file(action="format", ...)`

