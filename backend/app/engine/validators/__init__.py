"""确定性审查校验器。"""

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """校验器输出：已确定的问题与检查状态分开保存。"""

    findings: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
