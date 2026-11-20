# Delphi Project — Project Full Lifecycle Management

> Version: v1.3 | Last updated: 2026-07-15

---

## Table of Contents

1. [Overview](#1-overview)
2. [Action Quick Reference](#2-action-quick-reference)
3. [Compilation](#3-compilation)
4. [Configuration Management](#4-configuration-management)
5. [Code Audit](#5-code-audit)
6. [Device Deployment](#6-device-deployment)
7. [Workflow Scenarios](#7-workflow-scenarios)
8. [Compilation Failure Troubleshooting](#8-compilation-failure-troubleshooting)
9. [Technical Architecture](#9-technical-architecture)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

`delphi_project` is the core tool in Daofy, providing **full lifecycle management** for Delphi projects—from creating projects and configuring compilation options to executing compilation, code auditing, and device deployment. It merges the functionality of the original three tools `compile_project`, `dproj_tool`, and `run_audit`, and adds device deployment capabilities.

**In one sentence**: All Delphi project compilation, configuration, audit, and deployment operations are performed through this tool.

| Function Domain | Covers |
|--------|------|
| **Compilation** | `.dproj`/`.dpr`/`.dpk` project compilation, .pas syntax check, parameter preview |
| **Configuration** | Read/create/modify `.dproj` configurations, add/remove source files, add/remove build configurations |
| **Audit** | AST skeleton extraction, 50+ static analysis rules, runtime registration check, DFM UI layout audit |
| **Deployment** | Enumerate connected devices (iOS/Android/Windows), deploy applications to devices |

### Hard Constraints

> ❌ **Do not run dcc32/msbuild via bash/cmd** (bypasses MSBuild event handling and dependency resolution)

---

## 2. Action Quick Reference

| Action | Purpose | Required Parameters |
|--------|------|---------|
| `compile` | Compile .dproj/.dpr/.dpk project | `project_path` |
| `compile_file` | Check .pas file syntax | `project_path` |
| `dry_run` | Preview compilation parameters without executing | — |
| `info` | Read complete .dproj information | `project_path` |
| `create` | Create new .dproj file | `project_path`, `main_source` |
| `set` | Set .dproj property value | `project_path`, `property_name`, `value` |
| `add_config` | Add build configuration | `project_path`, `config_name` |
| `remove_config` | Remove build configuration | `project_path`, `config_name` |
| `add_source` | Add source file reference | `project_path`, `source_file` |
| `remove_source` | Remove source file reference | `project_path`, `source_file` |
| `audit` | Run 50+ static analysis rules | — |
| `ast` | ⭐ Code skeleton extraction (most token-efficient) | `base_dir` |
| `runtime` | Runtime registration check | — |
| `layout` | Static DFM UI layout audit | `base_dir` or `file_path` |
| `devices` | Enumerate connected devices | — |
| `deploy` | Deploy application to device | `project_path`, `target_platform` |

---

## 3. Compilation

### 3.1 `compile` — Compile Project

Compile `.dproj`/`.dpr`/`.dpk` projects. Automatically detects compiler version and dependency paths.

```python
# Simplest call — automatically detects project type and configuration
delphi_project(action="compile", project_path="Project.dproj")

# Full compilation with parameters
delphi_project(action="compile",
    project_path="App.dproj",
    build_configuration="Release",
    target_platform="win64",
    conditional_defines=["RELEASE", "MY_FEATURE"],
    unit_search_paths=["C:\Libs\Common", "..\Shared"],
    optimize=True,
    debug=False,
    extra_args=["/p:DCC_DebugInfoInTds=true", "/p:DCC_RemoteDebug=true"],
    output_path=".\Build\Release")
```

**Parameters**:

| Parameter | Required | Default | Description |
|------|------|--------|------|
| `project_path` | ✅ | — | .dproj/.dpr/.dpk/.pas path |
| `target_platform` | ❌ | win32 | win32/win64/osx64/... |
| `build_configuration` | ❌ | Debug | Debug/Release |
| `compiler_version` | ❌ | Auto-detect latest | Specify Delphi version |
| `conditional_defines` | ❌ | — | Conditional compilation symbol array |
| `unit_search_paths` | ❌ | — | Additional unit search paths |
| `resource_search_paths` | ❌ | — | Resource search paths |
| `optimize` | ❌ | true | Whether to enable optimization |
| `debug` | ❌ | true | Whether to generate debug information |
| `warning_level` | ❌ | 2 | Warning level 0-4 |
| `disabled_warnings` | ❌ | — | Disabled warning number array |
| `output_type` | ❌ | gui | gui/console/dll |
| `runtime_library` | ❌ | static | static/dynamic |
| `timeout` | ❌ | 600 | Timeout in seconds |
| `auto_install` | ❌ | true | Only for .dpk: whether to auto-install to IDE |
| `run_verify` | ❌ | false | After compilation, launch for 3 seconds to verify no crash |
| `output_path` | ❌ | — | Compilation output directory |
| `extra_args` | ❌ | — | Complete argument array appended to the actual compilation backend |

#### Additional Compilation Parameters

Each element in `extra_args` must be a complete argument. Daofy appends these parameters after the built-in parameters and interprets them according to the actual backend:

```python
# .dproj or a .dpr with a same-named .dproj: uses MSBuild; requests TDS/RSM debug symbols
delphi_project(action="compile",
    project_path="Project.dproj",
    extra_args=["/p:DCC_DebugInfoInTds=true", "/p:DCC_RemoteDebug=true"])

# .dpr without a same-named .dproj: goes directly to DCC
delphi_project(action="compile",
    project_path="Project.dpr",
    extra_args=["-VT", "-VR"])
```

If the compiler generates `.tds` or `.rsm` files, they will be listed in the compilation result's `output_files`. Do not add outer quotes in array elements yourself; a single argument containing spaces is still passed as one array element.

#### Build Events

`PreBuildEvent`/`PostBuildEvent`/`PreLinkEvent` in `.dproj` are executed automatically; no manual handling is required.

#### `run_verify` — Crash Detection

After a successful compilation, automatically launches the exe for 3 seconds; if the process crashes, marks verification as failed. When `exception.log` is detected, automatically reads its contents and embeds them in the response.

### 3.2 `compile_file` — Syntax Check

Compile a single .pas file for syntax checking; does not generate an executable.

```python
delphi_project(action="compile_file", project_path="Unit1.pas")

# With search paths
delphi_project(action="compile_file",
    project_path="Unit1.pas",
    unit_search_paths=["..\Shared"],
    conditional_defines=["TEST"])
```

### 3.3 `dry_run` — Preview Compilation Parameters

Does not actually execute compilation; only displays the compiler path and full command-line arguments that would be used.

```python
delphi_project(action="dry_run", project_path="Project.dproj", build_configuration="Release")
```

---

## 4. Configuration Management

### 4.1 `info` — Read Project Information

Read the complete structured information of a `.dproj` file: build configurations, source file list, resource files, build events, etc.

```python
delphi_project(action="info", project_path="Project.dproj")
```

### 4.2 `create` — Create Project

Create a new `.dproj` project file, optionally generating Form stub code at the same time.

```python
# Minimal creation
delphi_project(action="create",
    project_path="MyApp.dproj",
    main_source="MyApp.dpr")

# Creation with Form stub code
delphi_project(action="create",
    project_path="MyApp.dproj",
    main_source="MyApp.dpr",
    framework_type="VCL",
    form_units=["Unit1", "MainForm"],
    configs=["Debug", "Release", "Staging"])
```

**Parameters**:

| Parameter | Required | Default | Description |
|------|------|--------|------|
| `project_path` | ✅ | — | Project file path |
| `main_source` | ✅ | — | Main source file (.dpr) |
| `project_guid` | ❌ | Auto-generated | Project GUID