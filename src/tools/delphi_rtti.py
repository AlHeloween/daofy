"""MCP Tool: delphi_rtti — Delphi RTTI Bridge

Discover and invoke runtime capabilities of Delphi applications.

Three-step workflow:
  ① discover → scan methods and parameter schemas exposed via RTTI
  ② call → invoke methods
  ③ guide → return the complete usage guide
"""

import json
import time
import ctypes
from ctypes import wintypes

from src.services.rtti_bridge import get_rtti_bridge
from src.services.automation_service import _send_command_to_pipe


def _call_via_pipe(pipe_name: str, req: dict, timeout_ms: int = 15000) -> dict:
    """Invoke rcall through the pipe (async protocol: ack → poll peekresult).

    rcall is asynchronous on the Delphi side:
      1. Immediately returns {"status":"ack"}
      2. The main thread processes it and stores the result in FAsyncResults (keyed by reqId)
      3. The client must poll with the peekresult command until the result is ready
    """
    from src.services.automation_service import (
        _open_pipe, _write_pipe, _read_pipe_message, _CloseHandle,
        _send_command_to_pipe, _GetLastError,
    )

    req_id = req.get("reqId", "call_" + str(int(time.time() * 1000)))
    req["reqId"] = req_id

    # Step 1: send rcall and read ack
    handle = _open_pipe(pipe_name, timeout_ms)
    if handle is None:
        return {"status": "error", "message": f"pipe_unavailable (err={_GetLastError()})"}
    try:
        cmd_bytes = json.dumps(req, ensure_ascii=False).encode("utf-8")
        if not _write_pipe(handle, cmd_bytes):
            return {"status": "error", "message": f"write_failed (err={_GetLastError()})"}

        raw = _read_pipe_message(handle)
        if raw is None:
            return {"status": "error", "message": "no ack response"}
        ack_resp = json.loads(raw.decode("utf-8", errors="replace").strip())
        if ack_resp.get("status") != "ack":
            # Unexpected: returned the actual result directly
            data_raw = ack_resp.get("data", "")
            if data_raw:
                try:
                    data_resp = json.loads(data_raw)
                    return {
                        "status": data_resp.get("status", "ok"),
                        "data": data_resp.get("data", ""),
                        "response": ack_resp,
                    }
                except (json.JSONDecodeError, TypeError):
                    pass
            return {
                "status": ack_resp.get("status", "error"),
                "data": data_raw,
                "response": ack_resp,
            }
    finally:
        _CloseHandle(handle)

    # Step 2: poll peekresult
    deadline = time.time() + (timeout_ms / 1000)
    peek_req = json.dumps({
        "reqId": f"peek_{req_id}",
        "cmd": "peekresult",
        "target": req_id,
    }, ensure_ascii=False)

    while time.time() < deadline:
        resp = _send_command_to_pipe(pipe_name, peek_req, 5000)
        if resp.startswith("ERR:"):
            time.sleep(0.1)
            continue

        try:
            peek = json.loads(resp)
        except (json.JSONDecodeError, TypeError):
            time.sleep(0.1)
            continue

        if peek.get("status") != "ok":
            time.sleep(0.1)
            continue

        data_raw = peek.get("data", "")
        if data_raw.startswith("NR:"):
            # Result not ready yet; wait for the main thread to finish processing rcall
            time.sleep(0.1)
            continue

        # Result is ready! (the data field contains the complete response JSON returned by HandleRCall)
        try:
            result_resp = json.loads(data_raw)
            if isinstance(result_resp, dict):
                return {
                    "status": result_resp.get("status", "ok"),
                    "data": result_resp.get("data", ""),
                    "response": result_resp,
                }
            # Not a dict (e.g., JSON array) → return directly as data
            return {
                "status": "ok",
                "data": data_raw,
            }
        except (json.JSONDecodeError, TypeError):
            return {
                "status": "ok",
                "data": data_raw,
            }

    return {"status": "error", "message": f"timeout: result not ready for req_id={req_id}"}

# ── Complete usage guide (L3 loaded on demand)──

RTTI_GUIDE = """\
# Delphi RTTI Bridge — Usage Guide

## Overview
Discover and invoke runtime capabilities of an application through Delphi's Enhanced RTTI.

## Prerequisites
- The Delphi application has linked the DaofyAutomation unit (VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation)
- The application is compiled and running, and the named pipe is ready

## Three-step workflow

### Step 1: Connect and discover
```
delphi_rtti(action="discover", app_path="C:\\App\\MyApp.exe")
```
Returns the list of published+public methods/properties for all classes in the application, including:
- Method names and parameter Schema (JSON Schema format)
- Parameter type mapping
- Whether parameters are required

### Step 2: View capability details
The tools array returned by discover includes the following for each method:
- name: method name
- description: method description
- parameters: parameter definitions in JSON Schema format

### Step 3: Invoke a method
```
delphi_rtti(
  action="call",
  app_path="C:\\App\\MyApp.exe",
  class_name="TMainForm",
  method="CreateOrder",
  params={"customerName": "John Doe", "amount": 100}
)
```

## Type Mapping
| Delphi Type | JSON Type | Description |
|------------|----------|------|
| string (UnicodeString, AnsiString, etc.) | string | UTF-8 encoding |
| Integer, SmallInt, Int64, etc. | integer | |
| Single, Double, Currency | number | |
| Boolean, ByteBool | boolean | |
| TDateTime | string | format: date-time |
| TObject / TPersistent | object | Child object (limited support) |
| TArray<T> / array of ... | array | Element types mapped recursively |
| TStrings / TStringList | array of string | |
| Enum type | string | With enum constraints |

## AI Annotations (Custom Attributes)

Add attribute annotations with the `AI` prefix on Delphi methods or parameters to provide richer context to AI Agents:

| Attribute | Applied To | Description |
|------|---------|------|
| `[AIDescription('...')]` | Method | Function description |
| `[AIResultDescription('...')]` | Method | Return value description |
| `[AIExample('...')]` | Method | Call example |
| `[AIParamDescription('...')]` | Parameter | Parameter meaning |

Example:
```pascal
[AIDescription('Create a customer order and return the new order number')]
[AIResultDescription('Newly created order number; returns -1 on failure')]
[AIExample('CreateOrder("John Doe", 100) → 10001')]
function CreateOrder(
  [AIParamDescription('Customer name')] const customerName: string;
  [AIParamDescription('Order amount (CNY)')] amount: Integer
): Integer;
```

After annotation, the JSON Schema returned by discover carries fields such as `description` and `example`.

## Best Practices
1. **Discover first, then call** — always obtain the capability list first
2. **Cache discovery results** — an application's capabilities do not change during its lifetime
3. **Use keep_alive** — keep the process alive for scenarios with multiple calls
4. **Match parameter types** — refer to the type mapping table to ensure parameter types are correct

## Troubleshooting
- "pipe_unavailable" → confirm that the Delphi application is started and linked with DaofyAutomation (VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation)
- Method invocation fails → check whether parameter names and types match the Schema returned by discover
- Empty result → confirm that the target class's methods are marked as published or public
"""


async def handle_delphi_rtti(arguments: dict) -> dict:
    """Handle delphi_rtti tool calls.

    Args:
        arguments: Tool parameter dictionary containing action/app_path/class_name/method/params

    Returns:
        dict: Response containing content and isError
    """
    action = arguments.get("action", "guide")
    bridge = get_rtti_bridge()

    if action == "guide":
        return {
            "content": [{"type": "text", "text": RTTI_GUIDE}],
            "isError": False,
        }

    if action == "list":
        result = bridge.list_running_apps()
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": result.get("status") == "error",
        }

    app_path = arguments.get("app_path", "")
    pipe = arguments.get("pipe", "")

    if not app_path and not pipe:
        return {
            "content": [{"type": "text", "text": "Error: app_path or pipe is required"}],
            "isError": True,
        }

    if action == "discover":
        class_name = arguments.get("class_name", "")
        force = arguments.get("force", False)
        keep_alive = arguments.get("keep_alive", False)

        if pipe:
            # Use an already running pipe (no app_path needed)
            result = bridge.discover_from_pipe(pipe, class_name, force)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                "isError": result.get("status") == "error",
            }

        # Traditional way: connect via app_path
        conn = bridge.connect(app_path)
        if conn.get("status") == "error":
            return {
                "content": [{"type": "text", "text": json.dumps(conn, ensure_ascii=False, indent=2)}],
                "isError": True,
            }

        result = bridge.discover(app_path, class_name, force)

        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": result.get("status") == "error",
        }

    elif action == "call":
        class_name = arguments.get("class_name", "")
        method = arguments.get("method", "")
        params = arguments.get("params", {})

        if not class_name:
            return {
                "content": [{"type": "text", "text": "Error: class_name is required"}],
                "isError": True,
            }
        if not method:
            return {
                "content": [{"type": "text", "text": "Error: method is required"}],
                "isError": True,
            }

        if pipe:
            # Invoke through an existing pipe (no app_path needed)
            req = {
                "reqId": f"call_{int(time.time() * 1000)}",
                "cmd": "rcall",
                "target": class_name,
                "method": method,
            }
            if params:
                req["params"] = json.dumps(params, ensure_ascii=False)
            result = _call_via_pipe(pipe, req)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                "isError": result.get("status") == "error",
            }

        # Traditional way: via app_path
        conn = bridge.connect(app_path)
        if conn.get("status") == "error":
            return {
                "content": [{"type": "text", "text": json.dumps(conn, ensure_ascii=False, indent=2)}],
                "isError": True,
            }

        result = bridge.call(app_path, class_name, method, params)
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": result.get("status") == "error",
        }

    return {
        "content": [{"type": "text", "text": f"Unknown action: {action}, available: guide, discover, call, list"}],
        "isError": True,
    }