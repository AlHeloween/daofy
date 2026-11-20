<!-- @when: During debugging, escalate according to these checkpoints after each failure -->
<!-- @chain: after=runtime-crash-classification.md -->

### 8.14 Attempt Escalation Checkpoints

Checkpoints after each failure to ensure a reasonable shift before the 3rd attempt:

#### 8.14.1 First Failure
```
□ Checkpoint 1
  ① Confirm whether this is essentially different from last time (homogeneous → change direction immediately)
  ② Check whether the right tool is used (§8.11 decision tree)
  ③ Create a debug log (§8.10)
  ④ Update hypothesis
```

#### 8.14.2 Second Failure
```
□ Checkpoint 2
  ① Search the experience base (mandatory!)
  ② Evaluate binary-search isolation
  ③ Try a different tool/method (same tool twice → change direction)
  ④ Update the excluded scope + remaining suspects
```

#### 8.14.3 Third Failure (Before Intervention)
```
□ Checkpoint 3 — Pre-intervention checks
  ① Debug log is complete
  ② Experience search has been performed
  ③ Exception scene information is complete (§8.3)
  ④ Binary-search isolation has been attempted
  ⑤ Fill out the intervention request per §8.4
  ✅ All satisfied → submit
  ❌ Any not satisfied → complete it before applying
```

#### 8.14.4 Overall Escalation Flowchart
```
Attempt #1 → Homogeneous? → change direction immediately
        → Checkpoint 1 → update log → update hypothesis → #2
Attempt #2 → search experience base + evaluate binary search
        → change tool? → Checkpoint 2 → update log → change direction → #3
Attempt #3 → Checkpoint 3 (pre-intervention)
        ├─ Pass → apply for intervention per §8.4
        └─ Fail → complete and retry
```

**Key rules**:
- Between attempts 1 and 2, you must change direction
- Between attempts 2 and 3, you must search the experience base + evaluate binary search
- Homogeneous solutions immediately trigger P2 to change direction
- Strictly distinguish "attempt count" and "solution count"


