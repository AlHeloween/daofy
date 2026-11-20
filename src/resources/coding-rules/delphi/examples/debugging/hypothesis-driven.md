# Hypothesis-Driven Debugging Loop Example

Do not fall into the random "guess → modify → verify" repair loop; use a hypothesis-driven approach to systematically narrow the scope:

```
① Information collection
   ├─ Complete error message + error number/exception type
   ├─ Call stack (symbolized/unsymbolized both acceptable)
   ├─ Environment information (Delphi version/OS/platform/configuration)
   ├─ Reproduction steps (determine whether it can be reproduced stably)
   ├─ Recent changes (git log --oneline -10)
   └─ Check experience library: experience(search, query="...")
        ↓
② Generate 2~3 independent hypotheses
   H1: Hypothesized cause A → Expected observation A' → Verification method V1
   H2: Hypothesized cause B → Expected observation B' → Verification method V2
   Requirements: Based on evidence, mutually exclusive or independent, sorted by easiest to verify > most likely
        ↓
③ Parallel verification
   ├─ Verify mutually independent hypotheses simultaneously
   ├─ Use minimal operations for each verification
   ├─ For compile errors, use compile_file single-file verification
   └─ For runtime, use rget/delphi_rtti for quick verification
        ↓
④ Analyze results → Decision
   ├─ Confirmed → Proceed to fix
   ├─ All falsified → Return to ① or intervene
   └─ Partially confirmed → Adjust hypothesis to narrow scope
```

If root cause still cannot be located after at most 3 rounds → trigger P0 intervention.

## Key Rules

1. **No zero-hypothesis fixes** — Do not change code without forming a hypothesis
2. **Verify only one hypothesis at a time** — Do not make multiple changes
3. **Hypotheses must be falsifiable** — If you cannot design a verification method, the hypothesis is not specific enough
4. **Maintain a debugging log** — Record according to 8.10 to avoid repeating homogeneous solutions

