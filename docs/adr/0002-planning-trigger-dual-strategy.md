# Planning Node 采用软策略+硬触发器双层选择机制

Planning Node 决定执行哪些 Reviewer。纯 LLM 裁量存在遗漏关键审查的风险（如 LLM 误判 SQL 拼接改动不需要 Security Review）。采用双层策略：软策略由 LLM 自由决定 Plan，硬触发器由纯正则规则引擎基于文件路径/内容模式强制激活 Reviewer。两者结果合并去重。

**Considered Options**: 纯 LLM（可能遗漏关键审查）；纯正则（僵化，无法理解语义变更）；混合方案（选中）。

**Consequences**: 需要在 Reviewer 模型中增加 `trigger_patterns` 字段声明匹配规则；Planning Node 内部先运行正则引擎再调用 LLM，最终取并集。
