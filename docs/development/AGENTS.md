# Public Contribution Guide — PPT-AI-Assistant

> 这是公开仓库的 AGENTS.md。Private Dev Repo 使用完整版 `AGENTS.md`。

## 项目定位

本地 AI-PPT 提效工具。个人 / 小团队使用。不做 SaaS、多租户、登录权限体系。

## 核心原则

1. **产品主线优先**：PPT 质量提升是唯一产品主线。Workbench、模板、Agent、IR、CI、开源工程均是手段。
2. **Reuse First**：做任何较大改动前，必须先检查项目里是否已有现成设计、脚本、入口、状态字段、门禁或工具可复用。
3. **KEEP > TUNE > CONNECT > ADD**：默认优先复用/微调/连接现有能力。只有真实样本证明现有能力无法承载，才允许新增。
4. **Capability-first, Agent-last**：新增 Agent/IR 只有在真实样本证明必须隔离上下文/权限、使用不同模型/专长且有可测收益、拥有独立生命周期或并行价值、现有合同确实无法承载所需语义时才成立。
5. **任务必须写清**：Goal / Allowed / Forbidden / Acceptance。不因发现技术债扩大任务。
6. **真实用户 / 真实 PPT 验证优先**：后续优先级由真实用户反馈和真实 PPT 结果决定，不再由架构设想或内部工程完整度决定。

## 贡献流程

1. 读取 `AGENTS.md` → `docs/development/SDD.md` → `docs/development/SPEC_TEMPLATE.md`
2. 在 Issue 中描述真实问题、期望行为、复现步骤
3. 总控评估后给出 SPEC（按 `SPEC_TEMPLATE.md`）
4. Bounded executor 实施最小修改
5. 真实任务验证（安装、健康检查、最小生成）
6. PR 合并 → 下一轮 Public Snapshot 发布

## 禁止事项

- 不得直接把 Private Repo 改为 Public
- 不得删除/弱化 Private Repo 的 SDD、SPEC、Agent Control、UAT、evidence、.learnings
- 不得重写 Private Git 历史
- 不得新增 Agent/IR/Pipeline/QA Gate（除非真实样本证明必要）
- 不得为开源建设插件平台、SaaS、多租户、复杂权限体系
- 不得建立复杂双向同步系统
- 不得把测试通过、PPTX 可下载或单次 UAT 写成生产级质量通过

## 运行验证

任何改动必须通过：

```bash
cd my-ppt-skill
python -m pip install -e .
cd ..
python -m workbench.healthcheck
python start_workbench.py
# 至少完成一次安全虚构材料的真实 1 页生成
```

> 注意：`pip install -e .` 必须在 `my-ppt-skill/` 子目录执行，仓库根目录不可直接安装。

## 许可证

项目自有代码：Apache-2.0
第三方资产：见 `THIRD_PARTY_NOTICES.md`