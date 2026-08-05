from __future__ import annotations


BUILTIN_TERMINOLOGY: tuple[tuple[str, str, str], ...] = (
    ("不够丝滑", "响应跟手度不足或动画过渡生硬", "将体验描述拆分为响应和过渡表现"),
    ("卡顿", "交互响应延迟或渲染性能下降", "需要结合操作、设备和时间范围进一步确认"),
    ("闪退", "进程异常退出或应用崩溃", "将口语现象映射为可观测的崩溃行为"),
    ("刷新后恢复", "状态未持久化或初始化时覆盖了当前状态", "根据刷新前后状态变化提出候选原因"),
    ("不生效", "用户操作未产生预期状态变更", "保留操作、状态和预期结果之间的关系"),
    ("兼容性", "不同运行环境下的行为一致性", "提示需要明确环境、版本和复现条件"),
    ("不好用", "任务完成路径或交互可理解性存在问题", "避免把主观感受直接当作确定缺陷"),
)


def suggest_term_mappings(content: str) -> list[dict[str, str]]:
    """根据原文产生候选映射，最终是否采用由模型结合上下文判断。"""
    return [
        {"original": source, "professional": preferred, "reason": reason}
        for source, preferred, reason in BUILTIN_TERMINOLOGY
        if source in content
    ]
