"""
Experience memory service layer — saves/searches/manages experiences from AI successfully solving problems

Reuses embedding_service for semantic search, SQLite storage, thread-safe connections.
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.constants import SQLITE_BUSY_TIMEOUT_MS

logger = logging.getLogger(__name__)

# numpy optional dependency
np: Any = None
try:
    import numpy
    np = numpy
except ImportError:
    pass

# embedding service (optional; falls back to keyword search when unavailable)
try:
    from .knowledge_base.embedding_service import (
        encode_single,
        cosine_similarity,
        blob_to_vector,
        is_available as _embedding_available,
        is_model_loaded as _embedding_model_loaded,
    )
except ImportError:
    encode_single = None
    cosine_similarity = None
    blob_to_vector = None
    _embedding_available = lambda: False
    _embedding_model_loaded = lambda: False


def _embedding_ok() -> bool:
    """Check whether embedding is available (model loaded and dependencies present)

    Keeps consistent with the knowledge base: only use the embedding path after the model is loaded,
    avoiding save/search triggering lazy loading and causing timeouts.
    """
    try:
        # Model must be loaded (do not trigger lazy loading)
        if not (_embedding_model_loaded and callable(_embedding_model_loaded)
                and _embedding_model_loaded()):
            return False
        # Dependencies can be imported
        if _embedding_available and callable(_embedding_available):
            return _embedding_available()
    except Exception as e:
        logger.debug("embedding availability check failed (treated as unavailable): %s", e)
    return False


def _now() -> str:
    """Return an ISO-format timestamp"""
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    """Return a short UUID"""
    return uuid.uuid4().hex[:12]


_STORE_FILENAME = "experiences.sqlite"


class ExperienceMemoryService:
    """Experience memory service.

    Provides CRUD and semantic search for experiences. Thread-safe. Designed for graceful embedding fallback.

    Args:
        kb_dir: Storage directory, defaults to data/experience-knowledge-base/
    """

    def __init__(self, kb_dir: Optional[str] = None):
        if kb_dir is None:
            # Default storage under data/
            kb_dir = str(Path(__file__).parent.parent.parent / "data" / "experience-knowledge-base")
        self._kb_dir = Path(kb_dir)
        self._kb_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(self._kb_dir / _STORE_FILENAME)
        self._conn = None  # single connection, protected by a lock for concurrency
        self._conn_lock = threading.Lock()
        self._init_db()

    # ── Connection management (single connection + lock to prevent multi-thread connection leaks)──

    def _get_conn(self):
        """Get a database connection (thread-safe, single-connection mode)"""
        import sqlite3
        with self._conn_lock:
            if self._conn is None:
                conn = sqlite3.connect(self._db_path)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
                conn.row_factory = sqlite3.Row
                self._conn = conn
                self._init_tables(conn)
            else:
                try:
                    self._conn.execute("SELECT 1")
                except Exception:
                    # Connection invalid, recreate it
                    conn = sqlite3.connect(self._db_path)
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
                    conn.row_factory = sqlite3.Row
                    self._conn = conn
                    self._init_tables(conn)
            return self._conn

    def _init_db(self):
        """Initialize the database (create tables on first use)"""
        import sqlite3
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            self._init_tables(conn)
            conn.close()
        except Exception as e:
            logger.error("Failed to initialize experience store: %s", e)

    def _init_tables(self, conn):
        """Create tables (idempotent)"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id          TEXT PRIMARY KEY,
                problem     TEXT NOT NULL,
                solution    TEXT NOT NULL,
                tools_used  TEXT DEFAULT '[]',
                context     TEXT DEFAULT '{}',
                tags        TEXT DEFAULT '[]',
                embedding   BLOB,
                hit_count   INTEGER DEFAULT 1,
                score       REAL DEFAULT 1.0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exp_created
            ON experiences(created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exp_updated
            ON experiences(updated_at)
        """)
        conn.commit()

    def close(self):
        """Close the database connection (thread-safe)"""
        with self._conn_lock:
            if self._conn is not None:
                try:
                    self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception as e:
                    logger.debug("WAL checkpoint failed (connection will be closed normally): %s", e)
                try:
                    self._conn.close()
                except Exception as e:
                    logger.debug("Failed to close sqlite connection: %s", e)
                self._conn = None

    # ── Internal helpers ──

    def _row_to_dict(self, row) -> dict:
        """sqlite3.Row → dict (parse JSON fields)"""
        d = dict(row)
        for field in ("tools_used", "context", "tags"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        # embedding is not returned
        d.pop("embedding", None)
        return d

    def _maybe_encode(self, text: str, prefix: str = "passage"):
        """Try to encode text as an embedding BLOB"""
        if not _embedding_ok() or encode_single is None or np is None:
            return None
        try:
            vec = encode_single(text, prefix=prefix)
            if vec is not None:
                return np.array(vec, dtype=np.float32).tobytes()
        except Exception as e:
            logger.warning("Failed to encode embedding: %s", e)
        return None

    # ── Core operations ──

    def save(
        self,
        problem: str,
        solution: str,
        tools_used: Optional[list] = None,
        context: Optional[dict] = None,
        tags: Optional[list] = None,
    ) -> dict:
        """Save an experience (automatic deduplication and merge: if embedding similarity >0.85, update the old record instead of adding a new one).

        Args:
            problem: Problem description
            solution: Solution steps
            tools_used: List of tool names used
            context: Context information (project path, files, etc.)
            tags: Tag list

        Returns:
            Created/updated experience record dict, with a _merged flag
        """
        now = _now()

        # ── Deduplication: search for semantically similar existing experiences ──
        merged = self._search_embedding(problem, top_k=1, tags=None)
        if merged:
            best = merged[0]
            sim = best.get("similarity", 0)
            if sim > 0.85:
                # Merge without creating a new record
                best_id = best["id"]
                merged_solution = best["solution"] + "\n" + solution
                merged_tags = list(set(best.get("tags", []) + (tags or [])))
                merged_tools = list(set(best.get("tools_used", []) + (tools_used or [])))

                conn = self._get_conn()
                conn.execute(
                    """UPDATE experiences SET solution = ?, tags = ?, tools_used = ?,
                       updated_at = ?, score = MIN(1.0, score + 0.05),
                       embedding = COALESCE(?, embedding)
                       WHERE id = ?""",
                    (
                        merged_solution,
                        json.dumps(merged_tags, ensure_ascii=False),
                        json.dumps(merged_tools, ensure_ascii=False),
                        now,
                        self._maybe_encode(problem, prefix="passage"),
                        best_id,
                    ),
                )
                conn.commit()
                result = best.copy()
                result.update({
                    "solution": merged_solution,
                    "tags": merged_tags,
                    "tools_used": merged_tools,
                    "updated_at": now,
                    "_merged": True,
                    "_merged_from": best_id,
                })
                logger.info("Experience merged into %s — %s", best_id, problem[:80])
                return result

        # ── No similar record, create new ──
        exp_id = _uuid()
        embedding_blob = self._maybe_encode(problem, prefix="passage")

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO experiences
               (id, problem, solution, tools_used, context, tags,
                embedding, hit_count, score, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1.0, ?, ?)""",
            (
                exp_id,
                problem,
                solution,
                json.dumps(tools_used or [], ensure_ascii=False),
                json.dumps(context or {}, ensure_ascii=False),
                json.dumps(tags or [], ensure_ascii=False),
                embedding_blob,
                now,
                now,
            ),
        )
        conn.commit()

        result = {
            "id": exp_id,
            "problem": problem,
            "solution": solution,
            "tools_used": tools_used or [],
            "context": context or {},
            "tags": tags or [],
            "hit_count": 1,
            "score": 1.0,
            "created_at": now,
            "updated_at": now,
            "_merged": False,
        }
        logger.info("Experience saved: %s — %s", exp_id, problem[:80])
        return result

    def search(self, query: str, top_k: int = 5, tags: Optional[list] = None) -> list:
        """Semantically search experiences.

        Prefer embedding-based true semantic search; fall back to LIKE keyword matching when unavailable.
        If the embedding model is loaded but no results are found (possibly old records lack vectors),
        automatically trigger rebuild_embeddings() to fill them in then retry.

        Args:
            query: Search keywords
            top_k: Number of results to return
            tags: Filter by tags (results must match all specified tags)

        Returns:
            [{id, problem, solution, tools_used, tags, similarity, ...}, ...]
        """
        # Try embedding semantic search
        emb_results = self._search_embedding(query, top_k, tags)
        if emb_results:
            return emb_results

        # embedding available but no results → old records may lack vectors; automatically rebuild and retry
        if _embedding_ok():
            rebuilt = self.rebuild_embeddings()
            if rebuilt.get("rebuilt", 0) > 0:
                logger.info("Automatically rebuilt %d missing vectors, retrying semantic search", rebuilt["rebuilt"])
                emb_results = self._search_embedding(query, top_k, tags)
                if emb_results:
                    return emb_results

        # Fallback: keyword LIKE search
        return self._search_keyword(query, top_k, tags)

    def _search_embedding(self, query: str, top_k: int, tags: Optional[list]) -> list:
        """Embedding-based semantic search"""
        if not _embedding_ok() or encode_single is None or cosine_similarity is None:
            return []

        query_emb = encode_single(query, prefix="query")
        if query_emb is None:
            return []

        conn = self._get_conn()
        cursor = conn.cursor()
        # Limit scanned rows to avoid full-table scans becoming slower as data grows
        scan_limit = max(top_k * 10, 200)
        cursor.execute(
            "SELECT id, problem, solution, tools_used, context, tags, "
            "hit_count, score, created_at, updated_at, embedding "
            "FROM experiences WHERE embedding IS NOT NULL "
            "ORDER BY updated_at DESC LIMIT ?",
            (scan_limit,)
        )
        rows = cursor.fetchall()
        if not rows:
            return []

        # Collect vectors and rows
        vecs = []
        valid_rows = []
        for row in rows:
            vec = blob_to_vector(row["embedding"])
            if vec is not None:
                vecs.append(vec)
                valid_rows.append(row)

        if not vecs:
            return []

        # Compute cosine similarity
        _np_local = np
        embs = _np_local.array(vecs, dtype=_np_local.float32)
        sims = cosine_similarity(query_emb, embs)
        if sims is None:
            return []

        # Sort
        scored = []
        for row, sim in zip(valid_rows, sims):
            entry = self._row_to_dict(row)
            entry["similarity"] = round(float(sim), 4)
            # Tag filtering
            if tags:
                row_tags = entry.get("tags", [])
                if not isinstance(row_tags, list):
                    row_tags = []
                if not all(t in row_tags for t in tags):
                    continue
            scored.append(entry)

        scored.sort(key=lambda x: -x["similarity"])
        return scored[:top_k]

    def _search_keyword(self, query: str, top_k: int, tags: Optional[list]) -> list:
        """Keyword LIKE fallback search"""
        conn = self._get_conn()
        cursor = conn.cursor()

        like = f"%{query}%"
        cursor.execute(
            "SELECT id, problem, solution, tools_used, context, tags, "
            "hit_count, score, created_at, updated_at "
            "FROM experiences WHERE problem LIKE ? OR solution LIKE ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (like, like, top_k * 2),
        )
        results = []
        for row in cursor.fetchall():
            entry = self._row_to_dict(row)
            if tags:
                row_tags = entry.get("tags", [])
                if not isinstance(row_tags, list):
                    row_tags = []
                if not all(t in row_tags for t in tags):
                    continue
            results.append(entry)
            if len(results) >= top_k:
                break

        # Keyword search does not assign a similarity score
        for r in results:
            r["similarity"] = 0.0
        return results

    def get(self, exp_id: str) -> Optional[dict]:
        """Get experience details and increment hit_count.

        Args:
            exp_id: Experience ID

        Returns:
            Experience dict or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, problem, solution, tools_used, context, tags, "
            "hit_count, score, created_at, updated_at "
            "FROM experiences WHERE id = ?",
            (exp_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        # Increment hit_count
        conn.execute(
            "UPDATE experiences SET hit_count = hit_count + 1 WHERE id = ?",
            (exp_id,),
        )
        conn.commit()

        return self._row_to_dict(row)

    def list(
        self,
        tags: Optional[list] = None,
        sort_by: str = "updated_at",
        limit: int = 20,
    ) -> list:
        """Browse the experience list.

        Args:
            tags: Filter by tags
            sort_by: Sort field, defaults to updated_at, options are created_at / hit_count / score
            limit: Number of results to return

        Returns:
            [{id, problem, solution, ...}, ...]
        """
        allowed_sort = {"updated_at", "created_at", "hit_count", "score"}
        if sort_by not in allowed_sort:
            sort_by = "updated_at"

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, problem, solution, tools_used, context, tags, "
            f"hit_count, score, created_at, updated_at "
            f"FROM experiences ORDER BY {sort_by} DESC LIMIT ?",
            (limit * 2,),
        )

        results = []
        for row in cursor.fetchall():
            entry = self._row_to_dict(row)
            if tags:
                row_tags = entry.get("tags", [])
                if not isinstance(row_tags, list):
                    row_tags = []
                if not all(t in row_tags for t in tags):
                    continue
            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def update(
        self,
        exp_id: str,
        solution: Optional[str] = None,
        tags: Optional[list] = None,
        problem: Optional[str] = None,
        tools_used: Optional[list] = None,
        context: Optional[dict] = None,
    ) -> Optional[dict]:
        """Update an experience.

        Args:
            exp_id: Experience ID
            solution: New solution steps (optional)
            tags: New tag list (optional)
            problem: New problem description (optional; regenerates embedding)
            tools_used: New tool name list (optional)
            context: New context information (optional)

        Returns:
            Updated experience dict, or None if it does not exist
        """
        existing = self.get(exp_id)
        if existing is None:
            return None

        now = _now()
        updates = []
        params = []

        if problem is not None:
            updates.append("problem = ?")
            params.append(problem)
            # Regenerate embedding
            blob = self._maybe_encode(problem, prefix="passage")
            updates.append("embedding = ?")
            params.append(blob)

        if solution is not None:
            updates.append("solution = ?")
            params.append(solution)

        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags, ensure_ascii=False))

        if tools_used is not None:
            updates.append("tools_used = ?")
            params.append(json.dumps(tools_used, ensure_ascii=False))

        if context is not None:
            updates.append("context = ?")
            params.append(json.dumps(context, ensure_ascii=False))

        updates.append("updated_at = ?")
        params.append(now)
        params.append(exp_id)

        conn = self._get_conn()
        conn.execute(
            f"UPDATE experiences SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

        # Re-read
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, problem, solution, tools_used, context, tags, "
            "hit_count, score, created_at, updated_at "
            "FROM experiences WHERE id = ?",
            (exp_id,),
        )
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def merge(self, ids: list, keep: Optional[str] = None) -> Optional[dict]:
        """Merge multiple experiences into one and delete the rest.

        Args:
            ids: List of experience IDs to merge
            keep: ID to keep (others are deleted); if None, create a new entry

        Returns:
            Merged experience dict, or None on failure
        """
        records = []
        for eid in ids:
            r = self.get(eid)
            if r:
                records.append(r)

        if len(records) < 2:
            logger.warning("merge requires at least 2 valid records")
            return None

        # Merge fields
        problems = "\n".join(r["problem"] for r in records)
        solutions = "\n".join(r["solution"] for r in records)
        all_tags = list(set(t for r in records for t in r.get("tags", [])))
        all_tools = list(set(t for r in records for t in r.get("tools_used", [])))
        hit_total = sum(r.get("hit_count", 1) for r in records)
        now = _now()

        if keep and keep in [r["id"] for r in records]:
            # Update the keep record
            target_id = keep
            conn = self._get_conn()
            conn.execute(
                """UPDATE experiences SET problem = ?, solution = ?, tags = ?,
                   tools_used = ?, hit_count = ?, score = 1.0,
                   embedding = COALESCE(?, embedding), updated_at = ?
                   WHERE id = ?""",
                (
                    problems,
                    solutions,
                    json.dumps(all_tags, ensure_ascii=False),
                    json.dumps(all_tools, ensure_ascii=False),
                    hit_total,
                    self._maybe_encode(problems, prefix="passage"),
                    now,
                    target_id,
                ),
            )
            conn.commit()
        else:
            # Create a new entry
            target_id = _uuid()
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO experiences
                   (id, problem, solution, tags, tools_used,
                    hit_count, score, embedding, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?)""",
                (
                    target_id,
                    problems,
                    solutions,
                    json.dumps(all_tags, ensure_ascii=False),
                    json.dumps(all_tools, ensure_ascii=False),
                    hit_total,
                    self._maybe_encode(problems, prefix="passage"),
                    now,
                    now,
                ),
            )
            conn.commit()

        # Delete the other records
        delete_ids = [r["id"] for r in records if r["id"] != target_id]
        for did in delete_ids:
            self.delete(did)

        # Re-read
        return self.get(target_id)

    def _compute_experience_value(self, row) -> float:
        """Compute the experience value score (used for prune sorting)

        Factors considered:
        - hit_count: More reuse means higher value
        - score: Higher score means higher value
        - recency: Newer means higher value (decays if unused for more than 30 days)
        """
        hit = row.get("hit_count", 1)
        score = row.get("score", 1.0)
        recency = row.get("updated_at", "")
        value = hit * score
        # Time decay: value halves if not updated for more than 30 days
        if recency:
            try:
                updated = datetime.fromisoformat(recency)
                days_since = (datetime.now(timezone.utc) - updated).days
                if days_since > 30:
                    value *= 0.5 ** (days_since / 30)
            except Exception as e:
                logger.debug("Time decay calculation failed (keeping original score): %s", e)
        return round(value, 4)

    def prune_list(self, limit: int = 20) -> list:
        """List low-value experiences, sorted ascending by value score.

        Args:
            limit: Number of results to return

        Returns:
            [{id, problem, tags, hit_count, value, ...}, ...]
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, problem, tags, hit_count, score, created_at, updated_at "
            "FROM experiences"
        )
        rows = cursor.fetchall()
        scored = []
        for row in rows:
            d = self._row_to_dict(row)
            d["value"] = self._compute_experience_value(d)
            scored.append(d)
        scored.sort(key=lambda x: x["value"])
        return scored[:limit]

    def delete(self, exp_id: str) -> bool:
        """Delete an experience.

        Args:
            exp_id: Experience ID

        Returns:
            Whether the deletion succeeded
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM experiences WHERE id = ?", (exp_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Experience deleted: %s", exp_id)
        return deleted

    def rebuild_embeddings(self) -> dict:
        """Rebuild vectors for all experience records missing embeddings.

        Call after the model is loaded to generate embeddings for records saved earlier without vectors because the model was not loaded.
        Records that already have embeddings are not affected.

        Returns:
            {total: total record count, rebuilt: rebuilt count, skipped: existing vector count, failed: failure count}
        """
        if not _embedding_ok() or encode_single is None or np is None:
            return {
                "total": 0,
                "rebuilt": 0,
                "skipped": 0,
                "failed": 0,
                "error": "embedding model is not loaded; call delphi_kb(action=build_embedding) to load the model first",
            }

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, problem FROM experiences WHERE embedding IS NULL"
        )
        rows = cursor.fetchall()

        total = len(rows)
        rebuilt = 0
        failed = 0

        # Also scan the count of records that already have embeddings
        cursor.execute("SELECT COUNT(*) as cnt FROM experiences WHERE embedding IS NOT NULL")
        skipped = cursor.fetchone()["cnt"]

        for row in rows:
            exp_id = row["id"]
            problem = row["problem"]
            try:
                blob = self._maybe_encode(problem, prefix="passage")
                if blob is not None:
                    conn.execute(
                        "UPDATE experiences SET embedding = ? WHERE id = ?",
                        (blob, exp_id),
                    )
                    rebuilt += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning("Failed to rebuild embedding (id=%s): %s", exp_id, e)
                failed += 1

        if rebuilt > 0:
            conn.commit()

        logger.info("Experience embedding rebuild complete: rebuilt=%d, skipped=%d, failed=%d", rebuilt, skipped, failed)
        return {
            "total": total + skipped,
            "rebuilt": rebuilt,
            "skipped": skipped,
            "failed": failed,
        }


# Global singleton
_instance: Optional[ExperienceMemoryService] = None
_instance_lock = threading.Lock()


def get_experience_service(kb_dir: Optional[str] = None) -> ExperienceMemoryService:
    """Get the global ExperienceMemoryService instance (singleton)"""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ExperienceMemoryService(kb_dir=kb_dir)
    return _instance


def cleanup():
    """Clean up resources (called when the service shuts down)"""
    global _instance
    if _instance is not None:
        _instance.close()
        _instance = None