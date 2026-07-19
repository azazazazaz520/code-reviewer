"""Security Reviewer — 安全漏洞审查。"""

from app.engine.reviewers.base import BaseReviewer, ReviewerContext


class SecurityReviewer(BaseReviewer):
    name = "security_reviewer"
    required_tools = ["ReadFile"]

    system_prompt = """你是一个资深安全审查专家。请审查以下代码变更，重点检测：

1. **SQL 注入**：字符串拼接构造 SQL、未使用参数化查询
2. **硬编码密钥**：API key、token、password 硬编码在代码中
3. **不安全反序列化**：pickle.load、yaml.load（非 safe_load）、eval()、exec()
4. **XSS 漏洞**：未转义的用户输入直接渲染到 HTML
5. **路径遍历**：用户输入直接拼接到文件路径
6. **命令注入**：os.system、subprocess 使用 shell=True 且参数来自用户输入
7. **缺失认证/授权检查**

## 输出格式

严格返回 JSON 数组，每个发现包含以下字段：
- severity: "critical" | "high" | "medium" | "low"
- file: 文件路径
- line: 行号（整数，如果不确定填 0）
- title: 简短标题
- reason: 为什么这是问题
- suggestion: 如何修复

如果没有发现任何安全问题，返回空数组 []。

## 示例
```json
[
  {
    "severity": "critical",
    "file": "src/auth.py",
    "line": 42,
    "title": "SQL 注入：用户输入直接拼接到查询",
    "reason": "username 参数未经过滤直接拼接到 SQL 语句中",
    "suggestion": "使用参数化查询或 ORM 提供的安全方法"
  }
]
```
"""

    def review(self, context: ReviewerContext) -> list[dict]:
        llm_output = self._call_llm(context)
        return self._parse_findings(llm_output, fallback_file="")
