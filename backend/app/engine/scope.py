"""变更范围分类与 Reviewer 选择。

范围分类只决定“使用哪种审查方式”，不负责判断某条 Finding 是否成立。
后者由 finding_gate 统一处理。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class ChangeScope:
    """单个变更文件的审查范围。"""

    path: str
    kind: str
    reason: str


SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}

CONFIG_EXTENSIONS = {".conf", ".env", ".ini", ".json", ".toml", ".xml", ".yaml", ".yml"}
DOCUMENTATION_EXTENSIONS = {".md", ".mdx", ".rst", ".txt"}
DEPENDENCY_LOCK_FILES = {
    "Cargo.lock",
    "Gemfile.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "yarn.lock",
}


def _normalise(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def classify_file(path: str) -> ChangeScope:
    """按文件语义分类，分类结果不依赖提交作者或提交消息。"""
    normalised = _normalise(path)
    pure_path = PurePosixPath(normalised)
    name = pure_path.name
    suffix = pure_path.suffix.lower()

    if name in DEPENDENCY_LOCK_FILES:
        return ChangeScope(normalised, "dependency_lock", "依赖解析锁定文件")

    if normalised.startswith(".github/workflows/"):
        return ChangeScope(normalised, "ci_workflow", "持续集成与发布工作流")

    if normalised.startswith("update/") and suffix == ".json":
        return ChangeScope(normalised, "release_manifest", "自动更新发布清单")

    generated_prefixes = ("build/", "dist/", "target/", ".codegraph/")
    if normalised.startswith(generated_prefixes) or ".generated." in name:
        return ChangeScope(normalised, "generated_artifact", "构建或生成产物")

    if suffix in SOURCE_EXTENSIONS:
        return ChangeScope(normalised, "source_code", "源码文件")

    if suffix in DOCUMENTATION_EXTENSIONS:
        return ChangeScope(normalised, "documentation", "文档文件")

    if suffix in CONFIG_EXTENSIONS:
        return ChangeScope(normalised, "configuration", "配置或数据文件")

    return ChangeScope(normalised, "unknown", "未识别文件类型")


def classify_files(changed_files: list[str]) -> dict[str, ChangeScope]:
    """返回文件路径到范围分类的映射。"""
    return {scope.path: scope for scope in (classify_file(path) for path in changed_files)}


def build_review_plan(changed_files: list[str], diff: str) -> list[str]:
    """根据变更范围选择 Reviewer，不为未知文件默认启用 Style Reviewer。"""
    scopes = list(classify_files(changed_files).values())
    plan: list[str] = []

    if any(scope.kind == "source_code" for scope in scopes):
        plan.append("style_reviewer")

    if any(scope.kind == "source_code" and scope.path.endswith(".py") for scope in scopes):
        plan.append("performance_reviewer")

    security_scopes = {"source_code", "configuration", "ci_workflow"}
    security_keywords = (
        "sql",
        "password",
        "token",
        "secret",
        "pickle",
        "yaml.load",
        "eval(",
        "exec(",
        "subprocess",
        "os.system",
        "shell=true",
    )
    if any(scope.kind in security_scopes for scope in scopes):
        lowered_diff = diff.lower()
        if any(keyword in lowered_diff for keyword in security_keywords):
            plan.append("security_reviewer")

    return list(dict.fromkeys(plan))
