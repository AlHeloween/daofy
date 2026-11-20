# Delphi Knowledge Base — Knowledge Base Search and Management

> Version: v1.1 | Last Updated: 2026-07-05

---

## Table of Contents

1. [Overview](#1-overview)
2. [Knowledge Base Types](#2-knowledge-base-types)
3. [Operation Guide](#3-operation-guide)
4. [Search Strategy](#4-search-strategy)
5. [Knowledge Base Construction](#5-knowledge-base-construction)
6. [Vector Index (Embedding)](#6-vector-index-embedding)
7. [Document Knowledge Base](#7-document-knowledge-base)
8. [Technical Architecture](#8-technical-architecture)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Overview

`delphi_kb` is Daofy's knowledge base search and management tool. It integrates four major knowledge bases—Delphi official source code, project code, third-party libraries, and general documentation—and supports class/function/semantic and other search methods.

**Core use**: Before AI writes Delphi code, query the knowledge base to confirm API definitions and avoid fabricating them.

### Four Major Knowledge Bases at a Glance

| Knowledge Base | Data Volume | Purpose |
|--------|--------|------|
| Delphi Source | 163,737 classes / 300,228 functions | Look up VCL/FMX/RTL official APIs |
| Project Knowledge Base | Project-defined | Look up the current project's own code |
| Third-party Libraries | 5,724 classes / 28,801 functions | Look up third-party component APIs |
| General Documentation | 160,328 documents | Look up Delphi help documentation/CHM |

### Statistics

```
Delphi Source: 2,798 files, 163,737 classes, 300,228 functions, 260 MB
Third-party Libraries:   1,800 files, 5,724 classes, 28,801 functions, 27 MB
General Documentation:   160,328 files, 1,306 MB
```

---

## 2. Knowledge Base Types

### 2.1 Type Reference Table

| kb_type | Name | Storage Path | Requires project_path |
|---------|------|---------|---------------------|
| `delphi` | Delphi official source | `data/delphi-knowledge-base/` | ❌ |
| `project` | Project's own code | `<project directory>/.delphi-kb/` | ✅ (or auto-detect) |
| `thirdparty` | Third-party components | `data/thirdparty-knowledge-base/` | ❌ |
| `document` | General documentation | `data/document-knowledge-base/` | ❌ |
| `example` | Example code | `data/example-knowledge-base/` | ❌ |
| `all` (default) | All | — | — |

### 2.2 Project Path Auto-Detection

When `project_path` is not passed, automatically scans the current working directory and parent directories for `.dproj`:

- If exactly one `.dproj` is found, use it automatically
- If multiple have the same name, match by directory name

```python
# Rely on auto-detection
delphi_kb(query="TfrmMain", kb_type="project")

# Explicitly specify
delphi_kb(query="TfrmMain", kb_type="project", project_path="C:/MyProject/Project.dproj")
```

### 2.3 Storage Structure

> ⚠️ Starting from v2026.06.22, all knowledge bases have been migrated from SQLite FTS5 to the **ZVec vector engine**. Only the experience knowledge base (`experience`) retains SQLite.

Each knowledge base directory contains:
- `*.zvec/` — ZVec vector database directory (document/example/project/third-party knowledge bases)
- `config.json` — configuration file (auto-generated on first build)
- Knowledge base configuration supports custom databases, source paths, and build parameters

The experience knowledge base (`data/experience-knowledge-base/`) still uses `experiences.sqlite` and does not contain a ZVec directory.

---

## 3. Operation Guide

### 3.1 `action="search"` — Search

```python
# Search for class
delphi_kb(query="TStringList")

# Search for function
delphi_kb(query="Create", search_type="function")

# Semantic search (requires vector index to be built first)
delphi_kb(query="如何创建数据库连接", search_type="semantic")

# Search project code
delphi_kb(query="TfrmMain", kb_type="project", project_path="Project.dproj")

# Search Delphi official API
delphi_kb(query="TCustomADODataSet", kb_type="delphi")

# Search references (evaluate modification impact)
delphi_kb(query="TStringList", search_type="reference")
```

**Parameter Description**:

| Parameter | Required | Default | Description |
|------|------|--------|------|
| `query` | ✅ | — | Search keyword |
| `kb_type` | ❌ | all | all/delphi/project/thirdparty/document |
| `search_type` | ❌ | — | function/procedure/class/record/semantic/reference/all etc. |
| `top_k` | ❌ | 200 | Maximum number of results to return (max 500) |
| `project_path` | ❌ | Auto-detect | Project path (required for project/thirdparty) |
| `content_type` | ❌ | — | Document type filter (used for document) |

### 3.2 `action="stats"` — View Statistics

View the file count, class count, function count, and last build time of each knowledge base.

```python
delphi_kb(action="stats")
```

### 3.3 `action="read"` — Read Content

Read document content or source files.

```python
# Read by document URL/doc_id
delphi_kb(action="read", url="...")
delphi_kb(action="read", doc_id="...")

# Read by file path
delphi_kb(action="read", file_path="System.SysUtils.pas", offset=0, limit=1000)
```

### 3.4 `action="scan"` — Scan Documents

Scan a specified directory to add documents to the knowledge base.

```python
delphi_kb(action="scan",
    kb_type="document",
    directory="C:\Docs\Delphi",
    extensions=[".txt", ".md", ".html"],
    max_workers=4)
```

### 3.5 `action="web"` — Add Web Pages

```python
delphi_kb(action="web",
    url="https://docwiki.embarcadero.com/",
    max_pages=50,
    max_depth=2)
```

### 3.6 `action="build_embedding"` — Build Vector Index

See Chapter 6 for details.

---

## 4. Search Strategy

### 4.1 Priority (Standard Search Flow Before Writing Code)

```
⭐1  delphi_kb(query="TStringList")           Exact class name search
     └─ No results? → Try another name
⭐2  delphi_kb(query="TMainForm")             Try another name (TMainForm→TfrmMain)
     └─ Still no results? → Search functions
⭐3  delphi_kb(query="Create",
          search_type="function")             Search functions (matches both FF and FP)
     └─ Still no results? → Search references
⭐4  delphi_kb(query="TForm1",
          search_type="reference")            Search references (evaluate modification impact)
     └─ Still no results? → Semantic search fallback
⭐5  delphi_kb(query="创建主窗口",
          search_type="semantic")             Chinese semantic search fallback
```

> `search_type="function"` matches both functions (FF) and procedures (FP). `search_type="procedure"` only searches procedures.

### 4.2 Troubleshooting When the KB Cannot Find It

```
Cannot find class/function → Check whether kb_type is correct (use project for project code)
             → Try partial match (class name only, without namespace)
             → Check whether the third-party library is installed/built
             → Search directly by file path System.SysUtils → search file name
             → Read source directly: delphi_file(action="read", ...)
```

### 4.3 Working with delphi_file

```python
# First search the KB to confirm the API
delphi_kb(query="TButton", kb_type="delphi")

# Then read the official source code for the specific implementation
delphi_file(action="read", search_type="class", type_name="TButton")

# Project code
delphi_file(action="read", search_type="class",
    type_name="TfrmMain", search_in="project", project_path="...")
```

---

## 5. Knowledge Base Construction

### 5.1 Build Commands

```python
# Delphi source KB (~1 minute, 163737 classes/300228 functions)
delphi_kb(action="build", kb_type="delphi", rebuild=True, async_mode=True)

# Third-party library KB (~6 seconds, 5606 classes/51265 functions)
delphi_kb(action="build", kb_type="thirdparty", rebuild=True, async_mode=True)

# Document KB (~6 minutes, 160328 documents)
delphi_kb(action="build", kb_type="document", rebuild=True, async_mode=True)

# Project KB
delphi_kb(action="build", kb_type="project",
    project_path="Project.dproj", rebuild=True)
```

### 5.2 Parameter Description

| Parameter | Description |
|------|------|
| `async_mode` | Default true; asynchronous execution does not block the MCP channel |
| `rebuild` | Force a full rebuild (default false) |
| `incremental` | Incremental update, only process changed files (default false) |
| `build_thirdparty` | When building the project KB, also build the third-party library KB (default true) |
| `build_project` | Whether to build the project KB (default true) |
| `version` | Specify Delphi version |
| `directory` | Scan directory (can be specified when building document; defaults to auto-detecting the Delphi help directory) |
| `extensions` | File extension filter (e.g. `[".chm"]`) |

### 5.3 Auto-Build on Startup

When the MCP Server starts, it automatically detects `.dproj` under the CWD and submits a background incremental KB build (without blocking MCP readiness).

### 5.4 Hot-Swap Rebuild

Build to a temporary directory `.delphi-kb-tmp-{ts}/`; the old KB remains searchable during the build, and an atomic swap occurs after the build completes.

---

## 6. Vector Index (Embedding)

### 6.1 Overview

The vector index is based on the sentence-transformers model, encoding text into vectors to enable **semantic search**—searching for "how to create a database connection" can also match `TADOConnection.Create`.

### 6.2 Load Model

```python
delphi_kb(action="build_embedding", async_mode=True)
```

The first load downloads the model (takes several minutes); use `async_mode=True` for asynchronous execution.

### 6.3 Effects After Loading

| Feature | Model Not Loaded | Model Loaded |
|------|-----------|-----------|
| Knowledge base `search_type="semantic"` | Falls back to inverted index | True semantic search, ranked by cosine similarity |
| Experience KB save | No deduplication | Automatic >0.85 deduplication merge |
| Experience KB search | LIKE keyword fallback | Semantic vector search |

### 6.4 Notes

- **Load only once**; the knowledge base and experience KB share the same embedding model
- When the model is not loaded, all features are **fully available**, but search precision is lower
- The loading process is asynchronous; check progress via `async_task`
- Old records (saved before the model was loaded) lack vectors and are automatically backfilled on the next search

---

## 7. Document Knowledge Base

### 7.1 Supported Formats

| Format | Required Dependency |
|------|---------|
| TXT / MD / HTML | Built-in support |
| DOCX | `python-docx` (optional) |
| DOC | `antiword`/`catdoc` (optional) |
| CHM | Requires 7-Zip (portable version available in `tools/7z/`) |
| PDF | `PyMuPDF` (recommended) or `pdfplumber` (alternative) |
| EPUB / HLP | Built-in support |
| Web pages | `beautifulsoup4`, `html2text`, `lxml`, `requests` |

### 7.2 Build Delphi Help Documentation Knowledge Base

```python
# Auto-detect the latest installed Delphi help directory
delphi_kb(action="build", kb_type="document",
    extensions=[".chm"], async_mode=True)

# Manually specify the directory
delphi_kb(action="build", kb_type="document",
    directory="C:\Program Files (x86)\Embarcadero\Studio\23.0\Help\Doc",
    extensions=[".chm"], async_mode=True)
```

**Version Reference**: 37.0=Delphi 13, 23.0=Delphi 12, 22.0=Delphi 11, 21.0=Delphi 10.4, 20.0=Delphi 10.3

### 7.3 Web Crawling Parameters

| Parameter | Default | Description |
|------|--------|------|
| `max_pages` | 100 | Maximum pages to crawl |
| `max_depth` | 3 | Maximum crawl depth |
| `domain_filter` | — | Domain filter |
| `url_pattern` | — | URL pattern filter |
| `exclude` | — | List of excluded directories |

---

## 8. Technical Architecture

```
AI Agent
    │
    ▼
delphi_kb(action="search"|"build"|"stats"|...)
    │
    ▼
┌───────────────────────────────────────┐
│       src/tools/knowledge_base.py       │
│  action dispatch + multi-KB query routing │
└──────┬──────────┬──────────┬───────────┘
       │          │          │
       ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Delphi   │ │ Project  │ │ Document │
│ KB       │ │ KB       │ │ KB       │
├──────────┤ ├──────────┤ ├──────────┤
│· RTL/VCL │ │· Project source │ │· CHM/PDF │
│· FMX/api │ │· Third-party libraries │ │· TXT/MD  │
│· Official source │ │· Incremental updates │ │· Web pages │
└──────────┘ └──────────┘ └──────────┘
       │
       ▼
┌───────────────────────────────────────┐
│    embedding_service (vector engine)   │
│  · sentence-transformers               │
│  · encode_single / cosine_similarity   │
│  · Experience KB reuses the same model │
└───────────────────────────────────────┘
```

---

## 9. Troubleshooting

| Symptom | Cause | Solution |
|------|------|------|
| Search returns no results | KB not built | `delphi_kb(action="build", ...)` |
| Cannot find class/function | kb_type is wrong | Use `kb_type="project"` for project code |
| Semantic search inaccurate | Vector index not built | `delphi_kb(action="build_embedding")` |
| KB build timeout | Large data volume | Use `async_mode=True` for asynchronous execution |
| KB build failed | Third-party library path is wrong | Check the `DCC_UnitSearchPath` configuration |
| CHM cannot be parsed | 7-Zip not installed | Place `7z.exe` in the `tools/7z/` directory |
| Document KB search returns no results | Knowledge base not built | First run `delphi_kb(action="build", kb_type="document")` |

