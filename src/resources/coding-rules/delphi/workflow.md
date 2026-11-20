<!-- @when: When starting coding/a task for the first time, to understand the overall workflow -->
<!-- @chain: after=planning.md, before=writing.md -->

## Workflow Overview

```
① → ② → ③/④ → ⑤ → ⑥ → ⑦      Optional: ⑧/⑨
         ↑      │    │    │
         └── failure ──┴────┴────┘ ← fall back to ③

 ① Environment check → check_environment / get_coding_rules
 ② Query KB     → delphi_kb / delphi_file(read)
 ③ Write code   → delphi_file(action="write")
 ④ Format       → delphi_file(action="format")           # ③④ loop: format immediately after changes
 ⑤ Compile and verify → delphi_project(action="compile")       # failure → back to ③
 ⑥ Code review  → get_coding_rules(section="review")      # not passed → back to ③
 ⑦ Cleanup     → remove unused variables/imports/dead code # review first, then clean
  ⑧ Automated testing → automate_delphi (GUI/Console both supported)     # failure → back to ③
  ⑨ ─── Merged into ⑧ ───
 §⑩ Pre-flight self-check → get_coding_rules(section="human_collab")  # can be triggered at any step
 §⑪ Experience capture → experience(action="save")
```

