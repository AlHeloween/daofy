<!-- @when: Running Python scripts, formatting strings, or handling optional parameters -->
<!-- @chain: independent -->

## Agent Operating Hard Rules

### Script Execution
- ❌ Never use `python -c "..."` (PowerShell quote escaping always breaks)
- ✅ Write a `.py` file → `bash python script.py` → clean up with `Remove-Item`

### String Formatting
- ❌ f-string with an embedded dictionary key `f'{d["key"]}'` (quote conflict)
- ✅ Use `.format()` or `%`

### Python Traps
- **No local `import` inside a function**: `from X import Y` makes Y a local variable in the function scope, and even the reference at the top of the function raises UnboundLocalError. Always write imports at the top of the module.
- **`if x:` vs `if x is not None:`**: 0, `""` and `[]` are all False. For optional numeric parameters use `Optional[int]` and test with `is not None`.
- **`$()` macro expansion**: registry key names do not contain `$()`; when adding them to the `macros` dictionary you must write `macros[f'$({k})'] = v`. Using `update(dict)` makes `str.replace('SKIADIR', ...)` wrongly match `$(SKIADIR)`.

