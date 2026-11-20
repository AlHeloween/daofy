<!-- @when: An exception occurs and the scene information must be collected to locate the root cause -->
<!-- @chain: after=six-step-method.md -->

### 8.3 Exception Information Collection

```python
# Python exception collection template
import traceback, sys
def capture_exception_context(exc, locals_dict=None):
    exc_type, exc_value, exc_tb = sys.exc_info()
    return {
        "exc_type": type(exc).__name__,
        "exc_message": str(exc),
        "traceback": traceback.format_exc(),
        "frames": [{
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno,
            "function": frame.f_code.co_name,
            "locals": {k: repr(v) for k, v in frame.f_locals.items()}
        } for frame in traceback.extract_tb(exc_tb)],
    }
```

For Delphi exception collection, two options are recommended (pick one):

**Option A: Guide the user to reproduce in the IDE (recommended, zero dependencies)**
The AI guides the user to set breakpoints, single-step, and collect the call stack and variable values.
- Must compile with the Debug configuration
- The user reports: failing file + line number, exception message, Call Stack (Ctrl+Alt+S), Watch variable values

**Option B: Wire in an exception-tracking tool (production environment)**
| Tool | Features |
|------|------|
| **StackTrace.pas** (ships with the project) | VEH hook + MAPDATA symbol resolution + local-variable snapshot |
| **madExcept** (commercial) | Gold standard: full call stack + source line numbers |
| **JclDebug** (JEDI open source) | map symbols embedded at compile time |
| **EurekaLog** (commercial) | Supports remote reporting |

Prefer StackTrace.pas:
```pascal
uses StackTrace;
initialization
  TStackTraceManager.Current.EnableDefaultLogger;
  TStackTraceManager.Current.CaptureVariables := True;
end.
```
Once enabled, exceptions automatically produce a log (symbolized call stack + source line numbers + local variable values).


