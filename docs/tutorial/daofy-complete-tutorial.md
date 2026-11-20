# Daofy for Delphi Complete User Guide

> **Version**: v2026.06.15.1 | **Last Updated**: 2026-06-20

---

## Table of Contents

- [Chapter 1: Daofy Overview](#chapter-1-daofy-overview)
- [Chapter 2: Installation and Configuration](#chapter-2-installation-and-configuration)
- [Chapter 3: Environment Check and Diagnostics](#chapter-3-environment-check-and-diagnostics)
- [Chapter 4: Knowledge Base Search and Management](#chapter-4-knowledge-base-search-and-management)
- [Chapter 5: Project Compilation and Configuration Management](#chapter-5-project-compilation-and-configuration-management)
- [Chapter 6: Delphi File Operations](#chapter-6-delphi-file-operations)
  - [6.1 Tool Overview](#61-tool-overview)
  - [6.2 Action Quick Reference](#62-action-quick-reference)
  - [6.3 Line Number Rules](#63-line-number-rules)
  - [6.4 Read Files](#64-read-files)
  - [6.5 Write Files](#65-write-files)
  - [6.6 Format Code](#66-format-code)
  - [6.7 Backup Management](#67-backup-management)
  - [6.8 Uses Clause Management](#68-uses-clause-management)
  - [6.9 Encoding Conversion (encode)](#69-encoding-conversion-encode)
  - [6.10 Dirty Marker Mechanism](#610-dirty-marker-mechanism)
- [Chapter 7: Coding Standards and Code Audit](#chapter-7-coding-standards-and-code-audit)
- [Chapter 8: Code Hosting and Git Operations](#chapter-8-code-hosting-and-git-operations)
- [Chapter 9: Experience Memory Management](#chapter-9-experience-memory-management)
- [Chapter 10: Delphi RTTI Bridge](#chapter-10-delphi-rtti-bridge)
- [Chapter 11: Automated Testing](#chapter-11-automated-testing)
- [Chapter 12: OCR Image Text Recognition](#chapter-12-ocr-image-text-recognition)
- [Chapter 13: Component Management](#chapter-13-component-management)
- [Chapter 14: Component Package Management](#chapter-14-component-package-management)
- [Chapter 15: Asynchronous Task Management](#chapter-15-asynchronous-task-management)
- [Chapter 16: Daofy Self-Update Management](#chapter-16-daofy-self-update-management)
- [Chapter 17: Software Copyright Document Generation](#chapter-17-software-copyright-document-generation)
- [Chapter 18: Troubleshooting and Best Practices](#chapter-18-troubleshooting-and-best-practices)

---

## Chapter 1: Daofy Overview

### 1.1 What Is Daofy?

**Daofy (道飞)**—giving creativity wings.

Daofy for Delphi is an MCP Server based on the **Model Context Protocol (MCP)**. It allows AI assistants (such as Claude Desktop, CodeArts Agent, Cursor, etc.) to directly compile Delphi projects and query the Delphi knowledge base. With this tool, you can directly compile Delphi projects, query API documentation, and search code examples within conversations with AI assistants, without manually switching to the IDE or command line.

### 1.2 Core Advantages

| Advantage | Description |
|------|------|
| **Seamless Integration** | Embedded in AI assistant workflows; complete compilation, search, and coding in chat |
| **Zero Configuration** | Automatically detects Delphi compilers from the registry; no manual configuration required |
| **Built-in Knowledge Base** | Built-in Delphi RTL/VCL/FMX source code index with semantic search support |
| **Full Lifecycle** | From project creation, compilation, and auditing to code hosting, all in one place |
| **Cross-Version Support** | Supports the full Delphi 2005 to Delphi 13 series |

### 1.3 Feature Overview

Daofy provides 16 MCP tools:

| # | Tool Name | Functional Domain | One-line Purpose |
|---|--------|--------|-----------|
| 1 | `project` | Compilation/configuration/audit | Full project lifecycle management |
| 2 | `delphi_kb` | Knowledge base search/build | Delphi API, project code, and document search |
| 3 | `delphi_file` | File operations | Delphi file read/write/format/encoding conversion/backup |
| 4 | `manage_component` | Component management | Add/remove/modify DFM components + automatic PAS sync |
| 5 | `check_environment` | Environment diagnostics | Check compiler, install pasfmt |
| 6 | `async_task` | Background tasks | Manage time-consuming tasks such as knowledge base builds |
| 7 | `package` | Component package management | Compile and install .dpk component packages |
| 8 | `get_coding_rules` | Coding standards | Get Delphi coding rules |
| 9 | `code_hosting` | Code hosting | Git operations + platform API |
| 10 | `tool_help` | Help documentation | Get complete help for any tool (see details below) |
| 11 | `experience` | Experience memory | Save/search AI problem-solving experience |
| 12 | `daofy_update` | Self-update | Check/update Daofy version |
| 13 | `delphi_rtti` | RTTI bridge | Discover and invoke Delphi runtime capabilities |
| 14 | `automate_delphi` | Automated testing | GUI screenshots + console interaction |
| 15 | `ocr` | Image analysis | Text recognition/screenshot comparison/color analysis |
| 16 | `generate_copyright` | Software copyright generation | Generate software copyright documents |

> 💡 **`tool_help` Usage Tip**: Whenever you are unsure about the detailed usage of a tool, you can call `tool_help(tool_name="tool name")` to get complete help for that tool, including parameter descriptions, action details, usage examples, trigger words, etc. For example, `tool_help(tool_name="delphi_file")`.

### 1.4 System Requirements

| Component | Requirement |
|------|------|
| **Python** | 3.10 ~ 3.14 |
| **Operating System** | Windows (Delphi is supported only on Windows) |
| **Delphi Compiler** | dcc32.exe or dcc64.exe (any version) |
| **Git** | Used for code hosting features |
| **7-Zip** | Optional, used to extract CHM help files (can be placed in `tools/7z/` as a portable install) |

---

## Chapter 2: Installation and Configuration

### 2.1 Method 1: pip Installation (Recommended)

```bash
pip install daofy-for-delphi
```

> **Acceleration for users in China**:
> ```bash
> pip install daofy-for-delphi -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

After installation, jump directly to → [2.3 Configure AI Assistant](#23-configure-ai-assistant).

### 2.2 Method 2: Source Code Installation

#### Step 1: Clone the Project

```bash
git clone https://github.com/chinawsb/daofy.git
# Users in China can use the Gitee mirror
# git clone https://gitee.com/zuoyouruanjian/daofy.git
cd daofy
```

#### Step 2: Create and Activate a Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux/macOS
```

#### Step 3: Install Dependencies

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### Step 4: Install Optional Extensions

```bash
# File change watching — automatically incrementally update the project knowledge base
pip install daofy-for-delphi[watcher]

# Semantic search enhancement — search quality improves significantly after installation
pip install daofy-for-delphi[embedding]

# OCR image text recognition
pip install daofy-for-delphi[ocr]

# Intel CPU OCR acceleration (replace onnxruntime → onnxruntime-openvino)
pip install daofy-for-delphi[ocr-openvino]
```

### 2.3 Configure AI Assistant

When the MCP Server starts for the first time, it automatically detects installed Delphi compilers from the Windows registry; **no manual configuration is required**.

#### Minimal Configuration for pip Installation

```json
{
  "mcpServers": {
    "daofy": {
      "command": "daofy",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

#### Source Installation Configuration

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "daofy": {
      "command": "python",
      "args": ["C:\\path\\to\\daofy\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

**Trae** (`C:\Users\<用户名>\.trae-cn\mcp_config.json`):

```json
{
  "mcpServers": {
    "daofy": {
      "command": "F:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["F:\\path\\to\\daofy\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

**CodeArts Agent** (`~/.codeartsdoer/mcp/mcp_settings.json`):

```json
{
  "mcpServers": {
    "daofy": {
      "command": "python",
      "args": ["src\\server.py"],
      "cwd": "C:\\path\\to\\daofy",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

### 2.4 Use the Installation Script (Source Installation)

The project provides an `install.bat` installation script that automatically detects installed AI clients and configures MCP:

```bash
.\install.bat
```

AI clients supported by the detection script:
- Claude Desktop
- Trae
- CodeArts Agent
- Cursor
- Windsurf
- Cline
- Tongyi Lingma
- Doubao
- Kimi
- OpenCode

### 2.5 Verify Installation

```bash
python src/server.py
```

Seeing the following output indicates successful startup:
```
INFO Starting Daofy v2026.06.15.1
INFO Configuration manager initialization complete
INFO Compilation service initialization complete
...
```

---

## Chapter 3: Environment Check and Diagnostics

### 3.1 Tool Overview

`check_environment` is Daofy's environment diagnostics tool, used to check Delphi compiler status, re-detect installed compilers, and install the pasfmt formatting tool.

### 3.2 Action Quick Reference

| Action | Purpose |
|--------|------|
| `check` (default) | Check the current compilation environment status |
| `detect` | Re-detect Delphi compilers from the registry/specified path |
| `install` | Download and install the pasfmt formatting tool |
| `format_install` | Install the pasfmt RAD Studio IDE plugin |

### 3.3 Check the Compilation Environment

```python
check_environment(action="check")
```

The returned information includes:
- List of available compilers (name, version, path)
- Default compiler
- Whether pasfmt is installed
- Environment status (ready/partially ready/not ready)

### 3.4 Detect Compilers

```python
# Detect from the registry
check_environment(action="detect")

# Detect from a specified path
check_environment(action="detect", search_path="D:\\Delphi\\Studio")
```

Detection process:
1. Scan all versions under the registry key `HKEY_CURRENT_USER\SOFTWARE\Embarcadero\BDS`
2. Automatically detect compiler paths for each version (dcc32.exe / dcc64.exe)
3. Write to `config/compilers.json`

### 3.5 Install the pasfmt Formatting Tool

```python
# Download and install to the default location
check_environment(action="install")

# Install to a specified directory
check_environment(action="install", install_dir="C:\\Tools\\pasfmt")
```

After installation, `delphi_file(action="format")` can be used.

### 3.6 Supported Delphi Versions

Automatic registry detection supports the full range of versions from Delphi 2005 to Delphi 13:

| Version | Registry Version Number |
|------|------------|
| Delphi 13 Florence | 37.0 |
| Delphi 12 Athens | 23.0 |
| Delphi 11 Alexandria | 22.0 |
| Delphi 10.4 Sydney | 21.0 |
| Delphi 10.3 Rio | 20.0 |
| ... | ... |
| Delphi 2005 | 3.0 |

### 3.7 Typical Workflow

```python
# First use
check_environment(action="check")    # Confirm environment status
# → Compiler not found
check_environment(action="detect")   # Detect from the registry
# → Start compilation
delphi_project(action="compile", ...)

# When compilation fails
delphi_project(action="compile")   # Failed
check_environment(action="check")   # Confirm compiler status
check_environment(action="detect")  # Re-detect and retry
```

---

## Chapter 4: Knowledge Base Search and Management

### 4.1 Tool Overview

`delphi_kb` is Daofy's knowledge base search and management tool. It integrates **four major knowledge bases** and supports multiple search methods such as class/function/semantic search.

**Core use case**: Before AI writes Delphi code, it first queries the knowledge base to confirm API definitions and avoid making things up.

### 4.2 Five Major Knowledge Bases

| Knowledge Base Type | kb_type | Data Volume | Storage Path |
|-----------|---------|--------|---------|
| Delphi Source | `delphi` | 163,737 classes / 300,228 functions | `data/delphi-knowledge-base/` |
| Project Knowledge Base | `project` | Project-defined | `<项目目录>/.delphi-kb/` |
| Third-Party Libraries | `thirdparty` | 5,724 classes / 28,801 functions | `data/thirdparty-knowledge-base/` |
| General Documents | `document` | 160,328 articles | `data/document-knowledge-base/` |
| Example Code | `example` | Project-defined | `data/example-knowledge-base/` |

### 4.3 Search API

```python
# Search for classes (most common)
delphi_kb(query="TStringList")

# Search for functions
delphi_kb(query="Create", search_type="function")

# Semantic search (describe requirements in natural language)
delphi_kb(query="如何创建数据库连接", search_type="semantic")

# Search project code
delphi_kb(query="TfrmMain", kb_type="project", project_path="Project.dproj")

# Search official Delphi API
delphi_kb(query="TCustomADODataSet", kb_type="delphi")

# Reference query (assess the impact scope of changes)
delphi_kb(query="TStringList", search_type="reference")
```

**Parameter Description**:

| Parameter | Required | Default | Description |
|------|------|--------|------|
| `query` | ✅ | — | Search keyword |
| `kb_type` | ❌ | all | all/delphi/project/thirdparty/document/example |
| `search_type` | ❌ | — | class/function/procedure/record/interface/enum/set/helper/type/const/resourcestring/variable/property/method/field/event/operator/string/dfm/attribute/unit/semantic/reference/all |
| `top_k` | ❌ | 200 | Maximum number of returned results (maximum 500) |
| `project_path` | ❌ | Automatically detected | Project path |

### 4.4 Search Strategy and Priority

> ⭐ **Standard search process for AI before writing code**

```
⭐1  delphi_kb(query="TStringList")            Exact class name search
     └─ No results? → Try another name
⭐2  delphi_kb(query="TMainForm")              Try another name (TMainForm→TfrmMain)
     └─ Still no results? → Search functions
⭐3  delphi_kb(query="Create",
          search_type="function")             Search functions (matches FF+FP at the same time)
     └─ Still no results? → Check references
⭐4  delphi_kb(query="TForm1",
          search_type="reference")            Check references (assess modification impact)
     └─ Still no results? → Semantic search as fallback
⭐5  delphi_kb(query="创建主窗口",
          search_type="semantic")             Chinese semantic search as fallback
```

### 4.5 Knowledge Base Statistics

```python
delphi_kb(action="stats")
```

| Knowledge Base | File Count | Class Count | Function Count | Database Size |
|--------|-------|--------|---------|-----------|
| Delphi Source | 2,798 | 163,737 | 300,228 | 260 MB |
| Third-Party Libraries | 1,800 | 5,724 | 28,801 | 27 MB |
| General Documents | 160,328 | — | — | 1,306 MB |

### 4.6 Build the Knowledge Base

```python
# Delphi source KB (~1 minute)
delphi_kb(action="build", kb_type="delphi", rebuild=True, async_mode=True)

# Third-party library KB (~6 seconds)
delphi_kb(action="build", kb_type="thirdparty", rebuild=True, async_mode=True)

# Document KB (~6 minutes, 160,328 documents)
delphi_kb(action="build", kb_type="document", rebuild=True, async_mode=True)

# Project KB
delphi_kb(action="build", kb_type="project",
    project_path="Project.dproj", rebuild=True)
```

**Parameter Description**:

| Parameter | Description |
|------|------|
| `async_mode` | Default true; executes asynchronously without blocking the MCP channel |
| `rebuild` | Force a complete rebuild (default false) |
| `incremental` | Incremental update, process only changed files |
| `directory` | Scan directory (can be specified when building documents; by default automatically detects the Delphi help directory) |
| `extensions` | File extension filter (e.g., `[".chm"]`) |

### 4.7 Build a Delphi Help Document Knowledge Base

```python
# Automatically detect the most recently installed Delphi help directory
delphi_kb(action="build", kb_type="document",
    extensions=[".chm"], async_mode=True)

# Manually specify a directory
delphi_kb(action="build", kb_type="document",
    directory="C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\Help\\Doc",
    extensions=[".chm"], async_mode=True)
```

**Version mapping**: 37.0=Delphi 13, 23.0=Delphi 12, 22.0=Delphi 11, 21.0=Delphi 10.4

### 4.8 Document Knowledge Base Search

After the build is complete, you can search help documents just like source code (`kb_type="document"` routes to an independent document search engine with full-text search support):

```python
# Search API documentation
delphi_kb(query="TCanvas.Draw", kb_type="document")

# Natural language search
delphi_kb(query="怎么用 PrintDialog 设置打印机参数", kb_type="document", search_type="semantic")
```

> 💡 **Tip**: `kb_type="document"` uses an independent route to search the document knowledge base; `kb_type="all"` also automatically includes document search results.

### 4.9 Vector Index (Embedding)

The vector index is based on the sentence-transformers model and enables **semantic search**—when you search "how to create a database connection", it can also match `TADOConnection.Create`.

```python
# Build the vector index
delphi_kb(action="build_embedding", async_mode=True)
```

| Feature | Model Not Loaded | Model Loaded |
|------|-----------|-----------|
| Semantic search | Falls back to inverted index | True semantic search, sorted by cosine similarity |
| Experience library save | No deduplication | Automatically deduplicate and merge when >0.85 |
| Experience library search | Falls back to LIKE keyword search | Semantic vector search |

---

## Chapter 5: Project Compilation and Configuration Management

### 5.1 Tool Overview

`project` is the core tool in Daofy, providing **full lifecycle management** for Delphi projects—from creating projects and configuring compilation options to performing compilations and code audits.

### 5.2 Action Quick Reference

| Action | Purpose | Required Parameters |
|--------|------|---------|
| `compile` | Compile .dproj/.dpr/.dpk projects | `project_path` |
| `compile_file` | Check .pas file syntax | `project_path` |
| `dry_run` | Preview compilation parameters without executing | — |
| `info` | Read complete .dproj information | `project_path` |
| `create` | Create a new .dproj file | `project_path`, `main_source` |
| `set` | Set .dproj property values | `project_path`, `property_name`, `value` |
| `add_config` | Add a build configuration | `project_path`, `config_name` |
| `remove_config` | Remove a build configuration | `project_path`, `config_name` |
| `add_source` | Add a source file reference | `project_path`, `source_file` |
| `remove_source` | Remove a source file reference | `project_path`, `source_file` |
| `audit` | Run 50+ static analysis rules | — |
| `ast` | Code skeleton extraction (most token-efficient) | `base_dir` |
| `runtime` | Runtime registration check | — |

### 5.3 Compile a Project

```python
# Simplest call — automatically detect project type and configuration
delphi_project(action="compile", project_path="Project.dproj")

# Compile with full parameters
delphi_project(action="compile",
    project_path="App.dproj",
    build_configuration="Release",
    target_platform="win64",
    conditional_defines=["RELEASE", "MY_FEATURE"],
    unit_search_paths=["C:\\Libs\\Common", "..\\Shared"],
    optimize=True,
    debug=False,
    output_path=".\\Build\\Release")

# Post-compile run verification (detect runtime crashes)
delphi_project(action="compile",
    project_path="App.dproj",
    run_verify=True)
```

**Compilation Parameter Description**:

| Parameter | Default Value | Description |
|------|--------|------|
| `project_path` | — | Path to .dproj/.dpr/.dpk/.pas |
| `target_platform` | win32 | win32/win64/osx64/... |
| `build_configuration` | Debug | Debug/Release |
| `compiler_version` | Automatically detect the latest | Specify Delphi version |
| `conditional_defines` | — | Array of conditional compilation symbols |
| `unit_search_paths` | — | Additional unit search paths |
| `optimize` | true | Whether to enable optimization |
| `debug` | true | Whether to generate debug information |
| `timeout` | 300 | Timeout in seconds |
| `run_verify` | false | Start for 3 seconds after compilation to verify whether it crashes |
| `output_path` | — | Compilation output directory |

### 5.4 Compilation Events

The `PreBuildEvent`/`PostBuildEvent`/`PreLinkEvent` in `.dproj` are executed automatically; no manual handling is required.

After a successful compilation, `run_verify` automatically starts the exe for 3 seconds; when `exception.log` is detected, it automatically reads the content and embeds it in the response.

### 5.5 Single-File Syntax Check

```python
delphi_project(action="compile_file", project_path="Unit1.pas")

# With search paths
delphi_project(action="compile_file",
    project_path="Unit1.pas",
    unit_search_paths=["..\\Shared"],
    conditional_defines=["TEST"])
```

### 5.6 Create a Project

```python
# Simplest creation
delphi_project(action="create",
    project_path="MyApp.dproj",
    main_source="MyApp.dpr")

# With Form stub code
delphi_project(action="create",
    project_path="MyApp.dproj",
    main_source="MyApp.dpr",
    framework_type="VCL",
    form_units=["Unit1", "MainForm"],
    configs=["Debug", "Release", "Staging"])
```

### 5.7 Read and Modify Project Configuration

```python
# Read project information
delphi_project(action="info", project_path="Project.dproj")

# Modify properties
delphi_project(action="set",
    project_path="Project.dproj",
    property_name="DCC_Define",
    value="DEBUG;TEST",
    config="Debug",
    platform="Win32")

# Add a build configuration
delphi_project(action="add_config",
    project_path="Project.dproj",
    config_name="Staging",
    base_config="Debug",
    defines=["STAGING"])

# Remove a build configuration
delphi_project(action="remove_config",
    project_path="Project.dproj",
    config_name="Staging")
```

### 5.8 Source File Management

```python
# Add a source file
delphi_project(action="add_source",
    project_path="Project.dproj",
    source_file="Unit1.pas")

# Remove a source file
delphi_project(action="remove_source",
    project_path="Project.dproj",
    source_file="Unit1.pas")
```

### 5.9 Compilation Error Troubleshooting

```python
# Common troubleshooting process
delphi_project(action="compile")  fails
check_environment(action="check")   # Confirm compiler status
# → Check whether DCC_UnitSearchPath contains the required third-party library paths
# → Confirm the compiler for the target platform (win32/win64) is available
# → Whether conditional compilation symbols match (DEBUG/RELEASE)
```

**Common Compilation Errors**:

| Error Symptom | Possible Cause | Solution |
|---------|---------|------|
| `Fatal: Unable to execute file` | Compiler path is incorrect | Re-detect with `check_environment(action="detect")` |
| `Fatal: File not found: xxx.dcu` | Missing search paths | Add the `unit_search_paths` parameter |
| Exit code 2 | Compilation event failed or syntax error | Check the detailed output to locate the error line |

---

## Chapter 6: Delphi File Operations

### 6.1 Tool Overview

`delphi_file` is a dedicated tool for operating on Delphi files. It supports `.pas`, `.dpr`, `.dpk`, `.dfm`, `.fmx`, `.inc`, and `.dproj`, and automatically handles encoding detection/conversion, `__history` backups, DFM/FMX binary conversion, and same-file read/write mutual exclusion.

> ⚠️ **Do not use native read/write/edit tools to modify .pas/.dfm files! You must use delphi_file.**

### 6.2 Action Quick Reference

| Action | Purpose |
|--------|------|
| `read` | Read by path, or locate by class name/function name/record and then read |
| `write` | Compatible write interface, using `edits=[...]` |
| `replace` | Replace by line range (old_content verification required) |
| `insert` | Insert at an anchor line (old_content verification required) |
| `delete` | Delete by line range (old_content verification required) |
| `format` | Format using pasfmt |
| `backup` | Create/list/restore `__history` backups |
| `encode` | File encoding conversion (automatically detects source encoding, supports BOM handling) |
| `uses` | Add/remove units in the uses clause |

### 6.3 Line Number Rules

All line number parameters and outputs for `read`/`write`/`uses` are **1-indexed inclusive**.

| Example | Meaning |
|------|------|
| `start_line=1` | Start from line 1 |
| `start_line=5, end_line=10` | Lines 5 through 10, inclusive |
| `write` does not pass `end_line` | Replace from `start_line` to the end of the file |

### 6.4 Read Files

```python
# Basic read
delphi_file(action="read", file_path="Unit1.pas")

# Read a range
delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)

# Show line numbers
delphi_file(action="read", file_path="Unit1.pas", show_line_numbers=True)

# Search and read by type
delphi_file(action="read", search_type="class", type_name="TButton")
delphi_file(action="read", search_type="function", function_name="Create")
delphi_file(action="read", search_type="record", record_name="TPoint")

# Cross-knowledge-base search
delphi_file(action="read", search_type="class",
    type_name="TMainForm", search_in="project", project_path="Project.dproj")
```

### 6.5 Write Files

**It is recommended to use `replace`/`insert`/`delete` semantic operations** (safer):

```python
# Replace a line range
delphi_file(action="replace",
    file_path="Unit1.pas",
    edits=[{"start_line": 5, "end_line": 10,
            "old_content": "  OldCall;\n",
            "content": "  NewCall;\n"}])

# Insert at an anchor
delphi_file(action="insert",
    file_path="Unit1.pas",
    edits=[{"start_line": 10, "position": "before",
            "old_content": "  OldCall;\n",
            "content": "  NewCall;\n"}])

# Delete a line range
delphi_file(action="delete",
    file_path="Unit1.pas",
    edits=[{"start_line": 10, "end_line": 12,
            "old_content": "  OldCall;\n  OtherCall;\n"}])
```

**Compatible `write` Interface**:

```python
# Full-text replacement
delphi_file(action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 1, "content": "unit Unit1;\n\ninterface\n\nimplementation\n\nend.\n"}])

# Partial replacement
delphi_file(action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 5, "end_line": 10, "content": "  // new code\n"}])

# Merge multiple modifications into one write
delphi_file(action="write",
    file_path="Unit1.pas",
    edits=[
        {"start_line": 5, "end_line": 7, "content": "  // first block\n"},
        {"start_line": 18, "end_line": 21, "content": "  // second block\n"},
    ])

# Preview mode (only calculates diff, does not write to disk)
delphi_file(action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 5, "end_line": 10, "content": "  // new code\n"}],
    preview=True)
```

**Write Parameter Description**:

| Parameter | Default | Description |
|------|------|------|
| `backup` | True | Back up to `__history` before writing |
| `encoding` | auto | Keep the original encoding; can be specified explicitly |
| `auto_format` | False | Automatically run pasfmt after writing |
| `preview` | False | Only calculate diff, do not write to disk |
| `force` | False | Skip consecutive duplicate line detection |
| `allow_dirty` | False | Skip the dirty marker check (prefer using old_content) |

### 6.6 Format Code

```python
delphi_file(action="format", file_path="Unit1.pas")

# Check mode (only check formatting, do not modify)
delphi_file(action="format", mode="check", file_path="Unit1.pas")

# Format a code string
delphi_file(action="format", mode="code", code="procedure Test; begin end;")
```

### 6.7 Backup Management

```python
# Create a backup
delphi_file(action="backup", file_path="Unit1.pas")

# List backups
delphi_file(action="backup", backup_action="list", file_path="Unit1.pas")

# Restore a backup
delphi_file(action="backup", backup_action="restore", file_path="Unit1.pas", version=3)
```

### 6.8 Uses Clause Management

```python
# Add a uses unit
delphi_file(action="uses",
    file_path="Unit1.pas",
    uses_action="add",
    unit_name="System.SysUtils",
    uses_section="interface")

# Remove a uses unit
delphi_file(action="uses",
    file_path="Unit1.pas",
    uses_action="remove",
    unit_name="System.SysUtils",
    uses_section="interface")
```

### 6.9 Encoding Conversion (encode)

**Function**: Convert Delphi source files between different encodings and automatically handle BOM (Byte Order Mark). Automatically backs up to `__history` before conversion to ensure rollback is possible.

**Applicable Scenarios**:
- Convert legacy project files encoded in GBK to UTF-8 (recommended modern encoding)
- Add/remove UTF-8 BOM (`utf-8-sig` ↔ `utf-8`)
- Unify project encoding during cross-platform collaboration

**Supported Target Encodings**:

| Encoding Name | Description |
|--------|------|
| `utf-8` | UTF-8 without BOM (recommended) |
| `utf-8-sig` | UTF-8 with BOM (best Windows compatibility) |
| `gbk` | Simplified Chinese GBK (legacy project compatibility) |
| `utf-16` | UTF-16 with BOM |
| `utf-16-le` | UTF-16 Little Endian |
| `utf-16-be` | UTF-16 Big Endian |
| `ansi` | System default ANSI code page (`locale.getpreferredencoding()`) |

**BOM Handling Rules**:

| Source Encoding → Target Encoding | BOM Behavior |
|------------------|---------|
| `utf-8-sig` → `utf-8` | Automatically **strip** BOM bytes |
| `utf-8` → `utf-8-sig` | Automatically **add** UTF-8 BOM (`EF BB BF`) |
| `utf-16` (any) → Other | Automatically **strip** the original BOM; re-add for the target encoding as needed |
| `utf-8-sig` → `utf-8-sig` | Keep the original BOM unchanged |

```python
# UTF-8 without BOM → UTF-8 with BOM (Windows compatibility)
delphi_file(action="encode",
    file_path="Unit1.pas",
    to_encoding="utf-8-sig")

# GBK → UTF-8 (unified project encoding)
delphi_file(action="encode",
    file_path="LegacyUnit.pas",
    from_encoding="gbk",
    to_encoding="utf-8")

# UTF-8 with BOM → UTF-8 without BOM (cross-platform collaboration)
delphi_file(action="encode",
    file_path="Unit1.pas",
    to_encoding="utf-8")

# UTF-8 → UTF-16 (specific platform requirements)
delphi_file(action="encode",
    file_path="Unit1.pas",
    from_encoding="utf-8",
    to_encoding="utf-16")

# Preview mode (only show conversion information, do not write to disk)
delphi_file(action="encode",
    file_path="Unit1.pas",
    to_encoding="utf-8-sig",
    preview=True)
```

**Parameter Description**:

| Parameter | Required | Default | Description |
|------|------|------|------|
| `file_path` | ✅ | — | Target file path (only Delphi source file extensions are supported) |
| `to_encoding` | ✅ | — | Target encoding (`utf-8`/`utf-8-sig`/`gbk`/`utf-16`/`utf-16-le`/`utf-16-be`/`ansi`) |
| `from_encoding` | ❌ | `auto` | Source encoding (`auto`=automatic detection, **it is recommended to always use auto**; if explicit specification is needed, ensure the encoding name is accurate, otherwise decoding may fail or garbled text may result) |
| `backup` | ❌ | `True` | Automatically back up to `__history` before conversion |
| `preview` | ❌ | `False` | Preview mode: only output conversion information without writing to disk |

**Return Information**:

```
Conversion successful: Unit1.pas
  Source encoding: utf-8-sig → Target encoding: utf-8
  File size: 1,024 B → 1,020 B (decreased by 4 B)
  Backup created: __history/Unit1.pas.20260620_123456.bak
```

**Safety Mechanisms**:

1. **Encoding validity check**: First validate the encoding name via Python `codecs.lookup()`. If an incorrect `from_encoding` causes decoding failure, the tool reports an error and prompts for correction; **it will not silently write a garbled file** (the backup has not yet been created during the read phase, so the file will not be damaged)
2. **Read-back verification**: After writing, re-read the file and compare it with the original to confirm there is no loss
3. **Automatic backup**: Create a `__history` backup before conversion and automatically clean up temporary files after failure
4. **Dirty marker protection**: After a successful conversion, the file is marked dirty and must be re-read before writing again
### 6.10 Dirty Flag Mechanism

After `write`, `format`, and `uses` succeed, the file is marked as **dirty**. Before writing to the same file again, you need to:

1. First `read` to re-obtain line numbers
2. Or provide non-empty `old_content` in each edit, and the tool verifies the old content at the matched line numbers
3. Or use `preview=True` to preview the diff and then read again
4. Or set `allow_dirty=True` when you are sure the line numbers are correct

---

## Chapter 7: Coding Standards and Code Auditing

### 7.1 Tool Overview

`get_coding_rules` provides on-demand queries of Delphi coding standards. Before writing or modifying any Delphi code, the AI Agent **must first call this tool** to learn the coding standards, ensuring the generated code style is consistent with the project.

### 7.2 Getting Coding Standards

```python
# Get the full workflow overview + section index (recommended for the first call)
get_coding_rules()

# Get a specified section
get_coding_rules(section="workflow")       # Workflow overview
get_coding_rules(section="writing")        # Code writing standards
get_coding_rules(section="review")         # Code review
get_coding_rules(section="safety")         # Safety standards
get_coding_rules(section="agent_rules")    # AI behavior rules
get_coding_rules(section="kb_search")      # KB search guide
get_coding_rules(section="format")         # Formatting rules
get_coding_rules(section="compile")        # Compilation rules
get_coding_rules(section="automation")     # Automation test architecture
get_coding_rules(section="list")           # List all available sections
```

### 7.3 Section Index

| Section | Content | Applicable Scenario |
|---------|------|---------|
| `workflow` | Workflow overview | Understanding the overall process when first encountering a project |
| `env` | ① Environment check | First run / when the environment is abnormal |
| `kb_search` | ② KB search | Looking up API definitions before coding |
| `writing` | ③ Naming/formatting/generics rules (including write-rule subsections) | Must-read before writing/modifying code |
| `format` | ④ Formatting | Formatting code |
| `compile` | ⑤ Compilation | Compilation verification |
| `review` | ⑥ Code review (including the complete review checklist) | Reviewing code after compilation passes |
| `cleanup` | ⑦ Cleanup and verification | Final cleanup |
| `safety` | Safety-sensitive operation rules | When involving registry, processes, or file operations |
| `performance` | Performance rules | Performance-sensitive paths |
| `agent_rules` | AI hard operating rules | Understanding the AI's behavioral limits |
| `human_collab` | ⑧ Human-machine collaboration — exception diagnosis and manual intervention | Exception diagnosis or when manual intervention is needed |
| `experience` | ⑨ Experience saving — depositing knowledge into the experience base | When saving experience after a problem is solved |
| `kb_build` | Knowledge base rebuild | When the KB needs to be rebuilt |
| `automation` | ⚙ Automation test architecture (including prompt template F + experience optimization loop G) | Before executing automated UI tests |

**Combined sections**:

| Section | Content |
|---------|------|
| `coding` | Combination: writing + format + compile (complete coding process) |

**writing subsections**:

| Section | Content |
|---------|------|
| `delphi_file_write_rule` | delphi_file write rules (1-indexed/edits parameter) |
| `delphi_file_dirty_flag` | Continuous editing and dirty flag protection |
| `delphi_file_output_format` | delphi_file compact output format |
| `delphi_file_usage_tips` | write usage tips |

**Review subsections**:

| Section | Content |
|---------|------|
| `consistency` | Consistency check |
| `completeness` | Completeness check |
| `resource_leak` | Resource leak check |
| `delphi_specific` | Delphi-specific patterns |
| `common_errors` | Common error patterns |
| `code_quality` | Code quality |
| `data_conversion` | Data conversion |
| `performance` | Performance |
| `safety` | Safety |

> Use `get_coding_rules(section="list")` to get the real-time updated complete section list.

### 7.4 Rule Priority

```
Project custom rules > Default rules
```

When `project_path` specifies a concrete project, the project's custom rules file (`CODING_RULES.mdc`) is loaded first; if there are no custom rules, the built-in default rules are used.

Daofy's built-in default rule source is located at `src/resources/coding-rules.md` and is exposed to the AI Agent through the MCP Resource
`delphi://coding-rules`. The `CODING_RULES.mdc` in the project directory is still used as the
project-level override filename.

### 7.5 Code Auditing

The three actions audit/ast/runtime of the `project` tool provide code auditing functionality:

```python
# ⭐ Code skeleton extraction (most token-efficient)
delphi_project(action="ast", base_dir="src")

# Single-file skeleton extraction
delphi_project(action="ast", file_path="Unit1.pas")

# Run 50+ static analysis rules
delphi_project(action="audit", base_dir="src")

# Single file with specified severity level
delphi_project(action="audit",
    file_path="Unit1.pas",
    rules="P0",
    severity="warning",
    output_format="report")

# Runtime registration check (detects missing uses units)
delphi_project(action="runtime", base_dir="src")
```

### 7.6 Auditing Workflow

```
① Determine the audit target
   ├─ Delphi code → get_coding_rules(section="review")
   └─ Python code → check item by item by category such as safety/MCP/concurrency
② Determine the audit scope (global/specified files/newly added code)
③ Search for relevant API definitions and evaluate usage
④ Call project(audit/ast)
   → mode="ast" (recommended, quickly understand the code structure)
   → mode="audit" (in-depth rule checking, 50+ rules)
⑤ AI interprets the results, rules out false positives, and generates fix suggestions
⑥ project(compile) / pytest verification
⑦ Output the audit report
```

### 7.7 Audit Report Template

```
## Source Code Audit Report

**Project**: <project name>
**Audit Scope**: <global / file list>

### Overview

| Category | Findings | Critical | General | Suggestion |
|------|--------|------|------|------|
| Security | N | N | N | N |
| Resource management | N | N | N | N |
| Error handling | N | N | N | N |
| **Total** | **N** | **N** | **N** | **N** |

### Critical Issues

1. [Critical] <file:F line>: <problem description>
   - **Problem**: ...
   - **Risk**: ...
   - **Suggested fix**: ...

### General Issues
...

### Audit Conclusion
<overall assessment>
```

---

## Chapter 8: Code Hosting and Git Operations

### 8.1 Tool Overview

`code_hosting` is the unified entry point for all Git operations and code hosting platform operations in Daofy. It provides local Git operations (status/add/commit/push/clone) and multi-platform API operations (Gitea/GitHub/GitLab/Gitee/GitCode).

> ⚠️ **Core rule**: All Git operations must use this tool; running git commands directly via bash is prohibited.

### 8.2 Supported Platforms

| Platform | Identifier | Description |
|------|------|------|
| Gitea | `gitea` | Self-hosted Gitea |
| GitHub | `github` | github.com |
| GitLab | `gitlab` | GitLab CE/EE |
| Gitee | `gitee` | gitee.com |
| GitCode | `gitcode` | gitcode.net |

### 8.3 Action Cheat Sheet

| Action Group | Action | Purpose |
|------------|--------|------|
| **Git read-only** | `git_status` | View repository status |
| | `git_diff` | View working tree/staged differences (add staged=True to also view diff) |
| | `git_show` | View commit or object content |
| | `git_log` | View commit history |
| **Git working tree changes** | `git_add` | Stage files (requires files parameter) |
| | `git_restore` | Restore files (destructive, requires files parameter) |
| | `git_unstage` | Unstage (requires files parameter) |
| | `git_stash` | Manage stash (push/list/pop/apply/drop/show) |
| **Git commit** | `git_commit` | Create a commit |
| **Git branch** | `git_branch` | View/create/delete branches (list/create/delete) |
| | `git_switch` | Switch to or create a branch (-c create) |
| | `git_merge` | Merge branches (supports ff-only/no-commit) |
| | `git_tag` | List/create/delete tags |
| **Git remote** | `git_fetch` | Fetch remote references (supports --prune) |
| | `git_pull` | Pull and merge remote branches (supports rebase/ff-only) |
| | `git_push` | Push to remote |
| | `git_push_retry` | Auto-retry push in the background (optional max_retries) |
| **Git async** | `git_clone` | Clone a remote repository |
| **Platform API — Issues** | `create_issue` | Create an issue |
| | `get_issue` | View issue details |
| | `edit_issue` | Edit an issue (title/body/state/labels) |
| | `set_labels` | Set issue labels |
| | `close_issue` | Close an issue |
| | `add_comment` | Add a comment |
| | `list_issues` | Query the issue list |
| **Platform API — PR** | `create_pull` | Create a Pull Request |
| | `get_pull` | View Pull Request details |
| | `list_pulls` | Query the Pull Request list |
| | `edit_pull` | Edit a Pull Request |
| | `merge_pull` | Merge a Pull Request |
| | `close_pull` | Close a Pull Request (without merging) |
| | `reopen_pull` | Reopen a closed Pull Request |
| **Platform API — Release** | `create_release` | Create a Release |
| | `get_release` | View Release details |
| | `list_releases` | Query the Release list |
| | `edit_release` | Edit a Release |
| | `delete_release` | Delete a Release |
| **Platform API — Other** | `create_token` | Create an access token (Gitea only) |
| | `init_labels` | Bulk-initialize the four-dimensional workflow labels |

### 8.4 Local Git Operations

**Read-only operations** (safe, does not modify the repository):

```python
# View status
code_hosting(action="git_status")

# View working tree diff
code_hosting(action="git_diff")

# View staged diff (staged)
code_hosting(action="git_diff", staged=True)

# View diff statistics summary
code_hosting(action="git_diff", stat=True)

# View diff for specified files
code_hosting(action="git_diff", files=["src/Unit1.pas", "src/Unit2.pas"])

# View the content of a commit
code_hosting(action="git_show", ref="HEAD")

# View commit history
code_hosting(action="git_log", limit=10)

# View commit history of specified files
code_hosting(action="git_log", files=["src/Unit1.pas"])
```

**Working tree change operations** (require files parameter to avoid accidentally operating on the entire working tree):

```python
# Stage specified files
code_hosting(action="git_add", files=["src/Unit1.pas", "src/Unit2.pas"])

# Restore working tree files (destructive, must pass files)
code_hosting(action="git_restore", files=["src/Unit1.pas"])

# Unstage
code_hosting(action="git_unstage", files=["src/Unit1.pas"])

# Stash management
code_hosting(action="git_stash", op="push", message="wip: refactoring", include_untracked=True)
code_hosting(action="git_stash", op="list")
code_hosting(action="git_stash", op="pop", ref="stash@{0}")
code_hosting(action="git_stash", op="show", ref="stash@{0}")
```

**Commit operations**:

```python
# Create a commit
code_hosting(action="git_commit", message="feat: add user authentication module")
```

**Branch and tag operations**:

```python
# List branches
code_hosting(action="git_branch")

# List all branches (including remote)
code_hosting(action="git_branch", remote_branches=True)

# Create a new branch
code_hosting(action="git_branch", branch="feature/new-ui")

# Delete a branch
code_hosting(action="git_branch", branch="old-feature", delete=True)

# Switch branch
code_hosting(action="git_switch", branch="main")

# Create and switch branch
code_hosting(action="git_switch", branch="feature/new-ui", create=True)

# Create a branch from a specified starting point
code_hosting(action="git_switch", branch="feature/hotfix", create=True, start_point="v1.0")

# Merge a branch
code_hosting(action="git_merge", branch="feature/new-ui")

# Fast-forward only merge
code_hosting(action="git_merge", branch="feature/bugfix", ff_only=True)

# List tags
code_hosting(action="git_tag")

# Create an annotated tag
code_hosting(action="git_tag", tag="v1.0.0", message="Release version 1.0.0")

# Delete a tag
code_hosting(action="git_tag", tag="v1.0.0-beta", delete=True)
```

**Remote operations**:

```python
# Fetch remote references
code_hosting(action="git_fetch", remote="origin", branch="main")

# Fetch and prune deleted remote branches
code_hosting(action="git_fetch", prune=True)

# Pull and merge remote branches
code_hosting(action="git_pull", remote="origin", branch="main")

# Pull using rebase
code_hosting(action="git_pull", rebase=True, ff_only=True)

# Push
code_hosting(action="git_push")

# Push a specified branch
code_hosting(action="git_push", branch="main", remote="origin")

# Auto-retry push in the background
code_hosting(action="git_push_retry")

# Auto-retry push in the background (custom retry parameters)
code_hosting(action="git_push_retry", remote="origin", retry_interval=120, max_retries=5)

# Clone a repository
code_hosting(action="git_clone",
    url="https://github.com/user/repo.git",
    mirror="https://gitclone.com")    # Domestic acceleration

# Clone a specified branch
code_hosting(action="git_clone",
    url="https://github.com/user/repo.git",
    branch="develop")
```

### 8.5 Platform API Operations

> ⚠️ **Parameter note**: For all platform API operations, the `repo` parameter uses the `"owner/repo"` format (e.g. `"myorg/myproject"`); each handler automatically separates owner and repo from that string.

**Issue operations**:

```python
# Create an issue
code_hosting(action="create_issue",
    repo="myorg/myproject",
    title="Fix login crash on Windows 11",
    body="## Problem description\nCrashes when clicking the login button on Windows 11",
    labels=["bug", "priority-high"])

# View issue details
code_hosting(action="get_issue",
    repo="myorg/myproject",
    issue_number=42)

# Edit an issue (can modify title/body/state/labels)
code_hosting(action="edit_issue",
    repo="myorg/myproject",
    issue_number=42,
    title="Updated title",
    body="Updated description",
    state="open")

# Set issue labels separately
code_hosting(action="set_labels",
    repo="myorg/myproject",
    issue_number=42,
    labels=["bug", "priority-high", "in-progress"])

# Close an issue
code_hosting(action="close_issue",
    repo="myorg/myproject",
    issue_number=42)

# Close an issue and add a note
code_hosting(action="close_issue",
    repo="myorg/myproject",
    issue_number=42,
    comment="Fixed in #43")

# Add a comment
code_hosting(action="add_comment",
    repo="myorg/myproject",
    issue_number=42,
    body="Fixed in #43")

# Query the issue list
code_hosting(action="list_issues",
    repo="myorg/myproject",
    state="open",
    labels=["bug"])

# Initialize labels
code_hosting(action="init_labels",
    repo="myorg/myproject")
```

**Pull Request operations**:

```python
# Create a Pull Request
code_hosting(action="create_pull",
    repo="myorg/myproject",
    title="fix: login crash on Windows 11",
    body="Fix the login button crash on Windows 11",
    source_branch="fix/login-crash",
    target_branch="main")

# View Pull Request details
code_hosting(action="get_pull",
    repo="myorg/myproject",
    pull_number=42)

# List Pull Requests
code_hosting(action="list_pulls",
    repo="myorg/myproject",
    state="open",
    limit=20)

# Edit a Pull Request (can modify title/body/state/source_branch/target_branch)
code_hosting(action="edit_pull",
    repo="myorg/myproject",
    pull_number=42,
    title="Updated PR title",
    state="closed")

# Merge a Pull Request
code_hosting(action="merge_pull",
    repo="myorg/myproject",
    pull_number=42,
    merge_style="merge")     # merge/squash/rebase

# Close a Pull Request (without merging)
code_hosting(action="close_pull",
    repo="myorg/myproject",
    pull_number=42)

# Reopen a closed Pull Request
code_hosting(action="reopen_pull",
    repo="myorg/myproject",
    pull_number=42)
```

**Release operations**:

```python
# Create a Release
code_hosting(action="create_release",
    repo="myorg/myproject",
    tag_name="v1.0.0",
    name="Version 1.0.0",
    body="## Changes\n- Fix login crash\n- Optimize performance",
    draft=True,
    prerelease=False)

# View Release details
code_hosting(action="get_release",
    repo="myorg/myproject",
    tag_name="v1.0.0")

# List Releases
code_hosting(action="list_releases",
    repo="myorg/myproject",
    limit=10)

# Edit a Release
code_hosting(action="edit_release",
    repo="myorg/myproject",
    tag_name="v1.0.0",
    name="Version 1.0.0 (revised)",
    body="## Changes\n- Fix login crash\n- Optimize performance\n- Update docs")

# Delete a Release
code_hosting(action="delete_release",
    repo="myorg/myproject",
    tag_name="v1.0.0")
```

**Token and other operations**:

```python
# Create a Gitea access token (requires base_url + username + password)
code_hosting(action="create_token",
    base_url="https://your-gitea.com",
    username="admin",
    password="your_password",
    name="daofy-ai-token",
    scopes=["read:repository", "write:repository", "read:issue", "write:issue"])
```

### 8.6 Complete Workflow

```python
# ═══════════════════════════════════════════════
# Daily development commits
# ═══════════════════════════════════════════════
delphi_file(action="write", ...)              # Write code
delphi_project(action="compile", ...)                # Compilation verification

# View changes and commit
code_hosting(action="git_diff", stat=True)     # View change overview
code_hosting(action="git_add", files=["."])   # Stage
code_hosting(action="git_commit", ...)        # Commit
code_hosting(action="git_push")               # Push

# ═══════════════════════════════════════════════
# Complete bug-fix loop
# ═══════════════════════════════════════════════
code_hosting(action="list_issues", repo="myorg/myproject", state="open", labels=["bug"])  # View pending bugs
# → Create a branch to fix
git_switch(branch="fix/login-crash", create=True)
# Fix the code
delphi_project(action="compile", ...)                # Compilation verification
code_hosting(action="git_add", files=["src/login.pas"])
code_hosting(action="git_commit", message="fix: #42 login crash")
code_hosting(action="git_switch", branch="main")       # Switch back to the main branch
code_hosting(action="git_merge", branch="fix/login-crash")  # Merge
code_hosting(action="git_push")
# Update the issue
code_hosting(action="get_issue", repo="myorg/myproject", issue_number=42)
code_hosting(action="add_comment", repo="myorg/myproject", issue_number=42, body="Fixed in #43")
code_hosting(action="close_issue", repo="myorg/myproject", issue_number=42)

# ═══════════════════════════════════════════════
# Feature development — branch management
# ═══════════════════════════════════════════════
code_hosting(action="git_switch", branch="feature/new-dialog", create=True)  # Create a feature branch
# Under development...
code_hosting(action="git_stash", op="push", message="wip: unfinished change")  # Temporarily save
code_hosting(action="git_switch", branch="main")       # Switch to the main branch to fix an urgent problem
# Fix the urgent problem
code_hosting(action="git_stash", op="pop")              # Restore the previous unfinished changes
code_hosting(action="git_add", files=["src/dialog.pas"])
code_hosting(action="git_commit", message="feat: add new customer dialog")
code_hosting(action="git_switch", branch="main")
code_hosting(action="git_merge", branch="feature/new-dialog")
code_hosting(action="git_tag", tag="v1.1.0", message="Version 1.1.0")  # Tag a version
code_hosting(action="git_push", branch="main")
code_hosting(action="git_push", branch="--tags")        # Push tags

# ═══════════════════════════════════════════════
# View history and debugging
# ═══════════════════════════════════════════════
code_hosting(action="git_log", limit=5)                  # The 5 most recent commits
code_hosting(action="git_show", ref="abc1234")           # View a specific commit
code_hosting(action="git_diff", files=["src/unit1.pas"]) # View the current file changes
```

---

## Chapter 9: Experience Memory Management

### 9.1 Tool Overview

`experience` is Daofy's built-in **AI experience memory system**, used to persistently store effective practices and techniques discovered by the AI while solving problems.

**Core idea**: Problems encountered by the AI during coding and their solutions should not be forgotten. The experience knowledge base allows each "trap-solution" cycle to accumulate.

### 9.2 Action Cheat Sheet

| Action | Purpose | Required Parameters |
|--------|------|---------|
| `save` | Save experience (auto-deduplication) | `problem`, `solution` |
| `search` | Semantic search of experience | `query` |
| `get` | View experience details | `id` |
| `list` | Browse the list | — |
| `update` | Update experience | `id` |
| `merge` | Merge multiple experiences | `ids` (at least 2) |
| `prune` | List low-value experiences | — |
| `delete` | Delete experience | `id` |
| `rebuild_embedding` | Rebuild missing vectors | — |

### 9.3 Saving Experience

```python
# Basic save
experience(action="save",
    problem="dcc32 returns exit code 2 when compiling the Delphi project",
    solution="Check whether DCC_UnitSearchPath in .dproj includes all third-party library paths, "
             "then pass unit_search_paths in delphi_project(action=compile) to supplement",
    tools_used=["project", "delphi_file"],
    tags=["Delphi", "compile", "dcc32"])

# Force save (skip the >0.7 similarity interception)
experience(action="save",
    problem="...",
    solution="...",
    force=true)
```

### 9.4 Searching Experience

```python
# Semantic search
experience(action="search",
    query="compile error file not found",
    top_k=5)

# Search filtered by tags
experience(action="search",
    query="Delphi compiler configuration",
    tags=["Delphi", "compile"])
```

### 9.5 Viewing and Managing

```python
# View experience details
experience(action="get", id="a1b2c3d4e5f6")

# Browse the list
experience(action="list", limit=20)
experience(action="list", tags=["Delphi"], sort_by="hit_count", limit=10)

# Update experience
experience(action="update", id="a1b2c3d4e5f6",
    solution="More complete solution steps...")

# Merge multiple experiences
experience(action="merge",
    ids=["a1b2c3d4e5f6", "b2c3d4e5f6a7"])

# List low-value experiences
experience(action="prune", limit=20)

# Delete experience
experience(action="delete", id="a1b2c3d4e5f6")
```

### 9.6 Automatic Deduplication Mechanism

`save()` is not a simple INSERT, but an intelligent "query first, then decide" flow:

| Similarity | Handling |
|--------|---------|
| > 0.85 | **Automatically merge** into the old record, no new entry |
| > 0.7 | **Intercept and remind**, manual judgment suggested |
| ≤ 0.7 | **Create normally** |

### 9.7 Best Practices for Experience Maintenance

1. **Generalize before saving**: First `search()` to confirm whether a similar experience already exists; if found, merge it with `merge`/`update`
2. **Actively merge after task completion**: When the new solution is related to an old experience but differs in approach, merge manually
3. **Clean up regularly**: Run `prune` to list low-value records, review and `delete`
4. **Abstract and merge when duplicates are found**: Merge similar problems into one abstract experience, with `tags` covering various scenarios
5. **Regularize when hit ≥ 3**: Evaluate whether it can be upgraded to a formal CODING_RULES rule

---

## Chapter 10: Delphi RTTI Bridging

### 10.1 Tool Overview

`delphi_rtti` discovers and invokes the runtime capabilities of a Delphi application through Delphi Enhanced RTTI. Three-step method: guide → discover → call.

### 10.2 Prerequisites

Add the automation unit to the Delphi project's `.dpr` file:

```pascal
program MyApp;

uses
  Vcl.Forms,                              // VCL project
  // or FMX.Forms,                        // FMX project
  Vcl.DaofyAutomation in 'path\to\tools\auto\Vcl.DaofyAutomation.pas',
  DaofyAutomation.Base in 'path\to\tools\auto\DaofyAutomation.Base.pas',
  // or Fmx.DaofyAutomation (FMX project)
  MainForm in 'MainForm.pas';

begin
  Vcl.DaofyAutomation.AutoStart;          // Start the automation pipeline thread
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
```

### 10.3 Three-Step Workflow

```python
# Step 1: Get the usage guide
delphi_rtti(action="guide")

# Step 2: Discover capabilities
delphi_rtti(action="discover",
    app_path="C:\\App\\MyApp.exe")
# Optional: restrict the class name, keep the process alive
delphi_rtti(action="discover",
    app_path="C:\\App\\MyApp.exe",
    class_name="TMainForm",
    keep_alive=True)

# Step 3: Call a method
delphi_rtti(action="call",
    app_path="C:\\App\\MyApp.exe",
    class_name="TMainForm",
    method="CreateOrder",
    params={"customerName": "Zhang San", "amount": 100})
```

### 10.4 Type Mapping

| Delphi Type | JSON Type | Description |
|------------|----------|------|
| string (UnicodeString/AnsiString) | string | UTF-8 encoded |
| Integer, SmallInt, Int64 | integer | — |
| Single, Double, Currency | number | — |
| Boolean, ByteBool | boolean | — |
| TDateTime | string | format: date-time |
| Enum type | string | with enum constraint |
| Dynamic array/TArray | array | element types mapped recursively |
| TObject subclass | object | limited support |
| Variant | [string, number, boolean, null] | — |

### 10.5 AI Annotations (Custom Attributes)

Add `AI`-prefixed attribute annotations on Delphi methods or parameters to provide richer context for the AI Agent:

```pascal
[AIDescription('Create a customer order and return the new order number')]
[AIResultDescription('The newly created order number; returns -1 on failure')]
[AIExample('CreateOrder("Zhang San", 100) → 10001')]
function CreateOrder(
  [AIParamDescription('Customer name')] const customerName: string;
  [AIParamDescription('Order amount (yuan)')] amount: Integer
): Integer;
```

| Attribute | Applied Position | Description |
|------|---------|------|
| `[AIDescription('...')]` | Method | Function description |
| `[AIResultDescription('...')]` | Method | Return value description |
| `[AIExample('...')]` | Method | Call example |
| `[AIParamDescription('...')]` | Parameter | Parameter meaning |

---

## Chapter 11: Automated Testing

### 11.1 Tool Overview

`automate_delphi` drives Delphi program automated testing, supporting **GUI screenshot mode** (Named Pipe) and **console interaction mode** (subprocess stdin/stdout).

### 11.2 Action Cheat Sheet

| Action | Mode | Description |
|--------|------|------|
| `auto` (default) | Auto-detect | Read the PE header to automatically identify GUI vs Console |
| `gui` | Named pipe GUI operations | Requires linking the DaofyAutomation unit |
| `console` | Console interaction | No Delphi-side modification required |

### 11.3 GUI Mode

GUI mode communicates with the Delphi program through a named pipe and supports the following commands:

**Perception commands** (get UI state):
| Command | Purpose |
|------|------|
| `capture` | Capture a screenshot of the current window |
| `dumpstate` | Export the complete control tree as JSON |
| `formsum` | Form summary (compact version of dumpstate) |
| `listwnd` | Enumerate all top-level windows |
| `msgscan` | Scan MessageBox popups |
| `dlgscan` | Scan file dialog state (synchronous) |
| `rinspect` | RTTI member discovery |

**Execution commands** (operate the UI):
| Command | Purpose |
|------|------|
| `goto` | Navigate to the target control |
| `click` / `rclick` / `dblclick` | Single-click/right-click/double-click (asynchronous) |
| `type` | Enter text (asynchronous) |
| `key` | Press Tab/Enter/Esc (asynchronous) |
| `hover` / `move` / `drag` | Mouse operations (asynchronous) |
| `rcall` / `rset` | RTTI invoke method/set property (asynchronous) |
| `msgclick` / `dlgclick` / `msgclose` | Popup/menu click and close (`msgclose` synchronous) |
| `dlgfile` | Enter a path in a file dialog (synchronous) |
| `snapdir` | Set the screenshot output directory (synchronous) |
| `exit` | Exit the target process |

**Verification commands** (confirm results):
| Command | Purpose |
|------|------|
| `waitfor` | Wait until a condition is satisfied |
| `wait` | Fixed time wait (milliseconds) |
| `rget` | RTTI read property value (preferred assertion method) |
| `rinspect` | RTTI member discovery (synchronous, view property names/types/methods, not values) |

### 11.4 GUI Mode Example

```python
# Basic automation
automate_delphi(action="gui",
    app_path="C:\\MyApp\\Win32\\Debug\\MyApp.exe",
    script=[
        {"cmd": "goto", "target": "TLoginForm"},
        {"cmd": "type", "target": "EditUser", "value": "admin"},
        {"cmd": "key", "target": "EditPwd", "key": "Tab"},
        {"cmd": "type", "target": "EditPwd", "value": "123456"},
        {"cmd": "click", "target": "BtnLogin"},
        {"cmd": "waitfor", "target": "StatusBar",
         "prop": "Caption", "value": "Login successful", "timeout": "5000"},
        {"cmd": "capture", "target": "login_result"},
    ],
    keep_alive=True)    # Process reuse
```

### 11.5 Process Reuse Mode

`keep_alive=true` keeps the process resident, avoiding repeated startup:

```python
# First time: start and keep alive
automate_delphi(app_path="MyApp.exe", script=[goto, capture], keep_alive=True)
# → returns process_reused:false, process_alive:true

# Second time: reuse the existing process
automate_delphi(app_path="MyApp.exe", script=[click, capture])
# → returns process_reused:true, process_alive:true

# At the end: send exit to terminate
automate_delphi(app_path="MyApp.exe", script=[exit])
# → returns process_alive:false
```

### 11.6 Console Mode

Console mode interacts with console programs through subprocess stdin/stdout, **no Delphi-side modification required**:

```python
# Basic interaction
automate_delphi(action="console",
    app_path="Deploy.exe",
    input="Y\n",
    expect="Deploy complete",
    args=["--silent"],
    timeout=30)

# Timeout test
automate_delphi(action="console",
    app_path="Tool.exe",
    timeout=5)
```

### 11.7 Screenshot Principles

The `capture` command automatically selects the best screenshot method:

| Scenario | Method |
|------|------|
| MessageBox/TaskDialog popup | `FindWindowW('#32770')` → GDI BitBlt → JPEG |
| FMX modal dialog | `TFmxFormState.Modal` detection → PaintTo |
| FMX 3D form | `TContext3D.CopyToBitmap` GPU readback |
| FMX 2D form | `TCustomForm.PaintTo(Canvas)` |
| VCL form | `GetWindowDC` + GDI BitBlt |

### 11.8 MCP Prompt Templates

Daofy registers **7 MCP Prompt templates**, designed specifically for the automated testing workflow. When the client supports the MCP Prompts protocol, they can inject the testing role and guide code analysis and test step planning.

| Template Name | Purpose |
|--------|------|
| `automate-expert-primer` | 🎭 **Inject the testing expert role**: set the identity and the three-layer progressive thinking model |
| `automate-code-analysis` | 🔍 **Code-aware analysis**: read DFM/PAS to generate a control mapping table, event analysis, and test paths |
| `automate-test-plan` | 📋 **Start test planning**: role setting + code analysis + structured step sequence |
| `automate-step-execute` | ⚡ **Single-step execution protocol**: pre-perception → execute → wait → verify |
| `automate-failure-recover` | 🔧 **Failure recovery**: diagnose → decide → recover → learn |
| `automate-save-experience` | 💾 **Save experience**: structurally record success/failure patterns |
| `automate-session-end` | 🏁 **End the session**: save experience, export scripts, switch the role back to development mode |

```python
# Usage example (via the MCP protocol prompts/get):
# 1. Inject the expert role
prompts/get name="automate-expert-primer" arguments={"app_name": "MyApp.exe", "project_path": "C:\\Project"}

# 2. Code-aware analysis
prompts/get name="automate-code-analysis" arguments={"form_name": "TNewCustomerForm", "project_path": "C:\\App"}

# 3. Use in combination with the automated testing workflow — see get_coding_rules(section="automation") for the complete methodology
```

> **Note**: MCP Prompts is an extension feature of the MCP protocol and requires AI client support. It does not conflict with Daofy's `automate_delphi` tool and can be used together with it.

---

## Chapter 12: OCR Image Text Recognition

### 12.1 Tool Overview

`ocr` provides image analysis capabilities: PP-OCRv6 text recognition, screenshot diff comparison, color analysis, and icon matching.

> ⚠️ **Optional feature**, requires installation: `pip install daofy-for-delphi[ocr]`

### 12.2 Action Quick Reference

| Action | Purpose |
|--------|---------|
| `recognize` | Full OCR pipeline: detection → orientation classification → text recognition |
| `detect` | Text box detection only |
| `status` | Query model loading status and backend info |
| `diff` | Screenshot diff comparison (pixel-level) |
| `color` | Region color analysis |
| `match` | Icon template matching |

### 12.3 Usage Examples

```python
# Query model status
ocr(action="status")

# Text recognition
ocr(action="recognize", image_path="screenshot.png")

# Text box detection only
ocr(action="detect", image_path="screenshot.png")

# Screenshot diff comparison
ocr(action="diff",
    baseline="before_test.png",
    current="after_test.png",
    threshold=10)

# Region color analysis
ocr(action="color",
    image_path="screenshot.png",
    region=[180, 170, 75, 25])    # [x, y, w, h]

# Icon matching
ocr(action="match",
    image_path="screenshot.png",
    template_path="save_icon.png",
    threshold=0.8)
```

### 12.4 Technical Architecture

| Component | Description |
|------|------|
| **Model** | PP-OCRv6 (~65MB) |
| **Inference Engine** | ONNX Runtime (OpenVINO acceleration optional on Intel CPU) |
| **Image Processing** | OpenCV + Pillow |
| **First Load** | Automatically downloads model to `data/ocr-models/` |

### 12.5 Response Format

```json
// recognize response
{
  "status": "ok",
  "action": "recognize",
  "count": 3,
  "results": [
    {
      "text": "确定",
      "confidence": 0.97,
      "box": [[10,20],[100,20],[100,50],[10,50]],
      "det_score": 0.85
    }
  ]
}

// diff response
{
  "changed": true,
  "diff_pixels": 1234,
  "diff_percent": 0.52,
  "regions": [{"bbox": [10,20,100,60], "area_pct": 0.3, "mean_diff": 45.3}]
}

// color response
{
  "avg_color": {"r": 255, "g": 0, "b": 0},
  "is_grayscale": false,
  "brightness": 0.33
}

// match response
{
  "found": true,
  "match_count": 1,
  "matches": [{"bbox": [100,200,130,230], "confidence": 0.92}]
}
```

---

## Chapter 13: Component Management

### 13.1 Tool Overview

`manage_component` manages **components (controls)** in Delphi forms, supporting adding, deleting, and modifying DFM components and automatic DFM↔PAS synchronization.

> ⚠️ **Note**: `manage_component` manages UI components on forms (such as TButton, TEdit), which is a different concept from the **component packages** (`.dpk` package files) managed by `package`.

### 13.2 Action Quick Reference

| Action | Purpose | Required Parameters |
|--------|------|---------|
| `create` | Generate a DFM definition text for a component (compile + runtime serialization) | `code` |
| `add` | Add a child component to an existing DFM, automatically syncing PAS | `target_dfm`, `new_component_class` (mutually exclusive with `dfm_text`) |
| `remove` | Delete a component (including its subtree) from a DFM, automatically syncing PAS | `target_dfm`, `component_name` |
| `modify` | Modify component properties in a DFM, syncing PAS when events change | `target_dfm`, `component_name`, `properties` |

### 13.3 DFM↔PAS Synchronization Rules

`add`/`remove`/`modify` operations **automatically synchronize** the corresponding PAS file:

| Operation | PAS Sync Content |
|------|-------------|
| **add** | New field declaration + event method stub (procedure declaration + implementation) + newly added uses units |
| **remove** | Delete field declaration + delete event methods (declaration + implementation) |
| **modify** | Event property changes → add/delete/modify event method declarations (no sync when property values are unchanged) |

### 13.4 Creating a Component DFM (create)

Compile and run the specified Pascal code, then serialize the component's DFM text from runtime RTTI:

```python
manage_component(action="create",
    code='''function CreateComponent(AOwner: TComponent): TComponent;
var
  Btn: TButton;
begin
  Btn := TButton.Create(AOwner);
  Btn.Caption := ''OK'';
  Btn.Name := ''BtnOK'';
  Btn.Left := 100;
  Btn.Top := 50;
  Result := Btn;
end;''',
    uses=["Vcl.StdCtrls"],
    type_decl='',
    init_code='')
```

| Parameter | Required | Default | Description |
|------|------|------|------|
| `code` | ✅ | — | Pascal implementation code, must contain `function CreateComponent(AOwner: TComponent): TComponent;` |
| `uses` | ❌ | [] | List of units to reference |
| `type_decl` | ❌ | "" | Type declaration section (used to declare Form classes, event stubs, etc.) |
| `init_code` | ❌ | "" | Initialization code (custom Form classes require `RegisterClass`) |
| `compile_timeout` | ❌ | 60 | Compile timeout in seconds |
| `exec_timeout` | ❌ | 15 | Execution timeout in seconds |

### 13.5 Adding a Component (add)

Add a child component to an existing DFM file and automatically sync the PAS field declarations and event methods:

```python
# Basic addition
manage_component(action="add",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    parent_name="",
    new_component_class="TButton",
    new_component_name="BtnOK",
    properties={"Caption": "确认", "Left": "100", "Top": "50",
                "OnClick": "BtnOKClick"})

# Add without specifying a name (auto-generates Button1)
manage_component(action="add",
    target_dfm="Unit1.dfm",
    new_component_class="TButton",
    properties={"Caption": "取消"})

# Add a complex component using a DFM text snippet
manage_component(action="add",
    target_dfm="Unit1.dfm",
    dfm_text='''object Panel1: TPanel
  Left = 0
  Top = 0
  Width = 300
  Height = 200
  Caption = "Panel"
end''')
```

| Parameter | Required | Description |
|------|------|------|
| `target_dfm` | ✅ | Target DFM file path |
| `target_pas` | ❌ | PAS file path (automatically syncs declarations when provided) |
| `parent_name` | ❌ | Parent component name (added under the root component by default) |
| `new_component_class` | ✅ (mutually exclusive with dfm_text) | New component class name (e.g., TButton) |
| `new_component_name` | ❌ | New component instance name (auto-generated such as Button1 by default) |
| `properties` | ❌ | Property dictionary (e.g., `{"Caption": "OK", "OnClick": "BtnClick"}`) |
| `dfm_text` | ❌ | DFM text snippet (replaces new_component_class+properties) |

### 13.6 Removing a Component (remove)

Delete a component and its subtree from a DFM, and simultaneously auto-delete the corresponding field declarations and event methods in the PAS:

```python
manage_component(action="remove",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnCancel")
```

| Parameter | Required | Description |
|------|------|------|
| `target_dfm` | ✅ | Target DFM file path |
| `target_pas` | ❌ | PAS file path (automatically syncs deletions when provided) |
| `component_name` | ✅ | Name of the component to delete |

The system automatically handles:
- Deleting the component and all its child components from the DFM
- Deleting the field declaration in the PAS (`BtnCancel: TButton;`)
- Deleting the event methods bound in the PAS (declaration section and implementation section)

### 13.7 Modifying a Component (modify)

Modify component property values in a DFM, and automatically sync PAS declarations when event bindings change:

```python
# Modify normal properties
manage_component(action="modify",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnOK",
    properties={"Caption": "确定", "Width": "100"})

# Modify event bindings (automatically syncs PAS declarations)
manage_component(action="modify",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnOK",
    properties={"OnClick": "BtnOKClickNew"})
```

| Parameter | Required | Description |
|------|------|------|
| `target_dfm` | ✅ | Target DFM file path |
| `target_pas` | ❌ | PAS file path (automatically syncs when events change) |
| `component_name` | ✅ | Name of the component to modify |
| `properties` | ✅ | Property dictionary (property names and values to modify) |

**Event synchronization rules**:
| Change Type | PAS Handling |
|---------|---------|
| New event binding (e.g., `OnClick=BtnClick`) | Add method declaration `procedure BtnClick(Sender: TObject);` + empty implementation |
| Modify event binding (`OnClick=OldClick` → `NewClick`) | Delete `OldClick` method + add `NewClick` method |
| Remove event binding (remove `OnClick` property) | Delete corresponding event method declaration+implementation |

> 💡 **Related chapters**:
> - [Chapter 6: Delphi File Operations](#第六章delphi-文件操作) — Learn more about DFM file read/write operations and backup management
> - [Chapter 10: Delphi RTTI Bridge](#第十章delphi-rtti-桥接) — Learn about runtime component analysis and remote invocation

---

## Chapter 14: Component Package Management

### 14.1 Tool Overview

`package` manages the compilation and installation of Delphi component packages. Supports package files in `.dproj`/`.dpk`/`.groupproj` formats.

### 14.2 Action Quick Reference

| Action | Purpose |
|--------|------|
| `install` (default) | Compile and install a component package |
| `list` | List component packages installed in the IDE |

### 14.3 Installing a Component Package

```python
# Install a .dpk package
package(action="install", package_path="MyPackage.dpk")

# Install a .dproj package
package(action="install", package_path="MyPackage.dproj")

# Install a .groupproj project group
package(action="install", package_path="MyPackage.groupproj")

# Release configuration, 64-bit
package(action="install",
    package_path="MyPackage.dpk",
    target_platform="win64",
    build_configuration="Release",
    timeout=300)

# Compile only without registering (runtime package)
package(action="install",
    package_path="MyRuntime.dpk",
    install=False)
```

### 14.4 Listing Installed Packages

```python
package(action="list")
```

### 14.5 Installation Process Description

| Package Type | Handling Method |
|--------|---------|
| **Design-time package** (Design-time) | Compile + automatically register to the IDE's `Known Packages` |
| **Runtime-only package** (Runtime-only) | Compile only, no registration |

---

## Chapter 15: Async Task Management

### 15.1 Tool Overview

`async_task` manages **background async tasks** in Daofy. Time-consuming operations (such as knowledge base construction, document scanning, and vector index building) execute in the background without blocking the MCP communication channel.

> Knowledge base construction is usually automatically triggered via `delphi_kb(action="build", async_mode=True)`, so manual invocation is not required.

### 15.2 Action Quick Reference

| Action | Purpose |
|--------|------|
| `start` | Start an async task |
| `status` | Query task status |
| `result` | Get task result |
| `list` | List all tasks |
| `cancel` | Cancel a running task |

### 15.3 Usage Examples

```python
# Query task status (short polling)
async_task(action="status", task_id="task_xxx")

# Long polling (wait up to 30 seconds)
async_task(action="status", task_id="task_xxx", long_poll_seconds=30)

# Get task result
async_task(action="result", task_id="task_xxx")

# List all tasks
async_task(action="list")

# Cancel a task
async_task(action="cancel", task_id="task_xxx")
```

### 15.4 Supported Task Types

| task_type | Description |
|-----------|------|
| `build_knowledge_base` | Build the Delphi source knowledge base |
| `build_thirdparty_knowledge_base` | Build a third-party library knowledge base |
| `init_project_knowledge_base` | Initialize the project knowledge base |
| `build_document_knowledge_base` | Build the document knowledge base |
| `build_embedding` | Build the vector index |

### 15.5 Notification Mechanism

Daofy supports **TaskStatusNotification push notifications**—whenever any async task completes/fails/is cancelled, a notification is automatically pushed to the MCP client, **no polling required**.

---

## Chapter 16: Daofy Self-Update Management

### 16.1 Tool Overview

`daofy_update` manages version checking and updates for the Daofy MCP Server itself. Supports updates for two installation modes:

| Installation Method | Update Method |
|---------|---------|
| **git clone** source installation | `git pull` to fetch the latest code |
| **pip install** installation | Prompt to use `pip install --upgrade daofy-for-delphi` |

### 16.2 Action Quick Reference

| Action | Purpose |
|--------|------|
| `check` | Check version (use cache/fast check first, automatically retry in the background on failure) |
| `check_retry` | Force submission of a background automatic version-check retry task (returns task_id) |
| `update` | Submit a background git pull update task (single attempt, returns task_id) |
| `update_retry` | Submit a background auto-retry git pull task (retry interval and count can be specified, returns task_id) |
| `version` | Show current version number and installation method (git/pip) |

### 16.3 Usage Examples

```python
# Check for updates (use cache/fast check first, automatically retry in the background on failure)
daofy_update(action="check")

# Force a background version-check retry (returns task_id)
daofy_update(action="check_retry")

# View current version
daofy_update(action="version")

# Perform update (git mode, single attempt)
daofy_update(action="update")

# Background auto-retry git pull (parameters can be specified)
daofy_update(action="update_retry", retry_interval=60, max_retries=10)

# Query background update progress via async_task
async_task(action="status", task_id="task_xxx")
```

### 16.4 Update Process

1. The server automatically checks for updates in the background at startup
2. When a new version is found, the AI is notified via smart prompts
3. The AI asks the user whether to update
4. After user confirmation, execute `daofy_update(action="update")`
5. After the update completes, **restart Daofy or the AI Agent** for the new version to take effect

---

## Chapter 17: Software Copyright Document Generation

### 17.1 Tool Overview

`generate_copyright` generates documents required for software copyright applications, including source code documents, software manuals, and application information summary tables.

### 17.2 Action Quick Reference

| Action | Purpose |
|--------|------|
| `generate` | Generate all copyright documents |
| `validate` | Check configuration completeness |
| `update_config` | Update configuration information |
| `status` | Check the browser environment |
| `list` | List generated files |
| `generate_content` | Generate a draft |
| `audit` | Audit the draft and identify rejection risks |

### 17.3 Usage Examples

```python
# Check configuration
generate_copyright(action="validate")

# Update configuration
generate_copyright(action="update_config",
    config={"contact_person": "张三", "phone": "138xxxxxxxx"})

# Generate documents
generate_copyright(action="generate")

# Audit the draft
generate_copyright(action="audit")
```

---

## Chapter 18: Troubleshooting and Best Practices

### 18.1 Common Troubleshooting

#### Compiler Not Found

```python
check_environment(action="detect")   # Re-detect
# Or manually specify the path
check_environment(action="detect", search_path="D:\\Delphi\\Studio")
```

#### MCP Server Fails to Start

```bash
# Check the Python environment
pip install -r requirements.txt
# Check the MCP library version
pip show mcp
```

#### Knowledge Base Search Returns No Results

```python
# Make sure the knowledge base has been built
delphi_kb(action="stats")                    # View statistics
delphi_kb(action="build", kb_type="project") # Build the project knowledge base
```

#### Cannot Find a Class/Function

- Check whether `kb_type` is correct (use `project` for project code)
- Try partial matching (class name only without namespace)
- Check whether the third-party library is installed/built
- Search directly by file path

#### "Dirty Flag" Error When Writing Files

```python
# Re-read the file first to get the latest line numbers
delphi_file(action="read", file_path="Unit1.pas")
# Or provide old_content verification in edit
```

#### Compilation Event Timeout

```python
# Increase the timeout parameter
delphi_project(action="compile", project_path="Project.dproj", timeout=900)
```


### 18.2 Knowledge Base Storage Locations

| Knowledge Base Type | Storage Path |
|-----------|---------|
| Delphi source knowledge base | `data/delphi-knowledge-base/` |
| Third-party library knowledge base | `data/thirdparty-knowledge-base/` |
| General document knowledge base | `data/document-knowledge-base/` |
| Project knowledge base | `<project directory>/.delphi-kb/` |
| Example knowledge base | `data/example-knowledge-base/` |
| Experience knowledge base | `data/experience-knowledge-base/` |

### 18.3 Knowledge Base Automatic Lifecycle

| Mechanism | Trigger Timing | Description |
|------|---------|------|
| **Auto-build at startup** | MCP Server startup | Automatically detects `.dproj` files under CWD and submits a background incremental KB build |
| **Hot-swap rebuild** | User manually rebuilds | Builds to a temporary directory while the old KB remains queryable; atomic swap upon completion |
| **File change watching** | User saves `.pas/.dfm/.dproj` | Requires `pip install daofy-for-delphi[watcher]`; automatically triggers incremental updates after a 3-second debounce |

### 18.4 Best Practices

#### Development Workflow

```python
# Standard Delphi development workflow
get_coding_rules(section="workflow")          # ① Learn the workflow
get_coding_rules(section="writing")           # ② Learn the coding standards
delphi_kb(query="TStringList")               # ③ Search API definitions
delphi_file(action="read", file_path=...)    # ④ Read source code to confirm modification points
delphi_file(action="write", edits=[...])     # ⑤ Write code
delphi_file(action="format", file_path=...)  # ⑥ Format
delphi_project(action="compile", project_path=...)  # ⑦ Compile and verify
get_coding_rules(section="review")           # ⑧ Review code
code_hosting(action="git_add", files=["."])  # ⑨ Stage code
code_hosting(action="git_commit", ...)       # ⑩ Create commit
code_hosting(action="git_push")              # ⑪ Push
```

#### Git Commit Message Convention

```bash
feat(scope): new feature
fix(scope): bug fix
docs(scope): documentation change
refactor(scope): refactor
test(scope): tests
chore(scope): build/tooling change
```

#### Knowledge Base Usage Principles

1. **Exact search first, semantic search later**: exact class name > function name > reference query > semantic search
2. **Use English search whenever possible**: English API names are far more accurate than Chinese semantic search
3. **Try alternative names when search returns nothing**: `TMainForm` → `TfrmMain` → `Form1`
4. **Use `kb_type="project"` for project code**: the default `all` does not include the project knowledge base

#### File Editing Safety Principles

1. **Merge multiple modifications into a single `write`**: do not call multiple times on the same file
2. **Automatic backup before formatting**: `backup=True` (default) ensures rollback capability
3. **Dirty flag protection**: files are marked dirty after writing; re-read is required before writing again
4. **old_content verification**: providing old_content in edit bypasses the dirty flag and ensures accurate line numbers

#### Experience Base Maintenance Principles

1. **Generalize before saving**: first search for existing similar experiences; if found, use merge/update
2. **Regular cleanup**: run prune monthly to list low-value records
3. **Promote to rule when hit ≥ 3**: high-frequency experiences are upgraded to formal CODING_RULES

---

## Appendix A: Quick Command Reference

### Environment and Configuration

```python
check_environment(action="check")            # Check the compilation environment
check_environment(action="detect")           # Detect compilers
```

### Knowledge Base

```python
delphi_kb(action="stats")                                    # View statistics
delphi_kb(query="TStringList")                               # Search for a class
delphi_kb(query="Create", search_type="function")             # Search for a function
delphi_kb(query="JSON compare", search_type="semantic")      # Semantic search
delphi_kb(action="build", kb_type="document")                # Build the document KB
delphi_kb(action="build", kb_type="project")                 # Build the project KB
```

### Compilation and Auditing

```python
delphi_project(action="compile", project_path="App.dproj")          # Compile the project
delphi_project(action="compile_file", project_path="Unit1.pas")     # Syntax check
delphi_project(action="ast", base_dir="src")                        # Code skeleton
delphi_project(action="audit", base_dir="src")                      # Code audit
```

### File Operations

```python
delphi_file(action="read", file_path="Unit1.pas")            # Read a file
delphi_file(action="write", file_path="Unit1.pas",           # Write a file
    edits=[{"start_line": 5, "content": "  // new code\n"}])
delphi_file(action="format", file_path="Unit1.pas")          # Format
delphi_file(action="encode", file_path="Unit1.pas",          # Encoding conversion
    to_encoding="utf-8")
delphi_file(action="uses", uses_action="add",                # Add uses
    unit_name="System.SysUtils", file_path="Unit1.pas")
```

### Code Hosting

```python
code_hosting(action="git_status")                            # View status
code_hosting(action="git_diff", stat=True)                    # View change summary
code_hosting(action="git_log", limit=5)                      # View commit history
code_hosting(action="git_add", files=["."])                  # Stage
code_hosting(action="git_commit", message="feat: xxx")       # Commit
code_hosting(action="git_branch")                             # List branches
code_hosting(action="git_switch", branch="feature")          # Switch branches
code_hosting(action="git_merge", branch="feature")           # Merge branches
code_hosting(action="git_fetch")                              # Fetch remote refs
code_hosting(action="git_pull")                               # Pull and merge
code_hosting(action="git_push")                              # Push
code_hosting(action="git_tag", tag="v1.0", message="v1.0") # Create a tag
code_hosting(action="create_issue", repo="my/myrepo",       # Create an issue
    title="Bug", body="description")
code_hosting(action="get_issue", repo="my/myrepo",           # View an issue
    issue_number=42)
code_hosting(action="edit_issue", repo="my/myrepo",          # Edit an issue
    issue_number=42, labels=["bug"])
```

### Experience and Updates

```python
experience(action="save", problem="...", solution="...")     # Save experience
experience(action="search", query="...")                     # Search experience
daofy_update(action="check")                                 # Check for updates
daofy_update(action="check_retry")                           # Force background retry check
daofy_update(action="update")                                # Background git pull update
daofy_update(action="update_retry")                          # Background auto-retry git pull
daofy_update(action="version")                               # View version
```

### Tool Help

```python
tool_help(tool_name="delphi_file")                           # View full tool help
tool_help(tool_name="project")                                # View project tool help
```

### Component Management

```python
manage_component(action="create", code="...", uses=["Vcl.StdCtrls"])  # Create a component DFM
manage_component(action="add", target_dfm="Unit1.dfm",        # Add a component
    new_component_class="TButton", properties={"Caption": "OK"})
manage_component(action="remove", target_dfm="Unit1.dfm",     # Remove a component
    component_name="BtnCancel")
manage_component(action="modify", target_dfm="Unit1.dfm",     # Modify component properties
    component_name="BtnOK", properties={"Caption": "确定"})
```

### Advanced Features

```python
delphi_rtti(action="discover", app_path="App.exe")           # RTTI discovery
delphi_rtti(action="call", app_path="App.exe",               # RTTI invocation
    class_name="TMainForm", method="CreateOrder")
automate_delphi(action="gui", app_path="App.exe",            # GUI automation
    script=[{"cmd":"goto","target":"TForm1"}])
automate_delphi(action="console", app_path="Tool.exe",       # Console interaction
    input="Y\n", expect="complete")
ocr(action="recognize", image_path="screenshot.png")         # OCR recognition
package(action="install", package_path="MyPackage.dpk")      # Install a component package
```

---

## Appendix B: Environment Variables

| Environment Variable | Description |
|---------|------|
| `PYTHONUNBUFFERED=1` | Disable Python output buffering |
| `PYTHONIOENCODING=utf-8` | Set standard I/O encoding to UTF-8 |
| `PYTHONUTF8=1` | Enable UTF-8 mode |
| `TRANSFORMERS_OFFLINE=1` | Offline mode (used when the embedding model is already cached) |

---

## Appendix C: Project Structure

```
daofy/
├── src/
│   ├── server.py              # MCP entry point
│   ├── tools/                 # MCP tool implementations
│   │   ├── project.py         # Project lifecycle management
│   │   ├── file_tool.py       # Delphi file operations
│   │   ├── knowledge_base.py  # Knowledge base search
│   │   ├── code_hosting.py    # Git/code hosting
│   │   ├── delphi_rtti.py     # RTTI bridge
│   │   ├── environment.py     # Environment check
│   │   ├── experience.py      # Experience memory
│   │   └── ...
│   ├── services/              # Business logic
│   │   ├── compiler_service.py
│   │   ├── automation_service.py
│   │   ├── rtti_bridge.py
│   │   └── knowledge_base/    # KB modules
│   ├── models/                # Data models
│   ├── resources/             # MCP Resource default documents
│   │   ├── coding-rules.md    # Built-in coding standards
│   │   └── automation/        # Automation test workflow resources
│   ├── utils/                 # Utility functions
│   └── tool_docs.py           # Tool documentation
├── config/
│   └── logging_config.json    # Logging configuration
├── tools/
│   ├── auto/                  # DaofyAutomation units
│   │   ├── DaofyAutomation.Base.pas
│   │   ├── Vcl.DaofyAutomation.pas
│   │   ├── Fmx.DaofyAutomation.pas
│   │   └── DaofyAutomation.RttiDiscovery.pas
│   └── daudit/                # Code audit engine
├── data/                      # Knowledge base data (generated at runtime)
├── docs/                      # Documentation
└── tests/                     # Test cases
```

---

## Appendix D: MCP Protocol Resources

Daofy provides stable documentation entry points to AI Agents via MCP Resources. Agents should preferentially read these
`delphi://...` URIs rather than relying directly on client-specific directories such as
`.opencode/`, `.claude/`, `.cursor/`, etc.

| Resource URI | Description |
|---------|------|
| `delphi://resources` | Daofy public resource index (Markdown format) |
| `delphi://coding-rules` | Delphi coding standards (Markdown format) |
| `delphi://automation/workflow` | Complete automation test workflow |
| `delphi://automation/script-generation-workflow` | Complete workflow for AI-generated automation scripts |
| `delphi://automation/script-schema` | `automate_delphi` script structure and assertion syntax |
| `delphi://automation/report-schema` | Automation test report structure and interpretation |
| `delphi://automation/repair-loop` | Failure diagnosis, script correction, code correction, and re-run loop |
| `delphi://automation/inline-unit` | `tools/auto` Delphi inline unit integration guide |
| `delphi://health` | Server health status (JSON format) |

```python
# View the public resource index
# Access delphi://resources via MCP resources/read

# View server status
# Access delphi://health via MCP resources/read
```

Resources are responsible for providing standards and process documentation; Prompts are responsible for launching specific workflows; Tools are responsible for actually
executing compilation, file editing, automation testing, and experience recording.

---

> **Copyright**: Copyright © 2026 吉林省左右软件开发有限公司 / Equilibrium Software Development Co., Ltd, Jilin
>
> **License**: MIT License
>
> **Contact**: Submit an Issue to [GitHub](https://github.com/chinawsb/daofy) | QQ Group: 250530692