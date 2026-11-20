"""
ZVec knowledge base adapter — compatible with the existing DelphiKnowledgeBaseService interface

Lets ZVecKnowledgeBase be used directly by server.py / knowledge_base.py.
"""
import json
import os
import time
import shutil
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ZVecKnowledgeBaseAdapter:
    """
    Adapter: makes ZVecKnowledgeBase compatible with the DelphiKnowledgeBaseService interface.

    Proxy methods:
      search_by_name(query)         → ZVec search
      semantic_search_classes()     → ZVec search + filter class
      semantic_search_functions()   → ZVec search + filter function
      get_statistics()              → ZVec stats
      build_knowledge_base()        → ZVec build
      close()
    """

    def __init__(self, kb_dir: str, source_dirs: Optional[List[str]] = None):
        from .zvec_knowledge_base import ZVecKnowledgeBase

        self.kb_dir = Path(kb_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.source_dirs = source_dirs or []

        # Migration: legacy data lives in the kb_dir/delphi_kb/ subdirectory; promote it one level up
        old_dir = self.kb_dir / "delphi_kb"
        if old_dir.exists():
            _migrate_old_zvec_data(old_dir, self.kb_dir)

        self._zvec = ZVecKnowledgeBase(str(self.kb_dir))
        self.progress_callback: Optional[Callable] = None

    # ── Build ──

    def build_knowledge_base(self, version: str = None, rebuild: bool = False) -> bool:
        """
        Build the knowledge base (legacy interface compatible).

        Collects .pas files from source_dirs and imports them into ZVec after chunking.
        When version is passed, the same version-filtering policy as the RTL/third-party
        library paths applies: index only that Delphi version's official sources; otherwise
        fall back to the source_dirs injected at construction time.
        """
        from .zvec_knowledge_base import ZVecKnowledgeBase

        # Version filter: resolve source directories by version only when version is passed explicitly
        if version:
            try:
                from ...utils.delphi_env import resolve_delphi_source_dirs
                scoped = resolve_delphi_source_dirs(version)
                if scoped:
                    source_dirs = scoped
                else:
                    logger.warning(
                        "No official sources found for Delphi version %s; falling back to the default all-versions directory",
                        version,
                    )
                    source_dirs = self.source_dirs
            except Exception:
                logger.debug("Failed to resolve source directories by version; falling back to the default directories", exc_info=True)
                source_dirs = self.source_dirs
        else:
            source_dirs = self.source_dirs

        if not source_dirs:
            logger.error("No source directories configured; cannot build")
            return False

        # Collect files
        all_files: List[str] = []
        for sd in source_dirs:
            src = Path(sd)
            if src.exists():
                all_files.extend(
                    str(f) for f in src.rglob("*.pas") if f.is_file()
                )

        if not all_files:
            logger.warning(f"No .pas files found under {source_dirs}")
            return False

        logger.info(f"Building ZVec knowledge base: {len(all_files)} files")

        # Remove the old store (rebuild)
        if rebuild:
            # Rebuild: close any open collection first to release Windows handles, then delete the whole directory
            # (no mkdir here — let create_and_open create it).
            import shutil as _shutil
            if self.kb_dir.exists():
                try:
                    self._zvec.close()
                except Exception:
                    pass
                _shutil.rmtree(str(self.kb_dir), ignore_errors=True)
            from .zvec_knowledge_base import ZVecKnowledgeBase
            self._zvec = ZVecKnowledgeBase(str(self.kb_dir))

        # Build
        stats = self._zvec.build(all_files, progress_callback=self.progress_callback)

        # Save build metadata to metadata.json
        if stats and stats.get("status") == "ok":
            metadata = {
                "files": stats.get("files", 0),
                "classes": stats.get("classes", 0),
                "chunks": stats.get("chunks", 0),
                "time_seconds": stats.get("time_seconds", 0),
            }
            try:
                (self.kb_dir / "metadata.json").write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"Failed to save KB metadata: {e}")

        return stats.get("status") == "ok"

    # ── Search ──

    def search_by_name(self, query: str) -> List[Dict]:
        """
        Search symbols by name (returns the legacy interface format).
        In the new schema chunk_text already carries the entity_name prefix, so search chunk_text directly.
        """
        try:
            result = self._zvec.search(query, top_k=50)
        except Exception as e:
            logger.debug(f"ZVec search failed: {e}")
            return []

        symbols = []
        for r in result.get("results", []):
            fields = r.get("fields", {})
            chunk_text = fields.get("chunk_text", "")
            chunk_type = fields.get("chunk_type", "")
            file_path = fields.get("file_path", "")
            start_line = fields.get("start_line", 0)
            base_class = fields.get("base_class", "")

            # Extract entity_name from the first line of chunk_text
            first_line = chunk_text.split('\n')[0].strip() if chunk_text else ""

            kind_map = {
                "class": "TC", "record": "TR", "interface": "TI",
                "object": "TC", "unit": "UI",
            }
            kind_code = kind_map.get(chunk_type, chunk_type.upper() if chunk_type else "??")

            symbols.append({
                "name": first_line,
                "kind_code": kind_code,
                "kind": chunk_type,
                "type_name": chunk_type,
                "file": {
                    "path": file_path,
                    "full_path": str(Path(self.kb_dir.parent, file_path)) if file_path else "",
                },
                "line": start_line,
                "definition": chunk_text[:300],
                "base_class": base_class,
            })
        return symbols

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Semantic class search — ZVec FTS + filter"""
        try:
            result = self._zvec.search(query, chunk_type="class", top_k=top_k)
        except Exception as e:
            logger.debug(f"ZVec semantic search failed: {e}")
            return []
        return [
            (r["fields"].get("chunk_text", "").split("\n")[0].strip(), r.get("score", 0.0))
            for r in result.get("results", [])
        ]

    def semantic_search_functions(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Semantic function search"""
        try:
            result = self._zvec.search(query, top_k=top_k)
        except Exception as e:
            logger.debug(f"ZVec function search failed: {e}")
            return []
        return [
            (r["fields"].get("chunk_text", "").split("\n")[0].strip(), r.get("score", 0.0))
            for r in result.get("results", [])
        ]

    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """Keyword search"""
        return self.search_by_name(keyword)

    def search_by_unit_name(self, unit_name: str) -> List[Dict]:
        """Search by unit name"""
        try:
            result = self._zvec.search(unit_name, chunk_type="unit", top_k=10)
        except Exception as e:
            logger.debug(f"ZVec unit search failed: {e}")
            return []
        return [
            {"name": r["fields"].get("chunk_text", "").split("\n")[0].strip(),
             "file": {"path": r["fields"].get("file_path", ""),
                      "full_path": r["fields"].get("file_path", "")}}
            for r in result.get("results", [])
        ]

    # ── Statistics ──

    def get_statistics(self) -> Dict:
        """Return statistics (legacy interface compatible)"""
        # Prefer reading the actual statistics from metadata.json
        metadata_file = self.kb_dir / "metadata.json"
        meta = {"files": 0, "classes": 0, "chunks": 0}
        if metadata_file.exists():
            try:
                meta.update(json.loads(metadata_file.read_text(encoding="utf-8")))
            except Exception:
                pass

        # Read the live ZVec doc_count (chunk level)
        doc_count = 0
        try:
            stats = self._zvec.get_statistics()
            if isinstance(stats, dict):
                doc_count = stats.get("doc_count", 0)
        except Exception:
            pass

        db_size = _calc_zvec_dir_size(self.kb_dir)

        return {
            "files": meta.get("files", 0),
            "classes": meta.get("classes", 0),
            "chunks": doc_count or meta.get("chunks", 0),
            "database_size_mb": round(db_size / (1024 * 1024), 1),
        }

    def close(self):
        """Close the knowledge base"""
        self._zvec.close()

    def load_knowledge_base(self) -> bool:
        """Compatibility interface: check whether the ZVec collection exists"""
        return _has_zvec_data(self.kb_dir)

    @property
    def kb_instance(self):
        """Compatibility interface: return self (some code calls .kb_instance.search_by_name)"""
        return self


# ══════════════════════════════════════════════════════════════════
# Module-level helper functions (independent of any instance, reusable by external code)
# ══════════════════════════════════════════════════════════════════


def _has_zvec_data(dir_path: Path) -> bool:
    """
    Check whether the directory holds ZVec collection data.
    ZVec always generates at least a manifest.* file when creating a collection.
    """
    if not dir_path.exists():
        return False
    try:
        for f in dir_path.iterdir():
            if f.name.startswith("manifest"):
                return True
    except PermissionError:
        pass
    return False


def _clean_zvec_collection(dir_path: Path):
    """Clean up the data files and subdirectories ZVec generated in the directory"""
    for item in dir_path.iterdir():
        name = item.name
        # ZVec internal files: manifest, scalar.*.ipc, *.sst, *.rocksdb, etc.
        if name.startswith("manifest") or name.startswith("scalar.") or \
           name.startswith("fts.") or name.startswith("scalar.index.") or \
           name.startswith("idmap") or name.startswith("del.") or \
           name == "LOCK":
            _safe_remove(item)
        # RocksDB subdirectories
        if item.is_dir() and (name.endswith(".rocksdb") or name.startswith("scalar.")):
            shutil.rmtree(item, ignore_errors=True)


def _safe_remove(path: Path):
    """Safely remove a file or directory"""
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except Exception:
        pass


def _calc_zvec_dir_size(dir_path: Path) -> int:
    """Compute the size of the ZVec data directory (bytes)"""
    total = 0
    try:
        for dp, _, fs in os.walk(dir_path):
            for f in fs:
                fp = os.path.join(dp, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _migrate_old_zvec_data(old_dir: Path, new_dir: Path):
    """
    Migrate the data in the legacy delphi_kb/ subdirectory up to the root directory.

    Old layout: kb_dir/delphi_kb/{zvec_data}
    New layout: kb_dir/{zvec_data}
    """
    if not old_dir.exists() or old_dir == new_dir:
        return

    logger.info("Migrating ZVec data: %s → %s", old_dir, new_dir)
    for item in old_dir.iterdir():
        target = new_dir / item.name
        try:
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        except Exception as e:
            logger.warning("Failed to migrate file %s: %s", item.name, e)

    shutil.rmtree(old_dir, ignore_errors=True)
    logger.info("ZVec data migration complete; old directory %s removed", old_dir)
