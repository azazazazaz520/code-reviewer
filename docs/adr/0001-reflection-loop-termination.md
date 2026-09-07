# Reflection Loop 采用硬限制+软判断双保险终止策略

> 状态：已废弃（2026-09-07）。当前流程不再执行 Reflection Loop，详见 ADR 0003。

Reflection Node 评估 Findings 后可能回退到 Collect Context，形成闭环。为防止无限循环，采用硬限制（max_reflection_rounds = 3）作为安全网，同时 Reflection Prompt 中明确终止软标准（findings 引用具体代码行 + 已读文件覆盖所有引用 + Reviewer confidence 标记）。两者结合，兼顾 Agent 的探索灵活性和系统稳定性。

**Considered Options**: 纯 LLM 自由裁量（可能无限循环，Token 成本不可控）；纯硬限制（可能过早终止，丢失发现）；硬限制+软判断（选中方案）。

**Consequences**: 需要在 ReviewState 中增加 `reflection_round` 计数器；Reflection Prompt 需编码终止判断标准。
