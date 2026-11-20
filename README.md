# Daofy — Multi-Language MCP Server for Delphi & Lazarus/FPC

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![Delphi 2005-13](https://img.shields.io/badge/Delphi-2005%20to%2013-red.svg)
![Lazarus/FPC](https://img.shields.io/badge/Lazarus-FPC-brightgreen)
[![Powered by OrcaRouter](https://img.shields.io/badge/Powered_by-OrcaRouter-2563eb)](https://www.orcarouter.ai/ref/ref_18b07a7c594033c5f754)

> 💡 **Promotion**: This tool is sponsored by [OrcaRouter](https://www.orcarouter.ai/ref/ref_18b07a7c594033c5f754). OrcaRouter is a powerful AI routing engine that intelligently dispatches the most suitable AI model for your task. Click the link above to learn more.

An MCP Server that gives AI assistants the ability to compile **Delphi** and **Lazarus/Free Pascal** projects and query knowledge bases. If you find it useful, please don't forget to give it a Star! ⭐

Daofy — spread your wings for creativity.

## Project Introduction

Daofy is an MCP Server built on the Model Context Protocol (MCP) that lets AI assistants compile **Delphi** and **Lazarus/Free Pascal** projects and query knowledge bases directly.

With this tool you can compile projects, look up API documentation and search code examples right inside a conversation with your AI assistant — no manual switching to the IDE or the command line.

**Key advantages:**

- **Multi-language support**: works with both the Embarcadero Delphi and the Lazarus/Free Pascal toolchains
- **Plugin architecture**: language plugins register dynamically and are enabled only when the corresponding development tools are installed
- **Delphi automation testing**: a built-in GUI/Console automation framework that lets AI-driven scripts drive Delphi applications
- Seamless integration into AI assistant workflows
- Automatic detection and configuration of compilers
- Built-in source knowledge base with semantic search
- Project-level knowledge base that tracks third-party libraries and project source automatically
- A general document knowledge base supporting full-text search over Delphi CHM and FPC documentation
- Support for all mainstream AI assistant platforms
- Complete build event support
- Detailed error diagnostics and logging

## Features

### Compilation

- **Whole-project compilation**: builds complete Delphi projects (.dproj/.dpr) and produces executables or dynamic link libraries
- **MSBuild compilation**: MSBuild is preferred, with dependencies and build events handled automatically
- **Single-file compilation**: compiles an individual Delphi unit (.pas) for syntax checking
- **Automatic compiler detection**: detects installed Delphi compilers from the registry, no manual configuration required
- **Smart library path resolution**: analyses project dependencies and intelligently selects the third-party library paths that are needed, avoiding an over-long command line
- **Build event support**: PreBuildEvent, PostBuildEvent and PreLinkEvent, with complete parameter substitution
- **Command line argument generation**: generates Delphi compiler command line arguments for debugging and preview
- **Compiler configuration management**: configure and manage several Delphi compiler versions
- **Environment checking**: reports the state of the compiler environment
- **Rich compilation options**: conditional compilation symbols, search paths, optimisation options, debug information, warning control and more

### Knowledge base

- **Delphi source knowledge base**: built-in knowledge base over the official Delphi source, with class and function search plus semantic search
- **Project knowledge base**: a separate knowledge base per project, tracking third-party libraries and project source automatically
- **Third-party library knowledge base**: extracts third-party library paths from the .dproj file and builds a knowledge base over them
- **Incremental updates**: detects source changes and updates the project knowledge base incrementally
- **Example knowledge base**: discovers the official Delphi Demos/Samples and third-party Demos/Tests, with full-text search over example code
- **General document knowledge base**: scans and searches txt/md/html/docx/doc/pdf/epub/hlp/chm and web documents (backed by the ZVec vector store plus a full-text index)
  - Required dependencies: `html2text`, `requests` (already in requirements.txt)
  - Optional dependencies: `python-docx` (Word .docx), `antiword/catdoc` (legacy Word .doc), `PyMuPDF` (PDF, recommended) or `pdfplumber` (PDF, alternative), `beautifulsoup4` (EPUB)
- **Smart de-duplication**: de-duplicates by full path, so files with the same name in different directories are handled correctly

### Building the Delphi help documentation knowledge base

On first use, or whenever the Delphi API documentation has to be rebuilt, call the `delphi_kb` tool with `action="build"`:

```
delphi_kb(
    action="build",
    kb_type="document",
    async_mode=true
)
```

Notes:

- **Without `directory`** the most recently installed Delphi help directory is detected automatically (through the registry or a default path)
- You can also point at it explicitly: `directory="C:\Program Files (x86)\Embarcadero\Studio\<version>\Help\Doc"`
  - Version mapping: 37.0 = Delphi 13, 23.0 = Delphi 12, 22.0 = Delphi 11, 21.0 = Delphi 10.4, 20.0 = Delphi 10.3
- `extensions=[".chm"]`: scan CHM files only; the tool unpacks and imports the HTML documentation by itself
- `async_mode=true`: run asynchronously (it takes several minutes), returning a `task_id` you can poll with `async_task(action=status, task_id=...)`
- 7-Zip must be installed on the system (it can also live in `tools/7z/` for a portable setup)

### Building the example knowledge base

Build a full-text knowledge base over the official Delphi Demos/Samples and the third-party Demos/Tests:

```
delphi_kb(
    action="build",
    kb_type="example"
)
```

Search example code:

```
delphi_kb(
    query="TThread.Queue",
    kb_type="example"
)
```

The example knowledge base is full-text only: it does not parse structured symbols (classes/functions), which makes it a fast way to find example usage.
With `kb_type="all"` the example knowledge base is not searched by default — pass `kb_type="example"` explicitly.

### Coding rules

- **Coding rule lookup**: returns the Delphi source coding rules an AI assistant uses for code review and code generation
- **Default rules**: a built-in default rule set covering naming, formatting, modification and review rules
- **Custom rules**: project-level custom coding rules take precedence over the defaults
- **Rule precedence**: project custom rules > default rules

### Automation testing

Daofy ships a Delphi GUI/Console automation test framework that supports AI-driven UI interaction testing:

- **Named-pipe GUI automation**: add the `DaofyAutomation` unit to a Delphi program and the AI drives the UI through the `automate_delphi` tool (click / type / capture / assert)
- **Console interaction tests**: test console applications over stdin/stdout without modifying the Delphi program
- **Script driven**: JSON test scripts with conditional waits (`waitfor`), RTTI property read/write (`rget`/`rset`) and screenshot comparison
- **Process reuse**: in `keep_alive` mode the process stays resident, avoiding repeated start-up cost
- **Report and repair loop**: a failure is located down to the failing step and a repair suggestion is produced

> 📖 **Enabling guide**: how to wire automation testing into your own Delphi project is described in the "Enabling guide" section of [`docs/automate_test_guide.md`](docs/automate_test_guide.md).

## MCP tool list

| Tool | Description |
|------|-------------|
| **Delphi tools** | |
| `delphi_project` | Full Delphi project lifecycle: compile (compile) / configuration (info, set, create) / audit (audit, ast, runtime) |
| `delphi_kb` | Search code, classes, functions, documentation and example code; show statistics; build a knowledge base |
| `delphi_file` | Delphi-specific file operations: read / write (batch `edits`) / format / backup management (encoding detection + automatic backup + DFM conversion) |
| `manage_component` | Add, remove, modify and generate DFM components, with automatic PAS synchronisation |
| `check_environment` | Diagnose the build environment, detect compilers, install pasfmt |
| `package` | Component package management: install (`action=install`) / list installed (`action=list`) |
| `get_coding_rules` | Fetch coding rules, by language (Delphi/Lazarus) and by section |
| `automate_delphi` | Delphi GUI/Console automation testing — script driven (click/type/waitfor/rget/capture), covering both the named-pipe GUI mode and the console mode, with `keep_alive` process reuse |
| `delphi_rtti` | Delphi RTTI bridge — discover and invoke the runtime capabilities of a Delphi application through RTTI (three steps: discover / call / guide) |
| **Lazarus/Free Pascal tools** | |
| `lazarus_compile` | Lazarus/FPC project compilation (lazbuild), supporting `.lpi`/`.lpr` project files |
| `lazarus_project` | Lazarus project information — parses the `.lpi` file for project name, source files and compiler options |
| `lazarus_kb` | Lazarus/FPC source knowledge base — indexes and searches LCL/FPC RTL source (a separate KB) |
| `lazarus_file` | Lazarus/FPC file read/write — read / write (batch `edits`, automatic backup) / backup |
| **Shared tools** | |
| `code_hosting` | One interface over Gitea/GitHub/GitLab/Gitee/GitCode plus local Git operations |
| `async_task` | Manage background tasks (knowledge base builds and similar) |
| `daofy_update` | Check for a Daofy update and run a git pull (check/update/version), executed asynchronously in the background |
| `tool_help` | Full help for any tool on demand (parameters, examples, trigger words) |
| `generate_copyright` | Software copyright document generation: source code, manual and abstract produced automatically (PDF rendered in a browser and validated automatically) |
| `experience` | Experience memory: save, search, update, merge and delete the practices an AI used to solve problems; prune low-value entries periodically; rebuild missing vectors once the model is loaded (`rebuild_embedding`) |
| `ocr` | Image analysis: text recognition (recognize) / text boxes (detect) / screenshot comparison (diff) / colour analysis (color) / icon matching (match) |
| `structured_content` | Unified read/write, search and modification of structured documents — DFM/LFM/FMX/XML/JSON/MessagePack/ProtoBuf. read / get_schema (JSON Schema generation) / set (modify by JSONPath) / search (path search) |

## System requirements

- Python 3.10-3.14
- **Delphi**: a Delphi compiler (dcc32.exe or dcc64.exe) to compile Delphi projects
- **Lazarus/FPC**: the Lazarus IDE (lazbuild.exe) to compile Lazarus projects (optional)
- Windows
- Git
- 7-Zip (used to unpack CHM help files, optional)

Compilers are detected automatically (PATH / registry / common install directories), so no manual configuration is needed. The relevant plugin is enabled as soon as the matching development tool is installed.

## Where knowledge bases are stored

All knowledge base data lives under the `data/` folder in the project root:

| Knowledge base | Storage path | Notes |
|-----------|---------|------|
| Delphi source knowledge base | `data/delphi-knowledge-base/` | Official Delphi source (RTL/VCL/FMX and so on) |
| Lazarus/FPC source knowledge base | `data/lazarus-knowledge-base/` | Lazarus LCL / FPC RTL source (a separate index) |
| Third-party library knowledge base | `data/thirdparty-knowledge-base/` | Third-party component library source |
| General document knowledge base | `data/document-knowledge-base/` | Delphi CHM help plus general documents |
| Project knowledge base | `<project dir>/.delphi-kb/` | A project-level knowledge base, kept inside the project directory |
| Example knowledge base | `data/example-knowledge-base/` | Official Delphi Demos plus third-party Demos/Tests, full-text search |
| Experience knowledge base | `data/experience-knowledge-base/` | AI experience memory (`experiences.sqlite`) |

Each knowledge base directory contains:

- `*.zvec/` — the ZVec vector database directory (document, example, project and third-party knowledge bases)
- `experiences.sqlite` — the experience memory database (only the experience knowledge base keeps SQLite)
- `config.json` — the knowledge base configuration file

Note: apart from the experience knowledge base, every knowledge base has moved from SQLite to the ZVec vector engine. The document knowledge base no longer uses SQLite FTS5; it uses the ZVec full-text index.

## Knowledge base configuration

Each knowledge base is configured through a `config.json` file that supports custom database settings, source paths, build parameters and more.

| Knowledge base | Configuration location |
|-----------|----------|
| Delphi source | `data/delphi-knowledge-base/config.json` |
| Third-party libraries | `data/thirdparty-knowledge-base/config.json` |
| General documents | `data/document-knowledge-base/config.json` |
| Project level | `<project dir>/.delphi-kb/config.json` |
| Example base | `data/example-knowledge-base/` (pure SQLite, no config.json) |
| Experience base | `data/experience-knowledge-base/` (pure SQLite, no config.json) |

Configuration files are generated automatically on the first build, so they rarely need editing by hand.

## Installation

### Option 1: install from pip (recommended)

```bash
pip install daofy-for-delphi
```

Once it is installed, go straight to [Configure your AI assistant](#configure-your-ai-assistant).

> **Users in mainland China** can speed this up with a mirror:
> ```bash
> pip install daofy-for-delphi -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

### Option 2: install from source

#### Prompt for an AI assistant to install it

Please install Daofy by following these steps:

[] Check for and install Git/Python 3.10-3.14/7-Zip

[] Install `https://github.com/chinawsb/daofy.git` (users in mainland China can use the mirror `https://gitee.com/zuoyouruanjian/daofy.git`)

[] Verify the result after installation and configure my current client for me

#### Manual installation

##### 1. Clone or download the project

```bash
git clone https://github.com/chinawsb/daofy.git
# Users in mainland China can use the Gitee mirror for speed:
# git clone https://gitee.com/zuoyouruanjian/daofy.git
cd daofy
```

##### 2. Create a virtual environment

```bash
python -m venv venv
```

##### 3. Activate the virtual environment

Windows:

```bash
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

##### 4. Install the dependencies (using a mainland-China mirror for speed)

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Optional mirrors:

- Tsinghua: <https://pypi.tuna.tsinghua.edu.cn/simple>
- Aliyun: <https://mirrors.aliyun.com/pypi/simple/>
- USTC: <https://pypi.mirrors.ustc.edu.cn/simple/>

## Configure your AI assistant

### Automatic Delphi compiler detection

**On first use the MCP Server detects the installed Delphi compilers from the Windows registry; no manual configuration is needed.**

Delphi versions detected automatically:

- Delphi 13 Florence (37.0)
- Delphi 12 Athens (23.0)
- Delphi 11 Alexandria (22.0)
- Delphi 10.4 Sydney (21.0)
- Delphi 10.3 Rio (20.0)
- Delphi 10.2 Tokyo (19.0)
- Delphi 10.1 Berlin (18.0)
- Delphi 10 Seattle (17.0)
- Delphi XE8 (16.0)
- Delphi XE7 (15.0)
- Delphi XE6 (14.0)
- Delphi XE5 (12.0)
- Delphi XE4 (11.0)
- Delphi XE3 (10.0)
- Delphi XE2 (9.0)
- Delphi XE (8.0)
- Delphi 2010 (7.0)
- Delphi 2009 (6.0)
- Delphi 2007 (5.0)
- Delphi 2006 (4.0)
- Delphi 2005 (3.0)

### Manual compiler configuration (optional)

If you need to configure a compiler by hand or add a custom one, edit `config/compilers.json`, or re-run detection with the `detect` action of the `check_environment` tool.

#### Choosing MSBuild and the Delphi version (per project / per version)

When several Delphi versions coexist, **the recommended place for the configuration is the project directory**: different projects on the same machine can then each use their own Delphi/MSBuild without affecting one another.

**Project-level configuration (recommended)**: place `.daofy/project.json` or `daofy.project.json` in the project directory (or in any parent directory, up to eight levels up):

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe",
  "compiler_version": "Delphi XE4 Win32"
}
```

| Field | Description |
|------|------|
| `delphi_version` | The Delphi version this project uses: the registry version number (`"11.0"`), the product name (`"XE4"`) or the `.dproj ProjectVersion` (`"14.6"` → XE6, `"18.2"` → Berlin, `"19.2"` → Tokyo) |
| `msbuild_path` | The `MSBuild.exe` this project uses; a relative path is resolved against the directory holding the configuration file |
| `compiler_version` | The compiler name in `compilers.json`; a version number (`"11.0"`) also works |

- Nearest match wins: the configuration file closest to the project applies, and fields it does not set fall through to the next rule
- The project-level configuration applies to compilation, to `install_package` (BPL/DCP/IDE registration) and to `deploy`
- A project configuration can point at any executable path, so **only use it with trusted projects**

**Per-version configuration (`compilers.json`, optional)**:

| Option | Description |
|--------|------|
| `msbuild_by_delphi_version` | A per-Delphi-version MSBuild mapping, e.g. `{"11.0": "...\\v3.5\\MSBuild.exe", "23.0": "...\\MSBuild.exe"}` |

```json
{
  "compilers": [ ... ],
  "default_compiler": "Delphi XE4 Win32",
  "msbuild_by_delphi_version": {
    "11.0": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe",
    "23.0": "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe"
  }
}
```

The keys of `msbuild_by_delphi_version` accept a registry version number (`"11.0"`), a product name (`"XE4"`) or a `.dproj ProjectVersion` (`"14.6"` and so on). Relative paths in the mapped values are resolved against the directory holding `compilers.json`.

> The global `msbuild_path`, `default_registry_version` and the `DAOFY_MSBUILD` / `DAOFY_DELPHI_VERSION` environment variables have been removed. Those keys are ignored if present in an old configuration; use the project-level `.daofy/project.json` (single project) or `msbuild_by_delphi_version` (per version) instead.

**Selection precedence**:

- Delphi version: the tool argument `compiler_version` > the project configuration's `compiler_version` > the project configuration's `delphi_version` > inferred from `.dproj ProjectVersion`
- MSBuild: the project configuration's `msbuild_path` > `msbuild_by_delphi_version[version]` > automatic detection

Behaviour notes:

- The version from the project configuration also drives MSBuild's `rsvars.bat`, automatic compiler matching, direct `dcc32` compilation and the RTL/third-party library search paths, which prevents "compiling with XE4's dcc32 while picking up Delphi 12's dcu files"
- When an explicitly configured MSBuild path does not exist, or the named version is not installed, the tool **fails with an error instead of silently falling back** to another MSBuild / Delphi version
- When a `.dpr/.dpk` has a matching `.dproj`, MSBuild is preferred; only when MSBuild cannot be auto-detected does it fall back to direct dcc compilation, and **an explicit configuration error is never hidden** by that fallback
- Automatic detection prefers, by project version: XE4 and earlier use `.NET Framework\v3.5\MSBuild.exe`, XE5–10 Seattle use `v4.0.30319`
- When the project version is not configured and the compiler for the `.dproj` version is missing from `compilers.json`, automatic matching may still fall back to a higher compiler version under the previous policy (with a warning in the log); configure the project's `delphi_version` when a **strict version** is required, and a version that is not installed fails outright
- An unrecognised `delphi_version` in the project configuration (a typo, for example) is an error; it never falls back silently to `.dproj ProjectVersion` inference
- Version numbers accept `"11"`, `"11.0"`, `"XE4"`, `"Delphi XE4"` and similar forms
- After changing the configuration, **restart the Daofy MCP service / IDE** for it to take effect

`check_environment(action="check")` confirms the per-version MSBuild paths and whether those files exist.

For the full set of parameters, the precedence rules and typical scenarios (multiple versions, older Delphi, package installation, deployment, CI), see **[docs/configuration.md](docs/configuration.md)**.

> **pip installation**: `compilers.json` lives at `<Python environment>/Lib/site-packages/src/config/compilers.json` and is overwritten by an upgrade. The project-level `.daofy/project.json` is unaffected by upgrades, so prefer it to pin the toolchain of a single project.

### Shared configuration (pip installation)

If you installed through `pip install daofy-for-delphi`, the configuration is minimal:

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

> **Error when the path contains spaces?** If Python is installed under a path such as `D:\Program Files\...`, some MCP clients cannot handle it. The fix is to set `command` to the full path of the Python interpreter and `args` to `-m src`:
> ```json
> {
>   "mcpServers": {
>     "daofy": {
>       "command": "D:\\Program Files\\Python311\\python.exe",
>       "args": ["-m", "src"],
>       "env": { ... }
>     }
>   }
> }
> ```
> You can also point at `server.py` directly: `"args": ["D:\\path\\to\\daofy\\src\\server.py"]`

### Configuration for a source installation

The configuration below is for users who installed from a git clone; replace the paths with your actual installation path.

#### Claude Desktop

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

#### Trae

**Windows**: `C:\Users\<username>\.trae-cn\mcp_config.json`

```json
{
  "mcpServers": {
    "daofy": {
      "command": "F:\\ProPlus\\DelphiPlus\\Experts\\DelphiMCPServer\\delphi-complier-mcp-server\\venv\\Scripts\\python.exe",
      "args": [
        "F:\\ProPlus\\DelphiPlus\\Experts\\DelphiMCPServer\\delphi-complier-mcp-server\\src\\server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

**Note**: replace the paths with your actual installation path.

#### CodeArts Agent

**Windows**: `~/.codeartsdoer/mcp/mcp_settings.json`

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

#### DSH (DeepSeek Harness)

DSH registers an MCP Server through the `cordis.patch.yml` of a profile. Use the `install_mcp.py` script to install or uninstall it in one step (the same entry point as for the other agents):

```bash
python install_mcp.py --agent DSH                        # install Daofy into the default profile (web)
python install_mcp.py --agent DSH --dsh-profile cli      # choose a profile
python install_mcp.py --agent DSH --python "D:\Python311\python.exe"   # choose the Python interpreter
python install_mcp.py --agent DSH --pip                  # pip mode (command=daofy)
python install_mcp.py --agent DSH --uninstall            # uninstall Daofy
```

You can also omit `--agent` and pick DSH from the interactive menu. The installer detects DSH automatically (the `~/.dsh/profiles/` directory or the `dsh` command).

The generated `cordis.patch.yml` entry (illustrative):

```yaml
# ── Daofy for Delphi MCP Server (managed by install_mcp.py; to uninstall, run the script again and choose DSH)
- insert:
    - id: mcp-daofy
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: 'daofy'
        transport: stdio
        command: 'C:\path\to\python.exe'
        args:
          - 'C:\path\to\daofy\src\server.py'
        env:
          PYTHONUNBUFFERED: '1'
          PYTHONIOENCODING: 'utf-8'
          PYTHONUTF8: '1'
        cwd: 'C:\path\to\daofy'
        toolCallTimeoutMs: 600000
```

Properties:

- **Idempotent**: an identical configuration is skipped, the file is not rewritten
- **Other entries preserved**: uninstalling removes only the Daofy block and leaves third-party MCP entries and `!!js` expressions untouched
- **Environment detected automatically**: the Python interpreter the script detected is used by default; with `--pip` the `daofy` command is used directly
- **Safe uninstall**: after removal `[]` is restored so the patch file stays valid YAML

## Usage

### Knowledge base statistics

| Knowledge base | Files | Classes | Database size |
|--------    | -------   | ------    | -------    |
| Delphi source | 2,798 | 163,737 | 260 MB |
| Third-party libraries | 1,800 | 5,724 | 27 MB |
| General documents | 160,328 | - | 1,306 MB |

## Troubleshooting

### 1. Compiler not found

**Solution**:

- Check that the compiler paths in `config/compilers.json` are correct
- Re-run detection with the `check_environment` tool, `action=detect`

### 2. The MCP Server will not start

**Solution**:

- Check that the Python environment is configured correctly
- Check that the dependencies are installed: `pip install -r requirements.txt`
- Check the MCP library version: `pip show mcp`

### 2a. `Spawn D:\Program ENOENT` — error when the path contains spaces

After a pip installation, some MCP clients (Trae and others) cannot spawn correctly when the path contains spaces.

**Solution**: in the MCP configuration, replace the `daofy` command with the full path of the Python interpreter:

```json
{
  "command": "D:\\Program Files\\Python311\\python.exe",
  "args": ["-m", "src"]
}
```

The source installation form also works: `"args": ["D:\\path\\to\\daofy\\src\\server.py"]`

### 3. Knowledge base searches return nothing

**Solution**:

- Make sure the knowledge base has been built: use `delphi_kb` with `action=build`
- Check that the knowledge base directory exists

## License

MIT License

Copyright (c) 2026 吉林省左右软件开发有限公司
Copyright (c) 2026 Equilibrium Software Development Co., Ltd, Jilin

See the [LICENSE](LICENSE) file for details.

## Version history

### v2026.11.03 (latest)

- **Absolute-path validation for MCP tool paths**: whitelisted path fields are validated at `server.call_tool` boundary and relative paths are rejected, so an inconsistent MCP service CWD can no longer send file reads/writes, compilation or deployment to the wrong place; JSONPath and project-relative fields are not forced
- **Configuration documentation**: added [`docs/configuration.md`](docs/configuration.md), covering project-level and global parameters, precedence, multi-version / older Delphi / package installation / deployment / CI scenarios, error codes and migration
- **Unified project-configuration error code**: an invalid project configuration JSON or `delphi_version` now returns `PROJECT_CONFIG_INVALID`

### v2026.10.31

- **Project-level Delphi/MSBuild configuration**: added `.daofy/project.json` / `daofy.project.json` to set `delphi_version`, `compiler_version` and `msbuild_path` per project; different projects on one machine can use different Delphi/MSBuild versions without interfering
- **Machine-level overrides removed**: removed `msbuild_path` and `default_registry_version` from `compilers.json` and the `DAOFY_MSBUILD` / `DAOFY_DELPHI_VERSION` environment variables; `msbuild_by_delphi_version` remains for per-version mapping
- **Toolchain resolved by project version**: automatic MSBuild detection is re-selected by the project's Delphi version (XE4 and earlier prefer `.NET Framework v3.5`, XE5–10 Seattle prefer `v4.0.30319`); `rsvars.bat`, RTL/third-party library paths, package installation (BPL/DCP and IDE registration) and deployment MSBuild are all resolved by the project version
- **Strict failure**: an invalid MSBuild path in the project configuration or the version mapping, and a version that is not installed, now fail with an error rather than falling back silently; `.dpr` no longer hides a configuration error behind direct compilation; `rsvars.bat` is validated before PreBuildEvent
- **Version matching fixes**: fixed false prefix matches such as `Delphi XE`/`XE8` and `Delphi 12`/`12 Athens`; `delphi_version` accepts `.dproj ProjectVersion` forms such as `14.6`/`18.2`/`19.2`

### v2026.09.16

- **_SafeStderrHandler**: when a client does not drain stderr and the pipe fills, a log `emit` no longer blocks (it writes directly only when there is room, otherwise it enqueues and drops when full), and the background drain thread is cancellable (`CancelSynchronousIo` watchdog with a 30s cooldown retry); `setup_logger` attaches the file handler first and is decoupled from `console_logging` — this fixes a field failure where a full stderr pipe froze the service (even MCP `initialize` stopped responding)
- **Example knowledge base log format fix**: `example_knowledge_base._scan_directory` had four placeholders but passed only three arguments, which pytest's log capture surfaced as a `TypeError` during the full test run (24 cases failed)
- **StackTrace refactoring leftovers**: `TLocalVarInfo.GetTypeSize` became `MapDataSerializer.GetLocalVarTypeSize`, and `MapDataSerializer` now exports `MakeLocalVarInfo` / `GetLocalVarTypeSize`

### v2026.09.15

- **`console_logging` switch**: logs no longer go to the stderr console by default (to avoid interfering with MCP stdio) and are written to files only
- **`file_backup` encoding detection rewritten**: multi-point sampling of very large files, chardet accepted only above low confidence for multi-byte CJK encodings, and UTF-16 BOM heuristic analysis
- **DSH installation integrated**: `install_mcp.py` installs or uninstalls DeepSeek Harness (`--agent DSH`) by reading and writing `cordis.patch.yml`
- **Relative-path resolution**: `delphi_file` resolves a relative path by `project_path` → `workspace_root` → CWD
- **Exact multi-version compiler matching**: the project version is matched in four steps and no longer falls through to a compiler of another Delphi version
- **Build output directories allowed**: the `.dproj` `DCC_ExeOutput` / `DCC_DcuOutput` directories are now directly readable and writable
- **StackTrace VEH logging unified** under `exception.log`

### v2026.09.02

- **Multi-version compiler mismatch fixed**: library, RTL, third-party and system paths now match the dcc32 version
- **System libraries filtered by compiler version**: `delphi_kb(build, kb_type=delphi, version=...)` indexes only the matching RTL/VCL/FMX source
- **MCP v1/v2 interface consistency**: read_resource/title/description/isError/jsonschema validation aligned
- **Fmx.DaofyAutomation synchronised with Vcl**: RTTI named_paths, GetRttiClasses, path resolution and Unicode key input

### v2026.08.06

- **`waitfor` main-thread query timeout protection**: `SendMessageTimeout` plus a lock-free three-counter protocol (submit/complete/abandon incremented individually, zombie messages filtered by LParam); when the main thread is deadlocked or busy the pipe thread yields after at most 200ms, so asynchronous results are never blocked for long
- **`waitfor` smoke tests**: `Tests/冒烟测试/` gained a normal path (`waitfor-basic.json`) and a timeout/modal failure path (`waitfor-timeout-modal.json`); three rounds on AutoTest.exe all passed

### v2026.08.05

- **Coding rule examples completed**: `get_coding_rules(examples=...)` gained four example files — `naming`, `formatting`, `documentation` and `error-handling` — fixing examples that the skill advertised but the server did not have

### v2026.07.18

- **Release**: full sync of the Lazarus plugin support, multi-language coding rules and plugin availability detection

### v2026.07.17

- **Lazarus/Free Pascal plugin support**: four Lazarus-specific tools — `lazarus_compile` (lazbuild compilation), `lazarus_project` (project information), `lazarus_kb` (FPC/LCL source knowledge base) and `lazarus_file` (file read/write and backup)
- **Multi-language coding rules**: `coding-rules/` split into three layers — `delphi/`, `lazarus/` and `shared/`; `get_coding_rules` gained a `language` parameter (`"delphi"` and `"lazarus"`)
- **Plugin availability detection**: on start-up each plugin checks whether its development tool is installed and does not register its tools when it is not, avoiding unavailable MCP tools
- **FPC error parsing**: `OutputParser` supports the FPC format (`File(13,3) Fatal: (2003) message`)
- **`uses` ordering fix**: units are inserted by namespace group and existing units are not reordered, so the relative order of `Winapi.Windows` and `Vcl.Graphics` no longer changes and breaks type resolution

### v2026.07.05

- **Documentation fully synchronised**: every doc aligned with the implementation — `project()` → `delphi_project()`, the ZVec storage layout, the completed kb_type list, the extended section index, and the tutorial fixes
- **CHANGELOG completed**: the Added/Fixed/Removed entries missed in v2026.06.22 were added

### v2026.06.22

- **Tool rename**: `project` → `delphi_project`, so non-Delphi users do not trigger it by mistake
- **`delphi_rtti` tool**: a Delphi RTTI bridge that discovers and invokes published methods of a Delphi application through Enhanced RTTI (three steps: guide/discover/call)
- **`generate_copyright` tool**: automatic software copyright document generation (source code, manual and abstract, PDF rendered in a browser and validated automatically)
- **`daofy_update` tool**: Daofy's own version check and update management (check/update/version)
- **Storage engine migration**: the document, example, project and third-party knowledge bases moved from SQLite FTS5 to the ZVec full-text index
- **HTML parsing optimisation**: the BeautifulSoup dependency was removed in favour of html2text's built-in filters; build time −41%
- **Scan engine rework**: `scan_directory` became a producer-consumer pipeline, bringing peak memory down from the gigabyte range to kilobytes
- **`DaofyAutomation.RttiDiscovery.pas`**: new RTTI capability discovery unit; the `TRttiDiscoverer` class maps Delphi types to JSON Schema
- **`DaofyAutomation.Base.pas` / `Vcl.DaofyAutomation.pas`**: new `rtti_discover` command routing and a rewritten VCL-side `GetRttiClasses`
- **`src/services/rtti_bridge.py`**: new RTTI bridge service (connection management, 5-minute cache, discover/call)
- **`src/tools/delphi_rtti.py`**: new MCP tool handler (action=guide/discover/call)
- **`.opencode/skills/delphi-rtti-bridge/SKILL.md`**: new AI agent skill file (YAML frontmatter plus progressive L3 documentation)
- **`scripts/build-skills.py`**: multi-platform skill distribution script (distributes to .claude/ .cursor/ .windsurfrules automatically)
- **`tests/test_rtti_bridge.py` / `tests/test_delphi_rtti.py`**: 38 test cases covering the bridge service and the tool handler
- **DaofyAutomation split into three layers**: `tools/auto/` split into Base/VCL/FMX layers, overlapped I/O pipes, and an extended command set (move/drag/key/waitfor/rcall and more)
- **`automate_delphi` Console mode**: subprocess stdin/stdout interaction, with automatic PE-header detection of GUI versus Console
- **`file_tool` path whitelist validation and dirty-flag system**: `_validate_path()` safety validation, and a post-write dirty mark that prevents line-number drift
- **`CODING_RULES.mdc` rules reworked**: the delphi_file write rules, the compact output format and the dirty-flag protection were rewritten
- **Build verification**: DCC compiles with 0 errors, Python imports cleanly

### v2026.06.08.1

- `delphi_file` uses an RWLock across all operations to prevent concurrent file corruption: read/write/format/backup/uses all take a multi-reader single-writer lock, a concurrent write returns a clear error and the caller is directed to combine the changes into one `write(edits=[...])`
- `tools/7z/` now ships 7z.dll, so the release package works out of the box
- `tool_docs.py` constraints tightened: the write parameter is unified as `edits`, and parallel writes are forbidden (later versions recommend the structured `replace`/`insert`/`delete` entry points)
- `.gitignore` excludes dot-prefixed directories and stops tracking AI working directories

### v2026.06.03

- `delphi_file` writes unified as `write(edits=[...])`: several edits are passed at once, sorted internally by ascending `start_line`, accumulated in memory with their offsets and written in one go
- `compilers.json` path self-healing: when it is not under `src/config/` it falls back to the project-root `config/`, so an MCP start-up no longer fails because of a path difference
- 18 `except Exception: pass` sites gained `logger.debug` exception logging, making failures easier to locate while debugging
- `search_knowledge` refactored: 597 → 37 lines, split into 16 module-level helper functions, behaviour fully equivalent
- Full test run: 727 passed

### v2026.06.01

- `delphi_file` partial-write line-number fix: the 0-indexed documentation was corrected, and a write now returns the offset plus the formula for adjusting subsequent line numbers
- `delphi_file(action="uses")` returns offset information as well
- `AGENTS.md` gained a partial-write rules section at the time; later versions unified on 1-indexed inclusive line numbers
- Full test run: 684 passed, 6 skipped

### v2026.05.14

- New `manage_component` tool: add, remove, modify and generate DFM components with automatic PAS synchronisation (replacing `generate_component_dfm`)
- `delphi_file` renamed and enhanced: automatic DFM binary conversion, backup management and search-based location (formerly `file_tool`, which is still accepted as an alias)
- `get_coding_rules` enhanced: sections can be fetched one at a time, saving tokens
- New `code_hosting` tool: one interface over Gitea/GitHub/GitLab
- The workflow grew from six steps to seven (① environment check → ② KB lookup → ③ write code → ④ format → ⑤ compile → ⑥ audit → ⑦ clean up)

The complete version history is in [CHANGELOG.md](CHANGELOG.md).

## Contributing

Issues and pull requests are welcome!

## Sponsorship

If Daofy for Delphi helps you, you are welcome to support the project through any of the channels below.
Your support keeps the project going! ❤️

### Alipay

**Account**: guansonghuan@sina.com (name: 管耸寰 — please mention your QQ number)

<img src="https://blog.qdac.cc/wp-content/uploads/2018/04/pay_alipay.jpg" alt="Alipay QR code" width="200"/>

### WeChat

**Account**: wangshengbo (send a red packet or a transfer)

<img src="https://blog.qdac.cc/wp-content/uploads/2018/04/pay_wechat.jpg" alt="WeChat QR code" width="200"/>

### QQ

Pay through the group, or send a red packet to the group owner

<img src="https://blog.qdac.cc/wp-content/uploads/2018/04/pay_qq.png" alt="QQ QR code" width="200"/>

**Official QQ group**: 250530692

### Bank transfer

| Bank | Account holder | Account number | Branch |
|------|------|------|--------|
| 光大银行 (China Everbright Bank) | 王胜波 | 6226 6208 0391 5552 | 光大银行长春人民大街支行 |
| 建设银行 (China Construction Bank) | 管耸寰 | 4367 4209 4324 0179 731 | 建设银行长春团风储蓄所 |

## Contact

For questions or suggestions, please open an Issue.
