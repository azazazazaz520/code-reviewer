from __future__ import annotations

from typing import Literal

from app.engine.prompt.schemas import PromptResult


ExportFormat = Literal["markdown", "jira", "issue"]


def _result(value: PromptResult | dict) -> PromptResult:
    return value if isinstance(value, PromptResult) else PromptResult.model_validate(value)


def export_markdown(value: PromptResult | dict) -> str:
    result = _result(value)
    solutions = "\n".join(f"{index}. {item}" for index, item in enumerate(result.solution, 1))
    mappings = "\n".join(
        f"- `{item.original}` → **{item.professional}**：{item.reason}"
        for item in result.term_mappings
    ) or "- 无候选术语映射"
    checks = "\n".join(f"- {item}" for item in result.checks) or "- 无"
    assumptions = "\n".join(f"- {item}" for item in result.assumptions) or "- 无"
    return (
        f"# {result.team_message}\n\n"
        f"## 问题现象\n{result.problem_phenomenon}\n\n"
        f"## 技术本质\n{result.technical_essence}\n\n"
        f"## 解决方案\n{solutions}\n\n"
        f"## 分类\n{result.classification.type.value}（置信度 {result.classification.confidence:.0%}）\n"
        f"{result.classification.reason}\n\n"
        f"## Bug 视角\n{result.bug_view}\n\n"
        f"## 需求视角\n{result.prd_view}\n\n"
        f"## 术语对照\n{mappings}\n\n"
        f"## 待确认事项\n{checks}\n\n"
        f"## 前提假设\n{assumptions}\n"
    )


def export_jira(value: PromptResult | dict) -> str:
    result = _result(value)
    solutions = "\n".join(f"* {item}" for item in result.solution)
    return (
        f"h2. 问题现象\n{result.problem_phenomenon}\n\n"
        f"h2. 技术本质\n{result.technical_essence}\n\n"
        f"h2. 解决方案\n{solutions}\n\n"
        f"h2. 需求与缺陷视角\n{result.bug_view}\n\n{result.prd_view}\n\n"
        f"h2. 沟通摘要\n{result.team_message}"
    )


def export_issue(value: PromptResult | dict) -> str:
    result = _result(value)
    solutions = "\n".join(f"- [ ] {item}" for item in result.solution)
    checks = "\n".join(f"- [ ] {item}" for item in result.checks) or "- [ ] 无"
    return (
        f"## 问题描述\n{result.problem_phenomenon}\n\n"
        f"## 技术背景\n{result.technical_essence}\n\n"
        f"## 实施清单\n{solutions}\n\n"
        f"## 验收与待确认\n{checks}\n\n"
        f"## 分类\n`{result.classification.type.value}`\n\n"
        f"## 沟通摘要\n{result.team_message}\n"
    )


def export_text(value: PromptResult | dict, export_format: ExportFormat) -> str:
    exporters = {
        "markdown": export_markdown,
        "jira": export_jira,
        "issue": export_issue,
    }
    return exporters[export_format](value)
