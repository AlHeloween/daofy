<!-- @when: After compilation passes, review final code quality -->
<!-- @chain: after=compile.md, before=cleanup.md -->

## ⑥ Code Review

**After compilation passes, review the code according to the dimensions below.**

| Dimension | Key points |
|------|------|
| Consistency | Naming/exception patterns/formatting uniformity |
| Completeness | Branch coverage/boundary conditions/input validation/resource release |
| Resource leaks | Create/Free pairing/handles/interface release |
| Delphi-specific | Reference counting/strings/TComponent ownership |
| Code quality | Cyclomatic complexity/magic numbers/duplicate code |
| Security | SQL injection/hardcoded credentials/buffer overflow |

> See `get_coding_rules(section="review")` for the complete checklist.

