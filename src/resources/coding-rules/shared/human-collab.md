<!-- @when: An anomaly appears, you are stuck, or the next step is uncertain -->
<!-- @chain: before=experience.md, after=testing/console.md -->

## Human–AI Collaboration — Anomaly Diagnosis and Human Intervention

### Pre-checks (common to every task)
When starting work or when stuck, self-check against this list:
- 🔴 A tool returns something abnormal → cross-verify once; if still abnormal, pause
- 🟡 Unsure which option to choose → check "Option Selection Ambiguity"
- 🟡 About to retry something essentially the same as last time → check "Consecutive Homogeneous Options"
- 🟡 Missing key information and forced to guess → check "Guessing with Insufficient Information"

### Diagnostic Flow

Detailed debugging procedures, trigger conditions, the six-step method, review tables, hypothesis-driven debugging, DCC error decoding, binary-search isolation, crash classification, attempt escalation and other in-depth content are covered in the following sections:

| Section | Content | Applicable scenario |
|------|------|---------|
| 8.1 Human-intervention trigger conditions | P0/P1/P2 trigger-condition table + priority interaction | Deciding whether to request intervention when stuck |
| 8.2 Six-step anomaly diagnosis | Analyze→Plan→Audit→Back up→Execute→Verify | General anomaly troubleshooting flow |
| 8.3 Exception information collection | Python/Delphi exception collection templates | When the exception scene must be captured |
| 8.4 Human-intervention handover checklist | Request template (all six items required) | Filled in after intervention is triggered |
| 8.5 Collaboration workflow | AI→human collaboration flow + 5 key rules | How to work after intervention |
| 8.6 MCP tool exception-handling conventions | Exception handling per layer | When developing/debugging tools |
| 8.7 Hypothesis-driven debugging | Four-step loop: collect→hypothesize→verify→decide | Systematic troubleshooting when the root cause is unknown |
| 8.8 DCC compile error classification and decoding | Error levels + quick reference + handling flow | When a compile error occurs |
| 8.9 Binary search and isolation debugging | File-level/code-level/project-level bisection + git bisect | When a large project is hard to localize |
| 8.10 Debug status log | Structured log template + usage rules | Before starting to debug any problem |
| 8.11 Debug tool selection decision tree | Decision tree for choosing tools by problem type | When unsure which tool to use |
| 8.12 Post-fix retrospective | Root-cause classification→defense evaluation→experience saving→rule linkage | After every fix passes |
| 8.13 Runtime crash classification and troubleshooting | Four crash classes A/B/C/D + decision tree | When a runtime crash occurs |
| 8.14 Attempt escalation checkpoints | Checkpoint after each failure + overall escalation map | On the 1st/2nd/3rd failure |

