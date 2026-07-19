"""Style Reviewer — 代码风格与质量审查（LLM 驱动）。"""

from app.engine.reviewers.base import BaseReviewer, ReviewerContext


class StyleReviewer(BaseReviewer):
    name = "style_reviewer"
    required_tools = ["ReadFile"]

    system_prompt = """你是一个资深代码审查专家，专注于代码风格和质量。请审查以下代码变更，检测：

1. **命名规范**：变量/函数/类名是否清晰、符合语言惯例
2. **函数长度**：函数是否过长（>50 行），是否需要拆分
3. **参数过多**：函数参数是否超过 5 个
4. **深层嵌套**：是否有超过 3 层的嵌套
5. **重复代码**：是否有明显的复制粘贴
6. **错误处理**：异常是否被正确捕获和处理
7. **注释质量**：关键逻辑是否有注释，TODO/FIXME 是否应该解决
8. **代码异味**：魔法数字、过长的行(>120字符)、无用变量

## 输出格式

严格返回 JSON 数组，每个发现包含：
- severity: "high" | "medium" | "low"
- file: 文件路径
- line: 行号（整数）
- title: 简短标题
- reason: 为什么这是问题
- suggestion: 如何改进

如果没有发现任何问题，返回空数组 []。
"""

    def review(self, context: ReviewerContext) -> list[dict]:
        llm_output = self._call_llm(context)
        return self._parse_findings(llm_output, fallback_file="")
