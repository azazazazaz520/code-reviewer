"""发布清单确定性校验。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from app.engine.validators import ValidationResult


REQUIRED_FIELDS = (
    "version",
    "download_url",
    "sha256",
    "release_notes",
    "release_url",
    "release_date",
)
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _relative_path(path: Path, repo_root: str) -> str:
    try:
        return path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return path.name


def _key_line(text: str, key: str) -> int:
    pattern = re.compile(rf'^\s*"{re.escape(key)}"\s*:')
    for line_number, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            return line_number
    return 1


def _finding(
    *,
    file_path: str,
    line: int,
    title: str,
    reason: str,
    suggestion: str,
    evidence: str,
) -> dict:
    return {
        "severity": "medium",
        "file": file_path,
        "line": line,
        "title": title,
        "reason": reason,
        "suggestion": suggestion,
        "evidence": evidence,
        "evidence_type": "static_check",
        "impact": "compatibility",
    }


def validate_release_manifest(
    path: str,
    changed_lines: set[int],
    repo_root: str,
) -> ValidationResult:
    """校验发布清单格式和字段契约。

    ``changed_lines`` 保留在接口中，供后续按变更范围细化校验；当前契约检查
    针对整个清单，因为缺少字段本身可能无法定位到某一行。
    """
    del changed_lines
    file_path = Path(path)
    display_path = _relative_path(file_path, repo_root)
    result = ValidationResult()

    try:
        text = file_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        result.findings.append(
            _finding(
                file_path=display_path,
                line=1,
                title="发布清单无法读取",
                reason=f"确定性校验器无法读取文件：{exc}",
                suggestion="确认审查快照包含该发布清单文件。",
                evidence=f"文件读取错误：{exc}",
            )
        )
        return result

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        result.findings.append(
            _finding(
                file_path=display_path,
                line=exc.lineno,
                title="发布清单不是合法 JSON",
                reason=f"JSON 解析失败：{exc.msg}",
                suggestion="修正 JSON 语法后再发布更新清单。",
                evidence=f"第 {exc.lineno} 行第 {exc.colno} 列解析失败：{exc.msg}",
            )
        )
        result.checks.append(
            {"name": "release_manifest_json", "status": "fail", "message": exc.msg}
        )
        return result

    result.checks.append(
        {"name": "release_manifest_json", "status": "pass", "message": "JSON 格式有效"}
    )

    if not isinstance(payload, dict):
        result.findings.append(
            _finding(
                file_path=display_path,
                line=1,
                title="发布清单根节点类型错误",
                reason="发布清单根节点必须是 JSON 对象。",
                suggestion="将发布清单改为包含版本字段的 JSON 对象。",
                evidence=f"JSON 根节点实际类型：{type(payload).__name__}",
            )
        )
        return result

    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        result.findings.append(
            _finding(
                file_path=display_path,
                line=1,
                title="发布清单缺少必填字段",
                reason=f"缺少字段：{', '.join(missing)}。",
                suggestion="补齐发布客户端所需的必填字段。",
                evidence=f"缺失字段列表：{', '.join(missing)}",
            )
        )
        result.checks.append(
            {
                "name": "release_manifest_required_fields",
                "status": "fail",
                "message": f"缺少字段：{', '.join(missing)}",
            }
        )
    else:
        result.checks.append(
            {
                "name": "release_manifest_required_fields",
                "status": "pass",
                "message": "必填字段齐全",
            }
        )

    version = payload.get("version")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        result.findings.append(
            _finding(
                file_path=display_path,
                line=_key_line(text, "version"),
                title="版本号格式无效",
                reason="version 不符合项目使用的三段式版本格式。",
                suggestion="使用形如 0.4.2 或带预发布标识的合法版本号。",
                evidence=f"version 实际值：{version!r}",
            )
        )
        result.checks.append(
            {"name": "release_version", "status": "fail", "message": "版本号格式无效"}
        )
    else:
        result.checks.append(
            {"name": "release_version", "status": "pass", "message": "版本号格式有效"}
        )

    sha256 = payload.get("sha256")
    if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
        result.findings.append(
            _finding(
                file_path=display_path,
                line=_key_line(text, "sha256"),
                title="SHA256 格式无效",
                reason="sha256 必须是 64 位十六进制校验和。",
                suggestion="从实际发布安装包重新计算并写入 SHA256。",
                evidence=(
                    f"sha256 实际类型：{type(sha256).__name__}，"
                    f"长度：{len(sha256) if isinstance(sha256, str) else 0}"
                ),
            )
        )
        result.checks.append(
            {"name": "release_sha256_format", "status": "fail", "message": "SHA256 格式无效"}
        )
    else:
        result.checks.append(
            {"name": "release_sha256_format", "status": "pass", "message": "SHA256 格式有效"}
        )

        result.checks.append(
            {
                "name": "release_artifact_sha256",
                "status": "unverified",
                "message": "当前校验器未获取远程 Release 安装包",
            }
        )

    for field_name in ("download_url", "release_url"):
        value = payload.get(field_name)
        expected_tokens = (
            (f"v{version}", str(version)) if isinstance(version, str) else ()
        )
        if not isinstance(value, str) or not expected_tokens or not any(
            token in value for token in expected_tokens
        ):
            expected = f"v{version}" if isinstance(version, str) else "(invalid version)"
            result.findings.append(
                _finding(
                    file_path=display_path,
                    line=_key_line(text, field_name),
                    title=f"{field_name} 与版本号不一致",
                    reason=f"{field_name} 未包含当前版本标识 {expected}。",
                    suggestion="使地址中的版本标识与 version 字段保持一致。",
                    evidence=f"{field_name} 实际值：{value!r}；期望包含：{expected}",
                )
            )
            result.checks.append(
                {
                    "name": f"release_{field_name}_version",
                    "status": "fail",
                    "message": f"{field_name} 与版本号不一致",
                }
            )
        else:
            result.checks.append(
                {
                    "name": f"release_{field_name}_version",
                    "status": "pass",
                    "message": f"{field_name} 与版本号一致",
                }
            )

    release_date = payload.get("release_date")
    try:
        if not isinstance(release_date, str):
            raise ValueError("release_date 必须是字符串")
        datetime.fromisoformat(release_date.replace("Z", "+00:00"))
    except ValueError as exc:
        result.findings.append(
            _finding(
                file_path=display_path,
                line=_key_line(text, "release_date"),
                title="release_date 格式无效",
                reason=f"release_date 不是合法 ISO 时间：{exc}。",
                suggestion="使用带时区的 ISO 8601 时间。",
                evidence=f"release_date 实际值：{release_date!r}；解析错误：{exc}",
            )
        )
        result.checks.append(
            {"name": "release_date", "status": "fail", "message": "时间格式无效"}
        )
    else:
        result.checks.append(
            {"name": "release_date", "status": "pass", "message": "时间格式有效"}
        )

    return result
