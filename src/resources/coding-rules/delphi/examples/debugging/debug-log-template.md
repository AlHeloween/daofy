# Debug State Log Template

AI Agent **must maintain a structured debugging log**, explicitly tracking attempted solutions and results to prevent repeating homogeneous solutions.

```
[Debug Log] <Problem Summary>
═══════════════════════════════════════
Problem description: {One-sentence description}

Attempted solutions:
  #1: Hypothesis H1=... → Verification=... → Result=falsified → Inference=exclude cause A
  #2: Hypothesis H2=... → Verification=... → Result=confirmed → Inference=cause B → Fixed
  #3: ...

Current scope:
  Excluded: [Module X, Module Y, ...]
  Remaining suspects: [Module W, ...]
  Current most likely hypothesis: {Hypothesis + basis}

Next step plan: {Specific verification content}
Trigger manual intervention: Yes/No (reason)
```

## Usage Rules

- Create a log before starting to debug **any problem**
- Update after each attempt (hypothesis → verification → result → inference)
- Review before entering the next round of hypotheses to confirm the new hypothesis is fundamentally different from those falsified
- The log is not saved to a file, only in current working memory
- After the problem is resolved, persist experience via `experience(save)`

