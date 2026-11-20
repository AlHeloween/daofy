"""
Tool complete documentation dictionary — queried on demand by the tool_help tool

Each tool contains：summary、triggers、collaboration chain、all action descriptions、examples、fallback strategies etc。
The description field is a condensed 1-2 sentence summary，other fields are detailed descriptions retrieved by AI on demand。
"""

TOOL_HELP_DOCS: dict = {
    "delphi_project": {
        "summary": "Delphi project full lifecycle management：compile/config view/code and UI layout audit/device deployment。Supports .dproj/.dpr/.dpk。",
        "description": "Delphi project full lifecycle management — compile/config/audit/deploy",
        "triggers": [
            "【Delphi only】compile、build、generate exe、syntax check、compile errors、build、compile、msbuild、dcc32",
            "【Delphi only】project files、dproj、project configuration、create project、add configuration、delete configuration",
            "syntax parsing、AST parsing、audit code、review code、review code、audit",
            "【Delphi only】deploy、deploy、device list、iOS devices、Android devices、PAServer",
        ],
        "constraints": [
            "❌ Do not use bash/cmd to run dcc32/msbuild（bypasses MSBuild/events/dependencies）",
        ],
        "workflow": "tool_help(tool_name=\"delphi_project\", action=\"<action>\") → delphi_project(action=...) view current action parameters → call",
        "actions": {
            "compile": "Compile .dproj/.dpr/.dpk projects",
            "compile_file": "Check .pas file syntax（shortcut，equivalent to compile + .pas）",
            "dry_run": "Preview compilation parameters，do not actually execute",
            "info": "Read complete .dproj file information（config/source files/resources/compile events）",
            "create": "Create a new .dproj file",
            "set": "Set .dproj property value（PropertyGroup），can specify config/platform",
            "add_config": "Add a new build configuration（e.g. Staging）",
            "remove_config": "Delete specified build configuration",
            "add_source": "Add source file reference to ItemGroup",
            "remove_source": "Delete source file reference from ItemGroup",
            "audit": "Run 50+ static analysis rules",
            "ast": "⭐ Code skeleton extraction（daudit --mode skeleton --compact），most token-efficient",
            "runtime": "Runtime registration check，detect whether required units are missing from uses",
            "layout": "Static DFM UI layout audit，detect overlap、out-of-bounds、alignment、spacing、field pairing、TabOrder and absolute coordinate overflow risks in resizable windows",
            "devices": "Enumerate connected device list（iOS/Android/Windows）",
            "deploy": "Deploy the compiled application to a device",
        },
        "action_params": {
            "compile": {
                "description": "Compile Delphi project",
                "required": ["project_path"],
                "optional": {
                    "target_platform": "Target platform(win32/win64/osx64/...)，default win32",
                    "build_configuration": "Debug/Release，default Debug",
                    "compiler_version": "Compiler version，if not passed automatically detect latest",
                    "conditional_defines": "Conditional compilation symbol array，e.g. ['DEBUG','TEST']",
                    "unit_search_paths": "Additional unit search path array",
                    "resource_search_paths": "Resource search path array",
                    "optimize": "Whether to optimize，default true",
                    "debug": "Whether to generate debug information，default true",
                    "warning_level": "Warning level 0-4，default 2",
                    "disabled_warnings": "Disabled warning numbers，e.g. ['W1000']",
                    "output_type": "gui/console/dll，default gui",
                    "runtime_library": "static/dynamic，default static",
                    "timeout": "Timeout seconds，default 600",
                    "auto_install": "Only valid for .dpk，whether to automatically install to IDE，default true",
                    "run_verify": "After compilation start for 3 seconds to verify whether it crashes，default false",
                    "output_path": "Compilation output directory",
                    "extra_args": "Complete parameter array appended to the actual compilation backend；.dproj/MSBuild uses /p:...，direct DCC compilation without a corresponding .dproj uses switches such as -VT/-VR",
                },
                "examples": [
                    'delphi_project(action="compile", project_path="App.dproj", build_configuration="Release")',
                    'delphi_project(action="compile", project_path="App.dproj", extra_args=["/p:DCC_DebugInfoInTds=true", "/p:DCC_RemoteDebug=true"])',
                    'delphi_project(action="compile", project_path="unit.pas")',
                ],
            },
            "dry_run": {
                "description": "Preview compilation parameters，do not actually execute",
                "optional": {
                    "project_path": "Absolute path of project file",
                    "target_platform": "Target platform",
                    "build_configuration": "Build configuration",
                    "compiler_version": "Compiler version",
                    "conditional_defines": "Conditional compilation symbols",
                    "unit_search_paths": "Unit search paths",
                    "optimize": "Whether to optimize",
                    "debug": "Whether to debug",
                    "output_type": "Output type",
                    "runtime_library": "Runtime library",
                    "extra_args": "Additional compiler parameters",
                },
                "examples": [
                    'delphi_project(action="dry_run", project_path="App.dproj")',
                ],
            },
            "compile_file": {
                "description": "Check .pas file syntax",
                "required": ["project_path"],
                "optional": {
                    "unit_search_paths": "Unit search paths",
                    "conditional_defines": "Conditional compilation symbols",
                    "compiler_version": "Compiler version",
                    "extra_args": "Additional DCC parameters",
                },
                "examples": [
                    'delphi_project(action="compile_file", project_path="unit.pas")',
                ],
            },
            "info": {
                "description": "Read complete .dproj file information",
                "required": ["project_path"],
                "examples": [
                    'delphi_project(action="info", project_path="App.dproj")',
                ],
            },
            "create": {
                "description": "Create a new .dproj project file",
                "required": ["project_path", "main_source"],
                "optional": {
                    "project_guid": "Project GUID，auto-generated",
                    "framework_type": "VCL/FMX，default VCL",
                    "unit_search_paths": "Initial unit search paths",
                    "namespace": "Namespace",
                    "configs": "Build configuration list，default ['Debug','Release']",
                    "target_platform": "Target platform shortcut parameter，e.g. win32/win64；during create equivalent to a single platforms item",
                    "platforms": "Target platform list，e.g. ['Win32','Win64']；default ['Win32']",
                    "sources": "Initial source file list",
                    "form_units": "Also generate Form stub code，e.g. ['Unit1','Main']",
                },
                "examples": [
                    'delphi_project(action="create", project_path="App.dproj", main_source="App.dpr")',
                    'delphi_project(action="create", project_path="App64.dproj", main_source="App64.dpr", target_platform="win64")',
                    'delphi_project(action="create", project_path="App.dproj", main_source="App.dpr", form_units=["Unit1"])',
                ],
            },
            "set": {
                "description": "Set .dproj property value",
                "required": ["project_path", "property_name", "value"],
                "optional": {
                    "config": "Build configuration，e.g. Debug/Release",
                    "platform": "Target platform，e.g. Win32/Win64",
                },
                "examples": [
                    'delphi_project(action="set", project_path="App.dproj", property_name="DCC_Define", value="DEBUG;TEST", config="Debug")',
                ],
            },
            "add_config": {
                "description": "Add a new build configuration",
                "required": ["project_path", "config_name"],
                "optional": {
                    "base_config": "Which existing configuration to copy properties from",
                    "defines": "Conditional compilation symbols",
                    "optimize": "Whether to enable optimization",
                    "debug_info": "Whether to generate debug information",
                },
                "examples": [
                    'delphi_project(action="add_config", project_path="App.dproj", config_name="Staging", base_config="Debug")',
                ],
            },
            "remove_config": {
                "description": "Delete build configuration",
                "required": ["project_path", "config_name"],
                "examples": [
                    'delphi_project(action="remove_config", project_path="App.dproj", config_name="Staging")',
                ],
            },
            "add_source": {
                "description": "Add source file to project",
                "required": ["project_path", "source_file"],
                "optional": {
                    "main_source_flag": "true=add as main source file，false=add to DCCReference",
                },
                "examples": [
                    'delphi_project(action="add_source", project_path="App.dproj", source_file="Unit1.pas")',
                ],
            },
            "remove_source": {
                "description": "Delete source file reference from project",
                "required": ["project_path", "source_file"],
                "examples": [
                    'delphi_project(action="remove_source", project_path="App.dproj", source_file="Unit1.pas")',
                ],
            },
            "audit": {
                "description": "Run 50+ static analysis rules",
                "optional": {
                    "base_dir": "Audit base directory",
                    "file_path": "Absolute path of single file",
                    "rules": "Rule set P0/P1，default P0",
                    "severity": "Minimum severity level suggestion/warning/critical",
                    "output_format": "report/json，default report",
                },
                "examples": [
                    'delphi_project(action="audit", base_dir="src")',
                    'delphi_project(action="audit", file_path="Unit1.pas")',
                ],
            },
            "ast": {
                "description": "⭐ Code skeleton extraction，most token-efficient",
                "required": ["base_dir"],
                "optional": {
                    "file_path": "Absolute path of single file",
                },
                "examples": [
                    'delphi_project(action="ast", base_dir="src")',
                    'delphi_project(action="ast", file_path="Unit1.pas")',
                ],
            },
            "runtime": {
                "description": "Runtime registration check，detect missing uses units",
                "optional": {
                    "base_dir": "Project base directory",
                },
                "examples": [
                    'delphi_project(action="runtime", base_dir="src")',
                ],
            },
            "layout": {
                "description": "Statically audit .dfm layout quality，including that resizable windows should preferably use Align or set the parent container minimum size。",
                "optional": {
                    "base_dir": "Recursively scan .dfm files under the directory",
                    "file_path": "Absolute path of a single .dfm file",
                    "output_format": "report/json，default report",
                },
                "examples": [
                    'delphi_project(action="layout", base_dir="src")',
                    'delphi_project(action="layout", file_path="MainForm.dfm", output_format="json")',
                ],
            },
            "devices": {
                "description": "Enumerate connected device list（iOS/Android/Windows）",
                "optional": {
                    "target_platform": "Target platform (iosdevice64/iossimulator/android64/androidarm64/win32/win64)，if not passed then infer",
                    "project_path": "Absolute path of project file（optional，used to infer target platform）",
                },
                "examples": [
                    'delphi_project(action="devices")',
                    'delphi_project(action="devices", target_platform="iosdevice64")',
                    'delphi_project(action="devices", project_path="App.dproj")',
                ],
            },
            "deploy": {
                "description": "Deploy the compiled application to a device",
                "required": ["project_path", "target_platform"],
                "optional": {
                    "device_id": "Target device ID（iOS UDID or Android serial），if not passed deploy to default device",
                    "build_configuration": "Build configuration (Debug/Release)，default Debug",
                    "extra_args": "Parameter array appended to MSBuild",
                    "timeout": "Timeout seconds，default 600",
                },
                "examples": [
                    'delphi_project(action="deploy", project_path="App.dproj", target_platform="iosdevice64")',
                    'delphi_project(action="deploy", project_path="App.dproj", target_platform="android64", device_id="emulator-5554")',
                    'delphi_project(action="deploy", project_path="App.dproj", target_platform="iosdevice64", device_id="UDID123", build_configuration="Release")',
                ],
            },
        },
        "workflow_hints": {
            "创建项目": "delphi_project(create) → delphi_project(info) → delphi_project(compile)",
            "日常编译": "delphi_project(compile, project_path=...) automatically detect .pas/.dproj",
            "审计代码": "delphi_project(ast) → analyze → delphi_file → delphi_project(compile)",
            "改配置": "delphi_project(set, property_name=...) → delphi_project(compile) verify",
            "设备部署": "delphi_project(devices, target_platform=...) → delphi_project(deploy, project_path=..., target_platform=..., device_id=...)",
        },
    },    "delphi_kb": {
        "summary": "Search Delphi API/project code/third-party libraries/docs (class/function/semantic search), build knowledge base.",
        "description": "Knowledge base search/management — query Delphi API, project code, docs",
        "triggers": [
            "Search classes, search functions, look up API, look up definitions, knowledge base, build knowledge base, KB, semantic search",
        ],
        "file_triggers": "Before writing .pas code, first search KB for API definitions",
        "workflow": "Before writing code→delphi_kb query API→delphi_file(read) view definition→write code→compile",
        "actions": {
            "search": "Search classes/functions/docs (query required), kb_type limits scope, search_type limits type",
            "stats": "View knowledge base statistics (file count, class count, function count, last build time)",
            "build": "Build/update knowledge base (supports async async_mode=true)",
            "scan": "Scan directory to add documents (kb_type=document)",
            "web": "Add web documents (kb_type=document)",
            "read": "Read document content (url/doc_id) or source file (file_path)",
            "build_embedding": "Build vector index",
        },
        "examples": [
            'delphi_kb(query="TStringList")                                    Search classes',
            'delphi_kb(query="Create", search_type="function")                  Search functions',
            'delphi_kb(query="TfrxReport", kb_type="thirdparty")                Search third-party libraries (e.g. FastReport)',
            'delphi_kb(action="stats")                                          View statistics',
            'delphi_kb(action="build", kb_type="project")                       Build project knowledge base',
        ],
        "action_params": {
            "search": {
                "description": "Search classes/functions/docs",
                "required": [],
                "optional": {
                    "query": "Search keyword",
                    "kb_type": "Knowledge base type: all/delphi/project/thirdparty/document/example",
                    "search_type": "Search type: class/function/unit/semantic/reference/all etc.",
                    "top_k": "Maximum number of results (default 200, max 500)",
                    "project_path": "Absolute project path (required when searching project/thirdparty)",
                },
            },
            "stats": {
                "description": "View knowledge base statistics",
                "required": [],
                "optional": {},
            },
            "build": {
                "description": "Build/update knowledge base",
                "required": [],
                "optional": {
                    "kb_type": "Knowledge base type: all/delphi/project/thirdparty/document/example",
                    "project_path": "Absolute project path",
                    "version": "Delphi version",
                    "rebuild": "Whether to force rebuild",
                    "incremental": "Whether to update incrementally",
                    "async_mode": "Whether to run asynchronously (default true)",
                    "directory": "Absolute directory path to scan (used for document KB)",
                    "extensions": "File extension filter",
                    "max_pages": "Maximum pages to crawl",
                    "max_depth": "Maximum crawl depth",
                    "domain_filter": "Domain filter",
                    "url_pattern": "URL pattern filter",
                    "exclude": "List of excluded directories",
                    "max_workers": "Maximum number of workers",
                    "show_progress": "Whether to show progress",
                    "build_thirdparty": "Whether to also build third-party library KB",
                    "build_project": "Whether to build project KB",
                },
            },
            "scan": {
                "description": "Scan directory to add documents",
                "required": [],
                "optional": {
                    "directory": "Absolute directory path to scan",
                    "extensions": "File extension filter",
                    "max_workers": "Maximum number of workers",
                    "show_progress": "Whether to show progress",
                },
            },
            "web": {
                "description": "Add web documents",
                "required": [],
                "optional": {
                    "url": "Webpage URL",
                    "max_depth": "Maximum crawl depth (default 3)",
                    "max_pages": "Maximum pages to crawl (default 100)",
                    "domain_filter": "Domain filter",
                },
            },
            "read": {
                "description": "Read document content or source file",
                "required": [],
                "optional": {
                    "url": "Document URL",
                    "doc_id": "Document ID",
                    "file_path": "Absolute file path",
                    "offset": "Read offset",
                    "limit": "Read byte limit",
                },
            },
            "build_embedding": {
                "description": "Build vector index",
                "required": [],
                "optional": {},
            },
        },
    },
    "delphi_file": {
        "summary": "Delphi file (.pas/.dfm/.dproj/.dpr/.dpk/.fmx/.inc/.groupproj) dedicated read/write/search/replace entry point. Delphi files must use delphi_file, do not use built-in Read/Edit/Write/grep.",
        "description": "Dedicated operations for Delphi files: read/write (edits)/replace/insert/delete/format/backup management/encoding conversion/uses clause add/remove (encoding detection + automatic backup + DFM conversion). AI tool routing rule: reading or modifying Delphi files must choose delphi_file.",
        "triggers": [
            "read file, view source, open file, cat, Agent built-in Read, built-in Read, write code, edit file, modify code, change code, Agent built-in Edit/Write",
            "create file, format, tidy code, restore backup, roll back changes, diff, compare differences",
            "view backups, restore file, add/remove uses, add unit, remove unit",
            "batch write, batch modify, multiple changes, multiple edits, write edits",
        ],
        "file_triggers": "When seeing .pas/.dfm/.dproj/.dpk/.dpr/.fmx/.inc/.groupproj file paths you must use this; reading also counts",
        "constraints": [
            "❌ Delphi files must use delphi_file to read/write/search/regex match+replace, do not use built-in Read/Edit/Write/grep",
            "🚫 Parallel writes to the same file are prohibited; merge multiple changes into one write(edits=[...])",
            "🚫 format/uses/write mark dirty; must read before writing again",
        ],
        "features": [
            "Automatic encoding detection (UTF-8/GBK/UTF-16), automatic backup (__history)",
            "Transparent DFM binary↔text conversion",
            "1-indexed line numbers (parameters and output consistent), dirty mark mechanism",
        ],
        "workflow": "get_coding_rules → delphi_file(read) plan changes→ replace/insert/delete/write(edits=[...]) write out in one go → format → compile. write/replace/insert/delete/format/uses mark dirty; must read or verify with old_content before continuing to write. Different files can be processed in parallel.",
        "client_wrappers": [
            "Clients that expose MCP tools directly: when calling delphi_file pass only Daofy parameters, e.g. action/file_path/start_line/end_line.",
            "Clients such as Trae that only expose run_mcp: pass server_name and tool_name at the outer layer, and put Daofy parameters in the inner args; server_name is the Daofy service alias in that client's MCP configuration, fill in according to actual configuration, not a fixed Daofy value.",
            "Do not mix server_name/tool_name into the parameter object of delphi_file, and do not flatten action/file_path/start_line/end_line into the outer layer of run_mcp.",
            'Trae example: run_mcp({"server_name":"<client-configured-daofy-server-name>","tool_name":"delphi_file","args":{"action":"read","file_path":"C:\\\\path\\\\Unit1.pas","start_line":1,"end_line":100}})',
        ],
        "actions": {
            "read": "Read file, supports segmented read (start_line/end_line) or locating by class name/function name. All line numbers are 1-indexed inclusive. For project source search use search_in='project' + project_path. Reading automatically clears dirty mark.",
            "write": "Compatibility write interface (old semantics). Accepts edits array, internally auto-sorts + accumulates offsets, writes out at once. edits=[{start_line:1, content:'...'}] full replacement; edits=[{start_line:5, end_line:10, content:'...'}] partial replacement. Supports dry_run preview diff. Marks dirty after writing.",
            "replace": "Replace by line range. In existing files each edit must provide non-empty old_content; the tool uses line number + old content to verify the hit range.",
            "insert": "Insert by start_line anchor. In existing files each edit must provide non-empty old_content (single-line anchor, no newline needed), position=before/after.",
            "delete": "Delete by line range. In existing files each edit must provide non-empty old_content, content can be omitted.",
            "format": "Format code using pasfmt. Marks dirty after formatting.",
            "backup": "Backup management (create/list/restore)",
            "encode": "File encoding conversion. Automatically detects source encoding, writes target encoding. Supports utf-8/utf-8-sig/gbk/utf-16/utf-16-le/utf-16-be/ansi. Automatic backup. Marks dirty after conversion.",
            "uses": "Add/remove units in uses clause. Marks dirty after success.",
            "grep": "Regex search/replace. file_path supports string (auto-detect file/directory) or path array (resolve each item). Supports multi-pattern OR search (patterns), secondary AND filter (filter_pattern), NOT exclude (exclude_pattern). replace switches to replacement mode (dry_run default True, preview does not write to disk).",
            "fix_garbled": "Fix Chinese garbled text: automatically detect U+FFFD replacement characters, missing UTF-8 BOM, encoding misdetection and fix. Supports backup.",
        },
        "examples": [
            'delphi_file(action="read", file_path="Unit1.pas")                                         Read file',
            'delphi_file(action="read", search_type="class", type_name="TForm1")                       Search class definition',
            'delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)              Read lines 5~15',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:1,content:"unit ..."}])             Full replacement',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:10,end_line:12,content:"替换内容"}])  Partial replacement of lines 10~12',
            'delphi_file(action="write", file_path="src/Unit1.pas", edits=[{start_line:5,content:"新内容"}], dry_run=true)   Preview diff (from line 5 to end)',
            'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,content:"..."},{start_line:18,end_line:21,content:"..."}])  Batch replace two places',
            'delphi_file(action="replace", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,old_content:"旧代码",content:"新代码"}])  Replace by original text',
            'delphi_file(action="insert", file_path="Unit1.pas", edits=[{start_line:10,position:"before",old_content:"  OldCall;",content:"  NewCall;\\n"}])  Anchor insert',
            'delphi_file(action="delete", file_path="Unit1.pas", edits=[{start_line:10,end_line:12,old_content:"  OldCall;\\n  OtherCall;\\n"}])  Delete by original text',
            'delphi_file(action="format", file_path="src/Unit1.pas")                                   Format',
            'delphi_file(action="backup", file_path="Unit1.pas")                                       Create backup',
            'delphi_file(action="backup", backup_action="list", file_path="Unit1.pas")                 List backups',
            'delphi_file(action="backup", backup_action="restore", file_path="Unit1.pas", version=3)   Restore',
            'delphi_file(action="uses", uses_action="add", unit_name="System.SysUtils", file_path="Unit1.pas")  Add uses',
            'delphi_file(action="grep", file_path="Unit1.pas", pattern="/TMyClass/i")                                                     Single-file regex search (case-insensitive)',
            'delphi_file(action="grep", file_path="Unit1.pas", pattern="/^procedure/m", context=2)                                        Multiline mode + context search',
            'delphi_file(action="grep", file_path="Unit1.pas", pattern="/TMyClass/i", replace="TNewClass", dry_run=True)                 Replace preview',
            'delphi_file(action="grep", file_path="src/", include="**/*.pas", pattern="/TMyClass/i", context=1)                            Directory recursive search (file_path auto-detected as directory)',
            'delphi_file(action="grep", file_path="Unit1.pas", patterns=["/TMyClass/i", "/TSomeClass/"])                                   Multi-pattern OR search',
            'delphi_file(action="grep", file_path=["Unit1.pas", "src/"], pattern="/TMyClass/i")                                         Path array search',
            'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="utf-8-sig")                       Add UTF-8 BOM',
            'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="gbk")                             Convert to GBK',
            'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="utf-8", from_encoding="gbk")      Specify GBK→UTF-8',
        ],
        "action_params": {
            "read": {
                "description": "Read file, supports segmented read or locating by class name/function name. All line numbers are 1-indexed inclusive.",
                "required": ["file_path"],
                "optional": {
                    "start_line": "Start line number (1-indexed inclusive, default 1)",
                    "end_line": "End line number (1-indexed inclusive), if not provided then start_line+limit-1",
                    "limit": "Maximum number of lines returned (default 500, upper limit 1000)",
                    "show_line_numbers": "Whether to show 1-indexed line number prefix (default false)",
                    "search_type": "Read mode: path/class/function/record",
                    "search_in": "Search scope all/delphi/project/thirdparty; project requires project_path",
                    "project_path": "Absolute project file path, used for search_in=project or to restrict write path",
                    "type_name": "Class/interface name",
                    "function_name": "Function/procedure name",
                    "class_name": "Class name (used when search_type=class, equivalent to type_name)",
                    "record_name": "Record type name (used when search_type=record)",
                    "encoding": "Read encoding auto/utf-8/gbk/utf-16 (default auto)",
                },
                "examples": [
                    'delphi_file(action="read", file_path="Unit1.pas")',
                    'delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)',
                    'delphi_file(action="read", search_type="class", type_name="TMainForm", search_in="project", project_path="App.dproj")',
                ],
            },
            "write": {
                "description": "Compatibility write interface. New calls should prefer replace/insert/delete. Line numbers in edits are 1-indexed inclusive; marks dirty after writing.",
                "required": ["file_path", "edits"],
                "optional": {
                    "backup": "Automatically back up before writing, default true",
                    "encoding": "Write encoding auto/utf-8/gbk/utf-16, default auto",
                    "auto_format": "Automatically call pasfmt formatting after writing, default false. Returned offsets already include line count changes caused by formatting",
                    "force": "Skip duplicate detection and dirty mark check (default false: duplicates only warn, not block writing)",
                    "dry_run": "When set to true only preview diff without writing to disk (no backup, no write, no formatting), default false. dry_run does not clear dirty mark; subsequent write still requires read or old_content.",
                    "old_content": "Written inside each edit; non-empty old content of the range to be replaced. Before writing, whitespace outside strings is ignored for comparison to avoid line number misalignment. Note: do not include trailing \\r\\n newline; the tool ignores it automatically",
                    "allow_dirty": "Skip dirty mark check (default false). Prefer non-empty old_content in each edit; bare allow_dirty at your own risk",
                    "project_path": "Optional; when provided, restricts file_path to be within project directory",
                },
                "examples": [
                    'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,content:"新行"},{start_line:18,end_line:21,content:"新行"}])',
                    'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,old_content:"旧行",content:"新行"}])',
                    'delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:7,end_line:10,content:"新代码"}], dry_run=true)',
                ],
            },
            "replace": {
                "description": "Replace one or more line ranges. In existing files each edit must provide non-empty old_content; the tool uses line number + old content to verify the hit range.",
                "required": ["file_path", "edits"],
                "optional": {
                    "dry_run": "When set to true only preview diff without writing to disk, default false. Recommended",
                },
                "examples": [
                    'delphi_file(action="replace", file_path="Unit1.pas", edits=[{start_line:5,end_line:7,old_content:"旧代码",content:"新代码"}])',
                ],
            },
            "insert": {
                "description": "Insert content based on the anchor line pointed to by start_line. old_content is required to verify the anchor line (single-line content, no newline needed); position=before/after.",
                "required": ["file_path", "edits"],
                "optional": {
                    "dry_run": "When set to true only preview diff without writing to disk, default false. Recommended",
                },
                "examples": [
                    'delphi_file(action="insert", file_path="Unit1.pas", edits=[{start_line:10,position:"before",old_content:"  OldCall;",content:"  NewCall;\\n"}])',
                ],
            },
            "delete": {
                "description": "Delete one or more line ranges. Each edit must provide non-empty old_content; content can be omitted.",
                "required": ["file_path", "edits"],
                "optional": {
                    "dry_run": "When set to true only preview diff without writing to disk, default false. Recommended",
                },
                "examples": [
                    'delphi_file(action="delete", file_path="Unit1.pas", edits=[{start_line:10,end_line:12,old_content:"旧代码"}])',
                ],
            },
            "format": {
                "description": "Format code using pasfmt. Marks file dirty after successful formatting.",
                "required": ["file_path"],
                "optional": {
                    "mode": "Format mode: file/code/check, default file",
                    "code": "Code text to format when mode=code",
                    "config_path": "Absolute path to pasfmt config file",
                    "uses_style": "uses clause style: compact/pasfmt_default",
                    "dry_run": "true=only check format without modifying file",
                    "backup": "Whether to create backup, default true",
                    "project_path": "Absolute project path (optional)",
                },
            },
            "encode": {
                "description": "File encoding conversion. Supports automatic source encoding detection (from_encoding='auto'). Automatically backs up before conversion, marks dirty after conversion.",
                "required": ["file_path", "to_encoding"],
                "optional": {
                    "from_encoding": "Source encoding (auto=automatic detection, recommended to always use auto; if explicitly specified, ensure the encoding name is accurate, otherwise decoding may fail or produce garbled text)",
                    "backup": "Whether to back up to __history before conversion (default true)",
                    "dry_run": "Preview mode: only output conversion info without writing to disk (default false)",
                    "project_path": "Absolute project path (optional)",
                },
                "examples": [
                    'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="utf-8-sig")',
                    'delphi_file(action="encode", file_path="Unit1.pas", to_encoding="gbk")',
                    'delphi_file(action="encode", file_path="Unit1.pas", from_encoding="gbk", to_encoding="utf-8")',
                ],
            },
            "uses": {
                "description": "Add/remove units in uses clause. Marks dirty after success.",
                "required": ["file_path", "uses_action", "unit_name"],
                "optional": {
                    "uses_section": "Section: interface/implementation, default interface",
                    "auto_format": "Automatically format with pasfmt after adding (default false)",
                    "backup": "Whether to create backup (default true)",
                    "encoding": "Write encoding auto/utf-8/gbk/utf-16 (default auto)",
                    "project_path": "Absolute project path (optional)",
                },
                "examples": [
                    'delphi_file(action="uses", uses_action="add", unit_name="System.SysUtils", file_path="Unit1.pas")',
                    'delphi_file(action="uses", uses_action="remove", unit_name="Vcl.Dialogs", file_path="Unit1.pas")',
                ],
            },
            "backup": {
                "description": "Backup management: create backup, list backup versions, restore specified version.",
                "required": ["file_path"],
                "optional": {
                    "backup_action": "Sub-action: create (default) / list / restore",
                    "version": "Backup version number (required for restore; if omitted restores latest)",
                    "project_path": "Absolute project path (optional)",
                },
                "examples": [
                    'delphi_file(action="backup", file_path="Unit1.pas")',
                    'delphi_file(action="backup", backup_action="list", file_path="Unit1.pas")',
                    'delphi_file(action="backup", backup_action="restore", file_path="Unit1.pas", version=3)',
                ],
            },
            "grep": {
                "description": "Regex search + multi-level filtering + replacement. file_path auto-detects: file path→single-file search, directory path→recursive search. Also supports multi-pattern OR search (patterns).",
                "required": [],
                "optional": {
                    "file_path": "Absolute file path, absolute directory path, or path array. String auto-detects file/directory; array resolves each item",
                    "include": "glob include pattern (only valid when file_path is a directory), e.g. **/*.pas",
                    "exclude": "glob exclude pattern (only valid when file_path is a directory)",
                    "pattern": "Single-pattern regex, supports inline /expr/flags syntax",
                    "patterns": "Multi-pattern regex array, each pattern OR-searched",
                    "filter_pattern": "Secondary AND filter (optional), also supports inline /expr/flags",
                    "exclude_pattern": "NOT exclude pattern (optional), also supports inline /expr/flags",
                    "replace": "Replacement text; when provided switches to replacement mode (dry_run default True)",
                    "dry_run": "Replacement mode preview switch, default True (only preview, do not write to disk)",
                    "context": "Number of context lines, default 0",
                    "count": "Maximum number of returned results, default 200",
                    "project_path": "Absolute project path (optional)",
                },
                "examples": [
                    'delphi_file(action="grep", file_path="Unit1.pas", pattern="/TMyClass/i")',
                    'delphi_file(action="grep", file_path="Unit1.pas", pattern="/TMyClass/i", replace="TNewClass", dry_run=True)',
                    'delphi_file(action="grep", file_path="src/", include="**/*.pas", pattern="/TMyClass/i", context=1)',
                    'delphi_file(action="grep", file_path="Unit1.pas", patterns=["/TMyClass/i", "/TSomeClass/"])',
                    'delphi_file(action="grep", file_path=["Unit1.pas", "src/sub/"], pattern="/TMyClass/i")',
                ],
            },
            "fix_garbled": {
                "description": "Fix Chinese garbled text in Delphi files: detect UTF-8 without BOM, U+FFFD replacement characters, double encoding and other issues and fix them.",
                "required": ["file_path"],
                "optional": {
                    "backup": "Whether to create backup, default True",
                    "target_encoding": "Target encoding, default utf-8-sig (UTF-8 with BOM)",
                    "project_path": "Absolute project path (optional)",
                },
                "examples": [
                    'delphi_file(action="fix_garbled", file_path="Unit1.pas")',
                    'delphi_file(action="fix_garbled", file_path="Unit1.pas", target_encoding="utf-8-sig")',
                ],
            },
        },
    },    "manage_component": {
        "summary": "DFM component add/remove/modify/generate + PAS auto-sync.",
        "description": "DFM component add/remove/modify/generate + PAS auto-sync",
        "triggers": ["Add component, delete component, modify component, generate DFM, component sync, manage component"],
        "sync_rules": [
            "add:    new field declaration + event method stubs + uses unit",
            "remove: field declaration + event methods (declaration+implementation) + unused uses",
            "modify: event property change → add/remove/modify event method declarations",
        ],
        "actions": {
            "create": "Generate component DFM (compile+runtime serialization, original generate_component_dfm functionality)",
            "add": "Add child component to existing DFM, automatically sync PAS fields+events+uses",
            "remove": "Remove component from DFM (including subtree), automatically sync deletion of PAS fields+event methods",
            "modify": "Modify component properties in DFM, automatically sync PAS declarations when events change",
        },
        "examples": [
            'create: code="function CreateComponent(AOwner: TComponent): TComponent; ...", uses=["Vcl.Forms","Vcl.StdCtrls"]',
            'add: action="add", target_dfm="Unit1.dfm", new_component_class="TButton", properties={"Caption": "OK"}',
            'remove: action="remove", target_dfm="Unit1.dfm", component_name="BtnCancel"',
            'modify: action="modify", target_dfm="Unit1.dfm", component_name="BtnOK", properties={"Caption": "Confirm"}',
        ],
        "action_params": {
            "create": {
                "description": "Generate component DFM (compile+runtime serialization)",
                "required": ["code"],
                "optional": {
                    "uses": "List of units to reference, e.g. [\"Vcl.Forms\", \"Vcl.StdCtrls\"]",
                    "type_decl": "Type declaration section (optional)",
                    "init_code": "Initialization code (optional)",
                    "compile_timeout": "Compile timeout in seconds (default 60)",
                    "exec_timeout": "Execution timeout in seconds (default 15)",
                },
            },
            "add": {
                "description": "Add child component to existing DFM",
                "required": ["target_dfm"],
                "optional": {
                    "target_pas": "Absolute path to PAS file (optional, automatically sync declarations)",
                    "parent_name": "Parent component name (optional, default adds to root)",
                    "new_component_class": "New component class name, e.g. TButton",
                    "new_component_name": "New component instance name (optional, auto-generated)",
                    "properties": "Component properties dictionary",
                    "dfm_text": "DFM text snippet to add",
                },
            },
            "remove": {
                "description": "Remove component from DFM (including subtree)",
                "required": ["target_dfm", "component_name"],
                "optional": {
                    "target_pas": "Absolute path to PAS file (optional, automatically sync deletion)",
                },
            },
            "modify": {
                "description": "Modify component properties in DFM",
                "required": ["target_dfm", "component_name"],
                "optional": {
                    "target_pas": "Absolute path to PAS file (optional, automatically sync events)",
                    "properties": "Component properties dictionary",
                },
            },
        },
    },
    "check_environment": {
        "summary": "Diagnose Delphi compilation environment, detect compiler, install pasfmt. Run check first on first use.",
        "description": "Environment check — diagnose Delphi compilation environment, detect compiler, install pasfmt",
        "triggers": ["Check environment, detect compiler, diagnose, environment status, environment ready, compiler not found"],
        "workflow": "First use→check_environment(action=check)→compile→failure→check_environment(action=detect)",
        "actions": {
            "check": "Default — check current compilation environment status (how many compilers are available)",
            "detect": "Redetect Delphi compilers from registry/specified path",
            "install": "Download and install pasfmt formatting tool",
            "format_install": "Install pasfmt RAD Studio plugin",
        },
        "examples": [
            'check_environment(action="check")                                  check environment',
            'check_environment(action="detect", search_path="D:\\Delphi")       detect specified path',
        ],
        "action_params": {
            "check": {
                "description": "Check current compilation environment status",
                "required": [],
                "optional": {},
            },
            "detect": {
                "description": "Redetect Delphi compilers",
                "required": [],
                "optional": {
                    "search_path": "Additional search path",
                },
            },
            "install": {
                "description": "Download and install pasfmt formatting tool",
                "required": [],
                "optional": {
                    "install_dir": "Absolute installation directory path",
                },
            },
            "format_install": {
                "description": "Install pasfmt RAD Studio plugin",
                "required": [],
                "optional": {
                    "install_dir": "Absolute installation directory path",
                    "delphi_version": "Delphi version number, e.g. 11, 12",
                },
            },
        },
    },
    "async_task": {
        "summary": "Manage background time-consuming tasks such as knowledge base building. Usually automatically triggered by delphi_kb(action=build).",
        "description": "Async task management — manage background time-consuming tasks such as knowledge base building",
        "triggers": ["Task status, view progress, background task, build progress, cancel task"],
        "push_notification": (
            "Automatically push notification to MCP client when async task completes/fails; no polling needed."
        ),
        "actions": {
            "start": "Start async task (usually automatically started by delphi_kb(action=build); no manual call needed)",
            "status": "Query task status (returns progress percentage and status)",
            "result": "Get task result (large results automatically written to temporary file, returns summary+file path)",
            "list": "List all tasks",
            "cancel": "Cancel running task",
        },
        "examples": [
            'async_task(action="status", task_id="...")   view task progress',
            'async_task(action="list")                    list all tasks',
        ],
        "action_params": {
            "start": {
                "description": "Start async task",
                "required": [],
                "optional": {
                    "task_type": "Task type, e.g. build_knowledge_base",
                    "task_params": "Task parameters dict",
                },
            },
            "status": {
                "description": "Query task status",
                "required": [],
                "optional": {
                    "task_id": "Task ID",
                    "long_poll_seconds": "Long polling seconds, default 0 (return immediately), maximum 30",
                    "show_progress": "Whether to show progress, default true",
                },
                "note": "⚠️ For slow tasks (such as automated tests), do not use long_poll_seconds; instead use action=result polling to avoid MCP channel timeout",
            },
            "result": {
                "description": "Get task result (return immediately, zero wait)",
                "required": [],
                "optional": {
                    "task_id": "Task ID",
                },
                "note": "✅ Recommended for polling slow task status: return current result immediately without blocking. When task is not complete, returns \"Task not completed\" + current progress. When result exceeds 10KB, automatically writes to temporary file, returns summary+file path; after reading, call cleanup to clean up",
            },
            "list": {
                "description": "List all tasks",
                "required": [],
                "optional": {},
            },
            "cancel": {
                "description": "Cancel running task",
                "required": [],
                "optional": {
                    "task_id": "Task ID",
                },
            },
        },
    },
    "package": {
        "summary": "Compile/install/manage Delphi component packages. Supports .dproj/.dpk/.groupproj.",
        "description": "Component package management — compile/install/list installed",
        "triggers": ["Install component, install package, compile package, install dpk, register component, list installed, install package"],
        "details": "Automatically register design-time packages to IDE; runtime packages are only compiled",
        "workflow": "package(action=install) → package(action=list) verify installation",
        "actions": {
            "install": "Compile and install component package. package_path is required.",
            "list": "List component packages installed in IDE. No parameters.",
        },
        "examples": [
            'package(action="install", package_path="MyPackage.dpk")  install component package',
            'package(action="list")                                    verify installation',
        ],
        "action_params": {
            "install": {
                "description": "Compile and install component package",
                "required": ["package_path"],
                "optional": {
                    "target_platform": "Target platform win32/win64, default win32",
                    "build_configuration": "Build configuration Debug/Release, default Debug",
                    "timeout": "Timeout in seconds, default 300",
                    "install": "Whether to automatically install to IDE, default true",
                },
            },
            "list": {
                "description": "List installed component packages",
                "required": [],
                "optional": {},
            },
        },
    },
    "get_coding_rules": {
        "summary": "Load coding rules (supports Delphi / Lazarus/FPC). Load by scenario; do not read all at once.",
        "description": (
            "Load coding rules by scenario. Supports coding standards for multiple programming languages.\n\n"
            "**Language selection**:\n"
            "  `language=\"delphi\"` (default) — Delphi coding standards\n"
            "  `language=\"lazarus\"` — Lazarus/Free Pascal coding standards\n\n"
            "⚠️ Scenarios that must be called (violation may cause compilation failure/runtime crash):\n"
            "  Edit code → section=\"writing\"      (naming/formatting/line number rules)\n"
            "  Compile project → section=\"compile\"       (compile parameters/error handling)\n"
            "  Review code → section=\"review\"        (review checklist)\n\n"
            "📋 Scenarios to load on demand:\n"
            "  First-time coding → section=\"workflow\"      (overall process overview)\n"
            "  Debugging issues → section=\"debugging\"     (debug decision tree/exception classification)\n"
            "  Automated testing → section=\"automation\"  (test architecture/scripts/scenario templates)\n"
            "  UI layout → section=\"ui_layout\"      (layout audit standards)\n"
            "  Save experience → section=\"experience\"    (experience library operations)\n"
            "  Human collaboration → section=\"human_collab\"  (exception diagnosis/manual intervention)\n"
            "  Rebuild KB → section=\"kb_build\"       (knowledge base rebuild)\n\n"
            "💡 On-demand loading examples:\n"
            "  examples=\"naming\"           — naming standards example\n"
            "  examples=\"formatting\"       — formatting example\n"
            "  examples=\"documentation\"    — documentation comment example\n"
            "  examples=\"error-handling\"   — error handling example\n"
            "  examples=\"dirty-flag\"       — dirty flag protection example\n"
            "  examples=\"debug-log-template\" — debug log template example\n"
            "  examples=\"write-edits\"      — write(edits=[...]) batch write example\n"
            "  Rule files contain 📋 example: examples/xxx line, indicating available example names\n\n"
            "💡 Omit section= to return workflow overview+section index (recommended on first use)"
        ),
        "triggers": ["Coding rules, coding standards, code style, naming conventions, rules, coding rules"],
        "file_triggers": [
            "⚠️ When seeing .pas/.dfm/.dproj/.dpk/.dpr/.inc/.res/.groupproj and other Delphi files, you must call this tool first",
            "⚠️ Before writing/modifying any Delphi code, you must first call get_coding_rules to learn the coding standards",
        ],
        "workflow": "Before any .pas/.dproj operation→get_coding_rules(section='workflow') learn the process",
        "section_guide": {
            "workflow": "Workflow overview (load on first coding)",
            "writing": "Naming/formatting/generics rules when writing Delphi code (must load before editing code)",
            "compile": "Compile parameters/error handling (must load before compiling project)",
            "review": "Review code after compilation (must load before review)",
            "debugging": "Debug decision tree/exception classification (load when debugging issues)",
            "automation": "Automated test architecture/scripts/scenario templates (load during automated testing)",
            "ui_layout": "UI layout standards and auditing (load after modifying forms)",
            "experience": "Experience library operations (load when saving/searching experience)",
            "human_collab": "Human collaboration (load during exception diagnosis/manual intervention)",
            "kb_build": "Knowledge base rebuild (load when KB data is missing)",
            "agent_rules": "Agent operation hard rules (load when executing scripts/formatting)",
        },
        "examples_guide": {
            "naming": "Naming standards code example (T/I/E/P/F/A prefixes, PascalCase, UPPER_SNAKE constants)",
            "formatting": "Formatting code example (2-space indentation, begin on its own line, uses grouped alphabetically)",
            "documentation": "Documentation comment example (unit header comment, XML Doc style method comments)",
            "error-handling": "Error handling example (try/finally resource release, specific exception catching, no empty except)",
            "dirty-flag": "Dirty flag protection example (read/preview process before and after writing)",
            "debug-log-template": "Debug log template example (problem description/attempted solutions/current scope/next step)",
            "write-edits": "write(edits=[...]) batch write example (line number offset calculation)",
        },
        "default_section": "Omit section= to return workflow overview+section index (recommended on first call). language=delphi(default) or lazarus.",
    },    "code_hosting": {
        "summary": "Git local operations + code hosting platform. This tool must be used for all Git operations; do not execute git directly via bash.",
        "description": "All Git operations(status/diff/show/log/add/commit/fetch/pull/branch/switch/merge/restore/stash/tag/push/clone) + code hosting platform API. Do not execute git via bash (code_hosting saves tokens and automatically handles asynchronous pushes).",
        "triggers": ["git", "status", "diff", "show", "log", "add", "commit", "push", "clone", "pull", "branch", "stash", "commit", "push", "stage", "repository"],
        "platforms": {
            "gitea": "Self-hosted Gitea",
            "github": "GitHub (github.com)",
            "gitlab": "GitLab CE/EE (gitlab.com)",
            "gitee": "Gitee Code Cloud (gitee.com)",
            "gitcode": "GitCode (gitcode.net)",
        },
        "actions": {
            "api": {
                "create_token": "Create token (Gitea only)", "init_labels": "Initialize labels",
                "create_issue": "Create issue", "get_issue": "View issue",
                "edit_issue": "Edit issue", "set_labels": "Set issue labels",
                "close_issue": "Close issue", "add_comment": "Comment on issue",
                "list_issues": "List issues",
                "create_pull": "Create PR/MR", "get_pull": "View PR/MR",
                "list_pulls": "List PR/MR", "edit_pull": "Edit PR/MR",
                "merge_pull": "Merge PR/MR", "close_pull": "Close PR/MR",
                "reopen_pull": "Reopen PR/MR",
                "create_release": "Create Release", "get_release": "View Release",
                "list_releases": "List Releases", "edit_release": "Edit Release",
                "delete_release": "Delete Release",
            },
            "git_sync": {
                "git_status": "Repository status", "git_diff": "View diff", "git_show": "View commit/object",
                "git_log": "Commit history", "git_add": "Stage files", "git_commit": "Commit",
                "git_fetch": "Fetch remote refs (supports async_mode)", "git_pull": "Pull and merge (supports async_mode)",
                "git_branch": "List/create/delete branches", "git_switch": "Switch/create branch",
                "git_merge": "Merge branch (supports async_mode)", "git_restore": "Restore explicit files",
                "git_unstage": "Unstage", "git_stash": "stash management", "git_tag": "List/create/delete tags",
            },
            "git_async": {
                "git_clone": "Clone (supports GitHub mirror)", "git_push": "Push",
                "git_push_retry": "Push (automatic background retry)",
            },
        },
        "china_access": "git_clone supports the mirror parameter to specify a mirror source. Pushing depends on the user's own SSH/HTTPS proxy configuration.",
        "action_params": {
            "git_status": {
                "description": "View repository status",
                "required": ["dir"],
                "optional": {},
            },
            "git_diff": {
                "description": "View diff",
                "required": ["dir"],
                "optional": {"staged": "Show staged diff", "name_only": "Only output file names", "stat": "Output statistics", "limit": "Number of lines to truncate output to", "files": "List of file paths"},
            },
            "git_log": {
                "description": "View commit history",
                "required": ["dir"],
                "optional": {"limit": "Number of results", "files": "List of file paths", "stat": "Show statistics"},
            },
            "git_add": {
                "description": "Stage files",
                "required": ["dir"],
                "optional": {"files": "List of file paths"},
            },
            "git_commit": {
                "description": "Commit",
                "required": ["dir", "message"],
                "optional": {},
            },
            "git_push": {
                "description": "Push to remote",
                "required": ["dir"],
                "optional": {"remote": "Remote name, defaults to origin", "branch": "Branch name"},
            },
            "git_push_retry": {
                "description": "Push (automatic background retry)",
                "required": ["dir"],
                "optional": {"remote": "Remote name, defaults to origin", "branch": "Branch name", "retry_interval": "Retry interval in seconds, defaults to 300", "max_retries": "Maximum retry count, defaults to 12"},
            },
            "git_clone": {
                "description": "Clone repository",
                "required": ["repo_url", "dir"],
                "optional": {"branch": "Branch name", "mirror": "GitHub mirror source address"},
            },
            "git_branch": {
                "description": "Branch management",
                "required": ["dir"],
                "optional": {"branch": "Branch name", "delete": "Delete branch", "remote_branches": "List remote branches"},
            },
            "git_switch": {
                "description": "Switch/create branch",
                "required": ["dir", "branch"],
                "optional": {"create": "Create and switch branch", "start_point": "New branch start point"},
            },
            "git_fetch": {
                "description": "Fetch remote refs",
                "required": ["dir"],
                "optional": {"branch": "Branch name", "prune": "Use --prune", "async_mode": "Execute asynchronously in background"},
            },
            "git_pull": {
                "description": "Pull and merge",
                "required": ["dir"],
                "optional": {"branch": "Branch name", "rebase": "Use rebase mode", "async_mode": "Execute asynchronously in background"},
            },
            "git_merge": {
                "description": "Merge branch",
                "required": ["dir", "branch"],
                "optional": {"ff_only": "Use ff-only", "no_commit": "Use no-commit", "async_mode": "Execute asynchronously in background"},
            },
            "git_restore": {
                "description": "Restore files",
                "required": ["dir", "files"],
                "optional": {"staged": "Restore staged files", "source": "--source reference"},
            },
            "git_stash": {
                "description": "stash management",
                "required": ["dir"],
                "optional": {"op": "push/list/pop/apply/drop/show", "include_untracked": "Include untracked files", "message": "stash message", "files": "File list"},
            },
            "git_tag": {
                "description": "Tag management",
                "required": ["dir"],
                "optional": {"tag": "Tag name", "start_point": "Tag start point", "delete": "Delete tag"},
            },
            "git_unstage": {
                "description": "Unstage",
                "required": ["dir"],
                "optional": {"files": "File list"},
            },
            "git_show": {
                "description": "View commit/object",
                "required": ["dir", "ref"],
                "optional": {"stat": "Statistics", "name_only": "Only output file names"},
            },
            "create_issue": {
                "description": "Create issue",
                "required": ["repo", "title"],
                "optional": {"body": "Body content", "labels": "List of label names"},
            },
            "create_pull": {
                "description": "Create PR/MR",
                "required": ["repo", "title", "source_branch", "target_branch"],
                "optional": {"body": "Body content"},
            },
            "create_release": {
                "description": "Create Release",
                "required": ["repo", "tag_name"],
                "optional": {"name": "Release name", "body": "Body content", "target_commitish": "Target commit", "draft": "Draft flag", "prerelease": "Prerelease flag"},
            },
        },
    },

    "tool_help": {
        "summary": "Get the full help documentation for any tool, including parameter descriptions, examples, trigger words, and collaboration chains.",
        "description": "Get the full help documentation for a tool",
        "triggers": ["help, help documentation, usage, how to use, detailed description, full help"],
        "usage": "Call this tool when unsure about the detailed usage of a tool. Enter tool_name to return all detailed information such as trigger words, action descriptions, examples, and collaboration chains.",
        "examples": [
            'tool_help(tool_name="delphi_file")',
            'tool_help(tool_name="delphi_project")',
        ],
    },
    "delphi_rtti": {
        "summary": "Delphi RTTI bridge — discover and call the runtime capabilities of a Delphi application via RTTI. Three-step method: discover→discover capabilities, call→call methods, guide→usage guide.",
        "description": "Delphi RTTI bridge — discover/call Delphi application capabilities via Enhanced RTTI",
        "triggers": [
            "RTTI, runtime discovery, call Delphi methods, discover Delphi capabilities, published+public methods",
            "delphi rtti, rtti bridge, runtime type information",
        ],
        "constraints": [
            "❌ Requires the Delphi application to have linked the DaofyAutomation unit (VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation)",
            "❌ Requires Delphi 2010+ (Enhanced RTTI)",
            "⚠️ Cannot discover methods/properties in protected and private sections",
        ],
        "auto_unit_paths": [
            "VCL project → Vcl.DaofyAutomation.pas (automatically references DaofyAutomation.Base / RttiAttributes / RttiDiscovery)",
            "FMX project → Fmx.DaofyAutomation.pas (automatically references DaofyAutomation.Base / RttiAttributes / RttiDiscovery)",
            "The above files are all in $(DaofyRoot)\\tools\\auto\\; add this path to the project Search path to compile",
        ],
        "workflow": "delphi_rtti(action='guide') → discover → call",
        "features": [
            "Three-step method: guide(usage guide) → discover(capability scan) → call(method invocation)",
            "Automatic JSON Schema type mapping (15 Delphi types)",
            "5-minute cache; no repeated scan within the same application lifecycle",
            "Process pool reuse; keep_alive supports multiple calls",
            "AI annotation support: AIDescription / AIResultDescription / AIExample / AIParamDescription",
        ],
        "actions": {
            "guide": "Return the complete usage guide (including type mapping table, best practices, troubleshooting)",
            "discover": "Scan and return the published+public methods/properties of all classes in the Delphi application, including JSON Schema parameter definitions and AI annotation descriptions",
            "call": "Call the specified method of the specified class; params is an optional parameter dict",
        },
        "action_params": {
            "guide": {
                "description": "Get the usage guide for the delphi_rtti tool",
                "optional": {},
            },
            "discover": {
                "description": "Scan the RTTI capabilities of a Delphi application",
                "required": ["app_path"],
                "optional": {
                    "class_name": "Limited class name; an empty string scans all",
                    "force": "true forces cache refresh (default false)",
                    "keep_alive": "true keeps the process running for subsequent reuse (default false)",
                    "pipe": "Internal named pipe name (auto-generated; automatically set if not passed)",
                },
            },
            "call": {
                "description": "Call a method exposed by the Delphi application via RTTI",
                "required": ["app_path", "class_name", "method"],
                "optional": {
                    "params": "Parameter dict; key names must match the Schema returned by discover",
                    "keep_alive": "true keeps the process running for subsequent reuse (default false)",
                    "pipe": "Internal named pipe name (auto-generated; automatically set if not passed)",
                },
            },
        },
        "examples": [
            'delphi_rtti(action="guide")                                                        Get usage guide',
            'delphi_rtti(action="discover", app_path="C:\\App\\MyApp.exe")                      Scan all classes',
            'delphi_rtti(action="discover", app_path="C:\\App\\MyApp.exe", class_name="TMainForm")  Scan specified class',
            'delphi_rtti(action="discover", app_path="C:\\App\\MyApp.exe", keep_alive=True)      Scan and keep process alive',
            'delphi_rtti(action="call", app_path="C:\\App\\MyApp.exe", class_name="TMainForm", method="CreateOrder", params={"customerName":"Zhang San"})  Call method',
        ],
        "workflow_hints": {
            "首次使用": "delphi_rtti(action='guide') View complete usage instructions",
            "连接应用": "delphi_rtti(action='discover', app_path='...') → Auto-connect → Discover capabilities",
            "调用方法": "delphi_rtti(action='call', app_path='...', class_name='...', method='...')",
            "批量调用": "First use keep_alive=True → Multiple calls → Automatically reuse process",
        },
        "type_mapping": {
            "string": "String/UnicodeString/AnsiString → string",
            "integer": "Integer/Int64/Cardinal/Byte/Word → integer (unsigned adds minimum:0)",
            "number": "Single/Double/Currency → number",
            "boolean": "Boolean/ByteBool/WordBool/LongBool → boolean",
            "datetime": "TDateTime → string with format:date-time",
            "enum": "Enum type → string with enum constraint",
            "array": "Dynamic array/TArray → array, element types recursively mapped",
            "object": "TObject subclass → object",
            "variant": "Variant → [string,number,boolean,null]",
        },
    },    "experience": {
        "summary": "Experience memory management: save/search approaches that AI successfully used to solve problems, automatically reuse next time a similar problem is encountered. save automatically deduplicates.",
        "description": "Experience memory management — save/search/manage AI experiences that successfully solved problems, automatically deduplicate and merge on save",
        "triggers": ["experience, memory, save experience, search experience, how was it solved before, I remember"],
        "workflow": "Task succeeds → experience(action=save, ...) → auto deduplicate (>0.85 merged not added) → periodically experience(action=prune) clean low-value entries",
        "actions": {
            "save": "Save experience (auto deduplicate: merge when similarity >0.85). Required: problem+solution",
            "search": "Semantic search experiences. query+top_k",
            "get": "View experience details. id=experience ID",
            "list": "Browse list. tags+sort_by+limit",
            "update": "Update experience. id+fields to change",
            "merge": "Merge multiple experiences. ids=[id1,id2,...] at least 2",
            "prune": "List low-value experiences for review and deletion",
            "delete": "Delete experience. id=experience ID",
            "rebuild_embedding": "Rebuild missing vectors. Need delphi_kb(build_embedding) to load model first",
        },
        "action_params": {
            "save": {
                "description": "Save experience (auto deduplicate)",
                "required": ["problem", "solution"],
                "optional": {
                    "tools_used": "List of tools used",
                    "tags": "Tag list",
                    "context": "Context info dict",
                    "force": "Force new save (skip >0.7 deduplication reminder layer)",
                },
            },
            "search": {
                "description": "Semantic search experiences",
                "required": [],
                "optional": {
                    "query": "Search keywords",
                    "top_k": "Number of results, default 5",
                    "tags": "Tag filter",
                },
            },
            "get": {
                "description": "View experience details",
                "required": ["id"],
                "optional": {},
            },
            "list": {
                "description": "Browse list",
                "required": [],
                "optional": {
                    "tags": "Tag filter",
                    "sort_by": "Sort field: updated_at/created_at/hit_count/score, default updated_at",
                    "limit": "Number of results, default 20",
                },
            },
            "update": {
                "description": "Update experience",
                "required": ["id"],
                "optional": {
                    "problem": "New problem description",
                    "solution": "New solution steps",
                    "tags": "New tag list",
                    "tools_used": "New tool list",
                    "context": "New context info",
                },
            },
            "merge": {
                "description": "Merge multiple experiences",
                "required": ["ids"],
                "optional": {
                    "keep": "Target ID to keep (optional, creates new record if not passed)",
                },
            },
            "prune": {
                "description": "List low-value experiences",
                "required": [],
                "optional": {
                    "limit": "Number of results, default 20",
                },
            },
            "delete": {
                "description": "Delete experience",
                "required": ["id"],
                "optional": {},
            },
            "rebuild_embedding": {
                "description": "Rebuild missing vectors",
                "required": [],
                "optional": {},
            },
        },
    },
    "daofy_update": {
        "summary": "Check Daofy version updates, execute git pull update (similar to code_hosting async mode).",
        "description": "Daofy self-update management — version check / git pull update (background async + automatic retry)",
        "triggers": ["update, upgrade, new version, check for updates, daofy version, update, upgrade"],
        "workflow": "Automatically check in the background on startup → intelligently prompt/notify AI → AI asks user → daofy_update(action='update') → async_task check progress → notify restart",
        "actions": {
            "check": "Quickly check first (cache/sync), on failure automatically submit background retry task (returns task_id)",
            "check_retry": "Force submit background automatic retry version check task, returns task_id",
            "update": "Submit background git pull task (single run), returns task_id",
            "update_retry": "Submit background automatic retry git pull task (similar to git_push_retry), returns task_id",
            "version": "Show current version number and installation method (git/pip)",
        },
        "notes": (
            "On startup the server automatically checks for updates in the background; when a new version is available, it intelligently prompts/notifies the AI through the tool response.\n"
            "When check/update returns task_id, use async_task(action=status, task_id=...) to view progress.\n"
            "When the task completes, a notification is automatically pushed to the MCP client.\n"
            "After the update completes, restart Daofy or the AI Agent for the new version to take effect.\n"
            "pip installation users use: pip install --upgrade daofy-for-delphi"
        ),
        "examples": [
            'daofy_update(action="check")           Check version (quick/background retry)',
            'daofy_update(action="check_retry")     Force background retry check',
            'daofy_update(action="update")          Background git pull update',
            'daofy_update(action="update_retry")    Background automatic retry git pull',
            'async_task(action=status, task_id=...) Query async task progress',
            'daofy_update(action="version")         Show current version',
        ],
        "action_params": {
            "check": {
                "description": "Quickly check version updates",
                "required": [],
                "optional": {},
            },
            "check_retry": {
                "description": "Force background retry version check",
                "required": [],
                "optional": {},
            },
            "update": {
                "description": "Background git pull update",
                "required": [],
                "optional": {},
            },
            "update_retry": {
                "description": "Background automatic retry git pull",
                "required": [],
                "optional": {
                    "retry_interval": "Retry interval in seconds, default 60",
                    "max_retries": "Maximum retries, default 10",
                },
            },
            "version": {
                "description": "Show current version number",
                "required": [],
                "optional": {},
            },
        },
    },
    "generate_copyright": {
        "summary": "Generate software copyright documents (source code + manual + summary table).",
        "description": "Software copyright document generation — source code/manual/summary table",
        "triggers": ["software copyright, copyright, copyright registration, copyright"],
        "constraints": ["Requires Edge/Chrome browser headless"],
        "actions": {
            "generate": "Generate documents", "validate": "Check configuration",
            "update_config": "Update configuration (config dict)", "status": "Check browser",
            "list": "List generated files", "generate_content": "Generate draft",
            "audit": "Audit draft rejection risks",
        },
        "examples": [
            'generate_copyright(action="validate")',
            'generate_copyright(action="update_config", config={"contact_person":"John Doe"})',
            'generate_copyright(action="generate")',
            'generate_copyright(action="audit")',
        ],
        "action_params": {
            "generate": {
                "description": "Generate software copyright documents (source code + manual + summary table)",
                "required": [],
                "optional": {
                    "doc_type": "Document type: all/source/manual/summary, default all",
                    "output_dir": "Absolute path of output directory (optional, default docs/copyright)",
                    "project_path": "Absolute path of project (optional, default current working directory)",
                },
            },
            "validate": {
                "description": "Check configuration",
                "required": [],
                "optional": {},
            },
            "update_config": {
                "description": "Update configuration",
                "required": [],
                "optional": {
                    "config": "Configuration update dict",
                },
            },
            "status": {
                "description": "Check browser/environment status",
                "required": [],
                "optional": {},
            },
            "list": {
                "description": "List generated files",
                "required": [],
                "optional": {},
            },
            "generate_content": {
                "description": "Generate draft",
                "required": [],
                "optional": {},
            },
            "audit": {
                "description": "Audit draft, check rejection risks",
                "required": [],
                "optional": {},
            },
        },
    },
    "ocr": {
        "summary": "Image analysis: PP-OCRv6 text recognition + screenshot diff comparison + color analysis + icon matching.",
        "description": "Image analysis — text recognition/screenshot comparison/color analysis/template matching",
        "triggers": [
            "OCR, text recognition, image text, recognize image, extract text, image text",
            "image to text, screenshot recognition, ocr recognition, optical character recognition",
            "screenshot comparison, image diff, diff, color analysis, icon matching, template matching",
        ],
        "constraints": [
            "❌ image_path must be a path to an existing local file",
            "❌ base64-encoded images are not supported (save to a file first)",
            "⚠️ On first call the model (~65MB) is downloaded automatically; this may take time",
            "⚠️ Models are cached to data/ocr-models/; subsequent calls need no download",
            "⚠️ diff/color/match use OpenCV/Pillow and do not require the OCR model",
        ],
        "workflow": "ocr(action=status) → confirm model ready → ocr(action=recognize, image_path=...)",
        "auto_backend": (
            "Automatically select inference backend:\n"
            "  Intel CPU + openvino → OpenVINO (uses VNNI/AMX acceleration)\n"
            "  AMD / other CPU       → ONNX Runtime\n"
            "  Python ≥ 3.14        → ONNX Runtime (PaddlePaddle incompatible)"
        ),
        "actions": {
            "recognize": "Full OCR pipeline: detection → orientation classification → text recognition → return structured results",
            "detect": "Text box detection only, no text recognition (returns box + score)",
            "status": "Query model loading status and backend info",
            "diff": "Screenshot diff comparison: pixel-level comparison of two images, returns changed regions",
            "color": "Region color analysis: RGB average color/dominant color/brightness/grayscale check for specified region",
            "match": "Icon template matching: find the position of specified icon/pattern in screenshot",
        },
        "action_params": {
            "recognize": {
                "description": "Detect and recognize all text in the image",
                "required": ["image_path"],
                "optional": {},
                "examples": [
                    'ocr(action="recognize", image_path="C:\\screenshot.png")',
                    'ocr(action="recognize", image_path="data/test_img.png")',
                ],
            },
            "detect": {
                "description": "Detect text box positions only",
                "required": ["image_path"],
                "examples": [
                    'ocr(action="detect", image_path="screenshot.png")',
                ],
            },
            "status": {
                "description": "Query service status (backend type, whether model is loaded)",
                "examples": [
                    'ocr(action="status")',
                ],
            },
            "diff": {
                "description": "Compare two screenshots and find visually different regions",
                "required": ["baseline", "current"],
                "optional": {"threshold": "Pixel difference threshold 0-255 (default 10)",
                             "output_dir": "Absolute path of diff image output directory (optional)"},
                "examples": [
                    'ocr(action="diff", baseline="before.png", current="after.png")',
                    'ocr(action="diff", baseline="100%.png", current="150%.png", threshold=5)',
                ],
            },
            "color": {
                "description": "Analyze color features of specified region in image",
                "required": ["image_path"],
                "optional": {"region": "Analysis region [x,y,w,h]; if not passed, entire image"},
                "examples": [
                    'ocr(action="color", image_path="screenshot.png", region=[10,20,100,25])',
                    'ocr(action="color", image_path="button.png")',
                ],
            },
            "match": {
                "description": "Find specified icon/pattern in screenshot",
                "required": ["image_path", "template_path"],
                "optional": {"threshold": "Matching threshold 0-1 (default 0.8)"},
                "examples": [
                    'ocr(action="match", image_path="screenshot.png", template_path="save_icon.png")',
                ],
            },
        },
        "examples": [
            'ocr(action="status")                                                   Query model status',
            'ocr(action="recognize", image_path="screenshot.png")                   Full OCR recognition',
            'ocr(action="detect", image_path="screenshot.png")                      Text box detection only',
            'ocr(action="diff", baseline="base.png", current="new.png")             Screenshot diff comparison',
            'ocr(action="color", image_path="btn.png", region=[0,0,50,20])          Region color analysis',
            'ocr(action="match", image_path="shot.png", template_path="icon.png")   Icon matching',
        ],
        "response_format": {
            "recognize": (
                "{\n"
                '  "status": "ok",\n'
                '  "action": "recognize",\n'
                '  "count": 3,\n'
                '  "results": [\n'
                "    {\n"
                '      "text": "OK",\n'
                '      "confidence": 0.97,\n'
                '      "box": [[10,20],[100,20],[100,50],[10,50]],\n'
                '      "det_score": 0.85\n'
                "    },\n"
                "    ...\n"
                "  ]\n"
                "}"
            ),
            "status": (
                "{\n"
                '  "backend": "onnxruntime",\n'
                '  "model_size": "medium",\n'
                '  "loaded": true,\n'
                '  "models_available": {"det": true, "rec": true, "cls": true}\n'
                "}"
            ),
            "diff": (
                "{\n"
                '  "changed": true,\n'
                '  "diff_pixels": 1234,\n'
                '  "diff_percent": 0.52,\n'
                '  "regions": [{"bbox": [10,20,100,60], "area_pct": 0.3, "mean_diff": 45.3}]\n'
                "}"
            ),
            "color": (
                "{\n"
                '  "avg_color": {"r": 255, "g": 0, "b": 0},\n'
                '  "is_grayscale": false,\n'
                '  "brightness": 0.33\n'
                "}"
            ),
            "match": (
                "{\n"
                '  "found": true,\n'
                '  "match_count": 1,\n'
                '  "matches": [{"bbox": [100,200,130,230], "confidence": 0.92}]\n'
                "}"
            ),
        },
        "workflow_hints": {
            "首次使用": "ocr(action='status') Check whether the model has been downloaded",
            "日常识别": "ocr(action='recognize', image_path='...') Directly recognize",
            "快速检测": "ocr(action='detect', image_path='...') First check text box positions",
            "截图对比": "ocr(action='diff', baseline='...', current='...') Check whether UI changed",
            "颜色验证": "ocr(action='color', image_path='...', region=[...]) Check button color",
            "图标查找": "ocr(action='match', image_path='...', template_path='icon.png') Confirm the icon appears",
        },
    },    "automate_delphi": {
        "summary": "Drive Delphi program automation testing (GUI screenshots + console interaction). Supports a perceive-plan-execute-feedback loop.",
        "description": "Delphi automation testing — perceive·plan·execute·feedback",
        "triggers": ["automation testing", "screenshots", "Delphi automation", "console testing", "automate"],
        "constraints": ["gui mode requires the Delphi program to have linked the DaofyAutomation unit (VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation); console mode requires no Delphi-side changes"],
        "auto_unit_paths": [
            "VCL project → Vcl.DaofyAutomation.pas (automatically references DaofyAutomation.Base / RttiAttributes / RttiDiscovery)",
            "FMX project → Fmx.DaofyAutomation.pas (automatically references DaofyAutomation.Base / RttiAttributes / RttiDiscovery)",
            "callgraph optional diagnostics → additionally uses DaofyAutomation.CallGraph, and ensure tools\\stacktrace is in the Search path",
            "Core automation files are in $(DaofyRoot)\\tools\\auto\\, callgraph implementation is in $(DaofyRoot)\\tools\\stacktrace\\; use action=prepare to automatically register the required global search paths",
        ],
        "architecture": {
            "pattern": "Perceive → Plan → Execute → Feedback (loop)",
            "brain": "The large model is responsible for decision-making and planning",
            "hands": "MCP tools are responsible for perception and execution",
            "see_also": "Script generation workflow: MCP Resource delphi://automation/script-generation-workflow; resource index: delphi://resources; detailed methodology + prompt templates + experience optimization loop + script cache: get_coding_rules(section=\"automation\")",
            "self_learning": (
                "Implemented through the experience tool + delphi://coding-rules / get_coding_rules(section=\"automation\"): "
                "retrieve experience before testing → record failures/recovery during testing → save experience after testing → "
                "periodically merge and abstract into general patterns. Let the large model learn and evolve from each test."
            ),
        },
        "modes": {
            "gui": {
                "description": "Drive a GUI program through named pipes to perform operations and take screenshots.",
                "needs_auto_unit": True,
                "stop_on_failure": "Default true. After the first failure, stop executing subsequent dependent steps and mark them as skip in report.steps; set explicitly to false when full exploration is needed.",
                "script_shape": (
                    "script can be a file path, JSON string, step array, or the recommended full script object "
                    '{"test_name":"smoke","steps":[...]}; fields in the object other than steps are returned as script_metadata.'
                ),
                "exception_filter": (
                    "Script metadata can set exception_filter to automatically detect exception dialogs/focus loss/session expiration between steps, "
                    "handle them, and continue execution without interrupting the test. Supported exception types: dialog/notification/focus_lost/session_expired. "
                    "Supported actions: close(ESC)/refocus(goto)/restart_app/log/ignore/abort. "
                    "Configuration example: {'exception_filter': {'enabled': true, 'on_exception': {'dialog': 'close', 'focus_lost': 'refocus'}}}. "
                    "The return value includes exception_filter statistics: {enabled, exception_count, max_exceptions, exceptions_handled}."
                ),
                "environment": (
                    "Optional `env` / `environment` top-level script fields inject temporary child-process "
                    "environment variables. Values are applied only at tested-process startup, are not persisted, "
                    "and reports redact values to {count, names}. Changing env for a keep_alive process restarts "
                    "the tested app; the MCP server itself does not need to restart."
                ),
                "callgraph_diagnostics": (
                    "The full script object can set callgraph_diagnostics=true, and declare handler/entry/callgraph_target on failed steps; "
                    "the report will attach diagnostics.callgraph; disabled by default."
                ),
                "protocol": {
                    "transport": "Named pipe JSON request/response",
                    "async_cmds": "click/rclick/dblclick/hover/move/drag/msgclick/dlgclick/rcall/key/rset/type",
                    "sync_cmds": "goto/capture/waitfor/wait/dumpstate/listwnd/dlgscan/msgscan/msgclose/dlgfile/snapdir/exit/rget/rinspect/textbounds/run_tests/callgraph/callgraph_diff/callgraph_path/callgraph_impact/callgraph_select_tests/callgraph_failure_diag/callgraph_boundary_check/callgraph_refactor_check/callgraph_orphan_candidates/callgraph_explain_exception",
                },
                "commands_by_phase": {
                    "perception": {
                        "description": "Get the current UI state",
                        "cmds": {
                            "capture": "Capture a screenshot of the current window (verify state/compare with expectation)",
                            "dumpstate": "Export the full control tree JSON (includes all RTTI properties, locates control paths)",
                            "formsum": "Form summary JSON — distilled clean structure from dumpstate: key fields flattened, Controls nesting hierarchy, saves tokens",
                            "listwnd": "Enumerate all top-level windows (get the handle when a new window appears)",
                            "callgraph": "Get the function call graph (direction=callees/callers; max_depth controls BFS; project_only/exclude_prefixes/include_prefixes filters; edge_limit controls output cap and returns edge_count/returned_count/truncated; edges include call_addr/call_file/call_line/category; requires additional uses DaofyAutomation.CallGraph + Detailed .map)",
                            "callgraph_diff": "Compare baseline and current callgraph at edge level with added/removed/unchanged (default compare_by=name, optional addr/full; save_as can save a snapshot, path restricted to snapshots_dir; Python-side command, but still requests callgraph through the pipe)",
                            "callgraph_path": "Query call paths from source to target (max_depth/max_paths/include_prefixes control scope; returns found and paths; Delphi-side command)",
                            "callgraph_impact": "Change impact analysis: batch query callers for functions/targets or file+line/locations, summarize entry candidates and unresolved (Python-side command, but still requests callgraph through the pipe)",
                            "callgraph_select_tests": "Recommend regression scripts based on callgraph_impact and test handler mapping (Python-side command)",
                            "callgraph_failure_diag": "Combine failed steps and callgraph summary into diagnostics.callgraph (Python-side command)",
                            "callgraph_boundary_check": "Check architectural boundary violation calls according to prefix rules (Python-side command)",
                            "callgraph_refactor_check": "List affected callers before refactoring and mark static graph blind spots (Python-side command)",
                            "callgraph_orphan_candidates": "Generate low-confidence orphan candidates from the symbol table and direct call graph (Python-side command)",
                            "callgraph_explain_exception": "Use callgraph/impact to explain upstream and downstream impact of the top function in an exception stack (Python-side command)",
                            "msgscan": "Scan MessageBox dialogs (synchronous, must be done after each step)",
                            "dlgscan": "Scan file dialog state (synchronous)",
                            "rinspect": "RTTI member discovery: list a control's property names + types + methods (not property values). Supports visibility parameter to filter visibility (default public,published)",
                            "textbounds": "Find the bounding rectangle of matching items in a control by displayed text (replaces OCR). Two modes: paint-hook (intercepts GDI/GDI+ text drawing, generic, supports any control including third-party/custom-drawn) and type-bound (dispatches by control type, covers standard VCL controls). Mode routing: paint=only paint-hook; type=only type-bound; auto=paint-hook first, fall back to type-bound on failure. Script parameters: target='ControlName@searchText' or JSON {'text':'searchText','mode':'auto','include_invisible':false}. Return values: simple mode {\"x\":..,\"y\":..,\"width\":..,\"height\":..}; paint-hook rich mode additionally includes visible_state(full/partial/invisible/unknown)/clipped/clip_*/visible_*/api",
                        },
                    },
                    "execution": {
                        "description": "Perform operations on the UI",
                        "cmds": {
                            "goto": "Navigate to the target control (locate first, then operate)",
                            "click": "Single click (asynchronous)",
                            "rclick": "Right-click (asynchronous)",
                            "dblclick": "Double-click (asynchronous)",
                            "type": "Input text (asynchronous)",
                            "key": "Press key Tab/Enter/Esc (asynchronous)",
                            "hover": "Mouse hover (asynchronous)",
                            "move": "Move mouse to coordinates (asynchronous)",
                            "drag": "Drag operation (asynchronous)",
                            "msgclick": "Click MessageBox button Confirm/Cancel (asynchronous)",
                            "dlgclick": "Click file dialog button Open/Save (asynchronous)",
                            "dlgfile": "Input path in file dialog (synchronous)",
                            "rcall": "RTTI call method (asynchronous, preferred fallback)",
                            "rset": "RTTI set property value (asynchronous)",
                            "uiaclick": "UIA click (match by Name property; add via:'uia' to step to reuse click/goto/get commands)",
                            "uiagoto": "UIA navigate to control",
                            "uiaget": "UIA read control Name",
                            "uiaset": "UIA set control value",
                            "uiascan": "UIA scan control tree",
                            "uiawait": "UIA wait for control to appear",
                            "uia.rclick": "UIA right-click",
                            "uia.dblclick": "UIA double-click",
                            "uia.hover": "UIA hover (trigger Tooltip)",
                            "uia.drag": "UIA drag to coordinates",
                            "uia.wheel": "UIA mouse wheel scroll",
                            "uia.scroll": "UIA scroll control (direction+amount)",
                            "uia.scrollinto": "UIA scroll child item into view",
                            "uia.type": "UIA simulate keyboard typing",
                            "uia.key": "UIA send key",
                            "uia.toggle": "UIA toggle switch state",
                            "uia.select": "UIA select item",
                            "uia.expand": "UIA expand node",
                            "uia.collapse": "UIA collapse node",
                            "uia.invoke": "UIA invoke default action",
                            "uia.find": "UIA find control by condition",
                            "uia.list": "UIA list child controls",
                            "uia.close": "UIA close window",
                            "uia.minimize": "UIA minimize window",
                            "uia.maximize": "UIA maximize window",
                            "uia.restore": "UIA restore window",
                            "uia.move": "UIA move window",
                            "uia.resize": "UIA resize window",
                            "uia.state": "UIA read window state",
                            "uia.exists": "UIA determine whether control exists",
                            "uia.rect": "UIA get control bounding rectangle",
                            "uia.screenshot": "UIA capture control screenshot",
                        },
                        "uia_note": "Adding the via:'uia' field to a step can route click/goto/get/set/wait commands to Python UIA (uiautomation library), bypassing Delphi pipe and main-thread deadlock issues. When foreground dialogs such as IFileDialog / DirectUI / #32770 cannot be penetrated by Win32 messages, use UIA commands.",
                    },
                    "verification": {
                        "description": "Verify execution results. For new scripts, use assert_expr to write Python expressions; for natural-language expectations, write expected/note: {'cmd':'rget','target':'btnSave.Enabled','assert_expr':\"actual=='True'\"}",
                        "cmds": {
                            "capture": "Compare screenshots after operations",
                            "waitfor": "Wait for condition to be satisfied (control visible/disappeared)",
                            "wait": "Wait a fixed time (milliseconds)",
                            "rget": "RTTI read property value (synchronous, preferred result assertion)",
                            "rinspect": "RTTI member discovery (synchronous, view property names/types/methods, not values; supports visibility parameter)",
                        },
                    },
                },
                # Legacy flat commands for backward compat
                "commands": {
                    "goto/click/rclick/dblclick": "Activate/click control",
                    "hover/move/drag": "Mouse operations",
                    "type/key": "Input/key press",
                    "wait/waitfor": "Wait (ms/condition)",
                    "capture/listwnd/dumpstate/formsum": "Screenshot/enumerate/control tree/form summary",
                    "dlgscan/msgscan/msgclose": "Dialog/menu scan and close (synchronous)",
                    "dlgclick/msgclick": "Dialog/menu click (asynchronous)",
                    "rget": "RTTI read property value (synchronous)",
                    "callgraph": "Get the function call graph (direction=callees/callers; max_depth controls BFS; project_only/exclude_prefixes/include_prefixes filters; edge_limit controls output cap and returns edge_count/returned_count/truncated; edges include call_addr/call_file/call_line/category)",
                    "callgraph_diff": "Compare baseline and current callgraph at edge level with added/removed/unchanged (default compare_by=name, optional addr/full; save_as/baseline_path restricted to snapshots_dir)",
                    "callgraph_path": "Query call paths from source to target, supports max_depth/max_paths/include_prefixes",
                    "callgraph_impact": "Batch query callers for changed functions or file/line positions, summarize entry candidates and unresolved",
                    "callgraph_select_tests": "Select recommended regression scripts based on impact and test metadata",
                    "callgraph_failure_diag": "Generate a callgraph diagnostic summary for failed steps",
                    "callgraph_boundary_check": "Check architectural boundaries according to prefix rules",
                    "callgraph_refactor_check": "Refactoring safety check, outputs affected callers and blind-spot hints",
                    "callgraph_orphan_candidates": "Dead code/orphan candidates; results are candidates only and must not be deleted automatically",
                    "callgraph_explain_exception": "Exception stack extended explanation, outputs upstream/downstream call summary",
                    "rset/rcall": "RTTI write property/call method (asynchronous)",
                    "rinspect": "RTTI member discovery (synchronous; supports visibility parameter)",
                    "textbounds": "Find the bounding rectangle of matching items in a control by displayed text (replaces OCR). paint-hook mode intercepts GDI/GDI+ text drawing for generic matching; type-bound mode dispatches by control type and covers standard VCL controls. mode=paint/type/auto (auto=paint first, fall back to type). FMX only supports paint-hook",
                    "dlgfile/snapdir": "File dialog/screenshot directory (synchronous)",
                    "exit": "Exit process",
                    "uiaclick/uiagoto/uiaget/uiascan/uiaset/uiawait": "UIA automation (executed on Python side, matches controls by Name/ClassName, not limited by Delphi pipe/thread)",
                    "uia.rclick/uia.dblclick/uia.hover/uia.drag/uia.wheel": "UIA mouse operations",
                    "uia.scroll/uia.scrollinto": "UIA scroll operations",
                    "uia.type/uia.key/uia.toggle": "UIA input operations",
                    "uia.select/uia.expand/uia.collapse/uia.invoke": "UIA list/tree operations",
                    "uia.find/uia.list": "UIA navigation/inspection",
                    "uia.close/uia.minimize/uia.maximize/uia.restore/uia.move/uia.resize/uia.state": "UIA window operations",
                    "uia.exists/uia.rect/uia.screenshot": "UIA properties/state",
                    "via:'uia'": "Routing field: add via:'uia' to click/goto/get/set/wait to use Python UIA execution instead (e.g. {\"cmd\":\"click\",\"target\":\"Open(&O)\",\"via\":\"uia\"})",
                },
            },
            "prepare": {
                "description": "Register the DaofyAutomation path in the Delphi global Library Search Path (registry). Do it once and any project can use DaofyAutomation without extra configuration.",
                "needs_auto_unit": False,
                "params": {},
                "effect": "Read Search Path from HKCU\\SOFTWARE\\Embarcadero\\BDS\\{version}\\Library\\{platform}; if tools/auto/ or tools/stacktrace/ is not present, append it. Affects both Win32 + Win64 platforms.",
            },
            "console": {
                "description": "Drive console program interaction through subprocess stdin/stdout. No Delphi-side changes required.",
                "needs_auto_unit": False,
                "params": {
                    "input": "Text sent to stdin",
                    "expect": "stdout regex pattern to wait for",
                    "timeout": "Timeout in seconds (default 30)",
                    "args": "Array of additional command-line arguments",
                },
            },
        },
        "planning_guide": {
            "principle": "Explicitly mark each step's phase (perceive/execute/verify), 'one step, one verification'",
            "prefer_order": ["RTTI calls (most stable)", "control-level goto+click (most common)", "coordinate-level move+click (compatibility mode)"],
            "failure_recovery": {
                "waitfor_timeout": "capture current state → analyze cause → retry or report",
                "click_error": "dumpstate to check Enabled/Visible → fall back to RTTI or report",
                "unexpected_dialog": "msgscan → msgclick(OK/Cancel) → capture new state",
                "rtti_exception": "fall back to goto+click operation",
            },
            "prompt_templates": (
                "delphi://coding-rules / get_coding_rules(section=\"automation\") provides 4 reusable prompt templates: "
                "F1=test planning template (from goal to step sequence), "
                "F2=single-step execution protocol (pre-perception→execute→wait→verify), "
                "F3=failure recovery template (diagnose→decide→recover→learn), "
                "F4=experience saving template (turn test results into experience)."
                "\nUsage: get_coding_rules(section=\"automation\") to get the full templates."
            ),
            "experience_optimization": (
                "Use the experience tool to achieve continuous self-evolution (see delphi://coding-rules / get_coding_rules(section=\"automation\")):"
                "\n1) Before testing: experience/search to retrieve historical experience for similar scenarios → adjust strategy"
                "\n2) During testing: when encountering failures, recover according to F3 and record learnings"
                "\n3) After testing: experience/save to save experience according to the F4 template (automatic deduplication)"
                "\n4) Periodically: experience/merge to merge similar experiences → experience/prune to eliminate low-value records"
            ),
        },
        "examples": [
            'automate_delphi(action="prepare")  # ← register the global search path before first use',
            'automate_delphi(action="list_tests", app_path="TestHost.exe")  # ← list registered test classes and methods',
            'automate_delphi(action="gui", app_path="App.exe", script={"test_name":"main-smoke","steps":[{"cmd":"goto","target":"TMainForm"},{"cmd":"capture","target":"main"}]})',
            'automate_delphi(action="gui", app_path="App.exe", stop_on_failure=true, script=[{"cmd":"rget","target":"StatusBar.Caption","assert_expr":"actual==\'OK\'"}])',
            'automate_delphi(action="gui", app_path="App.exe", script=[{"cmd":"listwnd"}])',
            'automate_delphi(action="console", app_path="Tool.exe", input="Y\\n", expect="Continue?", timeout=10)',
            'automate_delphi(action="console", app_path="Deploy.exe", input="\\n", expect="success", args=["--silent"])',
            'automate_delphi(action="test", app_path="App.exe", test_timeout=30, tests=[{"id":"add","className":"Tests.TCalculator","method":"Add","params":[1,2],"expected":"3"}])',
            'automate_delphi(action="test", app_path="App.exe", tests=[{"id":"exception","className":"Tests.TCalculator","method":"Parse","params":["bad"],"expected_exception":"EConvertError","expected_message":"invalid"}])',
            'automate_delphi(action="gui", app_path="App.exe", script={"test_name":"resilient","exception_filter":{"enabled":true,"on_exception":{"dialog":"close","focus_lost":"refocus"}},"steps":[{"cmd":"goto","target":"TMainForm"},{"cmd":"click","target":"btnRun"}]})',
            '# See get_coding_rules(section="automation") for a complete perceive-plan-execute-feedback loop example',
        ],
        "action_params": {
            "gui": {
                "description": "Drive GUI program automation testing through named pipes (requires linking the DaofyAutomation unit)",
                "required": ["app_path"],
                "optional": {
                    "script": "JSON script (file path, JSON string, step array, or full script object)",
                    "snapshots_dir": "Absolute path to screenshot output directory (optional, default docs/copyright/snapshots)",
                    "wait_timeout": "Timeout in seconds to wait for the Delphi pipe to be ready (default 10s)",
                    "keep_alive": "True=keep the process running after execution for later reuse",
                    "stop_on_failure": "True=stop executing subsequent dependent steps after the first failure (default true)",
                    "env": "Temporary environment variable dict",
                },
            },
            "console": {
                "description": "Drive console program interaction through subprocess stdin/stdout (no Delphi-side changes required)",
                "required": ["app_path"],
                "optional": {
                    "input": "Text sent to stdin",
                    "expect": "stdout regex pattern to wait for",
                    "timeout": "Timeout in seconds (default 30s)",
                    "args": "Array of additional command-line arguments",
                    "keep_alive": "True=keep the process running after execution for later reuse",
                    "env": "Temporary environment variable dict",
                },
            },
            "auto": {
                "description": "Automatic detection mode (PE header determines GUI vs Console)",
                "required": ["app_path"],
                "optional": {
                    "script": "JSON script",
                    "input": "Text sent to stdin",
                    "expect": "stdout regex pattern to wait for",
                    "timeout": "Timeout in seconds",
                    "keep_alive": "True=keep the process running after execution for later reuse",
                },
            },
            "prepare": {
                "description": "Register the DaofyAutomation path in the Delphi global search path (one-time setup)",
                "required": [],
                "optional": {},
            },
            "list_tests": {
                "description": (
                    "List test classes and methods already registered in TestHost. Returns each class's registered name, unit name, "
                    "method name, parameter signature (name+type), and return type, without grepping source code. "
                    "Requires the TestHost process to already be started (keep_alive=True) or automatically starts a new process."
                ),
                "required": ["app_path"],
                "optional": {
                    "visibility": "RTTI visibility filter (default public,published)",
                    "wait_timeout": "Timeout in seconds to wait for TestHost pipe to be ready (default 10s)",
                    "env": "Temporary environment variable dict",
                },
            },
            "test": {
                "description": "Batch execute RTTI tests — each case independently sends a run_tests command, restarts TestHost after timeout, and returns stable statistics and per-case results",
                "required": ["app_path", "tests"],
                "optional": {
                    "tests": (
                        "Test case list; each item supports id/name, target(control name) or className, method, params, "
                        "constructor_params, expected, expected_exception, expected_message, assert_expr, "
                        "visibility, timeout(override that case's timeout in seconds)."
                        "\n\nclassName lookup order (highest to lowest priority):"
                        "\n  1. RegisterTestClass registered name (e.g. 'Agent.EditEngineV3Test') — will not be trimmed by the linker"
                        "\n  2. TRttiContext.FindType fully qualified name (e.g. 'Tests.TCalculator') — requires RTTI discoverability"
                        "\n  3. FindClass (Delphi VCL class name) — only for TComponent-derived classes"
                        "\nRecommended: prefer the RegisterTestClass registered name (most stable); for RTTI-discoverable classes, use the fully qualified name."
                        "\nUse RegisterFixture when setup/teardown is needed."
                        "\n⚠️ The value passed in must be one of the above three, not the Delphi source class name (e.g. TEditEngineV3Test)"
                    ),
                    "visibility": "Global RTTI visibility filter (default public,published, can be overridden per test item; when testing private methods set private,protected,public,published)",
                    "wait_timeout": "Timeout in seconds to wait for TestHost pipe to be ready (default 10s)",
                    "test_timeout": "Default timeout in seconds for each test (default 30s; overridden by the test item's timeout). After timeout the process is automatically terminated, and the next case starts a new process",
                    "keep_alive": "True=keep the process running after execution (default true)",
                    "env": "Temporary environment variable dict",
                },
                "assert_modes": (
                    "The three assertion modes are mutually exclusive; each case can use only one:"
                    "\n  1. expected: Delphi-side exact string match (result.ToString = expected)"
                    "\n  2. expected_exception: Delphi-side exception match (when phase=test, exception class name+message)"
                    "\n  3. assert_expr: Python expression (variable actual is the return value string, e.g. \"actual == '3'\")"
                    "\n❌ Forbidden combination: assert_expr overrides Delphi-side assert fields, causing confusing result=PASS + assert=fail"
                ),
            },
        },
    },    "lazarus_compile": {
        "summary": "Lazarus/Free Pascal project compilation (lazbuild)",
        "description": "Lazarus/Free Pascal project compilation",
        "triggers": [
            "Compile Lazarus project, lazbuild, lpi, lpr, Free Pascal",
        ],
        "constraints": [
            "❌ Do not run lazbuild with bash/cmd",
        ],
        "workflow": "lazarus_compile(project_path=.lpi) → check result.status",
        "actions": {
            "compile": "Compile .lpi/.lpr project",
        },
        "action_params": {
            "compile": {
                "description": "Compile Lazarus project",
                "required": ["project_path"],
                "optional": {
                    "target_platform": "win32/win64, default win32",
                    "build_configuration": "Default/Release/Debug",
                    "timeout": "Timeout seconds, default 600",
                },
            },
        },
    },
    "lazarus_project": {
        "summary": "Lazarus project information query — parse .lpi file",
        "description": "Lazarus project information query",
        "triggers": [
            "View lpi project information, Lazarus unit list, FPC compiler options",
        ],
        "constraints": [],
        "workflow": "lazarus_project(project_path=.lpi) → info/units/options",
        "actions": {
            "info": "Project summary (name/main source file/unit count/search paths/compiler options)",
            "units": "Unit list (including IsPartOfProject)",
            "options": "Compiler options (CPU/OS/debug/optimization level)",
        },
        "action_params": {
            "info": {
                "description": "Get project summary",
                "required": ["project_path"],
                "optional": {},
            },
            "units": {
                "description": "Get unit list",
                "required": ["project_path"],
                "optional": {},
            },
            "options": {
                "description": "Get compiler options",
                "required": ["project_path"],
                "optional": {},
            },
        },
    },
    "lazarus_kb": {
        "summary": "Lazarus/FPC source code knowledge base — index and search LCL/FPC RTL source",
        "description": "Standalone Lazarus/FPC source code knowledge base. Automatically detects C:\\lazarus installation directory, indexes LCL, components, and FPC RTL source. Uses the same ZVec engine as the Delphi documentation KB.",
        "triggers": [
            "lazarus kb, FPC API, LCL docs, search lazarus source, lazarus function definitions",
        ],
        "constraints": [],
        "workflow": "lazarus_kb(action=build) → lazarus_kb(action=search, query=...)",
        "actions": {
            "build": "Auto-detect and index LCL / FPC RTL source",
            "search": "Search indexed source (query parameter required)",
            "stats": "Knowledge base statistics",
            "read": "Read specified source file (file_path parameter required)",
        },
        "action_params": {
            "build": {
                "description": "Build Lazarus/FPC source code knowledge base",
                "required": [],
                "optional": {},
            },
            "search": {
                "description": "Search Lazarus/FPC source",
                "required": ["query"],
                "optional": {
                    "top_k": "Max number of results (default 20, max 100)",
                    "content_type": "Filter by file type (e.g. pas/inc/pp)",
                },
            },
            "stats": {
                "description": "Knowledge base statistics",
                "required": [],
                "optional": {},
            },
            "read": {
                "description": "Read source file",
                "required": ["file_path"],
                "optional": {},
            },
        },
    },
    "lazarus_file": {
        "summary": "Lazarus/FPC file read/write — read/write(edits,auto-backup)/backup",
        "description": "Lazarus/FPC file read/write, reusing the shared file kernel. Supports only read / write(edits batch modifications) / backup. Automatic BOM encoding detection, auto-backup to __history before write.",
        "triggers": [
            "lazarus files, read lfm, modify lpi, edit lazarus source",
        ],
        "constraints": [
            "❌ Does not support grep/format/uses/encode/fix_garbled — these are Delphi-specific operations",
        ],
        "workflow": "lazarus_file(action=read, file_path=...) → modify → lazarus_file(action=write, file_path=..., edits=[...])",
        "actions": {
            "read": "Read file (BOM auto-detection)",
            "write": "Write file (edits batch modifications, auto-backup to __history)",
            "backup": "Manually create backup to __history",
        },
        "action_params": {
            "read": {
                "description": "Read file content",
                "required": ["file_path"],
                "optional": {},
            },
            "write": {
                "description": "Write file (edits batch modifications)",
                "required": ["file_path", "edits"],
                "optional": {
                    "encoding": "File encoding (if omitted, auto-detect BOM)",
                },
            },
            "backup": {
                "description": "Manually backup to __history",
                "required": ["file_path"],
                "optional": {},
            },
        },
    },
    "structured_content": {
        "summary": "Unified read/write/search/modify for structured documents — DFM/LFM/FMX/XML/JSON/MessagePack/ProtoBuf. Read/write by JSONPath path, auto-generate JSON Schema.",
        "description": "Unified read/write/search/modify for structured documents — DFM/LFM/FMX/XML/JSON/MessagePack/ProtoBuf. Read/write by JSONPath path, auto-generate JSON Schema.",
        "triggers": [
            "structured documents, DFM files, XML config, JSON data, MessagePack, ProtoBuf, read/write config files",
            "modify component properties, add components, search components, path query, JSON Schema generation",
        ],
        "constraints": [
            "❌ Cannot be used for unstructured text files (.pas/.dpr/.txt/.md)",
            "❌ ProtoBuf requires a .proto file or a compiled pb2 module first",
        ],
        "workflow": "structured_content(action=\"get_schema\", file_path=...) → view Schema → read/write by JSONPath path",
        "actions": {
            "read": "Read structured file, returns JSON / Schema / both. path parameter extracts a subtree, output controls return format.",
            "get_schema": "Generate JSON Schema for target file, helping LLM understand document structure for subsequent path construction.",
            "set": "Modify node value by JSONPath path. For example path='$.Form.Left' value='200'.",
            "search": "Search nodes by JSONPath path, supports wildcards (*), recursive descent (..), filter expressions ([?@.name=='Button1']).",
        },
        "action_params": {
            "read": {
                "description": "Read structured file as JSON / Schema / both",
                "required": ["file_path"],
                "optional": {
                    "path": "JSONPath path, default $ (root)",
                    "format": "Force format: dfm/lfm/fmx/xml/json/msgpack/protobuf (default detects from extension)",
                    "output": "Output format: json(default)/schema/both",
                    "proto_file": "In ProtoBuf mode, pass absolute path to .proto file",
                    "message_name": "In ProtoBuf mode, pass message name",
                },
                "examples": [
                    'structured_content(action="read", file_path="MainForm.dfm")',
                    'structured_content(action="read", file_path="config.json", path="$.database")',
                    'structured_content(action="read", file_path="data.msgpack", output="schema")',
                ],
            },
            "get_schema": {
                "description": "Generate JSON Schema for target file",
                "required": ["file_path"],
                "optional": {
                    "format": "Force format (default detects from extension)",
                    "proto_file": "In ProtoBuf mode, pass absolute path to .proto file",
                    "message_name": "In ProtoBuf mode, pass message name",
                },
                "examples": [
                    'structured_content(action="get_schema", file_path="MainForm.dfm")',
                    'structured_content(action="get_schema", file_path="config.xml")',
                ],
            },
            "set": {
                "description": "Modify node value by JSONPath path",
                "required": ["file_path", "path", "value"],
                "optional": {
                    "format": "Force format (default detects from extension)",
                    "proto_file": "In ProtoBuf mode, pass absolute path to .proto file",
                    "message_name": "In ProtoBuf mode, pass message name",
                },
                "examples": [
                    'structured_content(action="set", file_path="MainForm.dfm", path="$.Form.Left", value="200")',
                    'structured_content(action="set", file_path="config.json", path="$.debug", value="true")',
                ],
            },
            "search": {
                "description": "Search nodes by JSONPath path",
                "required": ["file_path"],
                "optional": {
                    "path": "JSONPath path, supports wildcards/recursive descent/filter expressions, default $",
                    "format": "Force format (default detects from extension)",
                    "proto_file": "In ProtoBuf mode, pass absolute path to .proto file",
                    "message_name": "In ProtoBuf mode, pass message name",
                },
                "examples": [
                    'structured_content(action="search", file_path="MainForm.dfm", path="$..Button1")',
                    'structured_content(action="search", file_path="MainForm.dfm", path="$.Form.*")',
                    'structured_content(action="search", file_path="MainForm.dfm", path="$..[?@.ClassName==\'TButton\']")',
                ],
            },
        },
    },
}

# Tool name list (keep order, used for list_tools and tool_help enum)
TOOL_NAMES: list = [
    "delphi_project",
    "delphi_kb",
    "delphi_file",
    "manage_component",
    "check_environment",
    "async_task",
    "package",
    "get_coding_rules",
    "code_hosting",
    "tool_help",
    "experience",
    "daofy_update",
    "automate_delphi",
    "generate_copyright",
    "delphi_rtti",
    "ocr",
    "lazarus_compile",
    "lazarus_project",
    "lazarus_kb",
    "lazarus_file",
    "structured_content",
]
# Rule: one-sentence purpose + hard constraints (rules that error if not followed)
TOOL_SHORT_DESC: dict = {
    "delphi_project": (
        "Delphi project lifecycle: compile/config/audit."
        " compile(compilation)/info(config view)/set(modify)/add_config/remove_config/"
        "add_source/remove_source/audit(static analysis 50+ rules)/ast(code skeleton)/runtime(registry check)/layout(UI layout audit)."
        " Only supports Delphi project files(.dproj/.dpr/.dpk)."
        " Manual dcc32/msbuild is prohibited."
    ),
    "delphi_kb": (
        "Search Delphi API/project code/docs."
        " search_type=class(class)/function(function)/semantic(semantic)/reference(reference)/unit(unit)/all."
        " kb_type=delphi(official)/project(project)/thirdparty(third-party)/document(document)/example(sample code)."
        " search_in=all(default)/delphi/project/thirdparty."
        " ⚠️ Delphi files must use delphi_file for read/write/search/regex match+replace; do not use built-in Read/Edit/Write/grep."
    ),
    "delphi_file": (
        "Delphi file-specific read/write entry: read/write(edits)/replace/insert/delete/format/backup/encode/uses."
        " When seeing .pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx/.groupproj, use this tool even if just reading."
        " Delphi files must use delphi_file; do not use built-in Read/Edit/Write/grep/apply_patch/PowerShell/Python."
        " Built-in tools and external writes can only be post-hoc fallback by edit guard, and cannot be the primary editing path."
        " 🚫 Multiple changes in the same file must be merged into one write(edits=[...])."
    ),
    "manage_component": (
        "DFM component management: create(generate DFM+code)/add(add component)/remove/modify(property). Automatically sync PAS."
    ),
    "check_environment": (
        "Diagnose build environment: check(check status)/detect(redetect compiler)/install(install pasfmt). Call before first compilation."
    ),
    "async_task": (
        "Manage background async tasks: start(start)/status(progress)/result(result)/list/cancel. For time-consuming operations such as knowledge base build."
    ),
    "package": (
        "Compile and install Delphi component packages: install(compile and install)/list(list installed)."
    ),
    "get_coding_rules": (
        "Get coding rules (Delphi/Lazarus). Must call before writing/modifying code."
        " language=delphi(default) or lazarus. See coding-rules/{language}/ for specific rules by language."
    ),
    "code_hosting": (
        "Git operations: status/diff/show/log/add/commit/fetch/pull/branch/switch/merge/restore/unstage/stash/tag/push/clone"
        " + platform API(issue/PR/MR/release)."
        " Do not use bash to run git."
    ),
    "tool_help": (
        "Get complete help docs for any tool (parameters/examples/triggers). Call this first when usage is unclear."
    ),
    "experience": (
        "Experience memory: save(save,auto-deduplicate)/search/get/list/update/merge/prune/delete/rebuild_embedding."
        " Save experience after solving an AI problem, and reuse it directly for similar problems next time."
    ),
    "daofy_update": (
        "Check and update Daofy version: check(quick check)/update(git pull)/version(current version)."
    ),
    "automate_delphi": (
        "Delphi automated testing: gui(named pipe GUI operations+screenshots)/console(stdin/stdout interaction)/auto(auto-detect)/prepare(register global search paths)/test(batch RTTI tests)."
        " gui requires linking DaofyAutomation(uses Vcl/Fmx.DaofyAutomation); console requires no modification; prepare is one-time setup."
        " Supports keep_alive to reuse processes. cmd: formsum/dumpstate/capture/goto/click/type/rget/rinspect(supports visibility parameter)/rcall/rset/waitfor/msgscan/listwnd/exit/run_tests/callgraph/callgraph_diff/callgraph_path/callgraph_impact/callgraph_select_tests/callgraph_failure_diag/callgraph_boundary_check/callgraph_refactor_check/callgraph_orphan_candidates/callgraph_explain_exception. callgraph requires additional uses DaofyAutomation.CallGraph, supports edge_limit/include_prefixes/category; callgraph_path supports source/target/max_depth/max_paths/include_prefixes; callgraph_diff defaults to compare_by=name, optional addr/full, save_as/baseline_path limited to snapshots_dir."
    ),
    "generate_copyright": (
        "Generate software copyright documents: generate(source code+manual)/validate(check config)/audit(audit draft). Browser PDF rendering+automatic validation."
    ),
    "delphi_rtti": (
        "Delphi RTTI bridge: discover(scan capabilities)/call(invoke method)/guide(usage guide)."
        " Three-step method: discover→call, no UI operations needed. Requires linking DaofyAutomation."
    ),
    "ocr": (
        "Image analysis: recognize(text recognition)/detect(text boxes)/diff(screenshot comparison)/color(color analysis)/match(icon matching)/status(model status)."
        " Pure ONNX+OpenCV+Pillow. diff requires two screenshots; match requires a template image; color supports region analysis."
    ),
    "lazarus_compile": (
        "Lazarus/Free Pascal project compilation (lazbuild)."
        " project_path(.lpi/.lpr) is required. Supports target_platform(win32/win64)/build_configuration/timeout."
    ),
    "lazarus_project": (
        "Lazarus project information query — parse .lpi file."
        " action=info(default, project summary)/units(unit list)/options(compiler options)."
    ),
    "lazarus_kb": (
        "Lazarus/FPC source code knowledge base."
        " build(build)/search(search)/stats(statistics)/read(read source)."
        " Automatically detects LCL/FPC RTL source under C:\\lazarus."
    ),
    "lazarus_file": (
        "Lazarus/FPC file read/write."
        " read(read)/write(edits modify, auto-backup to __history)/backup(manual backup)."
        " Only read/write/backup; does not support Delphi-specific operations such as grep/format/uses."
    ),
    "structured_content": (
        "Unified read/write/search/modify for structured documents. Formats: DFM/LFM/FMX/XML/JSON/MessagePack/ProtoBuf."
        " read(read as JSON or Schema)/get_schema(generate JSON Schema)/set(modify by JSONPath path)/search(path search)."
        " Auto-detect format (supports .dfm/.lfm/.fmx/.xml/.json/.msgpack/.proto/.pb)."
        " ProtoBuf requires additionally specifying proto_file and message_name."
    ),
}