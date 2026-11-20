# Binary Search and Isolation Debugging Example

Use binary search to quickly narrow the suspect scope, O(log N) complexity.

## Compile Error Binary Search (File Level)

```
① Split file into upper and lower halves
② Comment out upper half with {$IFDEF DEBUG_SKIP}...{$ENDIF} → Compile
③ Error disappears → Upper; still present → Lower
④ Recurse until the specific line is located
```

## Runtime Crash Binary Search (Code Path Level)

```
① Determine the simplest triggering path
② Insert Exit/early return at the midpoint of the call chain
③ Crash disappears → Second half; still present → First half
④ Recurse until the specific function is located
```

## Multi-Module Isolation (Project Level)

```
① Temporarily disable compilation events
② Remove DCCReference one by one to locate missing units
③ Comment out uses in batches to locate circular references
```

## Regression Localization (Change Level)

```
git bisect start → bad → good → run <script>
Automatically bisect compile verification to locate the commit that introduced the problem
```

## Isolation Principles

- Change only one variable at a time
- Proceed to the next step after confirming the result
- Use `{$IFDEF}` instead of deleting code (for easy restoration)