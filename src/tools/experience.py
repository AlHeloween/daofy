"""
experience MCP tool — experience memory management

Dispatches operations via the action parameter; semantic search reuses embedding_service.

New suggest action: analyzes recent tool call history, automatically detects
experience save opportunities, and pre-fills problem/solution/tags/context
drafts for the AI to review and save.
"""

import json
from typing import Any, Optional
from ..services.experience_service import get_experience_service
from ..services.experience_tracker import get_tracker

import logging
logger = logging.getLogger(__name__)


def experience(**kwargs) -> dict:
    """Unified entry point for the experience memory tool.

    Dispatches to the specific operation via the action parameter.

    Args:
        action: the operation type
        **kwargs: parameters for each operation

    Returns:
        dict: the result
    """
    action = kwargs.pop("action", "")
    svc = get_experience_service()

    try:
        if action == "save":
            return _act_save(svc, **kwargs)
        elif action == "search":
            return _act_search(svc, **kwargs)
        elif action == "get":
            return _act_get(svc, **kwargs)
        elif action == "list":
            return _act_list(svc, **kwargs)
        elif action == "update":
            return _act_update(svc, **kwargs)
        elif action == "merge":
            return _act_merge(svc, **kwargs)
        elif action == "prune":
            return _act_prune(svc, **kwargs)
        elif action == "delete":
            return _act_delete(svc, **kwargs)
        elif action == "rebuild_embedding":
            return _act_rebuild_embedding(svc, **kwargs)
        elif action == "suggest":
            return _act_suggest(**kwargs)
        else:
            return _err(f"Unknown action: {action}, available: save/search/get/list/update/merge/prune/delete/rebuild_embedding/suggest")
    except Exception as e:
        logger.exception("experience execution failed")
        return _err(str(e))


def _ok(msg: str, data: Any = None) -> dict:
    result = {"status": "ok", "message": msg}
    if data is not None:
        result["data"] = data
    return result


def _err(msg: str) -> dict:
    return {"status": "failed", "message": msg}


def _fmt_experience(exp: dict) -> str:
    """Format a single experience as readable text"""
    tags = exp.get("tags", [])
    tools = exp.get("tools_used", [])
    sim = exp.get("similarity")
    lines = [
        f"ID: {exp['id']}",
        f"problem: {exp['problem']}",
        f"solution: {exp['solution']}",
    ]
    if tags:
        lines.append(f"tags: {', '.join(tags)}")
    if tools:
        lines.append(f"tools: {', '.join(tools)}")
    if sim is not None:
        lines.append(f"match: {sim:.2%}")
    lines.append(f"used: {exp.get('hit_count', 0)}x")
    return "\n".join(lines)


# ── Action handlers ──


def _act_save(svc, **kw):
    problem = kw.get("problem", "").strip()
    solution = kw.get("solution", "").strip()
    if not problem or not solution:
        return _err("Missing required parameters: problem (problem description) and solution (solution steps)")

    tools_used = kw.get("tools_used")
    context = kw.get("context")
    tags = kw.get("tags")

    # Search for similar experiences before saving, to remind the AI to generalize
    # Note: svc.save() also does >0.85 dedup merging internally; the >0.7 check here is an extra reminder layer
    # If the user does not force, return a warning and abort the save (let the AI choose merge/update)
    # If the user sets force=true, skip the reminder and let svc.save()'s >0.85 logic handle final dedup
    _force = kw.get("force", False)
    if not _force:
        try:
            similar = svc.search(query=problem, top_k=3)
            high_match = [s for s in similar if s.get("similarity", 0) > 0.7]
            if high_match:
                lines = ["⚠️ Found highly similar experiences; consider merging via merge/update instead of saving separately:"]
                for s in high_match:
                    lines.append(f"  [{s['similarity']:.0%}] {s['id']} {s['problem'][:60]}")
                lines.append("To merge after confirming, cancel this save and use:")
                best_id = high_match[0]['id']
                lines.append(f'  experience(action=merge, ids=["...", "{best_id}"]')
                lines.append(f'  or experience(action=update, id="{best_id}", ...)')
                lines.append("If you still need a new save, set force=true to skip this check")
                return _ok("\n".join(lines), data={"similar": [s["id"] for s in high_match]})
        except Exception as e:
            logger.debug("Experience dedup search failed (does not affect the save flow): %s", e)


    result = svc.save(
        problem=problem,
        solution=solution,
        tools_used=tools_used,
        context=context,
        tags=tags,
    )
    return _ok(
        f"saved\n  ID: {result['id']}\n  problem: {problem[:80]}",
        data=result,
    )


def _act_search(svc, **kw):
    query = kw.get("query", "").strip()
    if not query:
        return _err("Missing required parameter: query (search keywords)")

    top_k = int(kw.get("top_k", 5))
    tags = kw.get("tags")

    results = svc.search(query=query, top_k=top_k, tags=tags)
    if not results:
        return _ok(f"no results (query: {query})", data=[])

    lines = [f"{len(results)} results:"]
    for exp in results:
        sim = exp.get("similarity", 0)
        sim_str = f" [match:{sim:.2%}]" if sim else ""
        lines.append("")
        lines.append(f"{exp['problem']}{sim_str}")
        lines.append(f"  ID: {exp['id']}")
        lines.append(f"  solution: {exp['solution'][:200]}")
        if exp.get("tags"):
            lines.append(f"  tags: {', '.join(exp['tags'])}")

    return _ok("\n".join(lines), data=results)


def _act_get(svc, **kw):
    exp_id = kw.get("id", "").strip()
    if not exp_id:
        return _err("Missing required parameter: id (experience ID)")

    result = svc.get(exp_id)
    if result is None:
        return _err(f"Experience not found: {exp_id}")

    return _ok(f"detail:\n{_fmt_experience(result)}", data=result)


def _act_list(svc, **kw):
    tags = kw.get("tags")
    sort_by = kw.get("sort_by", "updated_at")
    limit = int(kw.get("limit", 20))

    results = svc.list(tags=tags, sort_by=sort_by, limit=limit)
    if not results:
        return _ok("no records", data=[])

    lines = [f"{len(results)} records:"]
    for exp in results:
        tags_str = f" [{', '.join(exp.get('tags', []))}]" if exp.get("tags") else ""
        lines.append(f"  - {exp['problem'][:60]} - used {exp.get('hit_count', 1)}x{tags_str}")

    return _ok("\n".join(lines), data=results)


def _act_update(svc, **kw):
    exp_id = kw.get("id", "").strip()
    if not exp_id:
        return _err("Missing required parameter: id (experience ID)")

    solution = kw.get("solution")
    tags = kw.get("tags")
    problem = kw.get("problem")
    tools_used = kw.get("tools_used")
    context = kw.get("context")

    if solution is None and tags is None and problem is None and tools_used is None and context is None:
        return _err("At least one update field must be provided: solution/tags/problem/tools_used/context")

    result = svc.update(exp_id=exp_id, solution=solution, tags=tags, problem=problem, tools_used=tools_used, context=context)
    if result is None:
        return _err(f"Experience not found: {exp_id}")

    return _ok(f"updated: {exp_id}", data=result)


def _act_merge(svc, **kw):
    ids = kw.get("ids")
    if not ids or not isinstance(ids, list) or len(ids) < 2:
        return _err("Missing required parameter: ids (a list of at least 2 experience IDs, e.g. ids=['a','b'])")
    ids = [i.strip() for i in ids if i.strip()]
    keep = kw.get("keep")
    result = svc.merge(ids, keep=keep)
    if result is None:
        return _err("Merge failed; please check whether the IDs are valid")
    return _ok(f"merged {len(ids)} records into {result['id']}", data=result)


def _act_prune(svc, **kw):
    limit = int(kw.get("limit", 20))
    results = svc.prune_list(limit=limit)
    if not results:
        return _ok("no stale records found", data=[])
    lines = [f"{len(results)} low-value records (ascending value):"]
    for r in results:
        tags_str = f" [{', '.join(r.get('tags', []))}]" if r.get("tags") else ""
        lines.append(
            f"  value={r['value']:.3f}  hits={r['hit_count']}  "
            f"{r['problem'][:60]}{tags_str}"
        )
    return _ok("\n".join(lines), data=results)

def _act_delete(svc, **kw):
    exp_id = kw.get("id", "").strip()
    if not exp_id:
        return _err("Missing required parameter: id (experience ID)")

    ok = svc.delete(exp_id)
    if not ok:
        return _err(f"Experience not found: {exp_id}")

    return _ok(f"deleted: {exp_id}")


def _act_rebuild_embedding(svc, **kw):
    result = svc.rebuild_embeddings()
    if "error" in result:
        return _err(result["error"])
    lines = [f"Experience embedding rebuild complete:"]
    lines.append(f"  total records: {result['total']}")
    lines.append(f"  existing vectors: {result['skipped']}")
    lines.append(f"  rebuilt this run: {result['rebuilt']}")
    lines.append(f"  failed: {result['failed']}")
    return _ok("\n".join(lines), data=result)


def _act_suggest(**kw) -> dict:
    """Analyze recent tool call history, automatically detect experience save opportunities, and pre-fill drafts.

    Returns pre-filled problem/solution/tags/context for the AI to review and
    then call experience(action="save", ...) to formally save.
    """
    tracker = get_tracker()
    draft = tracker.suggest()
    if draft is None:
        return _ok(
            "No experience worth saving detected.\n"
            "  suggest requires 2+ tool calls and one of the following patterns:\n"
            "  - fix_cycle:  compile failed → modify code → compile succeeded\n"
            "  - learn_apply: query knowledge base → modify code → compile succeeded\n"
            "  - clean_fix:  modify code → compile succeeded (no preceding failure)"
        )

    # Format the output
    lines = [
        "📋 Experience save opportunity detected; after review, use the following command to save:",
        "",
        f"experience(action=\"save\",",
        f'  problem="""{draft["problem"]}""",',
        f'  solution="""{draft["solution"]}""",',
        f'  tags={json.dumps(draft["tags"], ensure_ascii=False)},',
        f'  context={json.dumps(draft["context"], ensure_ascii=False)},',
        f'  force=true',
        f")",
    ]
    note = (
        "\n💡 Suggestion: after review, generalize the problem description (remove auto markers, "
        "abstract to common scenarios); you can use force=true to skip the >0.7 dedup reminder layer."
    )

    return _ok(
        "\n".join(lines) + note,
        data=draft,
    )

