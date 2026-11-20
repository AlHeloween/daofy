<!-- @when: First run, or when the environment is abnormal — confirm the compiler status -->
<!-- @chain: after=workflow.md, before=kb-search.md -->

## ① Environment Check

```python
check_environment(action="check")       # Confirm compiler status
get_coding_rules()                       # Get the workflow overview + section index (default)
get_coding_rules(section="writing")      # Before coding: fetch the coding standards
get_coding_rules(section="review")       # After compiling: fetch the review table
get_coding_rules(section="list")         # List all available section names
```

