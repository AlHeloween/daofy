# Daofy Tutorial — Recording Demo Script

**Total duration**: approx. 45-50 minutes  
**Target audience**: Delphi developers (familiar with basic Delphi development, new to MCP/AI-assisted programming)  
**Recommended recording tools**: OBS Studio / Bandicam / ScreenFlow  
**Recommended screen resolution**: 1920×1080 or higher  
**Editing suggestion**: Time-consuming steps such as installation and knowledge base building can be sped up or cut/skipped

---

## Part 1: Opening & Project Introduction (approx. 2 minutes)

### Visuals
- Show the GitHub project page full screen: <https://github.com/chinawsb/daofy>
- Cut to PPT / project README

### Narration Script

Hello everyone, welcome to this tutorial.

Today I'll introduce a very practical tool—**Daofy**.

MCP stands for Model Context Protocol, an open protocol introduced by Anthropic. It allows AI assistants (such as Claude, CodeArts Agent, etc.) to interact directly with your local development environment.

Simply put: **After installing Daofy, you can compile Delphi projects, search VCL/FMX source code, look up API documentation, and even format code directly in the AI assistant's chat conversation.**

No need to switch back and forth between AI and the IDE. With one instruction, the AI calls MCP tools to do it for you.

Let's see what this project can do:

- ✅ **Compile Delphi projects** — supports .dproj / .dpr / .pas files
- ✅ **Knowledge base search** — built-in Delphi RTL/VCL/FMX source code index, supports class name, function name, and semantic search
- ✅ **Project knowledge base** — automatically indexes code and third-party libraries in your project
- ✅ **Code formatting** — integrates pasfmt, one-click formatting of Delphi source code
- ✅ **Coding rules lookup** — retrieves project coding rules so AI-generated code matches your style
- ✅ **Component package installation** — compiles and installs .dpk component packages into the IDE

OK, let's start with installation.

---

## Part 2: AI Automatic Installation & Configuration (approx. 4 minutes)

> **Design idea**: The entire installation process does not show terminal operations; everything is completed in the AI chat interface. The user only needs to say one sentence or paste one prompt, and the AI Agent handles everything automatically.

### Scenario 2.1 — User Asks AI to Install

#### Visuals
- Show the AI assistant chat interface full screen (such as Claude Desktop / CodeArts Agent)
- The user enters the installation instruction

#### AI Conversation Demo

```
User: Help me install Daofy
```

Or paste the installation prompt from the README:

```
User: Please install Daofy by following these steps:

[] Check for and install Git/Python 3.10-3.14/7-Zip (during installation, prefer domestic mirror sources to speed up downloads)

[] Install https://github.com/chinawsb/daofy.git

[] After installation, verify the result and help me configure the current client
```

#### Narration

Many users new to MCP find configuration troublesome—they have to install Python, clone the project, set up a virtual environment, and write JSON configuration files.

But in this tutorial, **none of this needs to be done manually**.

You only need to enter one instruction in the AI assistant's chat box: "Help me install Daofy".

After receiving the instruction, the AI Agent will:
1. Check whether Python and Git are installed on your computer
2. If not, download and install them automatically
3. Clone the GitHub repository
4. Create a virtual environment and install dependencies
5. Run the installation script to automatically detect and configure your AI client

All operations are completed automatically by the AI in the conversation. You only need to watch it execute step by step, and then answer "yes" or "continue" at nodes that require confirmation.

---

### Scenario 2.2 — AI Executes Installation Step by Step (picture-in-picture terminal display)

#### Visuals
- Main view: AI chat interface, with AI outputting installation progress
- **Picture-in-picture (small window)**: real-time display of the terminal commands and output the AI is executing, so viewers can see what is actually happening behind the scenes

#### AI Conversation Output (illustrative)

```
AI: Starting Daofy installation...

Step 1: Checking environment...
  ✅ Git is installed (2.47.0)
  ✅ Python is installed (3.12.4)
  ⚠️ 7-Zip not detected, downloading and installing automatically... Done

Step 2: Cloning project...
  ✅ Cloned from github.com/chinawsb/daofy

Step 3: Configuring virtual environment and installing dependencies...
  ✅ Virtual environment created
  ✅ Dependencies installed (using Tsinghua mirror for acceleration)

Step 4: Configuring AI clients...
  🔍 Detecting installed AI assistants...
  ✅ Detected: Claude Desktop, Trae
  ✅ Claude Desktop configured automatically
  ✅ Trae configured automatically

Installation complete! 🎯
Now you can ask me to help you compile Delphi projects.
```

#### Narration

After receiving the instruction, the AI executes the installation steps in order.

In the picture-in-picture window, you can see the AI actually executing various terminal commands—checking the environment, cloning the repository, installing dependencies. But for viewers, it's enough to focus on the output in the AI chat interface; each step has clear progress and results.

The most impressive part is step 4: the AI automatically detects which AI clients are installed on your computer—Claude Desktop, Trae, CodeArts Agent, Cursor, Windsurf, Tongyi Lingma, Doubao, Kimi, and more than a dozen others—and then automatically writes the MCP configuration. **No manual editing of JSON files is needed at all.**

---

### Scenario 2.3 — Verify Installation Result

#### Visuals
- Continue with the AI chat interface

#### AI Conversation Demo

```
User: Check whether the installation succeeded
```

- AI calls the `check_environment(action="check")` tool
- Display the returned result: compiler version, path, available platforms

#### Narration

After installation is complete, enter "Check whether the installation succeeded".

The AI calls the `check_environment` tool and automatically detects Delphi compilers from the Windows registry. If everything is normal, you will see the Delphi version number, dcc32 path, and supported compilation platforms—**fully automatic, zero configuration**.

At this point, the entire installation and configuration process takes less than two minutes, without ever leaving the AI chat box.

---

## Part 3: Environment Detection & First Launch (approx. 2 minutes)

### Scenario 3.1 — Start MCP Server and Check Compiler

#### Visuals
- Enter instructions in the AI assistant chat interface
- **Use split screen or picture-in-picture to show the AI assistant interface**

#### AI Conversation Demo

```
User: Check the Delphi compilation environment
```

- AI calls the `check_environment(action="check")` tool
- Display the returned result: compiler version, path, available platforms, etc.

#### Narration

After starting the AI assistant configured with the MCP Server, the first thing we do is check the compilation environment.

Enter "Check the Delphi compilation environment", and the AI calls the `check_environment` tool, automatically detecting installed Delphi compilers from the Windows registry.

You will see the detected Delphi version, dcc32 compiler path, and supported compilation platforms. **No manual configuration is required throughout.**

---

### Scenario 3.2 — View Knowledge Base Statistics

#### AI Conversation Demo

```
User: View Delphi knowledge base statistics
```

- AI calls `delphi_kb(action="stats")`
- Display results: number of files, classes, and functions in the Delphi source knowledge base

#### Narration

Next, let's look at the knowledge base status. Enter "View Delphi knowledge base statistics", and the AI displays the scale of the built-in Delphi source knowledge base.

This knowledge base has already been prebuilt with source code indexes for Delphi's official RTL, VCL, and FMX—containing indexes of over **160,000 files, 160,000 classes, and 300,000 functions**, covering almost the complete range of Delphi versions.

---

## Part 4: Core Feature Demonstration (approx. 22 minutes)

### Scenario 4.1 — Search Delphi API Definitions (approx. 2 minutes)

#### AI Conversation Demo

```
User: Help me look up the class definition of TStringList
```

- AI calls `delphi_kb(query="TStringList", search_type="class", kb_type="delphi")`
- Display search results: class inheritance chain, unit location, key methods

#### Narration

First, let's look at the knowledge base search feature—this is what everyone uses most in daily work.

For example, if I want to look up the class definition of `TStringList`, I just enter:

The AI searches the Delphi source knowledge base and returns complete information about `TStringList`: it inherits from `TStrings` → `TPersistent` → `TObject`, is defined in the `System.Classes` unit, and what its key methods are.

---

### Scenario 4.2 — Search Functions (approx. 1 minute)

#### AI Conversation Demo

```
User: Find the Split string splitting function in Delphi
```

- AI calls `delphi_kb(query="Split", search_type="function", kb_type="delphi")`
- Display search results: function signature, parameter descriptions, unit location

#### Narration

Finding functions is just as simple.

For example, if I want to find a string splitting function, I enter "Find the Split function", and the AI returns matching functions such as `System.StrUtils.SplitString`, including parameter signatures and usage descriptions.

Note that here we recommend searching with English function names, which is much more accurate than Chinese semantic search.

---

### Scenario 4.3 — Semantic Search Discovers Hidden APIs (approx. 2 minutes)

> **Power point**: You don't even know the API name; describe your need in natural language, and the AI finds what you want among 300,000+ functions.
>
> ⚠️ **Prerequisite**: Semantic search requires building the embedding vector index first: `delphi_kb(action="build_embedding", async_mode=true)`. If not built, semantic mode degrades to inverted index search, and the effect may be less than expected. Please build it in advance before recording.

#### AI Conversation Demo

```
User: Does Delphi have a feature that can compare whether two JSON objects have the same structure?
     Not a string comparison, but a semantic comparison that ignores key order.
```

- AI calls `delphi_kb(query="JSON object deep compare structural equality", search_type="semantic", kb_type="delphi")`
- Matches `System.Json.TJSONObject.Equals` and `System.Generics.Defaults.TEqualityComparer` among 300,000 functions
- AI further calls `delphi_kb(query="TJSONObject.Equals", search_type="function", kb_type="delphi")` to confirm the signature
- Display result: `TJSONObject.Equals` indeed implements value comparison rather than reference comparison

```
User: Help me find another feature—when reading a large text file, process it line by line, but I don't want to load the entire file into memory at once.
```

- AI calls `delphi_kb(query="read large text file line by line streaming", search_type="semantic", kb_type="delphi")`
- Search results: `System.Classes.TStreamReader.ReadLine`, `System.IOUtils.TFile.ReadAllLines` (but it loads everything)
- AI recommends the `TStreamReader` approach and shows usage

#### Narration

This scenario demonstrates **the real power of semantic search**.

Earlier we demonstrated exact search—you know the name `TStringList` or `Split`, so you search directly. But in real-world development, the problem you often encounter is: **"Does Delphi have a feature that does X?"**—you don't even know what the API is called.

For example, "compare whether two JSON objects are the same"—if you use the `=` operator to compare two `TJSONObject`s, it compares reference addresses. What you actually want is value comparison. But you don't know what this API is called, and you're not even sure whether Delphi provides it.

At this point, you describe your need in natural language, and the AI performs semantic matching in a knowledge base of **300,000 functions**, finding `TJSONObject.Equals`—it indeed overrides the `Equals` method to do value comparison.

Another example: "read a large file line by line, don't load it all into memory at once." Semantic search can distinguish `TFile.ReadAllLines` (loads all) from `TStreamReader.ReadLine` (streaming read) and give the correct recommendation.

This is the combined power of a 300,000-function Delphi KB + semantic search—**you don't know the name, but you describe the need, and the AI finds it for you**.

---

### Scenario 4.4 — Knowledge Base-Driven Complex Code Generation (approx. 3 minutes)

> **Power point**: AI searches the KB to confirm API signatures → generates code → compiles successfully on the first try. This is especially powerful for libraries with many parameters like FireDAC.

#### AI Conversation Demo

```
User: Help me write a SQLite database management unit using FireDAC components.
      Requirements:
      1. Support connection configuration (file path, pool size, timeout)
      2. Connect / Disconnect methods
      3. Execute method to execute SQL, with parameter binding support
      4. Query method that returns a dataset
      5. TestConnection method
      Follow the project coding rules; go look up the rules first.
```

##### Step 1: Get Coding Rules

- AI calls `get_coding_rules(section="writing")`

##### Step 2: Search the KB to Confirm API Signatures (critical!)

- AI calls `delphi_kb(query="TFDConnection", search_type="class", kb_type="delphi")` → understand properties and methods
- AI calls `delphi_kb(query="TFDQuery", search_type="class", kb_type="delphi")` → understand SQL assignment and parameter binding
- AI calls `delphi_kb(query="TFDPhysSQLiteDriverLink", search_type="class", kb_type="delphi")` → confirm driver link usage
- AI calls `delphi_kb(query="TFDConnection.Params", search_type="function", kb_type="delphi")` → confirm parameter configuration method
- **(Picture-in-picture: API signature snippets the AI found in the KB)**

##### Step 3: Generate Code

- AI combines: coding rules + API signatures found in the KB + requirements → generates `DatabaseManager.pas`
- Code includes: TDatabaseConfig record, TDatabaseManager class, complete try/finally protection
- **(Picture-in-picture: file being generated in real time in VS Code)**

##### Step 4: Compile and Verify

- AI calls `delphi_project(action="compile", project_path="DatabaseManager.pas")` → passes on first try ✅

#### Narration

The earlier INI read/write example was relatively simple. This time let's do something truly challenging—**connecting to SQLite with FireDAC**.

FireDAC's parameter system is very large: `TFDConnection`'s driver selection, `Params` key-value configuration, `TFDQuery`'s SQL assignment and parameter binding, driver link creation... When writing this code by hand, you usually have to consult help or copy old code.

But the AI's approach is completely different:

**Step 1**: Get the coding rules and determine the style.

**Step 2, also the key**—the AI does not write blindly from memory; it calls knowledge base searches for the class definitions of `TFDConnection`, `TFDQuery`, and `TFDPhysSQLiteDriverLink` to **confirm the real API signatures**. How many parameters does the constructor have? What are the property names? What are the return types? All confirmed from the source KB.

**Step 3**: Combine the rules + requirements + retrieved API definitions to generate `DatabaseManager.pas`. Note how it handles resource release—create in `Create`, release in `Destroy`, and correct pairing of `Connect/Disconnect`.

**Step 4**: Compile and verify; it passes on the first try.

The key is the process of **"first search the KB to confirm the API, then write code"**—the generated code is not guessed from "AI memory", but based on real Delphi source definitions. For libraries with many parameters such as FireDAC, Indy, and REST, this is ten times faster than manually flipping through help documentation.

---

### Scenario 4.5 — Compile a Delphi Project (approx. 2 minutes)

#### AI Conversation Demo

```
User: Compile the current project, Debug mode, Win32 platform
```

- AI calls `delphi_project(action="compile", project_path="Project1.dproj", build_configuration="Debug", target_platform="win32")`
- Display compilation process output: build events, compilation parameters, compilation result

#### Narration

Next is the most core feature—compiling projects.

In the AI chat, enter "Compile the current project, Debug mode, Win32 platform".

The AI automatically finds the .dproj project file in the current directory and calls MSBuild or the dcc32 compiler to compile. The entire compilation process is output in real time in the chat window, including pre-build events, compilation parameters, and the final compilation result.

If compilation fails, the AI automatically analyzes the error messages and gives fix suggestions.

---

### Scenario 4.6 — Single-File Syntax Check (approx. 1 minute)

#### AI Conversation Demo

```
User: Check the syntax of Unit1.pas
```

- AI calls `delphi_project(action="compile", project_path="Unit1.pas")`
- Display syntax check result

#### Narration

If you only want to check the syntax of a single file rather than compile the entire project, it's also very simple.

Enter "Check the syntax of Unit1.pas", and the AI directly compiles the file with dcc32 for a syntax check, quickly reporting whether there are syntax errors.

---

### Scenario 4.7 — Code Audit + Gitea Defect Closed Loop (approx. 4 minutes)

> **Power point**: From audit to ticket to fix to close, the entire chain is completed in one MCP tool without leaving the AI conversation.

#### AI Conversation Demo

##### Phase 1: Code Audit

```
User: Review the code quality of review-demo/LegacyData.pas,
      compare it against the project coding rules, and output a review report
```

- AI calls `get_coding_rules(section="review")` — get audit dimensions and standards
- AI analyzes the code line by line and checks each item against the coding rules:

```
📋 Review Report — LegacyData.pas
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 [Critical] ExportData — Resource leak risk
  Line 26: No try/finally protection after TStringList.Create
  If SaveToFile throws an exception, LFile will never be Freed
  Suggestion: Wrap with try/finally

🔴 [Critical] ProcessItems — Deleting inside a loop causes skipped items
  Line 82: Executing AItems.Delete(I) inside a for loop
  After deletion, subsequent elements shift forward, and I++ will skip an element
  Suggestion: Change to reverse iteration: for I := Count-1 downto 0

🟡 [Warning] CalculateTotal — Magic numbers
  Line 62: Loop upper limit 10 should be defined as a constant
  Line 64: Factor 1.5 should be defined as a constant
  Line 66: Threshold 100 should be defined as a constant
  Line 68: Discount rate 0.95 should be defined as a constant

🟡 [Warning] GetUserCount — Logic error
  Line 49: LCount is assigned inside the try block
  Line 53: Returns LCount after LFile has been freed in finally
  The current code is correct, but the pattern is dangerous — easy to make mistakes when modifying
  Suggestion: Assign directly to Result inside the try block

🔵 [Suggestion] ExportData — Unused variable
  Line 24: LValue is declared but used only once
  Suggestion: Inline 'data1;data2;data3' directly
```

##### Phase 2: One-Click Create Gitea Issue

```
User: Create the critical issues as Gitea tickets, connect to https://code.qdac.cc:3000,
      repository myteam/demo-project
```

- AI calls `code_hosting(platform="gitea", action="create_token", base_url="https://code.qdac.cc:3000", username="...", password="...")` → get API Token (first use)
  ```
  ✅ Token created successfully
    Value: 93f2c9e8...a083
  ```

- AI calls `code_hosting(platform="gitea", action="init_labels", base_url="...", token="...", repo="myteam/demo-project")`
  → initialize the four-dimensional label system (can be executed repeatedly without creating duplicates)
  ```
  ✅ Label initialization complete
    Added: 18 | Skipped (existing): 18 | Total: 18
    Groups: Priority(4) Review(4) Status(5) Type(5)
  ```

- AI calls `code_hosting(platform="gitea", action="create_issue", base_url="...", token="...", repo="myteam/demo-project",
     title="LegacyData.pas 代码质量审计问题",
     body="""## 发现的问题

### 🔴 严重
1. 资源泄漏风险 — ExportData:26
   TStringList.Create 没有 try/finally 保护
2. 循环内删除导致跳项 — ProcessItems:82

### 🟡 警告
3. 魔法数值 — CalculateTotal:62-68
4. 逻辑错误风险 — GetUserCount:49-53""",
     label_names=["类型/缺陷", "优先级/高", "状态/待确认"])`
  ```
  ✅ Ticket created
    Number: #42 | Status: open
    Labels: Type/Defect, Priority/High, Status/To Confirm
    URL: https://code.qdac.cc:3000/myteam/demo-project/issues/42
  ```

##### Phase 3: Fix the Code

```
User: Fix the code according to the audit suggestions
```

- AI reads the `LegacyData.pas` source code
- AI fixes each item:
  - ExportData: add try/finally wrapping
  - ProcessItems: change to reverse iteration
  - CalculateTotal: replace magic numbers with constant definitions
  - GetUserCount: simplify the logic
  - ExportData: remove the unused LValue variable
- AI calls `delphi_project(action="compile", project_path="review-demo/LegacyData.pas")` — compile and verify the fixed code

##### Phase 4: Commit the Fix and Close the Issue

```
User: Commit the fix, link the commit in the issue, and close it
```

- AI calls `code_hosting(action="git_add", work_dir=".", files=["review-demo/LegacyData.pas"])`
- AI calls `code_hosting(action="git_commit", work_dir=".", commit_message="fix: resolve code audit issues in LegacyData.pas

- Add try/finally guard to prevent resource leak
- Fix loop index skipping on Delete
- Replace magic numbers with constants
- Clean up unused variable")`
  ```
  ✅ Commit successful
    Hash: a1b2c3d4e5f6
    Message: fix: resolve code audit issues in LegacyData.pas
  ```

- AI calls `code_hosting(platform="gitea", action="add_comment", base_url="...", token="...", repo="myteam/demo-project",
     issue_number=42, body="已在 commit a1b2c3d4 中修复所有 5 个问题。")`
  ```
  ✅ Comment added (ID: 14203)  Issue: #42
  ```

- AI calls `code_hosting(platform="gitea", action="close_issue", base_url="...", token="...", repo="myteam/demo-project",
     issue_number=42, comment_body="已在 a1b2c3d4 中修复，编译通过 ✅")`
  ```
  ✅ Issue #42 closed
    URL: https://code.qdac.cc:3000/myteam/demo-project/issues/42
    Close note: 已在 a1b2c3d4 中修复，编译通过 ✅
  ```

##### Phase 5: Verify the Closed Loop

```
User: Check the closed issues and confirm the fix record
```

- AI calls `code_hosting(platform="gitea", action="list_issues", base_url="...", token="...", repo="myteam/demo-project", state="closed")`
  ```
  📋 1 issue total (gitea, closed):
    #42 [closed] LegacyData.pas code quality audit issues  Type/Defect, Priority/High, Status/Closed
  ```

#### Narration

This scenario demonstrates the complete closed loop of **code audit → ticket tracking → fix → close**, and it is also a concentrated expression of the unified `code_hosting` tool.

The whole process is divided into five phases:

**Phase 1 — Audit**: `get_coding_rules` retrieves the rules → line-by-line review → output a structured report (with line numbers, severity levels, and fix suggestions)

**Phase 2 — Issue creation**: four actions of `code_hosting` connect together:
1. `create_token` → get an API access token (only needed the first time)
2. `init_labels` → initialize four-dimensional labels; mutually exclusive within the same scope
3. `create_issue` → create an issue, automatically matching label IDs by name
4. The returned issue link can be opened directly in a browser

**Phase 3 — Fix**: the AI modifies the source code item by item according to the audit suggestions. Each change targets a specific line number, and after modification it compiles to verify.

**Phase 4 — Close**: after the fixed code is committed via `git_commit`, it records the commit hash in the issue via `add_comment`, then closes it with `close_issue`. **The association between the commit and the issue is preserved in Gitea's comments**, so future developers can trace the fix history of each problem.

**Phase 5 — Verify**: use `list_issues` to filter by status and confirm the issue has been correctly closed, with the label automatically switched to "Status/Closed".

Key point: **all operations are completed through one `code_hosting` tool**, with different action parameters switching the operation type. From discovering the problem to fixing and closing it, the entire lifecycle never leaves the AI chat box. This is the power of the MCP protocol + unified tool interface.

---

### Scenario 4.8 — Search Project Code & Reference Lookup (approx. 2 minutes)

#### AI Conversation Demo

```
User: Search the project for the TfrmMain class
```

- AI calls `delphi_kb(query="TfrmMain", kb_type="project", search_type="class")`
- Display search results

```
User: See which units in the project reference Vcl.Forms
```

- AI calls `delphi_kb(query="Vcl.Forms", kb_type="project", search_type="reference")`
- Display the reference list

#### Narration

The project knowledge base is another very practical feature. The first time you search project code, the AI automatically builds the project knowledge base, indexing all source code and third-party libraries in your project.

Enter "Search the project for the TfrmMain class", and the AI looks up the definition location of this class in the project knowledge base.

If you want to know "which units reference Vcl.Forms", use reference search, and the AI lists all unit files that use Vcl.Forms. This is especially useful during refactoring or when assessing the impact scope of a change.

---

### Scenario 4.9 — Multi-File Refactoring (approx. 2 minutes)

#### AI Conversation Demo

```
User: I want to replace all TStringList in the project with TArray<String>.
      First check which places use TStringList and assess the impact scope.
```

- AI calls `delphi_kb(query="TStringList", kb_type="project", search_type="reference")` to find references
- Display the reference list: which files and which lines use TStringList
- AI lists the impact assessment: involves X files, Y references, Z units

```
User: The impact is not big. Start refactoring. Replace them file by file with TArray<String>,
      and adjust the related method calls.
```

- AI edits and modifies files one by one
- After each modification, it calls `delphi_project(action="compile", project_path="当前文件.pas")` for a syntax check
- After all modifications are complete, it calls `delphi_project(action="compile", project_path="项目.dproj")` for full project compilation verification, ensuring cross-file type references are correct
- After compilation passes, it calls `delphi_file(action="format")` to format the code
- Display confirmation that final compilation passed

#### Narration

The next scenario demonstrates **multi-file refactoring**—also a high-value scenario for AI-assisted development.

For example, I want to replace all uses of `TStringList` in the project with `TArray<String>`. This is a change spanning multiple files.

Step 1, **check references to assess impact**. After entering the instruction, the AI first calls `delphi_kb` reference search to find all files and locations that use `TStringList`, and lists an impact checklist—how many files and how many references are involved. This lets you know how large the change is before you start.

After confirming the impact is manageable, step 2, **execute the refactoring**. The AI modifies files one by one, compiling after each file to ensure no new errors are introduced.

After all changes are complete, it formats the code uniformly. The entire refactoring process is executed and verified by the AI. **You only need to make decisions—whether to change and what to change—while the dirty work is left to the AI**.

This is the chemical effect produced by reference lookup + project knowledge base + compilation verification working together.

---

### Scenario 4.10 — Code Formatting & Automatic Backup (approx. 2 minutes)

> **Power point**: Automatically creates a `__history` version backup before formatting, so you can roll back at any time. No fear of breaking things.

#### AI Conversation Demo

```
User: Format the code in refactor-demo/DataProcessor.pas
```

##### Step 1: Automatic Backup

- AI calls `delphi_file(action="format", file_path="DataProcessor.pas", backup=true)`
- pasfmt automatically executes the backup logic before formatting:
  ```
  ✅ Backup file created: DataProcessor.pas.__history\DataProcessor.pas.~1~
  ```

##### Step 2: Formatting

- pasfmt performs formatting and displays the diff:
  ```diff
  - for I := 0 to ALines.Count - 1 do begin
  + for I := 0 to ALines.Count - 1 do
  + begin
  ```

##### Step 3: View the Backup

```
User: Let me see the backup file
```

- AI lists the contents of the `__history` directory:
  ```
  DataProcessor.pas.~1~  (2026-05-15 09:00:00, 1.3 KB)
  ```

```
User: Compare the backup and the current file
```

- AI displays a `diff` comparison of the changes before and after formatting

```
User: If I'm not satisfied with the formatting result, help me restore to the backup version
```

- AI copies the backup file back to the original location, and restoration is complete

#### Narration

Code formatting and refactoring have a worrying question—"What if it breaks?"

`delphi_file` (formerly `file_tool`, the old name is still compatible) has a built-in automatic backup mechanism. By default, `backup=true`. Before performing any write, it creates a `__history` folder in the same directory as the source file and saves a versioned backup.

The backup file naming rule is **exactly the same as Delphi IDE's built-in History mechanism**—`filename.~version~`. If you format multiple times, the version number automatically increments: `~1~`, `~2~`, `~3~`...

Any time you feel a change is wrong, you can ask the AI to view backup files, compare differences, or even restore directly from the backup.

This mechanism is not only effective during formatting—**the AI backs up before modifying code in any operation, including refactoring and fixing compilation errors**, ensuring your source code is safe.

---

### Scenario 4.11 — How Coding Rules Affect AI Behavior (approx. 3 minutes)

> **Power point**: The same requirement, with a different set of coding rules, produces completely different code styles from the AI. This proves that coding rules truly control AI behavior.

#### AI Conversation Demo

```
User: Write a string utility unit for me, including Join and Split methods.
      Use demo-project's coding rules first.
```

##### Rule Set 1: Modern Rules (demo-project/CODING_RULES.mdc)

- AI calls `get_coding_rules(project_path="demo-project/DemoApp.dproj")`
- Retrieved rule summary:
  ```
  Type names: T + PascalCase  Variables: L + PascalCase  Parameters: A + PascalCase
  Indent: 2 spaces       begin: on a new line    Exceptions: specific types
  ```
- Code generated by AI:
  ```delphi
  unit StringUtils;

  interface

  type
    TStringUtils = class
    public
      class function Join(const AStrings: TArray<string>;
        const ASeparator: string): string; static;
      class function Split(const AText, ASeparator: string): TArray<string>; static;
    end;

  implementation

  { TStringUtils }

  class function TStringUtils.Join(const AStrings: TArray<string>;
    const ASeparator: string): string;
  var
    I: Integer;
  begin
    // ...
  end;
  ```

```
User: Now switch to the legacy project's coding rules and generate it again.
```

##### Rule Set 2: Legacy Project Rules (legacy-project/CODING_RULES.mdc)

- AI calls `get_coding_rules(project_path="legacy-project/LegacyApp.dproj")`

  (reads legacy-project/CODING_RULES.mdc, which contains rules such as Hungarian naming, 4-space indentation, and trailing begin)

  (or directly specify the rule file path—the AI reads another CODING_RULES file)

- Retrieved rule summary:
  ```
  Type names: camelCase without T prefix  Variables: Hungarian notation   Parameters: camelCase without prefix
  Indent: 4 spaces             begin: at end of line      Exceptions: catch-all except Exception
  ```
- Code generated by AI:
  ```delphi
  unit string_utils;

  interface

  type
    StringUtils = class
    public
      class function join(const arrStrings: array of string;
        const separator: string): string; static;
      class function split(const text, separator: string): TArray<string>; static;
    end;
  ```

##### Side-by-Side Comparison

- **Split-screen display** of the two code snippets, marking the differences:

| Dimension | Modern rules | Legacy project rules |
|------|----------|-----------|
| Type names | `TStringUtils` | `StringUtils` |
| Method names | `Join`, `Split` | `join`, `split` |
| Parameter names | `AStrings`, `ASeparator` | `arrStrings`, `separator` |
| Indent | 2 spaces | 4 spaces |
| begin | on a new line | at end of line |
| Unit name | `StringUtils` | `string_utils` |

#### Narration

Earlier we looked at coding rules lookup—but its real value is: **rules are not decoration; they actually change the AI's output behavior.**

This comparison experiment illustrates the point well:

The same requirement—"write a string utility unit including Join and Split methods." With a different set of CODING_RULES, the AI generates **two completely different styles of code**.

The left side is modern rules: `T`-prefixed type names, `A`-prefixed parameters, `L`-prefixed variables, 2-space indentation, `begin` on a new line.

The right side is legacy project rules: type names without prefixes, Hungarian notation, 4-space indentation, `begin` at the end of the line, and even the unit name becomes underscore style.

**Coding rules are not decoration—they truly control the AI's behavior.**

This means:
- Taking over a legacy project? Write the project's original coding rules into CODING_RULES.mdc, and AI-generated code automatically matches the project style without looking out of place
- Does the team have strict code review standards? Write the review rules in, and the AI automatically avoids red lines when generating code
- New people joining the team? No need to repeatedly emphasize the rules; the AI follows them automatically

This is the behavioral impact of coding rules on AI Agent—**you set the rules, the AI executes, and consistency is guaranteed**.

---

### Scenario 4.12 — Batch Multi-Project Compilation (approx. 2 minutes)

> **Power point**: Compile the entire solution with one sentence; the AI handles dependency order.

#### AI Conversation Demo

```
User: Compile the entire solution, all projects under group-project
```

- AI finds the `ProjectGroup.groupproj` file and parses project dependencies
- AI compiles in build order:
  - Step 1: `delphi_project(action="compile", project_path="LibProject/LibUtils.dproj", build_configuration="Debug")` → ✅
  - Step 2: `delphi_project(action="compile", project_path="AppProject/MainApp.dproj", build_configuration="Debug")` → ✅
- Display compilation output: two projects compiled successfully in sequence

```
User: Recompile all projects with Release configuration, Win64 platform
```

- AI recompiles in order, this time with `target_platform="win64"`, `build_configuration="Release"`
- Display output

#### Narration

Everything demonstrated earlier was single-project compilation. But in enterprise development, a solution often contains multiple projects—a common library project plus several application projects, with dependencies between them.

Traditional approach: open the IDE → open each project one by one → select configuration → compile → check results. If it's a full rebuild, you also have to pay attention to compilation order.

Now you only need to say "compile the entire solution", and the AI automatically finds the `.groupproj` project group file, parses the dependencies between projects, and **compiles them one by one in the correct order**—first LibProject, then AppProject.

Want to change platform? "Recompile everything with Release, Win64"—one sentence, and the AI recompiles in order. You don't need to touch the IDE.

## Part 5: Advanced Features (approx. 12 minutes)

### Scenario 5.1 — Build Documentation Knowledge Base (approx. 1.5 minutes)

#### AI Conversation Demo

```
User: Build the Delphi help documentation knowledge base
```

- AI calls `delphi_kb(action="build", kb_type="document", async_mode=true)`
- Returns task_id
- Then calls `async_task(action="status", task_id="xxx", long_poll_seconds=30)` to check progress
- **(Editing hint: This process takes several minutes; it is recommended to speed up or skip the wait)**

#### Narration

We know Delphi help documentation includes a large number of CHM files. The project supports building these CHM help documents into a full-text searchable knowledge base.

Enter "Build the Delphi help documentation knowledge base", and the AI automatically detects help documents in the Delphi installation directory, extracts CHM files with 7-Zip, and then builds the full-text index.

This process runs asynchronously, and you can check build progress via `async_task`. After the build is complete, you can search help documentation just like searching source code.

---

### Scenario 5.1b — Document Knowledge Base Search in Action (approx. 2 minutes)

> **Power point**: 160,000+ pages of Delphi help documentation; find the answer with one natural language sentence. No need to flip through CHM files or memorize API manuals.

#### AI Conversation Demo

After the build is complete:

```
User: Check the help documentation for the parameter descriptions of the TCanvas.Draw method,
      especially the role of the last parameter DrawOpacity
```

- AI calls `delphi_kb(query="TCanvas.Draw", kb_type="document", search_type="all")`
- Matches the help page for `Vcl.Graphics.TCanvas.Draw` among 160,000+ documentation pages
- Display result:
  ```
  procedure Draw(X, Y: Integer; const Graphic: TGraphic; DrawOpacity: Byte = 255);
  // DrawOpacity: Drawing opacity. 0 = fully transparent, 255 = fully opaque
  // The default value 255 means fully opaque
  ```

```
User: Search the help documentation for how to use the PrintDialog component to set printer parameters
```

- AI calls `delphi_kb(query="PrintDialog printer settings", kb_type="document", search_type="semantic")`
- Searches and finds the `Vcl.Dialogs.TPrintDialog` help page and related articles
- Returns usage instructions and code examples

#### Narration

After building the help documentation knowledge base, the most practical use is—**searching help**.

The traditional way to find Delphi help: open CHM → find the index → enter keywords → browse → flip to the right page. If you don't know the exact keyword, it's even more painful.

Now you only need to say "check the parameter descriptions of TCanvas.Draw", and the AI performs full-text search across 160,000 pages of help documentation, directly locates the help page for `Vcl.Graphics.TCanvas.Draw`, and extracts the parameter description—`DrawOpacity` controls opacity from 0 to 255, with the default 255 being opaque.

You can even search with natural language: "how to use PrintDialog to set printer parameters"—semantic search will help you find the relevant help articles.

This is **instant retrieval capability across 160,000 pages of documentation**, two orders of magnitude faster than flipping through CHM files.
### Scenario 5.2 — Install Component Package (about 1 minute)

#### AI Dialogue Demo

```
User: Install the MyComponent.dpk component package
```

- AI calls `package(action="install", package_path="MyComponent.dpk")`
- Show the compilation and registration process

```
User: View the list of installed component packages
```

- AI calls `package(action="list")`
- Show registered IDE component packages

#### Narration

Installing a Delphi component package has also become very simple.

Enter "Install MyComponent.dpk", and AI will compile this package file. If it is a design-time package, it will also automatically register it in the IDE.

After installation is complete, enter "View the list of installed component packages", and you can see all registered component packages.

---

### Scenario 5.3 — Complex Compile-Error Diagnosis (about 2 minutes)

> **Key highlight**: AI does not just look at the error line—it searches the KB to understand deeper information such as generic constraints and type definitions, and fixes the problem at the root.

#### AI Dialogue Demo

```
User: Compile compile-error-demo/ErrorCode.pas, and if there are errors, analyze and fix them
```

- AI calls `delphi_project(action="compile", project_path="compile-error-demo/ErrorCode.pas")`
- Compile error:
  ```
  [dcc32 Error] ErrorCode.pas(28): E2511 Type parameter 'TCustomKey' must have a comparer
                      to be used in TDictionary<TCustomKey, string>
  ```

**Traditional approach:** Seeing `E2511 must have a comparer`, a beginner may have no idea what it means. Even if they know, they still have to look up how to implement `IEqualityComparer<T>`.

**AI's approach:**

##### Step 1: Search the KB to Understand the Cause of the Error

- AI calls `delphi_kb(query="TDictionary", search_type="class", kb_type="delphi")` → view the generic constraint definition
- Discovers that `TDictionary<TKey, TValue>` requires `TKey` to implement `IEqualityComparer<TKey>` or to pass in a comparer
- AI calls `delphi_kb(query="TEqualityComparer", search_type="class", kb_type="delphi")` → view the comparer base class

##### Step 2: Analyze the Root Cause

- `TCustomKey` is a record type and has no default comparer
- Need to create a subclass of `TEqualityComparer<TCustomKey>` that implements `Equals` and `GetHashCode`
- Pass a comparer instance in `TDictionary.Create`

##### Step 3: Fix the Code

- AI generates the `TCustomKeyComparer` class
- Modify `TDataCache.Create` to pass in the comparer
- Recompile → passes ✅

#### Narration

The previous compile-error fix demo was a simple case such as "missing uses unit". This time we look at a **truly tough nut**.

`E2511 Type parameter must have a comparer`—for an experienced Delphi developer, this error means that when using a record as the key of a `TDictionary`, you need to provide a comparer. But if you are not familiar with generic constraints, this error message is very cryptic.

AI's approach is completely different from a human's:

**Step 1: AI searches the knowledge base**. It looks up the class definition of `TDictionary` to see what its generic constraint actually is—confirming that `TKey` needs the support of `IEqualityComparer`.

**Step 2: AI then searches the source-code KB for `TEqualityComparer`** to see how this base class is inherited and how it implements `Equals` and `GetHashCode`.

**Step 3: Root cause analysis**—`TCustomKey` is a record and has no default comparer, so a custom `TCustomKeyComparer` is needed and must be passed in at `TDictionary.Create`.

Finally, it generates fix code, and recompilation passes.

This is the pattern of **AI + knowledge base** working together to solve complex problems—**not relying on AI's memory to guess, but actually looking up source-code definitions to understand the root cause of the error**. For an ecosystem like Delphi, with a 30-year history and a huge, complex API, this capability is especially valuable.

**This forms a closed loop of "write code → compile → find errors → fix → recompile", completed entirely within the conversation.**

---

### Scenario 5.4 — Complete From-0-to-1 Workflow (about 3 minutes)

> **Design idea**: This is the soul scenario of the tutorial, connecting all the previous tools into a complete story. It shows the whole process of AI completing a feature from scratch.

#### AI Dialogue Demo

Storyline: The project needs a **read/write unit for JSON configuration files**, implemented from scratch.

```
User: I need to add a JSON configuration file management unit to the project,
      following the project coding standards. First get the rules.
```

##### Step 1: Get Coding Standards

- AI calls `get_coding_rules(section="writing")`
- Learn the naming conventions, file header format, and exception handling requirements

```
User: Look up the official Delphi classes for handling JSON
```

##### Step 2: Search the API

- AI calls `delphi_kb(query="TJSONObject", search_type="class", kb_type="delphi")` to search for `TJSONObject`
- AI calls `delphi_kb(query="TJSONValue", search_type="class", kb_type="delphi")` to search for `TJSONValue`
- AI calls `delphi_kb(query="TFile.ReadAllText", search_type="function", kb_type="delphi")` to confirm the file-reading API
- Show search results and API usage

```
User: Okay, start writing code. The unit name is JsonConfigManager,
      providing the LoadConfig, SaveConfig, GetValue, and SetValue methods
```

##### Step 3: AI Writes Code

- AI combines the coding standards and API definitions to generate the complete unit
- Show the generated code (picture-in-picture can show real-time changes to the code file)

##### Step 4: Compile and Verify

```
User: Compile the project to check syntax
```

- AI calls `delphi_project(action="compile", project_path="JsonConfigManager.pas")`
- If compilation fails, AI automatically fixes it and recompiles
- Show successful compilation

##### Step 5: Format

```
User: Format the code
```

- AI calls `delphi_file(action="format", file_path="JsonConfigManager.pas")`
- Show the final formatted code

##### Step 6: Code Audit

```
User: Audit the code quality
```

- AI calls `get_coding_rules(section="review")`
- Review item by item: resource leaks? Exception handling? Naming conventions? Type safety?
- Output a review report

```
User: Modify according to the review comments
```

- AI modifies the code according to the review report
- Compile again to confirm it passes

#### Narration

In this last scenario, we connect all the tools learned today into a complete **from-0-to-1 development workflow**.

The story is this: the project needs a JSON configuration file management unit.

You don't need to manually open the IDE, create files, or check help—everything is done in the AI conversation:

**① Get coding standards** → AI first learns the project rules
**② Search the API to confirm signatures** → look up the exact usage of `TJSONObject`, `TJSONValue`, and `TFile.ReadAllText`
**③ Knowledge-base-driven code generation** → generate code by combining standards + API definitions (delphi_file write automatically backs up by default), rather than guessing from memory
**④ Format** → pasfmt unifies style
**⑤ Compile and verify** → compile to check syntax
**⑥ Code audit + create ticket** → after the audit, automatically register issues as Issues
**⑦ Cleanup & verification** → remove unused code and confirm backups exist

The key difference lies in **steps ② and ⑥**:
- Step ② is not AI "recalling" the API from training data—it actually goes to the knowledge base and looks up `TJSONObject`'s class inheritance chain and constructor signatures
- Step ⑥ is not simply "change it and be done"—the audit report can be converted into a ticket with one click via the MCP built-in `code_hosting` tool and brought into Gitea issue tracking (⑧ Gitea defect closed loop: audit ticket → fix → `close_issue` links the commit and closes it)

Throughout the whole process, you only need to make decisions and state requirements; AI is responsible for execution and verification. This is the complete form of **MCP Server + AI-assisted Delphi development**.

---

### Scenario 5.5 — Gitea Defect Closed-Loop Practice (about 3 minutes)

> **Key highlight**: Using this project itself as a case study to demonstrate the complete Gitea closed loop of code commit → audit → create ticket → fix → close ticket.
>
> All operations are completed through a single `code_hosting` tool, with no need to switch platforms.

#### AI Dialogue Demo

Storyline: We have just completed development of the `code_hosting` tool and need to commit the code, audit it, and register the audit findings in Gitea for tracking.

```
User: Commit the code_hosting.py we just finished to Git,
      then audit the code quality, and if there are findings, create a Gitea ticket to track them.
```

##### Step 1: Code Commit

- AI calls `code_hosting(action="git_add", work_dir=".", files=["src/tools/code_hosting.py", "src/server.py", "tests/test_code_hosting.py"])`
- AI calls `code_hosting(action="git_commit", work_dir=".", commit_message="feat: add unified code_hosting tool")`
- Return commit hash: `0a7e8b7`

##### Step 2: Code Audit

- AI calls `get_coding_rules(section="review")` to get the review standards
- AI analyzes the `code_hosting.py` code and checks item by item:
  - ✅ Parameter validation completeness
  - ✅ Exception handling coverage
  - ✅ Return format consistency
  - ✅ Cross-platform path configuration
- Output a review report: list the passed items and improvement suggestions

##### Step 3: Connect to Gitea and Create a Ticket

```
User: Create the audit results as a Gitea ticket, connecting to https://code.qdac.cc:3000,
      repository swish/api_test
```

- AI calls `code_hosting(platform="gitea", action="create_token", base_url="https://code.qdac.cc:3000", username="...", password="...")` ← obtains Token
- AI calls `code_hosting(platform="gitea", action="init_labels", base_url="...", token="...", repo="swish/api_test")` ← ensure labels exist
- AI calls `code_hosting(platform="gitea", action="create_issue", base_url="...", token="...", repo="swish/api_test",
     title="[审计] code_hosting.py 代码审查",
     body="审计发现的改进建议...",
     label_names=["类型/改进", "优先级/中", "状态/待确认"])`
- Return ticket link: `https://code.qdac.cc:3000/swish/api_test/issues/7`

##### Step 4: Fix the Issues

- AI modifies the code according to the audit suggestions:
  - `_request()` adds a null check for token
  - `code_hosting()` adds pre-operation parameter checks for API operations
- AI calls `code_hosting(action="git_add", ...)` + `git_commit` → commit `8f929b5`

##### Step 5: Close the Ticket (Linked to Commit)

```
User: Explain the fix in the ticket and close it
```

- AI calls `code_hosting(platform="gitea", action="add_comment", base_url="...", token="...", repo="swish/api_test",
     issue_number=7, body="已在 commit 8f929b5 中修复: ...")`
- AI calls `code_hosting(platform="gitea", action="close_issue", base_url="...", token="...", repo="swish/api_test",
     issue_number=7, comment_body="已修复并合并，commit: 8f929b5")`
- Ticket closed ✅

#### Narration

In this last scenario, we use **this project itself** as a case study to walk through the complete Gitea defect closed loop.

This is a scenario that really happens in project development—you have just finished developing a feature module and need to go through the full process of "commit → audit → track → fix → close".

**① Code commit**: `git_add` + `git_commit` to commit to the local repository.

**② Code audit**: call `get_coding_rules` to get the review standards and review code quality item by item.

**③ Create a Gitea ticket**: use `code_hosting`'s `create_token` to obtain an access token → `init_labels` to ensure the four-dimensional labels exist → `create_issue` to create the ticket and apply labels. All done through **the same tool**, without leaving the AI conversation.

**④ Fix**: modify the code according to the audit suggestions and commit again.

**⑤ Close**: `add_comment` records the fix content (can include the commit hash), and `close_issue` closes the ticket. The ticket history is complete and traceable.

The key value of this closed loop is: **audit results do not just stay in the conversation—they are registered in Gitea's issue tracking system** and brought into the team's standardized process. The association between commits and issues is also recorded, so later developers can trace the fix history of each issue.

---

### Scenario 5.6 — Automated Testing (about 3 minutes)

> **Key highlight**: The same tool supports both GUI screenshots and console interaction. Auto mode automatically identifies the PE type, with no manual switching required.

#### AI Dialogue Demo

**GUI Mode — Screenshot Verification:**

```
User: Take a screenshot of App.exe's login screen and check the interface layout
```

- AI calls `automate_delphi(action="gui", app_path="App.exe", script=[{"cmd":"goto","target":"TLoginForm"},{"cmd":"capture","target":"login.png"}])`
- Return screenshot and control information

```
User: Click the login button, trigger the validation logic, enter the username, and take a screenshot
```

- AI calls `automate_delphi(action="gui", app_path="App.exe", script=[{"cmd":"goto","target":"TLoginForm"},{"cmd":"type","target":"edtUser","text":"admin"},{"cmd":"click","target":"btnLogin"},{"cmd":"capture","target":"after_login.png"}])`
- Show the screenshot of the interface after login

**Console Mode — Command-Line Tool Interaction:**

```
User: Test the Deploy.exe deployment tool, using auto mode for automatic detection
```

- AI calls `automate_delphi(action="auto", app_path="Deploy.exe", input="Y\n", expect="Deploy complete", args=["--silent"])`
- Return the complete output after matching `Deploy complete`

```
User: Test whether it exits normally on timeout when there is no input
```

- AI calls `automate_delphi(action="console", app_path="Tool.exe", timeout=5)`
- Return: timeout triggered correctly, process terminated

#### Narration

In this last scenario, we look at Daofy's automated testing capabilities.

**GUI mode** is used for screenshot-based interface verification. AI can establish Named Pipe communication with the target program through the `DaofyAutomation` unit (which needs to be referenced in the Delphi project) to simulate user operations—locating windows, clicking buttons, entering text, and verifying with screenshots. The whole process is completed in the AI conversation, with no need to manually write UI test scripts.

**Console mode** requires no Delphi-side modifications at all—it directly uses `subprocess` to launch the console program and interacts through stdin/stdout. The `input` parameter sends text (supports `\n` line breaks), the `expect` parameter waits for a specific output pattern, and `timeout` controls the timeout.

The most important part is the **`action="auto"` mode**—the tool automatically reads the Subsystem field in the EXE file's PE header (2=GUI, 3=Console), determines the target program type, and chooses the correct interaction method. The user does not need to specify it at all.

This solves a long-standing pain point in the Delphi ecosystem: **GUI and Console programs are mutually exclusive**. The same Delphi project is either a GUI Application or a Console Application—but when testing you may have both, and Daofy uses one `automate_delphi` tool to cover both scenarios uniformly.

---

## Part Six: Summary & Conclusion (about 1 minute)

### Visuals
- Return to the project GitHub page
- Show Star, License, and other information in the README

### Narration Script

Alright, that's the end of today's tutorial. Let's do a quick review:

**📋 Section One — Installation**
One sentence lets AI automatically complete cloning, environment setup, and client configuration, with zero manual operations.

**🔍 Section Two — Knowledge Base Search**
- Exact search: search classes (`TStringList`) and functions (`Split`) to locate APIs instantly
- **🆕 Semantic search**: Don't know the API name? Describe it in natural language, and AI finds what you need from 300,000+ functions
- **🆕 Reference query**: find which files use a certain type and assess the impact of refactoring
- **🆕 Documentation KB practical search**: after the build is complete, search 160,000 pages of help documentation with one natural-language sentence

**⚙️ Section Three — Compilation & Formatting**
- Compile a complete project or do a single-file syntax check
- **🆕 Complex compile-error diagnosis**: AI searches the KB to understand deep causes such as generic constraints and fixes them at the root
- **🆕 Batch multi-project compilation**: compile the entire solution with one sentence, automatically handling dependency order
- one-click code formatting with pasfmt

**📝 Section Four — AI-Assisted Development**
- **🆕 Knowledge-base-driven code generation**: AI first checks API signatures in the KB, then writes code, passing compilation on the first try
- **🆕 Coding-standard-driven code audit**: review item by item against the standards and output a structured report
- **🆕 Automatically create tickets from audit results**: use the MCP built-in `code_hosting` tool to create labels and tickets with one click
- **🆕 Multi-file refactoring**: reference query → impact assessment → file-by-file modification → compile verification
- **🆕 Automatic backup before modification**: automatically create a `__history` version backup before format/refactoring, which can be restored
- **🆕 Coding standards control AI behavior**: change the rule set for the same requirement and generate code in a completely different style

**🚀 Section Five — Advanced Features**
- Build a CHM help documentation knowledge base with full-text search over 160,000 pages
- Install .dpk component packages into the IDE
- Complete from-0-to-1 workflow: standards → API verification → code generation → compilation → formatting → audit → ticket
- **🆕 Gitea defect closed-loop practice**: code commit → audit → create ticket → fix → close, using this project itself as a case study
- **🆕 Automated testing**: GUI screenshots (Named Pipe) + console interaction (subprocess), same tool with dual modes, action=auto automatically identifies PE type

You can use this MCP Server with any AI assistant that supports the MCP protocol—Claude Desktop, Trae, CodeArts Agent, Cursor, and so on.

The project is completely open source (MIT License), and the GitHub address is at the top of the screen. If you find it useful, don't forget to click Star ⭐ to support it!

Finally, if you encounter any problems while using it, feel free to submit an Issue on GitHub.

Thanks for watching, and see you next time!

---

## Appendix: Recording Tips

### Screen Layout Suggestions

| Scenario | Layout |
|------|------|
| GitHub page introduction | Full-screen browser |
| AI installation demo | Full-screen AI dialogue interface + **picture-in-picture** terminal |
| AI writes code (complex code generation) | Full-screen AI dialogue + **picture-in-picture** VS Code showing code + KB search results |
| Semantic search discovers hidden APIs | Full-screen AI dialogue, highlighting KB search hits |
| Code audit report + create ticket | Full-screen AI dialogue + **picture-in-picture** Gitea ticket interface |
| Complex compile-error diagnosis | Full-screen AI dialogue, highlighting the process of searching the KB for the TDictionary definition |
| Batch multi-project compilation | Full-screen AI dialogue + picture-in-picture showing compilation order and results |
| Multi-file refactoring | Full-screen AI dialogue + **picture-in-picture** VS Code showing file switching |
| Documentation KB practical search | Full-screen AI dialogue, showing the help documentation content hit by the search |
| Code formatting + automatic backup | Split screen: left = AI dialogue, right = File Explorer showing the __history directory |
| Coding standard impact comparison | Split screen: left = code generated with modern standards, right = code generated with old standards, side-by-side comparison |
| Gitea defect closed-loop practice | Full-screen AI dialogue + **picture-in-picture** Gitea ticket interface showing ticket status changes |
| Automated testing GUI mode | Full-screen AI dialogue, highlighting the returned screenshot results and control tree information |
| Automated testing Console mode | Full-screen AI dialogue, highlighting the stdin/stdout interaction process |

### Preparation Required

- [ ] Python 3.10+ installed
- [ ] Git installed
- [ ] Delphi IDE installed (any version)
- [ ] Project cloned and dependencies installed
- [ ] AI client (such as Claude Desktop) configured with the MCP Server
- [ ] Prepare a compilable Delphi sample project (including a .dproj file)
- [ ] A .pas file for testing (containing a demonstrable compile error)
- [ ] Prepare sample code for a JSON read/write unit in advance (used in Scenario 5.4)
- [ ] The refactoring scenario needs a project containing multiple uses of TStringList (refactor-demo/)
- [ ] The complex compile-error scenario needs ErrorCode.pas (generic constraint error, compile-error-demo/)
- [ ] The code audit scenario needs LegacyData.pas (containing 5 types of intentionally left issues, review-demo/)
- [ ] The batch compilation scenario needs the multi-project structure in group-project/
- [ ] The documentation knowledge base needs to be built before recording (the build takes several minutes)
- [ ] The semantic search scenario requires building the embedding vector index in advance: `delphi_kb(action="build_embedding")`
- [ ] The Gitea scenario needs an accessible Gitea instance (such as https://code.qdac.cc:3000) and repository permissions
- [ ] The Gitea defect closed-loop scenario requires running init_labels once in the repository in advance to create labels
- [ ] The automated testing scenario needs a runnable GUI program (including the DaofyAutomation unit) and a console program
- [ ] Delay code: insert `Start-Sleep -Seconds 3` between operations to control pacing

### Editing Markers

- **[Speed up]** — For time-consuming operations such as installing dependencies and building the knowledge base, 5x-10x speed-up is recommended
- **[Cut]** — For waiting for completion, overly long intermediate output, etc., it is recommended to cut them directly
- **[Picture-in-picture]** — When AI dialogue and code/terminal need to be shown at the same time
- **[Audit report]** — When the code audit outputs a report, show each item for 2-3 seconds so viewers can clearly see each issue
- **[Refactoring process]** — Multi-file modifications can be shown at increased speed; pause after each file is modified to show the compilation result

### Common Pitfalls

1. **Python encoding issues** — Make sure to run `$env:PYTHONIOENCODING='utf-8'` in PowerShell first
2. **Virtual environment not activated** — Before the demo, confirm that `venv\Scripts\activate` has been run
3. **Configuration file paths** — When configuring manually, backslashes in paths must be doubled or forward slashes used
4. **Delphi compiler version** — The ProjectVersion of different dproj files must match the correct Delphi version