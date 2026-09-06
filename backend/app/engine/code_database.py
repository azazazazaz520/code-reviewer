"""绑定审查快照的代码数据库。"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class ReviewCodeDatabase:
    """一次审查专用的 CRG 数据库及其提取状态。"""

    database_id: str
    repo_root: str
    revision: str
    base_revision: str
    database_path: str
    database_status: str = "failed"
    extraction_status: str = "failed"
    planned_files: int = 0
    extracted_files: int = 0
    extraction_errors: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    build_tool_version: str = "unavailable"
    built_at: str = ""

    @property
    def ready(self) -> bool:
        return self.database_status == "ready"

    def metadata(self) -> dict:
        return {
            "database_id": self.database_id,
            "database_status": self.database_status,
            "extraction_status": self.extraction_status,
            "database_revision": self.revision,
            "database_base_revision": self.base_revision,
            "database_path": self.database_path,
            "planned_files": self.planned_files,
            "extracted_files": self.extracted_files,
            "extraction_errors": self.extraction_errors,
            "database_stats": self.stats,
            "build_tool_version": self.build_tool_version,
            "built_at": self.built_at,
        }

    def verify(self) -> None:
        """确认打开的 CRG 数据库仍属于当前快照 revision。"""
        if not self.ready:
            raise RuntimeError("代码数据库不可用")
        from code_review_graph.graph import GraphStore

        with GraphStore(self.database_path) as store:
            if store.get_metadata("review_revision") != self.revision:
                raise RuntimeError("代码数据库 revision 与审查快照不一致")
            if store.get_metadata("review_database_id") != self.database_id:
                raise RuntimeError("代码数据库标识与审查任务不一致")

    def get_review_context(self, changed_files: list[str]) -> dict:
        """在已验证的同一数据库上执行 CRG 影响范围查询。"""
        self.verify()
        from code_review_graph.tools.review import get_review_context

        result = get_review_context(
            changed_files=changed_files or None,
            max_depth=2,
            include_source=False,
            max_lines_per_file=200,
            repo_root=self.repo_root,
            detail_level="standard",
        )
        if result.get("status") != "ok":
            raise RuntimeError(result.get("error") or "代码数据库查询失败")
        return result


def _database_id(repo_root: str, revision: str, base_revision: str) -> str:
    digest = hashlib.sha256(
        f"{Path(repo_root).resolve()}\0{revision}\0{base_revision}".encode("utf-8")
    ).hexdigest()[:16]
    return f"crg-{revision[:12]}-{digest}"


def _package_version() -> str:
    try:
        return importlib.metadata.version("code-review-graph")
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def build_review_code_database(
    repo_root: str,
    revision: str,
    base_revision: str,
    *,
    log_hook=None,
) -> ReviewCodeDatabase:
    """在当前快照根目录建立一次全量 CRG 索引并记录失败范围。"""
    root = str(Path(repo_root).resolve())
    database_id = _database_id(root, revision, base_revision)
    built_at = datetime.now(UTC).isoformat()
    database = ReviewCodeDatabase(
        database_id=database_id,
        repo_root=root,
        revision=revision,
        base_revision=base_revision,
        database_path="",
        build_tool_version=_package_version(),
        built_at=built_at,
    )

    try:
        if not Path(root).is_dir():
            raise RuntimeError("代码数据库根目录不存在")
        from code_review_graph.graph import GraphStore
        from code_review_graph.incremental import get_db_path
        from code_review_graph.tools.build import build_or_update_graph

        database_path = Path(get_db_path(Path(root)))
        database.database_path = str(database_path)
        if log_hook:
            log_hook(
                step="build_database",
                level="info",
                message="正在为审查快照建立代码数据库...",
            )

        result = build_or_update_graph(
            full_rebuild=True,
            repo_root=root,
            postprocess="full",
        )
        errors = result.get("errors", []) if isinstance(result, dict) else []
        if not isinstance(errors, list):
            errors = [errors]
        errors = [
            error if isinstance(error, dict) else {"file": "", "error": str(error)}
            for error in errors
        ]
        # code-review-graph 的 files_parsed 已是本次发现的文件总数，errors
        # 只记录其中解析失败的文件，不能再次加到计划总数中。
        planned_files = int(result.get("files_parsed", 0)) if isinstance(result, dict) else 0

        if not database_path.is_file():
            raise RuntimeError("CRG 构建完成但数据库文件不存在")

        with GraphStore(database_path) as store:
            stats = store.get_stats()
            extracted_files = len(store.get_all_files())
            database.stats = {
                "files_count": stats.files_count,
                "total_nodes": stats.total_nodes,
                "total_edges": stats.total_edges,
                "nodes_by_kind": stats.nodes_by_kind,
                "edges_by_kind": stats.edges_by_kind,
                "languages": stats.languages,
            }
            store.set_metadata("review_database_id", database_id)
            store.set_metadata("review_revision", revision)
            store.set_metadata("review_base_revision", base_revision)
            store.set_metadata("review_root", root)
            store.set_metadata("review_build_tool", database.build_tool_version)
            store.set_metadata("review_built_at", built_at)
            store.set_metadata("review_extraction_status", "partial" if errors else "complete")
            store.set_metadata("review_extraction_errors", json.dumps(errors, ensure_ascii=False))

        database.planned_files = planned_files
        database.extracted_files = extracted_files
        database.extraction_errors = errors
        database.extraction_status = (
            "failed" if errors and extracted_files == 0 and planned_files > 0
            else "partial" if errors
            else "complete"
        )
        database.database_status = "ready"
        if log_hook:
            log_hook(
                step="build_database",
                level="warning" if errors else "info",
                message=(
                    f"代码数据库已就绪：成功索引 {extracted_files}/{planned_files} 个文件"
                    + (f"，{len(errors)} 个文件失败" if errors else "")
                ),
            )
    except Exception as exc:
        database.database_status = "failed"
        database.extraction_status = "failed"
        database.extraction_errors = [{"file": "", "error": str(exc)}]
        if log_hook:
            log_hook(
                step="build_database",
                level="error",
                message=f"代码数据库建立失败：{exc}",
            )

    return database
