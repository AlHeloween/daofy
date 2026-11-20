# Experience Knowledge Base — Design and Usage Manual

> Version: v1.0 | Last updated: 2026-06-08

---

## Table of Contents

1. [Overview](#1-overview)
2. [Storage Location and Structure](#2-storage-location-and-structure)
3. [Technical Architecture](#3-technical-architecture)
4. [Operation Guide](#4-operation-guide)
5. [Automatic Deduplication Mechanism](#5-automatic-deduplication-mechanism)
6. [Embedding Fallback Strategy](#6-embedding-fallback-strategy)
7. [Experience Maintenance Best Practices](#7-experience-maintenance-best-practices)
8. [Quality Assurance System](#8-quality-assurance-system)
9. [Relationship with the Knowledge Base System](#9-relationship-with-the-knowledge-base-system)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

The Experience Knowledge Base is Daofy's built-in **AI experience memory system**, used to persistently store effective approaches and techniques that the AI discovers when solving problems.

**Core idea**: Problems the AI encounters during coding and their solutions should not be forgotten. The Experience Knowledge Base accumulates value from every "pitfall-and-resolution" cycle, so the next time the AI encounters a similar problem it can reuse the solution directly without re-exploring or requesting human intervention.

Built on **SQLite** storage, with optional integration of the **sentence-transformers vector model** for semantic search. Designed to degrade gracefully when embeddings are unavailable (automatically falling back to keyword search when no vector model is available).

### Key Features

| Feature | Description |
|------|------|
| Semantic search | Integrates a vector model to support natural-language fuzzy matching |
| Automatic deduplication | When embedding similarity > 0.85, automatically merged into the old record |
| Fallback-friendly | Automatically degrades to LIKE keyword search when no vector model is available |
| Thread-safe | Independent SQLite connection per thread, WAL mode |
| Zero configuration | Pure SQLite, no config.json needed |

---

## 2. Storage Location and Structure

### 2.1 Storage Path

```
data/experience-knowledge-base/
└── experiences.sqlite          # SQLite database file
```

The experience base has no `config.json` — it is pure SQLite and zero-configuration.

### 2.2 Database Schema

```sql
CREATE TABLE IF NOT EXISTS experiences (
    id          TEXT PRIMARY KEY,          -- Short UUID (12-char hex)
    problem     TEXT NOT NULL,             -- Problem description
    solution    TEXT NOT NULL,             -- Solution steps
    tools_used  TEXT DEFAULT '[]',         -- List of tools used (JSON array)
    context     TEXT DEFAULT '{}',         -- Context information (JSON object)
    tags        TEXT DEFAULT '[]',         -- List of tags (JSON array)
    embedding   BLOB,                      -- Vector embedding (float32 bytes, optional)
    hit_count   INTEGER DEFAULT 1,         -- Number of views/reuses
    score       REAL DEFAULT 1.0,          -- Quality score
    created_at  TEXT NOT NULL,             -- Creation time (ISO 8601 UTC)
    updated_at  TEXT NOT NULL              -- Last update time (ISO 8601 UTC)
);

CREATE INDEX IF NOT EXISTS idx_exp_created ON experiences(created_at);
CREATE INDEX IF NOT EXISTS idx_exp_updated ON experiences(updated_at);
```

### 2.3 Field Descriptions

| Field | Type | Description |
|------|------|------|
| `id` | TEXT PK | Short UUID (`uuid4().hex[:12]`), unique identifier |
| `problem` | TEXT | Problem description, used for semantic search and display |
| `solution` | TEXT | Solution steps; may span multiple lines and include commands/code |
| `tools_used` | TEXT | JSON array, e.g. `["project", "delphi_file"]` |
| `context` | TEXT | JSON object, e.g. `{"project": "MyApp.dproj", "compiler": "Delphi 12"}` |
| `tags` | TEXT | JSON array, e.g. `["Delphi", "compile", "dcc32"]` |
| `embedding` | BLOB | `numpy.float32` vector serialization; NULL means not generated |
| `hit_count` | INTEGER | Number of times viewed via `get()`, reflecting reuse frequency |
| `score` | REAL | Quality score; increments by 0.05 on auto-merge |
| `created_at` | TEXT | ISO 8601 UTC timestamp |
| `updated_at` | TEXT | ISO 8601 UTC timestamp |

---

## 3. Technical Architecture

| Layer | Component | Description |
|------|------|------|
| **MCP tool layer** | `experience` tool (`src/tools/experience.py`) | action dispatch entry point, formatted output |
| **Service layer** | `ExperienceMemoryService` (`src/services/experience_service.py`) | CRUD + semantic search core logic |
| **Storage layer** | SQLite + optional embedding | Thread-safe connection, WAL mode |
| **Vector engine** | `embedding_service` (from the knowledge base module) | sentence-transformers, enabled only when the model is loaded |

### 3.1 Architecture Diagram

```
AI Agent
    │
    ▼
experience(action="save"|"search"|"merge"|...)
    │
    ▼
┌─────────────────────────────────────┐
│    experience.py (MCP tool layer)    │
│  · action dispatch                   │
│  · formatted output (_fmt_experience)│
│  · error handling                    │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  ExperienceMemoryService (service)   │
│  · save / search / get / list        │
│  · update / merge / delete           │
│  · prune / rebuild_embeddings        │
│  · auto-dedup logic (>0.85 merge)    │
│  · embedding encoding / vector search│
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  SQLite (storage layer)              │
│  · WAL mode                          │
│  · independent connection per thread │
│    (threading.local)                 │
│  · busy_timeout=5000                 │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  embedding_service (vector, optional)│
│  · sentence-transformers model       │
│  · encode_single / cosine_similarity │
│  · graceful fallback if not loaded   │
└─────────────────────────────────────┘
```

### 3.2 Thread Safety

Each thread maintains its own independent SQLite connection (`threading.local()`):

```python
def _get_conn(self):
    import sqlite3
    if not hasattr(self._local, 'conn') or self._local.conn is None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        self._local.conn = conn
        self._init_tables(conn)
    return self._local.conn
```

- `PRAGMA journal_mode=WAL`: readers and writers do not block each other, high concurrency performance
- `PRAGMA busy_timeout=5000`: waits 5 seconds on lock contention
- Graceful shutdown: `PRAGMA wal_checkpoint(TRUNCATE)` then close the connection

### 3.3 Embedding Encoding

```python
def _maybe_encode(self, text: str, prefix: str = "passage"):
    """Try to encode text into an embedding BLOB"""
    if not _embedding_ok() or encode_single is None or np is None:
        return None
    try:
        vec = encode_single(text, prefix=prefix)
        if vec is not None:
            return np.array(vec, dtype=np.float32).tobytes()
    except:
        return None
```

Encoded as `float32` bytes and stored in a BLOB; at search time the value is deserialized and cosine similarity is computed.

---

## 4. Operation Guide

All operations are dispatched via the `action` parameter of the `experience` MCP tool.

### 4.1 `action="save"` — Save an experience

Saves an experience to the database. Supports automatic dedup-merge (see Chapter 5 for details).

```python
# Basic save
experience(action="save",
    problem="dcc32 returns exit code 2 when compiling a Delphi project",
    solution="Check whether DCC_UnitSearchPath in .dproj includes all third-party library paths, "
             "then supplement them via unit_search_paths in delphi_project(action=compile)",
    tools_used=["project", "delphi_file"],
    tags=["Delphi", "compile", "dcc32"])

# Force save (skip the >0.7 similarity interception)
experience(action="save",
    problem="...",
    solution="...",
    force=true)
```

**Parameters**:

| Parameter | Required | Description |
|------|------|------|
| `problem` | ✅ | Problem description (concise, ideally under 80 chars) |
| `solution` | ✅ | Solution steps (may span multiple lines, include concrete commands/call examples) |
| `tools_used` | ❌ | List of tools involved |
| `context` | ❌ | Context JSON, e.g. project path, compiler version |
| `tags` | ❌ | Tag array, used for categorized filtering |
| `force` | ❌ | Default false; true skips similarity interception |

### 4.2 `action="search"` — Semantic search for experiences

```python
# Semantic search (automatically uses embedding or falls back)
experience(action="search",
    query="compile error file not found",
    top_k=5)

# Search filtered by tags
experience(action="search",
    query="Delphi compiler configuration",
    tags=["Delphi", "compile"])
```

**Parameters**:

| Parameter | Required | Default | Description |
|------|------|--------|------|
| `query` | ✅ | — | Search keywords (natural language is fine) |
| `top_k` | ❌ | 5 | Number of results to return |
| `tags` | ❌ | — | Tag filter (results must match all specified tags) |

**Search flow**:
1. If the embedding model is loaded → vector-encode the query → compute cosine similarity (scan the most recently updated `top_k × 10` rows) → return sorted by descending similarity
2. If there are no results but the model is loaded → automatically trigger `rebuild_embeddings()` to fill in missing vectors → retry
3. If the model is unavailable → fall back to `LIKE %keyword%` keyword search

**Returned fields**: `id, problem, solution, tools_used, tags, similarity (match score, 0~1), hit_count, score, created_at, updated_at`

### 4.3 `action="get"` — View experience details

```python
experience(action="get", id="a1b2c3d4e5f6")
```

Automatically increments `hit_count` (records reuse count).

### 4.4 `action="list"` — Browse the experience list

```python
# Latest updated first
experience(action="list", limit=20)

# Filter by tags + sort by usage count
experience(action="list", tags=["Delphi"], sort_by="hit_count", limit=10)
```

**Supported sort fields**: `updated_at` (default), `created_at`, `hit_count`, `score`.

### 4.5 `action="update"` — Update an experience

```python
# Update the solution
experience(action="update", id="a1b2c3d4e5f6",
    solution="More complete solution steps...")

# Update the problem description and tags at the same time (updating problem regenerates the embedding)
experience(action="update", id="a1b2c3d4e5f6",
    problem="More precise problem description",
    tags=["Delphi", "compile", "MSBuild"])
```

### 4.6 `action="merge"` — Merge multiple experiences

Merges multiple experiences that describe the same kind of problem into one and deletes the rest. This is the primary means of deduplication and abstraction.

```python
# Merge into an existing record (keep the target, delete the rest)
experience(action="merge",
    ids=["a1b2c3d4e5f6", "b2c3d4e5f6a7", "c3d4e5f6a7b8"],
    keep="a1b2c3d4e5f6")

# Merge into a new record (delete all, create a new ID)
experience(action="merge",
    ids=["a1b2c3d4e5f6", "b2c3d4e5f6a7"])
```

**Merge rules**:
| Field | Handling |
|------|---------|
| `problem` | Concatenate all problems with newlines |
| `solution` | Concatenate all solutions with newlines |
| `tags` | Deduplicate and merge |
| `tools_used` | Deduplicate and merge |
| `hit_count` | Sum |
| `score` | Reset to 1.0 |
| `embedding` | Re-encode (when model is available) |

### 4.7 `action="prune"` — List low-value experiences

Sorts in ascending order by value score for the AI to inspect and decide whether to delete. **prune does not delete automatically; it only lists candidates**.

```python
experience(action="prune", limit=20)
```

**Value calculation formula**:

```
value = hit_count × score × time_decay
```

Where `time_decay`: if not updated for more than 30 days, decay by half-life (× 0.5 every 30 days).

**Typical low-value patterns**:
| Pattern | Description |
|------|------|
| `hit_count=1` and not updated for a long time | Saved but never used |
| Content too specific | Can be generalized into a more abstract experience |
| Already covered by other experiences | Redundant record of the same problem |

### 4.8 `action="delete"` — Delete an experience

```python
experience(action="delete", id="a1b2c3d4e5f6")
```

### 4.9 `action="rebuild_embedding"` — Rebuild missing vectors

When the embedding model is loaded only after some experiences already exist, the old records lack embedding vectors. This operation generates vectors for all records whose `embedding IS NULL`.

```python
# Explicitly trigger rebuild
experience(action="rebuild_embedding")
```

**Note**: The vector model must first be loaded via `delphi_kb(action="build_embedding")`, otherwise an error is raised. `search()` automatically triggers the rebuild when the model is loaded but there are no results, so manual calls are usually unnecessary.

---

## 5. Automatic Deduplication Mechanism

This is the most core design of the experience base. **`save()` is not a simple INSERT, but a "look up first, then decide" intelligent flow**:

```
save(problem, solution)
  │
  ├─ embedding semantic search for similar records
  │   │
  │   ├─ similarity > 0.85 ──→ auto-merge into existing record (no INSERT)
  │   │   ├─ solution: old solution + new solution concatenated
  │   │   ├─ tags: deduplicate and merge
  │   │   ├─ tools_used: deduplicate and merge
  │   │   ├─ score: +0.05 (capped at 1.0)
  │   │   └─ hit_count: unchanged
  │   │
  │   ├─ similarity > 0.7 (non-force mode) ──→ intercept + prompt
  │   │     returns list of similar records, suggests AI merge manually via merge/update
  │   │     pass force=true to skip this check and save directly
  │   │
  │   └─ similarity ≤ 0.7 ──→ create new record ✅
  │
  └─ embedding unavailable ──→ create directly (no dedup, degrades to LIKE search)
```

### Design Intent

| Threshold | Meaning | Handling |
|------|------|---------|
| > 0.85 | Almost the same problem | **Auto-merge**, zero friction |
| > 0.7 | Possibly related | **Intercept and remind**, suggests manual judgment |
| ≤ 0.7 | Different problem | **Create new normally** |

### What Happens on Merge

```python
# Core code for auto-merge (simplified)
best = merged[0]
sim = best["similarity"]
if sim > 0.85:
    merged_solution = best["solution"] + "\n" + solution
    merged_tags = list(set(best.get("tags", []) + (tags or [])))
    merged_tools = list(set(best.get("tools_used", []) + (tools_used or [])))
    # UPDATE ... SET solution=?, tags=?, tools_used=?, score=score+0.05
    # no INSERT, no new ID
```

The merged record returned carries a `_merged: True` flag, indicating that this save actually merged into an existing record.

---

## 6. Embedding Fallback Strategy

The experience base remains fully usable without a vector model; only search precision is reduced.

### Fallback Flow

```
search(query)
  │
  ├─ embedding model loaded?
  │   ├─ yes → semantic search (cosine similarity ranking)
  │   │      └─ no results? → auto rebuild_embeddings() then retry ✅
  │   └─ no → LIKE keyword fallback search (%query%)
  │
  └─ return results
```

### Behavior in Each Scenario

| Scenario | `save()` | `search()` |
|------|----------|------------|
| Model loaded | Encode embedding into BLOB, perform dedup-merge | Cosine similarity search, precise ranking |
| Model not loaded | BLOB is NULL, no dedup (direct INSERT) | `LIKE %keyword%` fallback, similarity not returned |
| Model loaded later | — | Auto `rebuild_embeddings()` on first no-result, then retry |

### Auto-rebuild Trigger Condition

```python
def search(self, query, top_k, tags):
    emb_results = self._search_embedding(query, top_k, tags)
    if emb_results:
        return emb_results

    # Model available but no results → maybe old records lack vectors
    if _embedding_ok():
        rebuilt = self.rebuild_embeddings()
        if rebuilt.get("rebuilt", 0) > 0:
            emb_results = self._search_embedding(query, top_k, tags)
            if emb_results:
                return emb_results

    # Final fallback
    return self._search_keyword(query, top_k, tags)
```

**Key points**:
- Fallback is fully transparent; upper layers need not know which search mode is in use
- Once the model is loaded later, the first search auto-fills missing vectors with no manual intervention
- It can also be explicitly triggered via `experience(action="rebuild_embedding")`

---

## 7. Experience Maintenance Best Practices

### 7.1 Generalize Before Saving

Do not save overly specific scenarios; first search whether there is already an abstract experience covering the same kind of problem.

```python
# ❌ Wrong: save a specific scenario
experience(action="save",
    problem="In Unit1.pas line 42, change TForm1.Caption to 'Hello'",
    solution="Open Unit1.pas, find TForm1.FormCreate, add Caption := 'Hello'")

# ✅ Correct: abstract the general problem
experience(action="save",
    problem="Runtime modification of TForm.Caption must ensure assignment occurs after BeforeConstruction",
    solution="1. Ensure the Caption assignment is in TForm.AfterConstruction or the FormCreate event\n"
             "2. Do not set Caption in BeforeConstruction or the constructor")
```

### 7.2 Actively Merge After Completing a Task

If the problem just solved is highly related to an existing experience but the solution differs, merge manually via `merge` rather than leaving them independent.

```python
# Existing experience ID: exp_abc (describes the old approach to problem A)
# New approach: a better solution
# Merge the two so one experience contains both approaches
experience(action="merge",
    ids=["exp_abc", "exp_def"],
    keep="exp_abc")  # keep the old ID, fuse in the new content
```

### 7.3 Periodically Clean Up Low-value Entries

```bash
# Run monthly
experience(action="prune", limit=20)
# → lists the 20 lowest-value entries
# → review each one to decide whether to delete
# → experience(action="delete", id="...")
```

### 7.4 Abstract and Merge When Duplicates Are Found

When multiple experiences describe the same kind of problem (e.g. "message trimming" or "return value cleanup" for different tools), merge them manually into one abstract experience whose `tags` cover each search angle.

### 7.5 Rule Integration

Problems with an experience hit 3 or more times should be considered for promotion into official rules in the built-in coding rules resource
`src/resources/coding-rules.md` (MCP Resource: `delphi://coding-rules`),
so all AI Agents can benefit, rather than relying on experience recall.

```
experience with hit_count ≥ 3
    → assess whether it can be rule-ized
    → update src/resources/coding-rules.md to add the rule
    → keep the experience as a reference example
```

### 7.6 Summary of Maintenance Timing

| Timing | Practice | Description |
|------|------|------|
| **Before saving** | Generalize first | Call `search()` to confirm whether a similar experience already exists; if found, merge via `merge`/`update` |
| **After completing a task** | Actively merge | New approach related to an old experience but different in manner; merge manually to avoid independent copies |
| **Monthly** | Cleanup prune | Run `prune` to list low-value records, review then `delete` |
| **When duplicates found** | Abstract and merge | Merge the same kind of problem into one abstract experience; `tags` cover each scenario |
| **hit ≥ 3** | Rule-ize | Assess whether it can be promoted to a formal CODING_RULES rule |

---

## 8. Quality Assurance System

| Assurance mechanism | Layer | Description |
|----------|------|------|
| **Auto dedup-merge** | `save()` | similarity > 0.85 auto-merge, > 0.7 intercept and remind |
| **Auto vector rebuild** | `search()` | auto-trigger `rebuild_embeddings()` when model loaded but no results |
| **Time decay** | `prune_list()` | Value of experiences not updated for 30 days decays by half-life |
| **Usage counting** | `get()` | Each view increments `hit_count` |
| **Timeout protection** | `server.py` | 30-second timeout to prevent embedding loading from blocking the MCP channel |
| **Thread safety** | Connection layer | Independent SQLite connection per thread, WAL mode prevents locks |
| **Log tracing** | Service layer | All exceptions logged via `logger.debug`, no error swallowing |
| **Singleton management** | Global | `get_experience_service()` singleton, `cleanup()` graceful shutdown |

### Timeout Protection

```python
# The experience tool call in server.py has a 30s timeout
async def _handle_experience(arguments: dict) -> dict:
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_experience, **arguments),
            timeout=30.0,
        )
        return result
    except asyncio.TimeoutError:
        return {"status": "failed",
                "message": "experience operation timed out (30s); the embedding model may be taking too long to load/download. "
                           "Please call delphi_kb(action=build_embedding) to load the model first before using semantic search."}
```

### Thread-safe Connection Management

```python
# Independent connection per thread
def _get_conn(self):
    if not hasattr(self._local, 'conn') or self._local.conn is None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        self._local.conn = conn
    return self._local.conn

# When the service shuts down
def cleanup():
    if _instance is not None:
        _instance.close()
        _instance = None
```

---

## 9. Relationship with the Knowledge Base System

```
Daofy Knowledge Base System
│
├── Delphi Source Knowledge Base (data/delphi-knowledge-base/)
│   └── VCL/FMX/RTL official API, class, and function search
│
├── Project Knowledge Base (.delphi-kb/)
│   └── Project own code + third-party library tracking
│
├── General Document Knowledge Base (data/document-knowledge-base/)
│   └── Full-text search for CHM/PDF/DOCX and other documents
│
└── ★ Experience Knowledge Base (data/experience-knowledge-base/) ← this document
    └── AI problem-solving experience memory
```

### Comparison

| Dimension | Other knowledge bases | Experience Knowledge Base |
|------|-----------|-----------|
| **Data source** | Automatically built by tools (source/doc scanning) | **Actively written by the AI** (saved after solving a problem) |
| **Knowledge type** | Declarative knowledge ("what is") | Procedural knowledge ("how to") |
| **Search method** | Exact match + semantic search | Semantic search + keyword fallback |
| **Data format** | Structured API definitions / document full text | Free text (problem + solution) |
| **Storage** | SQLite + config.json | Pure SQLite, no config.json |
| **Deduplication** | Based on file path | Based on semantic similarity (> 0.85) |
| **Maintenance** | Automatic incremental updates | Requires AI to actively prune/merge |

### Shared Components

The Experience Knowledge Base reuses the Delphi knowledge base's `embedding_service` for vector encoding, therefore:

- The vector model only needs to be loaded once (via `delphi_kb(action="build_embedding")`); both knowledge bases share it
- `embedding_service`'s `encode_single()` and `cosine_similarity()` are shared between the experience base and knowledge base
- The model load status check `_embedding_model_loaded()` is global

---

## 10. Troubleshooting

| Symptom | Cause | Solution |
|------|------|------|
| `save` reports "found highly similar experience" | Found a > 0.7 match, intercepted in non-force mode | Merge into the existing record via `merge`/`update`, or pass `force=true` |
| Semantic search returns empty results | Embedding model not loaded or old records lack vectors | Auto-triggers rebuild or falls back to keyword search; no manual intervention needed |
| Search always uses keyword fallback | Embedding model was never loaded | Call `delphi_kb(action="build_embedding")` to load the model |
| Multiple duplicate entries after `save` | Same problem force-saved repeatedly | Merge via `merge`, or `prune` then `delete` redundancies |
| Database locked | Multi-thread contention, WAL not in effect | Check whether `PRAGMA journal_mode` is WAL |
| Connection timeout 30s | Embedding model takes too long to load the first time | Retry after background loading completes, or call `build_embedding` first to warm up |
| `merge` returns None | Invalid IDs or fewer than 2 | First confirm IDs exist via `list`/`search` |
| `rebuild_embedding` errors | Embedding model not loaded | First call `delphi_kb(action="build_embedding")` |
| Experience accidentally deleted | Unexpectedly called `delete` | The experience base has no recycle bin; recommend using `prune` to list then manually confirm before deleting |

---

## Appendix A: Source File Locations

| File | Purpose |
|------|------|
| `src/tools/experience.py` | MCP tool entry point, action dispatch, formatted output |
| `src/services/experience_service.py` | Core service: `ExperienceMemoryService` class |
| `src/server.py` | Tool registration + timeout protection |
| `src/tool_docs.py` | `experience` tool help docs |
| `data/experience-knowledge-base/experiences.sqlite` | Database file (auto-created) |

## Appendix B: Database Diagnostics

The experience base status can be inspected directly via the SQLite command line; **diagnostic read-only operations only**, manual write operations are prohibited:

```bash
# View the total number of experiences
sqlite3 data/experience-knowledge-base/experiences.sqlite "SELECT COUNT(*) FROM experiences;"

# View embedding coverage
sqlite3 data/experience-knowledge-base/experiences.sqlite \
  "SELECT COUNT(*) AS total,
          SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS with_vec,
          SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) AS without_vec
   FROM experiences;"

# View TOP 10 popular experiences
sqlite3 data/experience-knowledge-base/experiences.sqlite \
  "SELECT id, problem, hit_count, score, updated_at
   FROM experiences ORDER BY hit_count DESC LIMIT 10;"
```