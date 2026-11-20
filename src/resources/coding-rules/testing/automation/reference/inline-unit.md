<!-- @when: Need to integrate a Delphi project with the automation framework, or understand the in-process automation transport protocol -->
<!-- @chain: after=workflow.md -->

# Delphi Inline Automation Unit

The Delphi-side code is located at `tools/auto`.

MCP resource URI: `delphi://automation/inline-unit`.

## File List

| File | Function |
|------|------|
| `DaofyAutomation.Base.pas` | Transport interface, JSON protocol, command dispatch, and async result cache |
| `DaofyAutomation.Windows.pas` | Windows NamedPipe transport implementation and Overlapped I/O |
| `DaofyAutomation.Posix.pas` | POSIX Unix Domain Socket transport implementation and self-pipe wakeup |
| `Vcl.DaofyAutomation.pas` | VCL control lookup, screenshots, RTTI operations |
| `Fmx.DaofyAutomation.pas` | FMX control lookup, screenshots, RTTI operations |
| `DaofyAutomation.RttiDiscovery.pas` | Runtime RTTI capability discovery |
| `DaofyAutomation.RttiAttributes.pas` | Optional AI annotation attribute declarations |
| `DaofyAutomation.CallGraph.pas` | Optional call graph command extension; `tools\stacktrace` must also be added to the search path |

## Project Integration

VCL `.dpr` example:
```pascal
uses
  Vcl.Forms,
  Vcl.DaofyAutomation in 'C:\path\to\tools\auto\Vcl.DaofyAutomation.pas',
  MainForm in 'MainForm.pas' {MainForm};
begin
  Vcl.DaofyAutomation.AutoStart;
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
```
FMX uses `Fmx.DaofyAutomation`.

It is recommended to add `tools\auto` to the project search path to avoid listing all supporting units in the `.dpr`. If you need `callgraph`/`callgraph_diff`/`callgraph_path`/`callgraph_impact` and the purpose-level `callgraph_*` commands, you also need to add `tools\stacktrace` to the search path and additionally `uses DaofyAutomation.CallGraph` in the project.

## Protocol Description

- Transport is abstracted by `IAutomationTransport`; `TAutomationProcessorBase.CreateTransport` selects `TNamedPipeTransport` on Windows and `TUnixSocketTransport` on POSIX.
- Windows endpoints are derived from `\\.\pipe\daofy_auto`; POSIX endpoints use Unix Domain Sockets. The process registration file's `pipe` field is retained for compatibility with the old protocol; its value is the actual endpoint address returned by the transport layer.
- Both transports carry the same UTF-8 JSON requests/responses, and the command layer does not depend on the specific endpoint type.
- Asynchronous commands (return ACK, Python polls `peekresult`): `click`/`rclick`/`dblclick`/`hover`/`move`/`drag`/`msgclick`/`dlgclick`/`rcall`/`key`/`rset`/`type`.
- Synchronous commands (blocking wait): `goto`/`capture`/`waitfor`/`wait`/`dumpstate`/`listwnd`/`dlgscan`/`msgscan`/`msgclose`/`dlgfile`/`snapdir`/`exit`/`rget`/`rinspect`/`peekresult`; optional diagnostic commands `callgraph`/`callgraph_diff`/`callgraph_path`/`callgraph_impact` and purpose-level `callgraph_*` require additionally referencing `DaofyAutomation.CallGraph` and generating a Detailed-level `.map`. `callgraph` supports `direction=callees|callers`, `project_only`, `exclude_prefixes`, `include_prefixes`, `edge_limit`; the response contains `edge_count`, `returned_count`, `truncated`, and each edge contains `call_addr`, `call_file`, `call_line`, `category`, `from_category`, `to_category`; `callgraph_path` supports `source`, `target`, `max_depth`, `max_paths`, `include_prefixes`; `callgraph_diff` defaults to `compare_by=name`, with optional `addr|full`, and `baseline_path`/`save_as` and file-based graph/impact inputs at the purpose level are restricted to within `snapshots_dir`; `callgraph_impact` supports `functions`/`targets` or `file`+`line`/`locations`, queries callers in batch, and aggregates entry candidates.

`msgscan` returns `data="NOD"` (no MessageBox); when it returns `data="OK"`, it writes the MessageBox JSON to `_formstate.json`, and Daofy loads it into `response.state` for assertions and report checks.

### dumpstate Property Whitelist

`dumpstate` accepts a `props` parameter (comma-separated property name list) and outputs only the specified properties (skipping the `IsSkippedProp` blacklist). If not provided, it returns all filtered properties.
```
dumpstate                        → all properties (filtered by IsSkippedProp + unnamed control)
dumpstate props=caption,enabled  → only Caption and Enabled
dumpstate props=name,class,items → only name, class, and collection items
```
Unnamed controls (`Name=''`) and collection items with empty captions are not output.

### Generic RTTI Item Click

`click` supports the `ControlName@ItemCaption` syntax, finding and clicking items in any `TCollection` property through generic RTTI, with no VCL type binding required.
```
click cbMenus@打开工程...   → find the item with Caption="打开工程..." and click its Bounds center
```
Key implementation methods (`Vcl.DaofyAutomation.pas`):
- `ReadItemCaption(Item)` — RTTI reads the `Caption` property, falling back to `Text`
- `TryGetItemBounds(Item, out R)` — RTTI reads the fields of `Bounds` one by one (Left/Top/Right/Bottom)
- `TryFindAndClickItem(Ctrl, SearchCaption)` — scans all TCollection properties + nested collections, matches captions with `AnsiContainsText`, and clicks the Bounds center

Caption matching is case-insensitive (`AnsiContainsText`) and does not require referencing type-related units such as `Vcl.CategoryButtons`.

### FindDialog Behavior of msgscan/msgclick/msgclose

FindDialog has been rewritten: from the simple `FindWindowW('#32770', nil)` to `EnumWindows` + `IsWindowVisible` + title/class name matching.
- `FindDialog` accepts two filter parameters: `ATitle` (window title substring, case-insensitive) and `AClass` (dialog class name, default `#32770`)
- It checks the foreground window first, then traverses with `EnumWindows` and filters by `IsWindowVisible`
- The old behavior returned the first `#32770` HWND found — it failed when there was a hidden residual HWND
- Call examples: `msgscan target:'浏览' class:'#32770'` / `msgclick target:'确定'` / `msgclose class:'#32770'`
- `msgclose` also filters through `IsWindowVisible` to avoid closing residual HWNDs

### FindControl Fallback (Delphi Forms)

`dlgscan` uses a different strategy: `GetForegroundWindow` → `FindControl` to detect a Delphi `TForm` (fsModal) dialog. It falls back to Win32 `#32770` class detection. The VCL override can detect `TForm` (fsModal), scan the `TButton`s in its `Controls`, and return structured JSON (containing `type`/`class`/`title`/`text`/`name`/`buttons: [{caption, modalresult}]`).

### peekresult

`peekresult` consumes one result at a time and is protected by `FAsyncResultsCS` for thread safety.

