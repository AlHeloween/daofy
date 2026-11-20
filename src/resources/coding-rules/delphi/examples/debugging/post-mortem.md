# Post-Fix Retrospective Example — From Debugging to Defense

After fix verification passes, a retrospective must be performed to consolidate into long-term assets.

```
① Root cause classification
   ├─ Coding error (logic/syntax)
   ├─ API misuse (parameters/lifecycle/contract)
   ├─ Environment difference (version/OS/third-party library)
   ├─ Concurrency/timing (race/deadlock/event order)
   └─ External dependency change

② Evaluate defensive measures
   ├─ Add Assert → When preconditions are not met
   ├─ Add logging → When information is insufficient for difficult diagnosis
   ├─ Add automated tests → When business logic errors
   └─ Update rules → When common patterns

③ Experience saving (must execute)
   experience(action="save", problem="{泛化后描述}", solution="{步骤+关键代码}", tags=["调试", ...])

④ Rule linkage check
   ├─ hit_count ≥ 3 → Upgrade to formal rule
   └─ Discover rule blind spot → Add/update rule
```

## Principles

- Every fix is accompanied by a retrospective
- Experience half-life is 30 days (it decays if not recorded)
- Rules are the solidification of experience; upgrade when hit_count ≥ 3
- Retrospectives cannot be skipped

