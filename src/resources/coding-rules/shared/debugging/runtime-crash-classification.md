<!-- @when: The program crashes at runtime and the root cause must be classified and investigated -->
<!-- @chain: before=escalation-checkpoints.md, after=post-mortem.md -->

### 8.13 Runtime Crash Classification and Troubleshooting

Delphi runtime crashes have 4 distinct root-cause patterns:

#### 8.13.1 A: AV — Interface Reference Counting Issues
**Characteristics**: AV when calling an interface method; calling object methods works normally.
**Troubleshooting**:
① Confirm whether it is an interface call (does the call stack go through Interface Dispatch?)
② Check the interface source: was it obtained from an already Freed object? Passed across threads?
③ Fix: ensure the object lifetime ≥ the interface usage lifetime; or use a weak reference

#### 8.13.2 B: AV — TComponent Ownership Violation
**Characteristics**: AV after a Form closes or in the destruction chain.
**Troubleshooting**:
① Check the source line corresponding to the AV address
② Confirm whether the component has already been Freed
③ Check whether event registration/unregistration is paired (Timer/Socket callbacks accessing a released object)
④ Fix: unregister callbacks in OnDestroy; check Assigned(Self)/csDestroying

#### 8.13.3 C: DFM Streaming Errors
**Characteristics**: Error when opening a Form or a DFM streaming exception at runtime.
**Troubleshooting**:
```
Class TMyFrame not found      → missing uses or RegisterClass not called
Property Caption does not exist → DFM property name spelling or type mismatch
Error reading X: ...          → binary data corrupted or version incompatible
```
① Check that the uses clause, RegisterClass, and DFM class name match the PAS
② published section declarations, property name/type matching
③ DFM corruption → save as text DFM or restore from __history

#### 8.13.4 D: Package/Dynamic Library Loading Errors
**Characteristics**: Error when starting or loading a BPL/DLL.
```
"Cannot load package XXX"       → BPL not on path or version mismatch
"entry point YYY not found"    → exported function signature mismatch
"Runtime error 216/217"        → initialization exception
```
Troubleshooting: check_environment → delphi_project(info) → check PATH/RuntimePackages

#### 8.13.5 Crash Classification Decision Tree
```
Runtime crash
 ├─ Exception type is clear → jump to corresponding A/B/C/D
 ├─ Call stack goes through Interface Dispatch → A
 ├─ In TComponent.Notification/Form destruction → B
 ├─ Contains "Class not found"/"Property" → C
 ├─ Contains "Cannot load package"/"entry point"/"216"/"217" → D
 └─ Cannot classify → use StackTrace.pas to get full call stack, then reclassify
```


