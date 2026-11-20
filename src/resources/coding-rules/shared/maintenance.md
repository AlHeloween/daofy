<!-- @when: After fixing a bug, when the rule must be summarized and captured -->
<!-- @chain: after=experience.md -->

## ⑫ Rule Maintenance

After fixing a bug, summarize it as a rule and add it to the project rule file. Before adding, check whether the same rule already exists. After modifying, update the version number.

### New Rule Template
```markdown
#### [Category] [Title]
- **Problem**: what this rule guards against
- **Rule**: the concrete constraint or practice
- **Good example**: ```delphi {code that follows the rule} ```
- **Bad example**: ```delphi {code that breaks the rule} ```
```
Example:
```markdown
#### Common Error Pattern — Empty except Block
- **Problem**: an empty `except...end` swallows every exception
- **Rule**: inside `except`, at least log and re-raise, or handle it meaningfully
- **Good example**: `except on E: Exception do Logger.Error(E); raise; end;`
- **Bad example**: `except end;`
```

