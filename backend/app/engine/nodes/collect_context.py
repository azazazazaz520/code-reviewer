"""Node: 收集变更文件内容到上下文缓存。

先建立候选文件集合，再按轮次增量读取，避免 Reflection 重复读取同一批文件。
CRG 的结构性影响在上下文收集完成后才可用，作为硬触发器补入审查计划。
"""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.engine.state import ReviewState
from app.engine.crg import try_crg_context
from app.engine.tools.read_file import read_file


def collect_context_node(state: ReviewState) -> ReviewState:
    repo_path = state.get("repo_id", ".")
    changed_files = state.get("changed_files", [])

    if not state.get("review_plan"):
        state["context_initialized"] = True
        state["context_candidates"] = []
        if hook := state.get("_log_hook"):
            hook(
                step="collect_context",
                level="info",
                message="当前变更由确定性校验器覆盖，无需收集 LLM 上下文",
            )
        return state

    if hook := state.get("_log_hook"):
        hook(step="collect_context", level="info",
             message=f"正在收集文件上下文 ({len(state.get('changed_files', []))} 个文件)...")

    # 只在第一轮建立候选文件集合；后续 Reflection 只读取下一批。
    if not state.get("context_initialized"):
        state["context_initialized"] = True
        if settings.crg_enabled and try_crg_context(state, repo_path, changed_files):
            state["crg_enabled"] = True
        else:
            state["crg_enabled"] = False
            state["context_candidates"] = list(dict.fromkeys(changed_files))

    candidates = state.get("context_candidates", changed_files)
    cache = dict(state.get("file_context_cache", {}))
    round_number = state.get("context_round", 0)
    batch_size = max(1, settings.context_files_per_round)
    start = round_number * batch_size
    batch = candidates[start:start + batch_size]

    new_count = 0
    for file_path in batch:
        if file_path in cache:
            continue
        full_path = Path(repo_path) / file_path
        cache[file_path] = read_file(str(full_path), start_line=1, max_lines=200)
        new_count += 1

    state["context_round"] = round_number + 1
    state["file_context_cache"] = cache

    # CRG 的结构性影响在上下文收集完成后才可用，作为硬触发器补入计划。
    impact = state.get("impact_radius")
    if impact and (
        impact.get("impacted_nodes", 0) > 20
        or impact.get("changed_nodes", 0) > 5
    ):
        if "security_reviewer" not in state.get("review_plan", []):
            state.setdefault("review_plan", []).append("security_reviewer")

    source = "CRG" if state.get("crg_enabled") else "Normal"
    if hook := state.get("_log_hook"):
        hook(
            step="collect_context",
            level="info",
            message=(
                f"已收集 {len(cache)} 个文件 ({source})，"
                f"本轮新增 {new_count} 个"
            ),
        )

    return state
