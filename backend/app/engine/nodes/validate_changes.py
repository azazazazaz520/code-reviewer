"""Node: 使用确定性校验器检查可验证的变更契约。"""

from __future__ import annotations

from pathlib import Path

from app.engine.state import ReviewState
from app.engine.scope import classify_files
from app.engine.validators.release import validate_release_manifest


def validate_changes_node(state: ReviewState) -> ReviewState:
    repo_path = state.get("repo_id", ".")
    changed_files = state.get("changed_files", [])
    validator_findings: list[dict] = []
    checks: list[dict] = []

    for path, scope in classify_files(changed_files).items():
        if scope.kind != "release_manifest":
            continue

        result = validate_release_manifest(
            str(Path(repo_path) / path),
            set(),
            repo_path,
        )
        validator_findings.extend(result.findings)
        checks.extend(result.checks)

    state["validator_findings"] = validator_findings
    state["checks"] = checks
    if hook := state.get("_log_hook"):
        hook(
            step="validate_changes",
            level="info",
            message=(
                f"确定性校验完成: {len(validator_findings)} 个问题，"
                f"{len(checks)} 个检查项"
            ),
        )
    return state
