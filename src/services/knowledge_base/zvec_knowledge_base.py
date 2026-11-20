"""
ZVec knowledge base service — Delphi source search built on ZVec

Features:
  - Build: chunk Delphi sources and import them into a ZVec Collection
  - Search: FTS (full-text) + filter (type/base class) hybrid search
  - Incremental update: partial rebuild after detecting file changes

Dependency: pip install zvec numpy
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ZVecKnowledgeBase:
    """ZVec knowledge base service"""

    def __init__(self, kb_dir: str):
        """
        Args:
            kb_dir: knowledge base storage directory
        """
        self.kb_dir = Path(kb_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self._collection = None
        self._db_path = str(self.kb_dir)

    # ════════════════════════════════════════
    # Build
    # ════════════════════════════════════════

    def build(self,
              file_paths: List[str],
              progress_callback: Optional[Callable] = None) -> Dict:
        """
        Build the knowledge base.

        Flow:
          1. Chunk all files
          2. Import into the ZVec Collection
          3. Build the FTS / InvertIndex

        Args:
            file_paths: list of .pas file paths
            progress_callback: progress callback (percent, message)

        Returns:
            Statistics
        """
        start_time = time.time()

        # ── Chunk ──
        from .delphi_chunker import chunk_file_list

        if progress_callback:
            progress_callback(5, "Chunking files...")

        chunks = chunk_file_list(file_paths)
        if not chunks:
            return {"status": "error", "message": "No chunks produced"}

        logger.info(f"Chunking complete: {len(chunks)} chunks from {len(file_paths)} files")

        # ── 导入 ZVec ──
        if progress_callback:
            progress_callback(30, f"Importing {len(chunks)} chunks into ZVec...")

        import zvec
        from zvec import (CollectionSchema, FieldSchema, DataType,
                          FtsIndexParam, InvertIndexParam, Doc)

        # Create or open the collection
        col = self._open_collection(zvec)

        # Step 1: insert all data
        if progress_callback:
            progress_callback(30, f"Inserting {len(chunks)} chunks...")

        BATCH = 500
        inserted = 0
        for offset in range(0, len(chunks), BATCH):
            batch = chunks[offset:offset + BATCH]
            docs = []
            for i, c in enumerate(batch):
                docs.append(Doc(
                    id=f"c{offset + i:07d}",
                    fields={
                        # Merge entity_name to the front of chunk_text so FTS can search it
                        "chunk_text": (str(c['entity_name'])[:500] + "\n" + str(c['chunk_text'])[:99480]),
                        "chunk_type": str(c['chunk_type']),
                        "base_class": str(c['base_class'])[:200],
                        "file_path": str(c['file_path'])[:500],
                        "start_line": c['start_line'],
                        "end_line": c['end_line'],
                    },
                ))
            col.insert(docs)
            inserted += len(batch)

            if progress_callback and (offset + BATCH) % 4000 == 0:
                pct = 30 + int((offset + BATCH) / len(chunks) * 50)
                progress_callback(pct, f"Inserting {offset + BATCH}/{len(chunks)}...")

        col.flush()

        # Step 2: create a single FTS index (ZVec only persists the last FTS index)
        if progress_callback:
            progress_callback(80, "Building indexes...")
        # Merge all searchable text into one field to avoid the multiple-FTS-index bug
        col.create_index("chunk_text", FtsIndexParam(tokenizer_name="jieba"))
        col.create_index("chunk_type", InvertIndexParam())
        col.create_index("base_class", InvertIndexParam())

        # Step 3: optimize to ensure persistence
        col.optimize()
        col.flush()

        # Count by chunk_type
        class_count = sum(1 for c in chunks if c.get('chunk_type') in ('class', 'record', 'interface'))
        func_count = sum(1 for c in chunks if c.get('chunk_type') in ('function', 'procedure'))
        elapsed = time.time() - start_time
        stats = {
            "status": "ok",
            "files": len(file_paths),
            "chunks": len(chunks),
            "classes": class_count,
            "time_seconds": round(elapsed, 1),
            "dir": str(self.kb_dir),
        }

        if progress_callback:
            progress_callback(100, f"Build complete: {len(chunks)} chunks in {elapsed:.1f}s")

        return stats

    def _open_collection(self, zvec):
        """Open or create the ZVec Collection (merged-field version)"""
        from zvec import CollectionSchema, FieldSchema, DataType
        from pathlib import Path
        import glob, shutil

        schema = CollectionSchema("delphi_kb", fields=[
            FieldSchema("chunk_text", DataType.STRING),   # includes the entity_name prefix
            FieldSchema("chunk_type", DataType.STRING),
            FieldSchema("base_class", DataType.STRING),
            FieldSchema("file_path", DataType.STRING),
            FieldSchema("start_line", DataType.INT32),
            FieldSchema("end_line", DataType.INT32),
        ])

        # A valid collection exists → open; otherwise clean the directory and create_and_open
        db_path = Path(self._db_path)
        has_valid = db_path.exists() and any(
            f.name.startswith("manifest") for f in db_path.iterdir()
        )
        if has_valid:
            self._collection = zvec.open(self._db_path)
        else:
            if db_path.exists():
                shutil.rmtree(str(db_path), ignore_errors=True)
            self._collection = zvec.create_and_open(
                path=self._db_path, schema=schema
            )
        return self._collection

    # ════════════════════════════════════════
    # Search
    # ════════════════════════════════════════

    def search(self,
               query: str,
               chunk_type: Optional[str] = None,
               base_class: Optional[str] = None,
               unit_name: Optional[str] = None,
               file_path: Optional[str] = None,
               top_k: int = 10,
               output_fields: Optional[List[str]] = None) -> Dict:
        """
        Search the knowledge base.

        Args:
            query: search text
            chunk_type: filter by chunk type (class/record/interface/unit)
            base_class: filter by base class name
            unit_name: filter by unit name
            file_path: filter by file path
            top_k: number of results to return
            output_fields: returned fields

        Returns:
            {"results": [...], "total": N, "time_ms": M}
        """
        col = self._get_collection()
        if col is None:
            return {"results": [], "total": 0, "error": "Knowledge base not built"}

        if output_fields is None:
            output_fields = [
                "chunk_text", "chunk_type", "base_class",
                "file_path", "start_line", "end_line"
            ]

        # Build the filter expression
        filter_parts = []
        if chunk_type:
            filter_parts.append(f"chunk_type = '{chunk_type}'")
        if base_class:
            filter_parts.append(f"base_class = '{base_class}'")
        if unit_name:
            filter_parts.append(f"chunk_text LIKE '%{unit_name}%'")
        if file_path:
            filter_parts.append(f"file_path = '{file_path}'")
        filter_expr = " AND ".join(filter_parts) if filter_parts else None

        t0 = time.perf_counter()

        from zvec import Query, Fts

        # Single-field FTS search (chunk_text already carries the entity_name prefix)
        results = col.query(
            Query(field_name="chunk_text", fts=Fts(match_string=query)),
            topk=top_k * 2,
            filter=filter_expr,
            output_fields=output_fields,
        )

        elapsed = (time.perf_counter() - t0) * 1000

        return {
            "results": [
                {
                    "id": r.id,
                    "score": r.score,
                    "fields": dict(r.fields) if r.fields else {},
                }
                for r in results[:top_k]
            ],
            "total": min(len(results), top_k),
            "time_ms": round(elapsed, 1),
        }

    def _get_collection(self):
        """Get the already-opened collection (no-argument version)"""
        if self._collection is None:
            if os.path.exists(self._db_path):
                import zvec
                self._collection = zvec.open(self._db_path)
        return self._collection

    # ════════════════════════════════════════
    # Management
    # ════════════════════════════════════════

    def get_statistics(self) -> Dict:
        """Get knowledge base statistics"""
        import zvec

        col = self._get_collection()
        if col is None:
            return {"status": "not_built"}

        return {
            "status": "ok",
            "doc_count": col.stats.doc_count,
            "dir": str(self.kb_dir),
            "has_indexes": True,
        }

    def close(self):
        """Close the knowledge base"""
        if self._collection:
            try:
                self._collection.close()
            except Exception:
                pass
            self._collection = None

    def __del__(self):
        self.close()
