# Compilation Toolchain Configuration — Delphi Version and MSBuild

> Version: v1.0 | Last updated: 2026-10-31

This document explains how Daofy selects the **Delphi version** and **MSBuild**, and how to configure single-version, multi-version, legacy Delphi, package installation, deployment, CI, and other scenarios.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Configuration Files and Lookup Order](#2-configuration-files-and-lookup-order)
3. [Project-Level Configuration Parameters](#3-project-level-configuration-parameters)
4. [Global Configuration Parameters](#4-global-configuration-parameters)
5. [Selection Priority](#5-selection-priority)
6. [Typical Scenarios](#6-typical-scenarios)
7. [Diagnostics and Error Codes](#7-diagnostics-and-error-codes)
8. [Migrating from Old Configuration](#8-migrating-from-old-configuration)
9. [Notes](#9-notes)

---

## 1. Overview

Daofy's compilation toolchain consists of three parts:

| Part | Purpose |
|------|---------|
| **Delphi version** | Determines `rsvars.bat`, `dcc32/dcc64`, RTL/third-party library search paths, BPL/DCP directories, and IDE registry entries |
| **MSBuild path** | Determines which `MSBuild.exe` is used to compile `.dproj` |
| **Compiler configuration** | `dcc32.exe` / `dcc64.exe` paths in `compilers.json`, used for direct compilation and single-file compilation |

Core principle:

> **The Delphi version, MSBuild, and library paths used by the same project must come from the same toolchain and must not be mixed across versions.**

---

## 2. Configuration Files and Lookup Order

### 2.1 Project-Level Configuration (Recommended)

Place the following in the project directory or any parent directory:

```text
<project directory>/.daofy/project.json
<project directory>/daofy.project.json
```

Lookup order:

1. Start from the directory containing the `.dproj` / `.dpr` / `.dpk`
2. First look for `.daofy/project.json`, then `daofy.project.json`
3. If not found, search upward through parent directories, up to 8 levels
4. **The configuration file closest to the project takes effect**; fields not written in the same configuration file continue to be looked up according to the next-level rules

It is recommended to place the configuration in the project root directory:

```text
MyWorkspace/
├─ LegacyApp/
│  ├─ .daofy/project.json      ← LegacyApp uses XE4
│  └─ LegacyApp.dproj
├─ ModernApp/
│  ├─ .daofy/project.json      ← ModernApp uses Delphi 12
│  └─ ModernApp.dproj
└─ Shared/
   └─ .daofy/project.json      ← Workspace default (optional)
```

### 2.2 Global Configuration (`compilers.json`)

`compilers.json` stores the compiler list and the MSBuild mapped by version:

```text
<Python environment>/Lib/site-packages/src/config/compilers.json   # pip installation
<project root>/src/config/compilers.json                          # running from source
```

> Global configuration no longer provides a switch to "pin all projects to the same version / use the same MSBuild for all projects". Use project-level configuration for per-project differences.

---

## 3. Project-Level Configuration Parameters

Minimal example:

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

### 3.1 Parameter Table

| Field | Type | Required | Description |
|------|------|------|------|
| `delphi_version` | string | No | Delphi version used by the project |
| `compiler_version` | string | No | Compiler name in `compilers.json`; a version number can also be written directly |
| `msbuild_path` | string | No | `MSBuild.exe` used by the project; relative paths are resolved relative to the directory containing the configuration file |

All three fields can be used independently or in combination. Fields not written continue to use global/automatic detection.

### 3.2 Supported Formats for `delphi_version`

```json
{ "delphi_version": "11.0" }
```

| Format | Explanation |
|------|------|
| `"11.0"` / `"11"` | Registry version 11.0 = **Delphi XE4** |
| `"16.0"` | Delphi XE8 |
| `"19.0"` | Delphi 10.2 Tokyo |
| `"22.0"` / `"Delphi 11 Alexandria"` | Delphi 11 Alexandria |
| `"23.0"` / `"Delphi 12 Athens"` | Delphi 12 Athens |
| `"XE4"` / `"Delphi XE4"` | Match by product name |
| `"14.6"` | `.dproj ProjectVersion` → registry 14.0 (XE6) |
| `"18.2"` | `.dproj ProjectVersion` → registry 18.0 (10.1 Berlin) |
| `"19.2"` | `.dproj ProjectVersion` → registry 19.0 (10.2 Tokyo) |

Note the ambiguity of plain numbers:

- `"12.0"` means **registry version 12.0 = XE5**
- To mean **Delphi 12 Athens**, write `"23.0"` or `"Delphi 12 Athens"`

### 3.3 `compiler_version`

Used to directly specify a compiler in `compilers.json`, for example:

```json
{
  "compiler_version": "Delphi XE4 Win32"
}
```

Version numbers/product names are also supported:

```json
{
  "compiler_version": "11.0"
}
```

Priority and conflict rules:

- When both `compiler_version` and `delphi_version` are configured, **`compiler_version` takes precedence**; if the versions are inconsistent, a warning is logged
- If `compiler_version` is wrong but `delphi_version` is valid, it falls back to `delphi_version`
- If neither is available, it **fails directly** and does not fall back to another Delphi version

### 3.4 `msbuild_path`

```json
{
  "msbuild_path": "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe"
}
```

- Absolute paths are used directly
- Relative paths are resolved relative to **the directory containing the configuration file**, for example:

```text
<project>/.daofy/project.json
<project>/tools/MSBuild.exe
```

```json
{ "msbuild_path": "tools/MSBuild.exe" }
```

- If the path does not exist, MSBuild compilation fails directly with `MSBUILD_CONFIG_INVALID` and **does not fall back to another MSBuild**
- When a `.dpr` / `.dpk` has a corresponding `.dproj`, it also does not fall back to direct dcc compilation to mask configuration errors

### 3.5 Configuration Validation

The following cases cause compilation to fail directly instead of being silently ignored:

- The configuration file is not valid JSON
- `delphi_version` cannot be recognized
- The file pointed to by `msbuild_path` does not exist
- Neither `compiler_version` nor `delphi_version` can be resolved

---

## 4. Global Configuration Parameters

### 4.1 `compilers` Array

```json
{
  "compilers": [
    {
      "name": "Delphi XE4 Win32",
      "path": "C:\\Embarcadero\\RAD Studio\\11.0\\bin\\dcc32.exe",
      "is_default": false,
      "version": "Delphi XE4",
      "registry_version": "11.0",
      "compiler_type": "delphi"
    }
  ],
  "default_compiler": "Delphi XE4 Win32"
}
```

| Field | Description |
|------|------|
| `name` | Compiler display name, also the name matched by `compiler_version` |
| `path` | Path to `dcc32.exe` / `dcc64.exe` |
| `is_default` | Whether it is the default compiler |
| `version` | Product name, e.g. `"Delphi XE4"` |
| `registry_version` | Registry version number, e.g. `"11.0"`; if missing, matching can fall back by product name |
| `compiler_type` | `"delphi"` or `"lazarus"` |

### 4.2 `default_compiler`

Default compiler name. When there is no project configuration, direct compilation prioritizes it.

### 4.3 `show_timing`

Whether the tool response includes the `timing` field.

### 4.4 `msbuild_by_delphi_version`

Maps MSBuild by Delphi version, suitable for scenarios such as "on this machine XE4 uses v3.5 and Delphi 12 uses VS2022":

```json
{
  "msbuild_by_delphi_version": {
    "11.0": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe",
    "16.0": "C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319\\MSBuild.exe",
    "23.0": "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe"
  }
}
```

- Keys support registry version numbers, product names (`"XE4"`), or `.dproj ProjectVersion` (`"14.6"`)
- Values support absolute paths or relative paths based on the directory containing `compilers.json`
- If a mapping is configured but does not match the current version, a warning is output to the log
- If the mapped path is invalid, it fails directly

### 4.5 Removed Configurations

The following configurations have been removed. Keys in old files are ignored and a migration warning is output:

| Removed | Replacement |
|--------|----------|
| `msbuild_path` | Project-level `msbuild_path` or `msbuild_by_delphi_version` |
| `default_registry_version` | Project-level `delphi_version` |
| Environment variable `DAOFY_MSBUILD` | Project-level `msbuild_path` |
| Environment variable `DAOFY_DELPHI_VERSION` | Project-level `delphi_version` |

---

## 5. Selection Priority

### Delphi Version

```text
Tool parameter compiler_version
> Project configuration compiler_version
> Project configuration delphi_version
> .dproj ProjectVersion inference
```

### MSBuild

```text
Project configuration msbuild_path
> msbuild_by_delphi_version[version] in compilers.json
> Automatic detection
```

Automatic detection order:

1. Prioritize by project Delphi version: XE4 and earlier look for `.NET Framework\v3.5\MSBuild.exe`
2. XE5–10 Seattle look for `.NET Framework\v4.0.30319\MSBuild.exe`
3. `vswhere` queries Visual Studio 2017+
4. Common VS 2019/2022 installation paths
5. MSBuild bundled in the Delphi installation directory
6. `msbuild.exe` in `PATH`

> Automatic detection is heuristic. For scenarios where "a specific Delphi version must be paired with a specific VS/MSBuild", configure it explicitly.

---

## 6. Typical Scenarios

### 6.1 Single Delphi Version, No Special Requirements

No configuration is required. Daofy will:

- Read the only installed Delphi version from the registry
- Automatically detect MSBuild
- Use the default compiler in `compilers.json`

### 6.2 Multiple Delphi Versions, Different Projects Use Different Versions

It is recommended to configure each project separately:

**XE4 Project**

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

**XE8 Project**

```json
{
  "delphi_version": "16.0"
}
```

**Delphi 10.2 Tokyo Project**

```json
{
  "delphi_version": "19.0",
  "msbuild_path": "C:\\Program Files (x86)\\Microsoft Visual Studio\\2019\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe"
}
```

This way, the XE4 project will not use the wrong `rsvars.bat`, dcc, or library paths because Delphi 12 is also installed on the machine.

### 6.3 `.dproj ProjectVersion` Is Inconsistent with the Delphi Version You Want to Use

For example, the project file contains:

```xml
<ProjectVersion>14.6</ProjectVersion>
```

14.6 corresponds to XE6 (registry 14.0), but you want to compile with XE4. **Configuring only `msbuild_by_delphi_version["11.0"]` will not take effect**, because the inferred version is 14.0. You must explicitly write:

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

### 6.4 Legacy Delphi (XE4 and Earlier) Requires .NET 3.5 MSBuild

XE4 and other old versions usually require:

```text
C:\Windows\Microsoft.NET\Framework\v3.5\MSBuild.exe
```

If this file does not exist:

- Automatic detection outputs a warning and then continues to try the MSBuild from VS/PATH (may be incompatible)
- It is recommended to install .NET Framework 3.5, or point to a usable compatible MSBuild in the project configuration
- If you need strict failure instead of trying other MSBuild, write a project-level `msbuild_path` directly; an invalid path will immediately error

### 6.5 No Visual Studio on the Machine, Only Delphi

Automatic detection will continue to check:

- MSBuild bundled in the Delphi installation directory
- `msbuild.exe` in `PATH`

If neither exists:

- `.dproj` compilation returns `MSBUILD_NOT_FOUND`
- When `.dpr` / `.dpk` has a `.dproj`, it falls back to direct dcc compilation
- The most reliable way is to configure a usable `msbuild_path` for the project

### 6.6 Package Installation (`install_package`)

The project configuration of the package project applies to all of the following:

- `rsvars.bat` version
- Delphi/MSBuild used for compilation
- BPL/DCP output directories (`Documents\Embarcadero\Studio\<version>\...`)
- IDE `Known Packages` registry entry (`HKCU\Software\Embarcadero\BDS\<version>\Known Packages`)

Therefore, do not place an XE4 package project in an environment with a global default of Delphi 12 and install it directly; add `.daofy/project.json` to the package project.

### 6.7 Deployment (`deploy`)

During deployment, the MSBuild version is also resolved according to the project configuration.

> Known limitation: the deployment process currently only resolves the MSBuild path and does not automatically execute `rsvars.bat`. If the deployment target depends on `BDS`/Delphi environment variables, first load the corresponding version of `rsvars.bat` in the terminal that starts MCP.

### 6.8 CI / Team Collaboration

- Commit `.daofy/project.json` to the repository to ensure every machine/Agent uses the same toolchain
- Do not commit the machine-specific `compilers.json` to the repository (it is already in `.gitignore`)
- CI machines need the corresponding Delphi version installed and must ensure that `compilers.json` contains the corresponding compiler paths
- Legacy Delphi requires additional confirmation that the `.NET Framework v3.5` MSBuild is installed

### 6.9 Workspace Default + Project Override

You can place a default configuration in the workspace root and then override it in subprojects:

```text
Workspace/
├─ .daofy/project.json          { "delphi_version": "16.0" }   ← Workspace default XE8
├─ Legacy/
│  └─ .daofy/project.json       { "delphi_version": "11.0" }   ← Override to XE4
└─ Modern/
   └─ Legacy.dproj
```

The configuration found closest to the project takes precedence; subprojects only need to write the fields that need to be overridden.

---

## 7. Diagnostics and Error Codes

### 7.1 `check_environment`

```python
check_environment(action="check")
```

You can view:

- Compiler list and whether paths are valid
- Default compiler
- Mapping of `msbuild_by_delphi_version` and whether files exist
- Project-level configuration entry hints

> `check_environment` shows global compilers and version mappings; the version/MSBuild ultimately selected for a project is subject to the compilation log.

### 7.2 Common Error Codes

| Error Code | Meaning | Resolution |
|--------|------|----------|
| `MSBUILD_NOT_FOUND` | Automatic detection cannot find MSBuild | Install VS/Build Tools, or write `msbuild_path` in the project configuration |
| `MSBUILD_CONFIG_INVALID` | The MSBuild path in the project/version mapping is invalid | Fix the path; it will not fall back to another MSBuild |
| `RSVARS_NOT_FOUND` | The target Delphi version is not installed or the registry entry is missing | Install the corresponding Delphi, or fix `delphi_version` |
| `COMPILER_VERSION_UNRESOLVED` | The project `compiler_version` is invalid and the version cannot be inferred | Fix `compiler_version`, or use `delphi_version` instead |
| `COMPILER_NOT_FOUND` | No usable compiler in `compilers.json` | Run `check_environment(action="detect")` or manually add the configuration |
| `PROJECT_CONFIG_INVALID` | Project configuration JSON/`delphi_version` is invalid | Fix `.daofy/project.json` |
| `INVALID_PROJECT_PATH` | The project path does not exist or is not `.dproj/.dpr/.dpk` | Check `project_path` |

### 7.3 Configuration Does Not Take Effect

1. Confirm that the configuration file is in the project directory or a parent directory and that the file name is `.daofy/project.json` or `daofy.project.json`
2. Confirm that the JSON is valid (comments are not supported)
3. Confirm that you have **restarted the Daofy MCP service/IDE** after the modification
4. Check whether "loading project configuration ..." appears in the log
5. Old global configurations/environment variables have been removed; do not use `msbuild_path` in `compilers.json`, `default_registry_version`, or `DAOFY_*` environment variables anymore

---

## 8. Migrating from Old Configuration

If you previously used:

```json
{
  "msbuild_path": "...",
  "default_registry_version": "11.0"
}
```

Please change to project-level configuration:

```text
<project>/.daofy/project.json
```

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

If you only want "a certain version corresponds to a certain MSBuild", keep the global mapping:

```json
{
  "msbuild_by_delphi_version": {
    "11.0": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
  }
}
```

The environment variables `DAOFY_MSBUILD` / `DAOFY_DELPHI_VERSION` no longer take effect; remove them from the MCP client configuration.

---

## 9. Notes

- **Project configuration can specify arbitrary executable paths and should only be used in trusted projects**
- Explicit configuration takes precedence over automatic detection; when an explicit configuration is invalid, it fails directly and does not "guess" another version
- `msbuild_by_delphi_version` is only responsible for MSBuild and does not change the Delphi version; to override `.dproj ProjectVersion`, you still need project-level `delphi_version`
- When automatically matching compilers, if no compiler is configured for the `.dproj` version, it may still fall back to a higher version according to the original strategy (a warning is logged); use project-level `delphi_version` when strict versioning is required
- After modifying the configuration, you need to restart the MCP service/IDE
- Version numbers, compiler paths, and MSBuild paths are all machine-related configurations. It is recommended to only include `.daofy/project.json` in version control and not commit `compilers.json`

---

## Appendix: Complete Example

```json
{
  "delphi_version": "11.0",
  "compiler_version": "Delphi XE4 Win32",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

Corresponding `compilers.json` fragment:

```json
{
  "compilers": [
    {
      "name": "Delphi XE4 Win32",
      "path": "C:\\Embarcadero\\RAD Studio\\11.0\\bin\\dcc32.exe",
      "is_default": false,
      "version": "Delphi XE4",
      "registry_version": "11.0",
      "compiler_type": "delphi"
    }
  ],
  "default_compiler": "Delphi XE4 Win32"
}
```