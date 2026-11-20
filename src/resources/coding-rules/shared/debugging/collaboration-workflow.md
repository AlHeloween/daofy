<!-- @when: Intervention has been requested and work must be coordinated with the human developer -->
<!-- @chain: after=escalation-handover.md -->

### 8.5 Collaboration Workflow

```
AI Agent                            Human (developer)
   │                                      │
   │── Attempt to solve the problem alone ──────→  │
   │── Submit the intervention request (per the 8.4 checklist) ──→ │
   │←── Human response (locate root cause / provide info / authorize)── │
   │── Continue fixing per the feedback → verify ──────→   │
   │←── Acceptance confirmation (pass or adjust)──────────    │
```

**Key rules**:
1. **The AI must request intervention proactively** — trigger immediately when the 8.1 conditions are met; do not waste time
2. **The intervention request must be complete** — missing any item of 8.4 can be sent back for completion
3. **The AI keeps following through** — after the human provides a plan, the AI is responsible for executing the fix and verifying it
4. **Capture the experience** — once solved, save it with `experience(action="save")` so the next occurrence can be solved autonomously
5. **Update the rules after intervention** — a rule blind spot → update `src/resources/coding-rules.md`


