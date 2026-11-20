# Check Environment — Build Environment Diagnostics

> Version: v1.0 | Last updated: 2026-06-08

---

## Contents

1. [Overview](#1-overview)
2. [Action Quick Reference](#2-action-quick-reference)
3. [Check — Check Environment](#3-check--check-environment)
4. [Detect — Detect Compilers](#4-detect--detect-compilers)
5. [Install — Install pasfmt](#5-install--install-pasfmt)
6. [Format Install — Install RAD Plugin](#6-format-install--install-rad-plugin)
7. [Supported Delphi Versions](#7-supported-delphi-versions)
8. [Workflows](#8-workflows)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Overview

`check_environment` is Daofy's environment diagnostic tool, used to check Delphi compiler status, re-detect installed compilers, and install the pasfmt formatting tool.

**In one sentence**: On first use or when compilation fails, call this tool first to confirm the environment is ready.

---

## 2. Action Quick Reference

| Action | Purpose |
|--------|------|
| `check` (default) | Check the current build environment status |
| `detect` | Re-detect Delphi compilers from the registry/specified path |
| `install` | Download and install the pasfmt formatting tool |
| `format_install` | Install the pasfmt RAD Studio IDE plugin |

---

## 3. Check — Check Environment

Default action; checks the current build environment status: lists all available compilers, and each compiler's version and path.

```python
check_environment(action="check")
```

**Returned information**:
- List of available compilers (name, version, path)
- Default compiler
- Whether pasfmt is installed
- Environment status (ready/partially ready/not ready)

---

## 4. Detect — Detect Compilers

Re-detect Delphi compilers from the Windows registry or a specified path, and update `config/compilers.json`.

```python
# Detect from the registry
check_environment(action="detect")

# Detect from a specified path
check_environment(action="detect", search_path="D:\Delphi\Studio")
```

**Detection process**:
1. Scan all versions under the registry key `HKEY_CURRENT_USER\SOFTWARE\Embarcadero\BDS`
2. Automatically detect the compiler path for each version (dcc32.exe / dcc64.exe)
3. Write to `config/compilers.json`

---

## 5. Install — Install pasfmt

Download and install **pasfmt**—a Delphi code formatting tool.

```python
# Download and install to the default location
check_environment(action="install")

# Install to a specified directory
check_environment(action="install", install_dir="C:\Tools\pasfmt")
```

After pasfmt is installed, `delphi_file(action="format")` is ready to use.

---

## 6. Format Install — Install RAD Plugin

Install pasfmt as a RAD Studio IDE plugin so you can use the formatting feature directly in the IDE.

```python
# Install to Delphi 11
check_environment(action="format_install", delphi_version="11")

# Install to Delphi 12
check_environment(action="format_install",
    delphi_version="12",
    install_dir="C:\pasfmt")
```

---

## 7. Supported Delphi Versions

Automatic registry detection supports the following versions:

| Version | Registry version number |
|------|------------|
| Delphi 13 Florence | 37.0 |
| Delphi 12 Athens | 23.0 |
| Delphi 11 Alexandria | 22.0 |
| Delphi 10.4 Sydney | 21.0 |
| Delphi 10.3 Rio | 20.0 |
| Delphi 10.2 Tokyo | 19.0 |
| Delphi 10.1 Berlin | 18.0 |
| Delphi 10 Seattle | 17.0 |
| Delphi XE8 | 16.0 |
| Delphi XE7 | 15.0 |
| Delphi XE6 | 14.0 |
| Delphi XE5 | 12.0 |
| Delphi XE4 | 11.0 |
| Delphi XE3 | 10.0 |
| Delphi XE2 | 9.0 |
| Delphi XE | 8.0 |
| Delphi 2010 | 7.0 |
| Delphi 2009 | 6.0 |
| Delphi 2007 | 5.0 |
| Delphi 2006 | 4.0 |
| Delphi 2005 | 3.0 |

---

## 8. Workflows

### First Use

```
check_environment(action="check")    → Confirm environment status
  ↓ Compiler not found
check_environment(action="detect")   → Detect from registry
  ↓
delphi_project(action="compile", ...)       → Start compiling
```

### When Compilation Fails

```
delphi_project(action="compile")  Failed
  ↓
check_environment(action="check")   → Confirm compiler status
  ↓ Compiler unavailable
check_environment(action="detect")  → Re-detect
  ↓
delphi_project(action="compile")  Retry
```

### Install the Formatting Tool

```
check_environment(action="install")          → Download pasfmt
  ↓
delphi_file(action="format", file_path=...)  → Use formatting
```

---

## 9. Troubleshooting

| Symptom | Cause | Solution |
|------|------|------|
| No compiler detected | Delphi is not installed or registry entries are missing | Use `search_path` to specify the path manually |
| Detected but compilation fails | Compiler version is incompatible | Check whether the path in `config/compilers.json` is correct |
| pasfmt installation fails | Network issues prevent download | Download manually and place it in the `tools/pasfmt/` directory |
| Plugin installation fails | Wrong RAD Studio version | Confirm that `delphi_version` matches the actual version |

