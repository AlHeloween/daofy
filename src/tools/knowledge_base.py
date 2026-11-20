"""
Delphi knowledge base MCP tools

Copyright (C) Jilin Province Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

Provides MCP tools for knowledge base query and management
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp.types import CallToolResult

from src.constants import REG_KEY_EMBARCADERO_BDS

logger = logging.getLogger(__name__)

# Unified knowledge base service instances
_delphi_kb_service = None
_thirdparty_kb_service = None

# Project knowledge base cache {project_path: ProjectKnowledgeBase instance}
_pkb_cache = {}

# Example knowledge base cache
_example_kb_service: Optional[Any] = None


def _get_example_kb() -> Optional[Any]:
    """Get or create the ExampleKnowledgeBase instance (lazy loading)"""
    global _example_kb_service
    if _example_kb_service is None:
        try:
            from src.services.knowledge_base.example_knowledge_base import (
                ExampleKnowledgeBase,
            )
            _example_kb_service = ExampleKnowledgeBase()
            logger.info("Example knowledge base instance created")
        except Exception as e:
            logger.warning("Failed to create example knowledge base instance: %s", e)
    return _example_kb_service


def _auto_detect_delphi_help_dir() -> Optional[str]:
    """Auto-detect the installed Delphi help documentation directory (latest version)"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS)
        versions = []
        i = 0
        while True:
            try:
                versions.append(winreg.EnumKey(key, i))
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)

        versions.sort(key=lambda x: float(x) if x.replace('.', '').isdigit() else 0, reverse=True)
        for ver in versions:
            try:
                vk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{REG_KEY_EMBARCADERO_BDS}\\{ver}")
                root_dir = winreg.QueryValueEx(vk, "RootDir")[0]
                winreg.CloseKey(vk)
                help_dir = Path(root_dir) / "Help" / "Doc"
                if help_dir.exists():
                    logger.info(f"Auto-detected Delphi help directory (version {ver}): {help_dir}")
                    return str(help_dir)
            except Exception:
                continue
    except Exception:
        pass
    return None


def _format_build_info(s: dict) -> str:
    """Format last build information"""
    parts = []
    bt = s.get('last_build_time')
    if bt:
        # ISO time truncated to minutes
        parts.append(bt[:16].replace('T', ' '))
    dur = s.get('last_build_duration')
    if dur is not None:
        if dur < 60:
            parts.append(f'{dur}s')
        else:
            parts.append(f'{dur//60}m{dur%60}s')
    return f' (last build: {", ".join(parts)})' if parts else ''


def _append_stats_guide(guide: str, kb_type: str) -> str:
    """Try to append statistics info to the guide"""
    if kb_type in ("all", "delphi") and _delphi_kb_service:
        try:
            s = _delphi_kb_service.get_statistics()
            bi = _format_build_info(s)
            guide += (
                f"  Delphi KB:  {s.get('files', 0)} files, "
                f"{s.get('classes', 0)} classes{bi}\n"
            )
        except Exception as e:
            logger.debug("Failed to get Delphi KB statistics: %s", e)
    if kb_type in ("all", "project"):
        try:
            pp = _resolve_project_path(None)
            if pp:
                pkb = _get_or_create_pkb(pp)
                pkb.load_knowledge_bases()
                s = pkb.get_statistics()
                pj = s.get("project") or {}
                bi = _format_build_info(pj)
                guide += (
                    f"  Project KB: {pj.get('files', 0)} files, "
                    f"{pj.get('classes', 0)} classes{bi}\n"
                )
        except Exception as e:
            logger.debug("Failed to get Project KB statistics: %s", e)
    if kb_type in ("all", "thirdparty") and _thirdparty_kb_service:
        try:
            s = _thirdparty_kb_service.get_statistics()
            bi = _format_build_info(s)
            guide += (
                f"  Thirdparty: {s.get('files', 0)} files, "
                f"{s.get('classes', 0)} classes{bi}\n"
            )
        except Exception as e:
            logger.debug("Failed to get Thirdparty KB statistics: %s", e)
    if kb_type in ("example",):
        try:
            ekb = _get_example_kb()
            if ekb:
                s = ekb.get_statistics()
                bi = _format_build_info(s)
                guide += (
                    f"  Example KB: {s.get('files', 0)} files"
                    f"{bi}\n"
                )
        except Exception as e:
            logger.debug("Failed to get Example KB statistics: %s", e)
    return guide


def _resolve_project_path(project_path: Optional[str] = None) -> Optional[str]:
    """
    Resolve the project path: if not provided, auto-detect the project file in the current directory.

    Supported project file types (by priority):
    - .dproj (MSBuild project file, richest information)
    - .dpr   (traditional Delphi project file)
    - .dpk   (package file)

    Detection order:
    1. If project_path is provided (non-empty), use it directly (don't check existence, let downstream report the error)
    2. Scan CWD for *.dproj / *.dpr / *.dpk (prefer .dproj)
    3. Scan the parent directories of CWD for the same kind of files
    4. If exactly one is found, return that path
    5. If multiple are found, pick by priority (.dproj > .dpr > .dpk), same-name match preferred
    6. If 0 or multiple are found, return None (caller handles the error message)

    Args:
        project_path: user-provided project path (optional)

    Returns:
        Resolved project path, or None
    """
    # User explicitly provided a path → use it directly, regardless of existence
    if project_path:
        return str(Path(project_path))

    # Search patterns sorted by priority
    project_patterns = ["*.dproj", "*.dpr", "*.dpk"]

    # Auto-detect: start from CWD, search upward for project files
    cwd = Path.cwd()
    for search_dir in [cwd] + list(cwd.parents)[:5]:
        found_all: dict[str, list[Path]] = {}
        for pattern in project_patterns:
            found_all[pattern] = list(search_dir.glob(pattern))

        total_found = sum(len(v) for v in found_all.values())

        if total_found == 0:
            continue

        if total_found == 1:
            # Exactly one found, return directly
            for files in found_all.values():
                if files:
                    return str(files[0].resolve())

        # Multiple files → pick by priority
        project_name = search_dir.name
        for pattern in project_patterns:
            for f in found_all[pattern]:
                if f.stem == project_name or f.stem.lower() == project_name.lower():
                    return str(f.resolve())

        # Same-name match failed → return the first by priority
        for pattern in project_patterns:
            if found_all[pattern]:
                return str(found_all[pattern][0].resolve())

        # Theoretically unreachable

    return None


def set_delphi_kb_service(service):
    """Set the Delphi knowledge base service instance"""
    global _delphi_kb_service
    _delphi_kb_service = service


def set_thirdparty_kb_service(service):
    """Set the third-party library knowledge base service instance"""
    global _thirdparty_kb_service
    _thirdparty_kb_service = service


def _get_or_create_pkb(project_path: str, fresh: bool = False):
    """Get or create a project knowledge base instance (with cache)

    Args:
        project_path: project path
        fresh: whether to create a brand-new instance (for build operations, to avoid close() affecting the cache)

    Returns:
        ProjectKnowledgeBase instance
    """
    from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase

    if fresh:
        return ProjectKnowledgeBase(project_path)

    if project_path not in _pkb_cache:
        _pkb_cache[project_path] = ProjectKnowledgeBase(project_path)
    return _pkb_cache[project_path]


def _clear_pkb_cache(project_path: str) -> None:
    """Close and remove the PKB cache instance for the specified project (used to refresh the cache after a build completes)

    Args:
        project_path: project dproj path
    """
    if project_path in _pkb_cache:
        try:
            _pkb_cache[project_path].close()
        except Exception as e:
            logger.debug("Failed to close PKB cache: %s", str(e))
        del _pkb_cache[project_path]
        logger.info(f"Cleared project PKB cache: {project_path}")


def _cleanup_pkb_cache():
    """Close and clean up all cached ProjectKnowledgeBase instances"""
    for path, pkb in list(_pkb_cache.items()):
        try:
            pkb.close()
        except Exception as e:
            logger.debug("Failed to close PKB cache: %s", str(e))
    _pkb_cache.clear()


def _migrate_zvec_subdir(parent_dir: Path, old_subdir_name: str):
    """
    Migrate ZVec data from the old subdirectory to the parent directory (flatten).
    Similar to zvec_adapter._migrate_old_zvec_data, but a standalone function to avoid cross-module coupling.

    Old structure: parent_dir/{old_subdir_name}/{zvec_data}
    New structure: parent_dir/{zvec_data}
    """
    old_dir = parent_dir / old_subdir_name
    if not old_dir.exists() or old_dir == parent_dir:
        return
    import shutil
    logger.info("Migrating ZVec data: %s → %s (flattening subdirectory)", old_dir, parent_dir)
    for item in list(old_dir.iterdir()):
        target = parent_dir / item.name
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
    logger.info("ZVec data migration complete, removed old directory %s", old_dir)


def _migrate_doc_kb_subdir(kb_dir: Path):
    """Flatten the document knowledge base: doc_kb/ → kb_dir/"""
    _migrate_zvec_subdir(kb_dir, "doc_kb")


def _search_document_kb(query: str, top_k: int = 20) -> Optional[List[dict]]:
    """Search the document knowledge base (ZVec version), return a list of document results."""
    try:
        import zvec
        from zvec import Query, Fts

        server_root = Path(__file__).parent.parent.parent
        doc_kb_dir = server_root / "data" / "document-knowledge-base"
        _migrate_doc_kb_subdir(doc_kb_dir)
        zvec_dir = str(doc_kb_dir)
        if not _kb_dir_has_zvec_data(Path(zvec_dir)):
            return None

        col = zvec.open(zvec_dir)
        results = col.query(
            Query(field_name="chunk_text", fts=Fts(match_string=query)),
            topk=top_k,
            output_fields=["chunk_text", "path", "content_type", "extension"],
        )

        doc_list = []
        for r in results:
            fields = r.fields
            chunk_text = fields.get("chunk_text", "") if fields else ""
            lines = chunk_text.split("\n", 1)
            title = lines[0].strip() if lines else ""
            content = lines[1].strip() if len(lines) > 1 else ""

            doc_list.append({
                "id": r.id,
                "title": title[:500],
                "content": content[:5000],
                "content_type": fields.get("content_type", "") if fields else "",
                "path": fields.get("path", "") if fields else "",
                "size": len(content),
            })

        return doc_list if doc_list else None
    except Exception as e:
        logger.debug("Document knowledge base search failed: %s", str(e))
        return None


# AI Agents often pack multiple keywords into one long query; the following sets filter out meaningless noise words.
# Designed as two layers:
#   _MKW_HARD_STOP — extremely generic words, should always be filtered
#   _MKW_DELPHI_KEYWORDS — Delphi keywords, filtered in the first layer, but kept if all words get filtered out
_MKW_HARD_STOP: frozenset = frozenset({
    'a', 'an', 'the', 'in', 'of', 'for', 'to', 'with', 'on', 'at', 'by', 'is', 'it',
    'delphi', 'pascal', 'syntax', 'declaration', 'declare', 'definition', 'define',
    'example', 'examples', 'usage', 'use', 'using', 'keyword', 'keywords',
    'statement', 'statements', 'reference', 'attribute', 'attributes',
    'directive', 'directives', 'section', 'clause', 'demo', 'sample', 'howto',
})

_MKW_DELPHI_KEYWORDS: frozenset = frozenset({
    'class', 'type', 'types', 'private', 'public', 'protected', 'published', 'strict',
    'nested', 'field', 'fields', 'var', 'vars', 'const', 'consts', 'procedure',
    'function', 'constructor', 'destructor', 'property', 'read', 'write', 'default',
    'override', 'virtual', 'dynamic', 'abstract', 'static', 'inline', 'deprecated',
})


def _split_multikeywords(query: str) -> List[str]:
    """Split a long multi-keyword query assembled by the AI into independent search terms.

    AI Agents often pack multiple keywords into a single query, e.g.:
      "Delphi class field declaration syntax private type nested ..."
    This function recognizes such cases, extracts meaningful search terms, searches each one, and aggregates the results.

    Design: first layer filters hard stop words (_MKW_HARD_STOP), second layer filters Delphi keywords (_MKW_DELPHI_KEYWORDS).
    If all words are keywords (no words beyond the hard stop words), fall back to using the keywords themselves as search terms.

    Returns:
        List of valid search terms. Returns [original query] if no splitting is needed.
    """
    tokens = query.split()
    if len(tokens) <= 3:
        return [query]

    # First layer: filter hard stop words (a, the, delphi, syntax, etc.)
    hard_filtered = [
        t for t in tokens
        if t.lower() not in _MKW_HARD_STOP
        and len(t) > 1
    ]
    if hard_filtered:
        # Second layer: further filter Delphi keywords
        meaningful = [
            t for t in hard_filtered
            if t.lower() not in _MKW_DELPHI_KEYWORDS
        ]
        if not meaningful:
            # All remaining words are Delphi keywords (e.g. class, type, field), still more useful than the raw query
            meaningful = hard_filtered
    else:
        # All hard stop words, fall back to the original query
        return [query]

    # Dedupe (preserve order), truncate to at most 8 keywords
    seen: set = set()
    deduped: List[str] = []
    for w in meaningful:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            deduped.append(w)
        if len(deduped) >= 8:
            break
    return deduped


def _normalize_query(query: str) -> str:
    """Normalize the search keyword, handling common query patterns from AI Agents.

    Currently handled:
    - Delphi compiler directive {$WARN} → WARN (strip {$ prefix and } suffix)
      The knowledge base stores compiler directives as the name itself (e.g. 'WARN'), not the {$WARN} format.
    """
    q = query.strip()
    # Compiler directives like {$WARN} / {$WARN ON} / {$IFDEF DEBUG}
    if q.startswith('{$') and q.endswith('}'):
        inner = q[2:-1].strip()
        if inner:
            return inner
    # $ prefix only: $WARN → WARN
    if q.startswith('$') and len(q) > 1:
        return q[1:]
    return q


def _kb_needs_rebuild() -> List[str]:
    """Check whether each KB's ZVec data exists, return a list of KB hints that need rebuilding

    After upgrading to the ZVec version, old SQLite data is no longer usable; you must run
    delphi_kb(action='build', kb_type='delphi') once to rebuild.
    """
    hints = []

    # Delphi KB: ZVecAdapter.load_knowledge_base() checks the delphi_kb/ directory
    if _delphi_kb_service:
        try:
            if not _delphi_kb_service.load_knowledge_base():
                hints.append(
                    "[Rebuild required] Delphi source knowledge base (ZVec data missing). Please run:\n"
                    "  delphi_kb(action='build', kb_type='delphi')"
                )
        except Exception as e:
            logger.debug("Delphi KB health check exception: %s", e)

    # Thirdparty KB: ThirdPartyKnowledgeBase.load_knowledge_base() checks zvec_thirdparty/
    if _thirdparty_kb_service:
        try:
            if not _thirdparty_kb_service.load_knowledge_base():
                # Check whether there are third-party library paths (skip the hint if none)
                has_paths = bool(_thirdparty_kb_service.get_library_paths())
                if has_paths:
                    hints.append(
                        "[Rebuild required] Third-party library knowledge base. Please run:\n"
                        "  delphi_kb(action='build', kb_type='thirdparty')"
                    )
        except Exception as e:
            logger.debug("Thirdparty KB health check exception: %s", e)

    return hints


def _format_rebuild_hints(hints: List[str]) -> str:
    """Format rebuild hints as a string"""
    if not hints:
        return ""
    return (
        "═══════════════════════════════════════\n"
        "⚠ Knowledge base needs rebuilding\n"
        "═══════════════════════════════════════\n"
        + "\n\n".join(hints)
        + "\n═══════════════════════════════════════\n"
    )


def _kb_dir_has_zvec_data(dir_path: Path) -> bool:
    """Check whether the directory has a ZVec collection (manifest.* file)"""
    if not dir_path.exists():
        return False
    try:
        for f in dir_path.iterdir():
            if f.name.startswith("manifest"):
                return True
    except (PermissionError, OSError):
        pass
    return False
def _cleanup_old_kb_data(kb_type: str, dry_run: bool = False) -> dict:
    """Clean up residual old knowledge base files of the specified type

    When ZVec data already exists, delete unused old files in the KB directory.
    Safety constraints:
    - Only delete when the ZVec data directory (or doc_kb/) exists (ensures migration is complete)
    - Only delete known old file patterns, don't touch other files

    Args:
        kb_type: "delphi" / "thirdparty" / "project" / "document" / "example"
        dry_run: True=scan and list only, don't delete

    Returns:
        {"deleted": [file list], "freed_mb": float, "skipped": [reasons]}
    """
    import os
    import shutil

    result: dict = {"deleted": [], "freed_mb": 0.0, "skipped": []}

    def _del_one(path: Path, label: str):
        """Safely delete a file"""
        if not path.exists():
            return
        size_mb = path.stat().st_size / (1024 * 1024)
        if dry_run:
            result["deleted"].append(f"{label}: {path.name} ({size_mb:.1f} MB)")
            result["freed_mb"] += size_mb
        else:
            try:
                path.unlink()
                result["deleted"].append(f"{label}: {path.name} ({size_mb:.1f} MB)")
                result["freed_mb"] += size_mb
                logger.info("Cleaned up old KB file: %s (%.1f MB)", path, size_mb)
            except Exception as e:
                result["skipped"].append(f"{label}: {path.name} — {e}")

    # ── Delphi KB ──
    if kb_type in ("delphi", "all") and _delphi_kb_service:
        kb_dir = Path(_delphi_kb_service.kb_dir)
        # ZVec data now lives directly in kb_dir (no more delphi_kb/ subdirectory)
        zvec_ok = _kb_dir_has_zvec_data(kb_dir)
        if not zvec_ok:
            result["skipped"].append("delphi: ZVec data does not exist, skipping cleanup")
        else:
            old_patterns = [
                ("knowledge_base.sqlite", "Old Delphi KB"),
                ("documents.sqlite", "Old Delphi documents"),
                ("config.json", "Deprecated Delphi KB config"),
            ]
            for fname, label in old_patterns:
                _del_one(kb_dir / fname, label)
                _del_one(kb_dir / f"{fname}-wal", label)
                _del_one(kb_dir / f"{fname}-shm", label)

    # ── Thirdparty KB ──
    if kb_type in ("thirdparty", "all") and _thirdparty_kb_service:
        kb_dir = Path(_thirdparty_kb_service.kb_dir)
        _migrate_zvec_subdir(kb_dir, "zvec_thirdparty")
        zvec_ok = _kb_dir_has_zvec_data(kb_dir)
        if not zvec_ok:
            result["skipped"].append("thirdparty: ZVec data does not exist, skipping cleanup")
        else:
            old_patterns = [
                ("knowledge_base.sqlite", "Old Thirdparty KB"),
                ("knowledge.sqlite", "Old Thirdparty KB"),
                ("documents.sqlite", "Old Thirdparty documents"),
            ]
            for fname, label in old_patterns:
                _del_one(kb_dir / fname, label)
                _del_one(kb_dir / f"{fname}-wal", label)
                _del_one(kb_dir / f"{fname}-shm", label)

    # ── Project KB ──
    if kb_type == "project" or kb_type == "all":
        # Iterate over all cached project KBs
        for proj_path, pkb in _pkb_cache.items():
            kb_dir = pkb.kb_dir
            _migrate_zvec_subdir(kb_dir, "zvec_project")
            zvec_ok = _kb_dir_has_zvec_data(kb_dir)
            if not zvec_ok:
                result["skipped"].append(f"project({proj_path}): ZVec data does not exist, skipping cleanup")
                continue
            old_patterns = [
                ("knowledge.sqlite", f"Old project KB ({proj_path})"),
                ("knowledge_base.sqlite", f"Old project KB ({proj_path})"),
                ("documents.sqlite", f"Old project documents ({proj_path})"),
            ]
            for fname, label in old_patterns:
                _del_one(kb_dir / fname, label)
                _del_one(kb_dir / f"{fname}-wal", label)
                _del_one(kb_dir / f"{fname}-shm", label)

    # ── Document KB ──
    if kb_type in ("document", "all"):
        server_root = Path(__file__).parent.parent.parent
        kb_dir = server_root / "data" / "document-knowledge-base"
        _migrate_doc_kb_subdir(kb_dir)
        zvec_ok = _kb_dir_has_zvec_data(kb_dir)
        if not zvec_ok:
            result["skipped"].append("document: ZVec data does not exist, skipping cleanup")
        else:
            old_patterns = [
                ("documents.sqlite", "Old document KB"),
                ("knowledge.sqlite", "Old document KB"),
                ("knowledge_base.sqlite", "Old document KB"),
            ]
            for fname, label in old_patterns:
                _del_one(kb_dir / fname, label)
                _del_one(kb_dir / f"{fname}-wal", label)
                _del_one(kb_dir / f"{fname}-shm", label)

    # ── Example KB ──
    if kb_type in ("example", "all"):
        server_root = Path(__file__).parent.parent.parent
        kb_dir = server_root / "data" / "example-knowledge-base"
        _migrate_zvec_subdir(kb_dir, "zvec_example")
        zvec_ok = _kb_dir_has_zvec_data(kb_dir)
        if not zvec_ok:
            result["skipped"].append("example: ZVec data does not exist, skipping cleanup")
        else:
            # The example KB's knowledge.sqlite is the data source (from scanning the Demo directory),
            # ZVec is the search index built on top of it; do not delete the SQLite
            old_patterns = [
                ("knowledge_base.sqlite", "Old example KB"),
                ("documents.sqlite", "Old example KB"),
            ]
            for fname, label in old_patterns:
                _del_one(kb_dir / fname, label)
                _del_one(kb_dir / f"{fname}-wal", label)
                _del_one(kb_dir / f"{fname}-shm", label)

    result["freed_mb"] = round(result["freed_mb"], 1)
    return result


def _format_cleanup_result(info: dict) -> str:
    """Format the cleanup result"""
    if not info["deleted"] and not info["skipped"]:
        return "Nothing to clean up, no old SQLite files.\n"
    lines = []
    if info["deleted"]:
        lines.append(f"Cleaned up {len(info['deleted'])} old files, freed {info['freed_mb']} MB:")
        for d in info["deleted"]:
            lines.append(f"  ✔ {d}")
    if info["skipped"]:
        lines.append(f"\nSkipped {len(info['skipped'])} items:")
        for s in info["skipped"]:
            lines.append(f"  ⚠ {s}")
    return "\n".join(lines) + "\n"


async def search_knowledge(arguments: Any) -> CallToolResult:
    """Unified knowledge base search (thin orchestrator: routing + dispatch)"""
    kb_type = arguments.get("kb_type", "all")
    search_type = arguments.get("search_type", "all")
    query = _normalize_query(arguments.get("query", ""))
    top_k = min(arguments.get("top_k", 200), 500)

    # Empty query: return knowledge base status + usage guide
    if not query:
        base = _empty_query_guide(kb_type, search_type)
        rebuild_hints = _kb_needs_rebuild()
        if rebuild_hints:
            base += "\n" + _format_rebuild_hints(rebuild_hints)
        return CallToolResult(content=[{"type": "text", "text": base}])

    # Routing: decide the list of KBs to search based on kb_type
    results: dict = {}
    kb_types = [kb_type] if kb_type != "all" else ["delphi", "project", "thirdparty"]
    project_path = _resolve_project_path(arguments.get("project_path"))

    # Main search loop: each KB handles reference / symbols+semantic independently
    for kb in kb_types:
        try:
            if search_type == "reference":
                _search_references(kb, query, project_path, results)
            else:
                _search_symbols(kb, query, search_type, top_k, project_path, results)
        except Exception as e:
            results[f"{kb}_error"] = str(e)

    # Document knowledge base (only when kb_type="all")
    _maybe_search_document(kb_type, query, top_k, results)

    # Example knowledge base (only when kb_type="example", full-text search, no symbol matching)
    _maybe_search_example(kb_type, query, top_k, results)

    # Multi-keyword fallback: when the original query misses, automatically split, search each, dedupe, and aggregate
    keywords: list = [query]
    if not _has_meaningful_results(results):
        _kw_split = _split_multikeywords(query)
        if len(_kw_split) > 1:
            keywords = _kw_split
            _multi_keyword_search(keywords, kb_types, search_type, project_path, top_k, results)

    # Format output
    output = _format_search_output(query, kb_type, search_type, results, top_k, keywords)
    # Append rebuild hints (only shown when there are no search results, to avoid a banner on every output)
    if not _has_meaningful_results(results):
        rebuild_hints = _kb_needs_rebuild()
        if rebuild_hints:
            output += "\n" + _format_rebuild_hints(rebuild_hints)
    return CallToolResult(content=[{"type": "text", "text": output}])


# ──────────────────────────────────────────────────────────────────
# Constants + pure functions (refactored from original nested functions / inline constants)
# ──────────────────────────────────────────────────────────────────

_SEARCH_TYPE_TO_KIND: dict = {
    'class': ['TC'], 'record': ['TR'], 'interface': ['TI'], 'enum': ['TE'],
    'set': ['TS'], 'helper': ['TH'],
    'type': ['TY', 'AT', 'PT'], 'function': ['FF', 'FP'], 'procedure': ['FP'], 'operator': ['OP'],
    'const': ['CC'], 'resourcestring': ['CR'], 'variable': ['GV'],
    'property': ['MP'], 'field': ['MF'], 'method': ['MM'], 'event': ['ME'],
    'unit': ['UI'], 'string': ['KS'], 'dfm': ['DF'], 'attribute': ['AB'],
}

_KIND_DESC: dict = {
    'TC': 'Class', 'TR': 'Record', 'TI': 'Interface', 'TH': 'Helper', 'TE': 'Enum', 'TS': 'Set',
    'TY': 'Type alias', 'AT': 'Array', 'PT': 'Pointer', 'FF': 'Function', 'FP': 'Procedure', 'OP': 'Operator overload',
    'CC': 'Constant', 'CR': 'Resource string', 'GV': 'Global variable',
    'MP': 'Property', 'MF': 'Field', 'MM': 'Method', 'ME': 'Event',
    'UI': 'Unit', 'KS': 'String', 'DF': 'DFM property', 'AB': 'Custom attribute',
}


def _filter_by_search_type(symbols: list, st: str) -> list:
    """Filter the symbol list by search_type (based on kind_code)"""
    if st in _SEARCH_TYPE_TO_KIND:
        allowed_kinds = _SEARCH_TYPE_TO_KIND[st]
        return [s for s in symbols if s.get('kind_code', '') in allowed_kinds]
    return symbols


def _trunc_hint(items: list, results: dict, total_key, top_k: int) -> str:
    """If results are truncated by top_k, return a hint message"""
    total = len(items)
    if total_key and total_key in results:
        total = results[total_key]
    if total > top_k:
        return f"  (hint: {total} results in total, top_k={top_k}, {total - top_k} not shown, increase top_k to get all)\n"
    return ''


def _format_symbol(r: dict) -> str:
    """Format the output of a single symbol (with AST-enhanced fields)"""
    kind_code = r.get('kind_code', '')
    type_desc = _KIND_DESC.get(kind_code) or r.get('kind') or r.get('type_name', kind_code) or ''
    # File path: compatible with both KB return formats
    file_info = r.get('file')
    if isinstance(file_info, dict):
        file_path = file_info.get('full_path') or file_info.get('path', 'N/A')
    else:
        file_path = r.get('full_path') or r.get('relative_path', 'N/A')

    name = r.get('name', 'N/A')
    line = r.get('line', 'N/A')

    # AST-enhanced fields
    extra = []
    sig = r.get('signature', '') or r.get('kind', '')
    if sig and sig not in ('', name):
        extra.append(f"Signature: {sig}")
    inherits = r.get('inherits_from') or r.get('base_class', '')
    if inherits:
        extra.append(f"Inherits: {inherits}")
    visibility = r.get('visibility', '')
    if visibility and visibility != 'published':
        extra.append(f"Visibility: {visibility}")
    modifiers = r.get('modifiers')
    if modifiers and isinstance(modifiers, str) and modifiers != '[]':
        extra.append(f"Modifiers: {modifiers}")
    source = r.get('source', '')
    if source == 'ast':
        extra.append("(AST)")

    result = f"  - {name} ({type_desc})\n    File: {file_path}\n    Line: {line}\n"
    if extra:
        result += f"    {' | '.join(extra)}\n"
    return result


def _format_document_results(doc_list: list, limit: int) -> str:
    """Format document knowledge base search results"""
    if not doc_list:
        return ''
    out = f"Document knowledge base ({len(doc_list)}):\n"
    for i, doc in enumerate(doc_list[:limit], 1):
        doc_id = doc.get('id', '?')
        title = doc.get('title', 'N/A')
        out += f"  {i}. [ID:{doc_id}] {title}\n"
        ct = doc.get('content_type', '')
        if ct:
            out += f"     Type: {ct}\n"
        url = doc.get('url')
        path = doc.get('path', '')
        if url:
            out += f"     URL: {url}\n"
        elif path:
            out += f"     Path: {path}\n"
        sz = doc.get('size', 0)
        if sz:
            out += f"     Size: {sz} bytes\n"
        content = doc.get('content', '')
        if content:
            preview = content[:150].replace('\n', ' ')
            out += f"     Preview: {preview}...\n"
    hint = _trunc_hint(doc_list, {}, None, limit)
    if hint:
        out += hint
    out += "\n"
    return out


# ──────────────────────────────────────────────────────────────────
# Search sub-paths (refactored from original search_knowledge inline code)
# ──────────────────────────────────────────────────────────────────

def _empty_query_guide(kb_type: str, search_type: str) -> str:
    """Return knowledge base status + usage guide when query is empty"""
    guide = (
        "Delphi knowledge base search\n"
        "═══════════════════════════════════════\n"
        "Usage examples:\n"
        '  delphi_kb(query="TStringList")            — search for a class\n'
        '  delphi_kb(query="Create", search_type="function") — search for a function\n'
        '  delphi_kb(query="TForm", kb_type="delphi")  — specify a knowledge base\n'
        '  delphi_kb(query="TfrmMain", kb_type="project") — search project code\n'
        '  delphi_kb(query="frxReport.LoadFromFile", kb_type="example") — search example code\n'
        '  delphi_kb(search_type="reference", query="TfrmMain") — find references\n'
        '\n'
        f"Knowledge base scope: {kb_type}\n"
        f"search_type: {search_type}\n"
        f"First call delphi_kb(action=stats, kb_type={kb_type}) to see the file count of each KB\n"
    )
    try:
        guide = _append_stats_guide(guide, kb_type)
    except Exception as e:
        logger.debug("Failed to get statistics: %s", str(e))
    return guide


def _has_meaningful_results(results: dict) -> bool:
    """Check whether results contain valid data (excluding _error / _warning / async_task_id markers)"""
    return any(
        v for k, v in results.items()
        if not k.endswith('_error') and not k.endswith('_warning') and k != 'project_async_task_id'
    )


def _search_references(kb: str, query: str, project_path: Optional[str], results: dict) -> None:
    """Reference query for a single KB (search_type=='reference')

    - delphi: delegate to _delphi_kb_service.search_by_name
    - project: resolve the dproj namespace prefix, call project_kb.search_usages
    - thirdparty: delegate to _thirdparty_kb_service.kb_instance.search_usages
    """
    if kb == "delphi" and _delphi_kb_service:
        refs = _delphi_kb_service.search_by_name(query)
        if refs:
            results["delphi_symbols"] = refs
        return

    if kb == "project":
        if not project_path:
            results["project_error"] = "Project path not detected"
            return
        try:
            from ..utils.dproj_parser import DprojParser
            try:
                parser = DprojParser(project_path)
                ns_prefixes = parser.get_namespace()
            except Exception:
                ns_prefixes = None

            if not ns_prefixes:
                # Delphi 2010+ default namespace prefix
                ns_prefixes = [
                    'Winapi', 'System.Win', 'Data.Win', 'Datasnap.Win',
                    'Web.Win', 'Soap.Win', 'Xml.Win', 'System', 'Xml',
                    'Data', 'Datasnap', 'Web', 'Soap', 'Vcl',
                    'Vcl.Imaging', 'Vcl.Touch', 'Vcl.Samples', 'Vcl.Shell',
                ]

            pkb = _get_or_create_pkb(project_path)
            pkb.load_knowledge_bases()
            if not pkb.check_and_update_project_kb():
                results["project_warning"] = (
                    "Project source has changed, the knowledge base data may be out of date.\n"
                    "Please run delphi_kb(action='build', kb_type='project', "
                    f"project_path='{project_path}') to rebuild."
                )
            if pkb.project_kb is None:
                results["project_error"] = (
                    f"Project knowledge base not built. Please run first:\n"
                    f"  delphi_kb(action='build', kb_type='project', project_path='{project_path}')\n"
                    f"Then search after the build completes."
                )
            else:
                refs = pkb.project_kb.search_usages(query, namespace_prefixes=ns_prefixes)
                if refs:
                    results["project_references"] = refs
        except Exception as e:
            results["project_error"] = str(e)
        return

    if kb == "thirdparty" and _thirdparty_kb_service:
        if _thirdparty_kb_service.kb_instance is None:
            _thirdparty_kb_service.load_knowledge_base()
        if _thirdparty_kb_service.kb_instance:
            refs = _thirdparty_kb_service.kb_instance.search_usages(query)
            if refs:
                results["thirdparty_references"] = refs


def _search_symbols(
    kb: str,
    query: str,
    search_type: str,
    top_k: int,
    project_path: Optional[str],
    results: dict,
) -> None:
    """Symbol + semantic query for a single KB (search_type in {class, function, all, semantic, ...})"""
    if kb == "delphi" and _delphi_kb_service:
        # Name search (exact / wildcard match)
        symbol_results = _delphi_kb_service.search_by_name(query)
        filtered_by_type = _filter_by_search_type(symbol_results, search_type)
        total_before_cut = len(filtered_by_type)
        filtered = filtered_by_type[:top_k]
        if filtered:
            results["delphi_symbols"] = filtered
            results["delphi_symbols_total"] = total_before_cut
        # Semantic search (supplements semantic-match results)
        if search_type in ("semantic", "all"):
            try:
                semantic_classes = _delphi_kb_service.semantic_search_classes(query, top_k=top_k)
                if semantic_classes:
                    results["delphi_semantic_classes"] = semantic_classes
            except Exception as e:
                logger.debug("Ignoring non-fatal exception: %s", str(e))
            try:
                semantic_functions = _delphi_kb_service.semantic_search_functions(query, top_k=top_k)
                if semantic_functions:
                    results["delphi_semantic_functions"] = semantic_functions
            except Exception as e:
                logger.debug("Ignoring non-fatal exception: %s", str(e))
        return

    if kb == "project":
        if not project_path:
            results["project_error"] = "Please provide the project_path parameter (no .dproj file auto-detected in the current directory)"
            return
        try:
            pkb = _get_or_create_pkb(project_path)
            pkb.load_knowledge_bases()
            # Before searching, check whether the source has changed; if so, automatically start an async rebuild (re-entrancy protected)
            if not pkb.check_and_update_project_kb():
                _start_async_project_rebuild(project_path, results)
            if pkb.project_kb is None:
                results["project_error"] = (
                    f"Project knowledge base not built. Please run first:\n"
                    f"  delphi_kb(action='build', kb_type='project', project_path='{project_path}')\n"
                    f"Then search after the build completes."
                )
                return

            # Name search (search_by_name returns the same format as the Delphi KB)
            project_results = pkb.project_kb.search_by_name(query)
            filtered_by_type = _filter_by_search_type(project_results, search_type)
            total_before_cut = len(filtered_by_type)
            filtered = filtered_by_type[:top_k]
            if filtered:
                results["project_symbols"] = filtered
                results["project_symbols_total"] = total_before_cut
            # Semantic search
            if search_type in ("semantic", "all"):
                _try_semantic_search(pkb.project_kb, "project", query, top_k, results)
        except Exception as e:
            results["project_error"] = str(e)
        return

    if kb == "thirdparty" and _thirdparty_kb_service:
        # Ensure the knowledge base is loaded
        if _thirdparty_kb_service.kb_instance is None:
            _thirdparty_kb_service.load_knowledge_base()
        if _thirdparty_kb_service.kb_instance:
            # Name search: get complete match results directly from the underlying kb_instance
            symbol_results = _thirdparty_kb_service.kb_instance.search_by_name(query)
            filtered_by_type = _filter_by_search_type(symbol_results, search_type)
            total_before_cut = len(filtered_by_type)
            filtered = filtered_by_type[:top_k]
            if filtered:
                results["thirdparty_symbols"] = filtered
                results["thirdparty_symbols_total"] = total_before_cut
            # Semantic search
            if search_type in ("semantic", "all"):
                _try_semantic_search(_thirdparty_kb_service.kb_instance, "thirdparty", query, top_k, results)


def _try_semantic_search(kb_service, kb: str, query: str, top_k: int, results: dict) -> None:
    """Perform semantic search (classes + functions) on the project / thirdparty knowledge base, silent on failure"""
    try:
        sc = kb_service.semantic_search_classes(query, top_k=top_k)
        if sc:
            results[f"{kb}_semantic_classes"] = sc
    except Exception as e:
        logger.debug("Ignoring non-fatal exception: %s", str(e))
    try:
        sf = kb_service.semantic_search_functions(query, top_k=top_k)
        if sf:
            results[f"{kb}_semantic_functions"] = sf
    except Exception as e:
        logger.debug("Ignoring non-fatal exception: %s", str(e))


def _start_async_project_rebuild(project_path: str, results: dict) -> None:
    """Start an async rebuild task when project source changes (re-entrancy protected via dedup_key)"""
    try:
        from ..services.knowledge_base.async_task_manager import get_task_manager
        from ..services.knowledge_base.project_knowledge_base import (
            ProjectKnowledgeBase as _PKB,
        )

        _tm = get_task_manager()
        _rebuild_path = project_path
        _dedup_key = f"project_rebuild:{_rebuild_path}"

        def _rebuild_project_task(**kwargs):
            _pp = kwargs.get("project_path")
            _pc = kwargs.get("_progress_callback")
            _p = _PKB(_pp, progress_callback=_pc)
            _p.build_project_knowledge_base(rebuild=False)
            _p.close()
            return True

        _task_id = _tm.submit_task(
            f"Rebuild project knowledge base ({Path(_rebuild_path).stem})",
            _rebuild_project_task,
            dedup_key=_dedup_key,
            project_path=_rebuild_path,
        )
        results["project_async_task_id"] = _task_id
        logger.info(f"Detected project source change, starting async rebuild task_id={_task_id}")
    except Exception as e:
        logger.warning(f"Failed to start async rebuild: {e}")
        results["project_warning"] = (
            "Project source has changed, the knowledge base data may be out of date.\n"
            "Please run delphi_kb(action='build', kb_type='project', "
            f"project_path='{project_path}') to rebuild manually."
        )


def _maybe_search_document(kb_type: str, query: str, top_k: int, results: dict) -> None:
    """Document knowledge base search (when kb_type='all' or 'document')"""
    if kb_type not in ("all", "document"):
        return
    _is_multiword = bool(_split_multikeywords(query) and len(_split_multikeywords(query)) > 1)
    try:
        doc_results = _search_document_kb(query, top_k)
        if doc_results:
            results["document"] = doc_results
            results["document_is_multiword"] = _is_multiword
    except Exception as e:
        logger.debug("Document knowledge base search failed: %s", str(e))


def _maybe_search_example(kb_type: str, query: str, top_k: int, results: dict) -> None:
    """Example knowledge base search (when kb_type='all' or 'example')"""
    if kb_type not in ("all", "example"):
        return
    try:
        ekb = _get_example_kb()
        if not ekb:
            return
        example_results = ekb.search(query, top_k=top_k)
        if example_results:
            results["example"] = example_results
    except Exception as e:
        logger.debug("Example knowledge base search failed: %s", str(e))


def _multi_keyword_search(
    keywords: list,
    kb_types: list,
    search_type: str,
    project_path: Optional[str],
    top_k: int,
    results: dict,
) -> None:
    """After splitting multiple keywords, search each and dedupe/aggregate by (name, line, path) or (path, imported_by)"""
    seen_dedup: set = set()
    for kw in keywords:
        for kb in kb_types:
            try:
                if search_type == "reference":
                    _multi_kw_ref_one_kb(kb, kw, project_path, seen_dedup, results)
                else:
                    _multi_kw_sym_one_kb(kb, kw, search_type, project_path, seen_dedup, results)
            except Exception:
                continue
        # Also search the document knowledge base for each split keyword (full-text search is more relevant than symbol matching)
        try:
            kw_doc_results = _search_document_kb(kw, top_k // len(keywords) + 1)
            if kw_doc_results:
                seen_urls: set = set()
                for d in kw_doc_results:
                    du = d.get('url') or d.get('path', '')
                    if du and du not in seen_urls:
                        seen_urls.add(du)
                        results.setdefault("document", []).append(d)
        except Exception:
            continue
        # Also search the example knowledge base for each split keyword
        try:
            ekb = _get_example_kb()
            if ekb:
                kw_example_results = ekb.search(kw, top_k=top_k // len(keywords) + 1)
                if kw_example_results:
                    seen_paths: set = set()
                    for d in kw_example_results:
                        dp = d.get('path', '')
                        if dp and dp not in seen_paths:
                            seen_paths.add(dp)
                            results.setdefault("example", []).append(d)
        except Exception:
            continue


def _multi_kw_ref_one_kb(
    kb: str, kw: str, project_path: Optional[str], seen_dedup: set, results: dict
) -> None:
    """Multi-keyword search: reference branch for a single KB"""
    if kb == "delphi" and _delphi_kb_service:
        refs = _delphi_kb_service.search_by_name(kw)
        for r in refs:
            dk = (r.get('name', ''), r.get('line', 0),
                  r.get('file', {}).get('full_path', ''))
            if dk not in seen_dedup:
                seen_dedup.add(dk)
                results.setdefault("delphi_symbols", []).append(r)
    elif kb == "project" and project_path:
        try:
            pkb = _get_or_create_pkb(project_path)
            pkb.load_knowledge_bases()
            if pkb.project_kb:
                refs = pkb.project_kb.search_usages(kw)
                for r in refs:
                    dk = (r.get('file', {}).get('full_path', ''),
                          str(r.get('imported_by', [])))
                    if dk not in seen_dedup:
                        seen_dedup.add(dk)
                        results.setdefault("project_references", []).append(r)
        except Exception as e:
            logger.debug("Failed to search project references: %s", e)
    elif kb == "thirdparty" and _thirdparty_kb_service:
        if _thirdparty_kb_service.kb_instance is None:
            _thirdparty_kb_service.load_knowledge_base()
        if _thirdparty_kb_service.kb_instance:
            refs = _thirdparty_kb_service.kb_instance.search_usages(kw)
            for r in refs:
                dk = (r.get('file', {}).get('full_path', ''),
                      str(r.get('imported_by', [])))
                if dk not in seen_dedup:
                    seen_dedup.add(dk)
                    results.setdefault("thirdparty_references", []).append(r)


def _multi_kw_sym_one_kb(
    kb: str, kw: str, search_type: str, project_path: Optional[str], seen_dedup: set, results: dict
) -> None:
    """Multi-keyword search: symbol branch for a single KB"""
    if kb == "delphi" and _delphi_kb_service:
        refs = _delphi_kb_service.search_by_name(kw)
        filtered = _filter_by_search_type(refs, search_type)
        for r in filtered:
            dk = (r.get('name', ''), r.get('line', 0),
                  r.get('file', {}).get('full_path', ''))
            if dk not in seen_dedup:
                seen_dedup.add(dk)
                results.setdefault("delphi_symbols", []).append(r)
    elif kb == "project" and project_path:
        try:
            pkb = _get_or_create_pkb(project_path)
            pkb.load_knowledge_bases()
            if pkb.project_kb:
                refs = pkb.project_kb.search_by_name(kw)
                filtered = _filter_by_search_type(refs, search_type)
                for r in filtered:
                    dk = (r.get('name', ''), r.get('line', 0),
                          r.get('file', {}).get('full_path', ''))
                    if dk not in seen_dedup:
                        seen_dedup.add(dk)
                        results.setdefault("project_symbols", []).append(r)
        except Exception as e:
            logger.debug("Failed to search third-party library: %s", e)
    elif kb == "thirdparty" and _thirdparty_kb_service:
        if _thirdparty_kb_service.kb_instance is None:
            _thirdparty_kb_service.load_knowledge_base()
        if _thirdparty_kb_service.kb_instance:
            refs = _thirdparty_kb_service.kb_instance.search_by_name(kw)
            filtered = _filter_by_search_type(refs, search_type)
            for r in filtered:
                dk = (r.get('name', ''), r.get('line', 0),
                      r.get('file', {}).get('full_path', ''))
                if dk not in seen_dedup:
                    seen_dedup.add(dk)
                    results.setdefault("thirdparty_symbols", []).append(r)


# ──────────────────────────────────────────────────────────────────
# Output formatting
# ──────────────────────────────────────────────────────────────────

def _format_search_output(
    query: str,
    kb_type: str,
    search_type: str,
    results: dict,
    top_k: int,
    keywords: list,
) -> str:
    """Format search results into human-readable multi-section output"""
    has_multikeyword_results = _has_meaningful_results(results)
    output = (
        f"Search '{query}'"
        f" ({'auto-split keywords' if keywords and len(keywords) > 1 else 'type: ' + search_type}"
        f", knowledge base: {kb_type}):\n\n"
    )
    if keywords and len(keywords) > 1 and has_multikeyword_results:
        output += "> Original query had no hits; automatically split into the following keywords, searched individually and aggregated:\n"
        output += f"> {', '.join(keywords)}\n\n"
    _is_document_first = results.get("document_is_multiword", False) or (keywords and len(keywords) > 1)
    has_results = False
    # Multi-word query: document KB shown first (full-text search is more relevant)
    if "document" in results and _is_document_first:
        doc_fmt = _format_document_results(results["document"], top_k)
        if doc_fmt:
            output += doc_fmt
            has_results = True

    # Delphi symbols (6 sub-sections)
    for key, label, style in [
        ("delphi_symbols", "Delphi symbols", "detailed"),
        ("delphi_all", "Delphi all symbols", "all"),
        ("delphi_classes", "Delphi classes", "simple"),
        ("delphi_functions", "Delphi functions/procedures", "simple"),
        ("delphi_semantic_classes", "Delphi classes (semantic search)", "semantic"),
        ("delphi_semantic_functions", "Delphi functions/procedures (semantic search)", "semantic"),
    ]:
        if key in results and results[key]:
            output += _format_one_section(key, label, results[key], results, top_k, style)
            has_results = True

    # project + thirdparty symbols + semantic
    for kb, label in [("project", "Project"), ("thirdparty", "Third-party")]:
        for suffix, sublabel, style in [
            ("symbols", "symbols", "detailed"),
            ("semantic_classes", "classes (semantic search)", "semantic"),
            ("semantic_functions", "functions/procedures (semantic search)", "semantic"),
        ]:
            key = f"{kb}_{suffix}"
            if key in results and results[key]:
                output += _format_one_section(key, f"{label} {sublabel}", results[key], results, top_k, style)
                has_results = True

    # Reference query results
    for ref_key, label in [("project_references", "Project references"), ("thirdparty_references", "Third-party references")]:
        if ref_key in results and results[ref_key]:
            refs = results[ref_key]
            output += f"{label} ({len(refs)} file references):\n"
            for r in refs[:top_k]:
                fi = r.get("file", {})
                imported = r.get("imported_by", [])
                output += f"  - {fi.get('full_path', '?')}\n"
                if imported:
                    output += f"    Referenced units: {', '.join(imported[:5])}\n"
            output += _trunc_hint(refs, results, None, top_k)
            output += "\n"
            has_results = True

    # Example knowledge base results
    if "example" in results and results["example"]:
        ex_list = results["example"]
        output += f"Example knowledge base ({len(ex_list)}):\n"
        for i, ex in enumerate(ex_list[:top_k], 1):
            title = ex.get("title", "N/A")
            full_path = ex.get("full_path", ex.get("path", ""))
            source = ex.get("source", "")
            snippet = ex.get("snippet", "")
            output += f"  {i}. {title}\n"
            if full_path:
                output += f"     Path: {full_path}\n"
            if source:
                output += f"     Source: {source}\n"
            if snippet:
                output += f"     Snippet: {snippet}\n"
        output += _trunc_hint(ex_list, results, None, top_k)
        output += "\n"
        has_results = True

    # Asynchronous rebuild task info
    if "project_async_task_id" in results:
        output += (
            f"[Background rebuild] Project source changes detected; asynchronous rebuild started automatically.\n"
            f"  Check progress via async_task(action='status', task_id='{results['project_async_task_id']}').\n"
            f"  Search again after the rebuild completes to get the latest data.\n\n"
        )
        has_results = True

    # Notice messages
    if "project_warning" in results and results["project_warning"]:
        output += f"[Notice] {results['project_warning']}\n\n"
        has_results = True

    # Single-word query: document KB shown later
    if "document" in results and not _is_document_first:
        doc_fmt = _format_document_results(results["document"], top_k)
        if doc_fmt:
            output += doc_fmt
            has_results = True

    # Error messages
    for err_key, label in [("project_error", "Project"), ("thirdparty_error", "Third-party"), ("delphi_error", "Delphi")]:
        if err_key in results and results[err_key]:
            output += f"[{label}] Error: {results[err_key]}\n\n"
            has_results = True

    if not has_results:
        output += "No relevant content found\n"
    return output


def _format_one_section(
    key: str, label: str, items: list, results: dict, top_k: int, style: str
) -> str:
    """Format a single result section

    style:
    - 'detailed': uses _format_symbol(r) + definition (delphi/project/thirdparty symbols)
    - 'all': uses kind_code → _KIND_DESC + name (delphi_all)
    - 'simple': uses just name (delphi_classes, delphi_functions)
    - 'semantic': uses (name, sim) tuple format (semantic_*)
    """
    out = f"{label} ({len(items)}):\n"
    if style == "semantic":
        for name, sim in items[:top_k]:
            out += f"  - {name} (similarity: {sim:.2f})\n"
    elif style == "detailed":
        for r in items[:top_k]:
            out += _format_symbol(r)
            if r.get('definition'):
                out += f"    Definition: {r.get('definition')}\n"
    elif style == "all":
        for r in items[:top_k]:
            kind_code = r.get('kind_code', '')
            type_desc = _KIND_DESC.get(kind_code, r.get('kind', kind_code))
            out += f"  - {r.get('name', 'N/A')} ({type_desc})\n"
    elif style == "simple":
        for r in items[:top_k]:
            out += f"  - {r.get('name', 'N/A')}\n"
    total_key = f"{key}_total" if f"{key}_total" in results else None
    out += _trunc_hint(items, results, total_key, top_k)
    out += "\n"
    return out


async def build_unified_knowledge_base(arguments: Any) -> CallToolResult:
    """
    Unified knowledge base building
    
    Parameters:
    - kb_type: "delphi"|"project"|"thirdparty"|"help"|"all" knowledge base type, combinations supported (e.g. "delphi,project")
    - project_path: Project path (only needed for project type)
    - version: Delphi version (only needed for delphi/thirdparty)
    - async_mode: Whether to run asynchronously
    - rebuild: Whether to force rebuild
    """
    kb_type = arguments.get("kb_type", "all")
    project_path = _resolve_project_path(arguments.get("project_path"))
    version = arguments.get("version")
    async_mode = arguments.get("async_mode", True)
    rebuild = arguments.get("rebuild", False)
    
    # Parse knowledge base types
    if kb_type == "all":
        kb_types = ["delphi", "project", "thirdparty"]
    elif isinstance(kb_type, str):
        kb_types = [k.strip() for k in kb_type.split(",")]
    else:
        kb_types = [kb_type]
    
    results = {}
    
    for kb in kb_types:
        try:
            if kb == "delphi" and _delphi_kb_service:
                # Close existing connections before build (SQLiteVectorKnowledgeBase opens in WAL mode, which blocks other connections)
                _delphi_kb_service.close()
                success = _delphi_kb_service.build_knowledge_base(version=version, rebuild=rebuild)
                results["delphi"] = "success" if success else "failed"
            elif kb == "project" and project_path:
                pkb = _get_or_create_pkb(project_path, fresh=True)
                try:
                    success = pkb.build_project_knowledge_base(rebuild=rebuild)
                    results["project"] = "success" if success else "failed"
                finally:
                    pkb.close()
            elif kb == "thirdparty" and _thirdparty_kb_service:
                _thirdparty_kb_service.close()
                success = _thirdparty_kb_service.build_thirdparty_knowledge_base(version=version, rebuild=rebuild)
                results["thirdparty"] = "success" if success else "failed"
            elif kb == "example":
                ekb = _get_example_kb()
                if ekb:
                    success = ekb.build_example_knowledge_base(rebuild=rebuild)
                    results["example"] = "success" if success else "failed"
                else:
                    results["example"] = "Error: Failed to create example knowledge base"
            elif kb == "document":
                from pathlib import Path as _Path
                server_root = _Path(__file__).parent.parent.parent
                doc_kb_dir = server_root / "data" / "document-knowledge-base"
                doc_kb_dir.mkdir(parents=True, exist_ok=True)

                # Auto-detect Delphi help directory
                directory = arguments.get("directory")
                if not directory:
                    detected = _auto_detect_delphi_help_dir()
                    if detected:
                        directory = detected
                        logger.info(f"Auto-detected Delphi help directory: {directory}")
                if not directory:
                    results["document"] = "Skipped: no directory specified and no Delphi help directory detected"
                    continue

                extensions = arguments.get("extensions", [".chm"])
                exclude = arguments.get("exclude")

                from ..services.knowledge_base.scan_generic_documents import GenericDocumentScanner
                scanner = GenericDocumentScanner(str(doc_kb_dir))
                scan_result = scanner.scan_directory(
                    directory, extensions=extensions,
                    exclude=exclude, rebuild=rebuild
                )
                if scan_result.get("error"):
                    results["document"] = f"Scan failed: {scan_result['error']}"
                    continue

                total = scan_result.get("total_files", 0) or scan_result.get("processed", 0)

                # Scanner writes directly to ZVec, no export needed
                results["document"] = f"success ({total} files, ZVec built)"
        except Exception as e:
            results[kb] = f"Error: {str(e)}"
    
    # Format output
    output = f"Build knowledge base ({kb_type}):\n\n"
    for kb, status in results.items():
        output += f"- {kb}: {status}\n"
    
    # Automatically clean up old SQLite files after a successful build
    cleanup_parts = []
    for kb in kb_types:
        if results.get(kb) in ("success",):
            clean_info = _cleanup_old_kb_data(kb)
            if clean_info["deleted"]:
                cleanup_parts.append(
                    f"  {kb}: cleaned up {len(clean_info['deleted'])} old files"
                    f" (freed {clean_info['freed_mb']} MB)"
                )
    if cleanup_parts:
        output += "\nOld file cleanup:\n" + "\n".join(cleanup_parts) + "\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])



async def get_unified_knowledge_stats(arguments: Any) -> CallToolResult:
    """
    Unified knowledge base statistics retrieval
    
    Parameters:
    - kb_type: "delphi"|"project"|"thirdparty"|"all"
    - project_path: Project path (only needed for project)
    """
    kb_type = arguments.get("kb_type", "all")
    
    # Parse knowledge base types
    if kb_type == "all":
        kb_types = ["delphi", "project", "thirdparty"]
    elif isinstance(kb_type, str):
        kb_types = [k.strip() for k in kb_type.split(",")]
    else:
        kb_types = [kb_type]
    
    results = {}
    
    for kb in kb_types:
        try:
            if kb == "delphi" and _delphi_kb_service:
                stats = _delphi_kb_service.get_statistics()
                # Map keys to expected format
                stats["total_documents"] = stats.get("files", 0)
                stats["total_classes"] = stats.get("classes", 0)
                stats["procedures"] = stats.get("procedures", 0)
                results["delphi"] = stats
            elif kb == "project":
                project_path = _resolve_project_path(arguments.get("project_path"))
                if not project_path:
                    results["project"] = {"error": "Please provide the project_path parameter (no .dproj file auto-detected in the current directory)"}
                else:
                    try:
                        pkb = _get_or_create_pkb(project_path)
                        ok = pkb.load_knowledge_bases()
                        if not ok or not pkb.project_kb:
                            results["project"] = {"error": "Failed to load project knowledge base; please build it first (.delphi-kb/zvec_project/ does not exist)"}
                        else:
                            full_stats = pkb.get_statistics()
                            results["project"] = full_stats.get("project") or {"error": "Project statistics are empty"}
                    except Exception as e:
                        results["project"] = {"error": str(e)}
            elif kb == "thirdparty" and _thirdparty_kb_service:
                stats = _thirdparty_kb_service.get_statistics()
                results["thirdparty"] = stats
            elif kb == "example":
                ekb = _get_example_kb()
                if ekb:
                    s = ekb.get_statistics()
                    results["example"] = {
                        "files": s.get("files", 0),
                        "total_documents": s.get("files", 0),
                        "last_build_time": s.get("last_build_time", ""),
                        "last_build_duration": s.get("last_build_duration"),
                        "database_size_mb": s.get("database_size_mb", 0),
                    }
                else:
                    results["example"] = {"error": "Failed to create example knowledge base"}
        except Exception as e:
            results[kb] = {"error": str(e)}
    
    # Format output
    # If kb_type=all or includes document, add document knowledge base statistics
    if kb_type in ("all", "document"):
        try:
            from src.services.knowledge_base.schema import use_connection
            server_root = Path(__file__).parent.parent.parent
            doc_kb_dir = server_root / "data" / "document-knowledge-base"
            db_path = doc_kb_dir / "documents.sqlite"
            if db_path.exists():
                with use_connection(str(db_path), use_wal=False) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM documents")
                    total = cursor.fetchone()[0]
                    cursor.execute("SELECT extension, COUNT(*) FROM documents GROUP BY extension ORDER BY COUNT(*) DESC")
                    by_ext = dict(cursor.fetchall())
                    cursor.execute("SELECT content_type, COUNT(*) FROM documents GROUP BY content_type ORDER BY COUNT(*) DESC")
                    by_type = dict(cursor.fetchall())
                db_stat = db_path.stat()
                db_size_mb = round(db_stat.st_size / (1024 * 1024), 2)
                from datetime import datetime
                last_build = datetime.fromtimestamp(db_stat.st_mtime).isoformat()
                results["document"] = {
                    "total_documents": total,
                    "by_type": by_type,
                    "by_extension": by_ext,
                    "database_size_mb": db_size_mb,
                    "last_build_time": last_build,
                }
            elif _kb_dir_has_zvec_data(doc_kb_dir):
                # documents.sqlite has been cleaned up; read statistics from ZVec
                try:
                    import zvec
                    col = zvec.open(str(doc_kb_dir))
                    stats = col.stats
                    doc_count = getattr(stats, "doc_count", 0) if stats else 0
                    results["document"] = {
                        "total_documents": doc_count,
                        "database_size_mb": "ZVec",
                        "last_build_time": "after migration (documents.sqlite cleaned up)",
                        "note": "Statistics source: ZVec (flattened to root directory)",
                    }
                except Exception as zve:
                    results["document"] = {"error": f"doc_kb/ exists but ZVec read failed: {zve}"}
            else:
                results["document"] = {"error": f"Document knowledge base does not exist: {doc_kb_dir}"}
        except Exception as e:
            results["document"] = {"error": str(e)}
    
    output = f"Knowledge base statistics ({kb_type}):\n\n"
    
    for kb, stats in results.items():
        output += f"[{kb.upper()}]\n"
        if isinstance(stats, dict) and "error" in stats:
            output += f"  Error: {stats['error']}\n"
        else:
            if isinstance(stats, dict) and 'by_type' in stats and 'total_documents' in stats:
                # Document KB stats has different key structure (by_type + total_documents)
                output += f"  Total documents: {stats.get('total_documents', 0)}\n"
                db_size = stats.get('database_size_mb')
                if db_size is not None:
                    output += f"  Database: {db_size:.2f} MB\n"
                bt = stats.get('last_build_time')
                if bt:
                    output += f"  Last build: {bt[:16].replace('T', ' ')}\n"
                by_type = stats.get('by_type', {})
                if by_type:
                    output += f"  By type:\n"
                    for ct, cnt in by_type.items():
                        output += f"    {ct}: {cnt}\n"
                by_ext = stats.get('by_extension', {})
                if by_ext:
                    output += f"  By extension:\n"
                    for ext, cnt in sorted(by_ext.items(), key=lambda x: x[1], reverse=True):
                        output += f"    {ext}: {cnt}\n"
                continue
            output += f"  Files: {stats.get('total_documents', stats.get('files', 0))}\n"
            output += f"  Classes: {stats.get('total_classes', stats.get('classes', 0))}\n"
            output += f"  Database: {stats.get('database_size_mb', 0):.2f} MB\n"
            bt = stats.get('last_build_time')
            dur = stats.get('last_build_duration')
            if bt:
                output += f"  Last build: {bt[:16].replace('T', ' ')}"
                if dur is not None:
                    output += f" (took {dur//60}min {dur%60}s)" if dur >= 60 else f" (took {dur}s)"
                output += "\n"
            # File type/extension distribution
            by_ext = stats.get('by_extension', {})
            if by_ext:
                output += f"  File type distribution:\n"
                for ext, cnt in sorted(by_ext.items(), key=lambda x: x[1], reverse=True):
                    output += f"    {ext}: {cnt}\n"
        output += "\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])