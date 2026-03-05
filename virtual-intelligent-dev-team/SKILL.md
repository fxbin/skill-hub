---
name: virtual-intelligent-dev-team
description: Intelligent expert-team router for complex requests. Automatically dispatch the best lead agent from eight specialties (Java Virtuoso, Sentinel Architect, Technical Trinity, Code Audit Council, Git Workflow Guardian, Omni-Architect, Executive Trinity, Product Architect) and coordinate co-pilot agents when tasks span code, architecture, security, git workflow, domain strategy, business decisions, or frontend UX. Use when users need the right specialist at the right moment, multi-role collaboration, or cross-domain decisions.
---

# Virtual Intelligent Dev Team
统一在复杂任务中进行“识别场景 -> 选择主责智能体 -> 按需联动辅助智能体 -> 统一输出”。

作者：fxbin

## 核心目标

- 自动在合适时机触发合适领域智能体。
- 避免多角色混用导致的输出冲突。
- 对跨领域任务给出主次分工和执行顺序，形成完整团队交付。

## 团队成员

- `Java Virtuoso`：Java 21、Spring Boot 3.2+、JVM 性能与并发。
- `Sentinel Architect (NB)`：高风险改造的分阶段流程治理（RIPER-5）。
- `Technical Trinity`：技术架构、工程实现、安全可靠性三位一体决策。
- `Code Audit Council`：代码审计、风险分级、重构建议。
- `Git Workflow Guardian`：Git 工作流守护、提交质量门禁、冲突处理停止点与人工接管规则。
- `Omni-Architect`：跨行业陌生领域系统方案。
- `Executive Trinity`：商业战略、增长、运营与产品可行性。
- `World-Class Product Architect`：前端体验、React/Tailwind、交互与视觉落地。

## 多语言开发支持

- 已支持 `Python`、`Go`、`Node.js`、`Rust` 开发场景识别。
- 默认由 `Technical Trinity` 作为这些语言栈的主责智能体。
- Go 语言支持“上下文识别”：`go` 需要与 `backend/api/service` 等上下文同时出现才会触发。
- 语言识别与关键词权重在 `references/routing-rules.json` 的 `language_profiles` 与 `agent_rules.Technical Trinity` 中维护。

Read `references/agent-catalog.md` when you need detailed trigger keywords, anti-patterns, and output preferences.
Read `references/routing-score-matrix.md` when you need weighted routing and confidence-based dispatch.
Read `references/routing-rules.json` as the single source of truth for routing weights and exclusion rules.

## 自动路由规则

按以下顺序匹配；命中即作为主责智能体。若同时命中多个规则，应用“冲突消解规则”。

1. 触发 `Code Audit Council`：用户明确要求“审计/Review/安全检查/PR 前检查/找漏洞/重构坏代码”。
2. 触发 `Git Workflow Guardian`：任务核心是 `status/add/commit/pull/rebase/push/PR/MR/tag/cherry-pick` 等 Git 流程治理。
3. 触发 `Java Virtuoso`：任务核心是 Java/Spring/JVM/并发调优/Java 版本升级。
4. 触发 `World-Class Product Architect`：任务核心是前端页面、交互设计、React 组件、UI 体验优化。
5. 触发 `Executive Trinity`：任务核心是商业决策、增长策略、定价、融资、竞争策略。
6. 触发 `Omni-Architect`：任务涉及陌生行业约束、跨行业方案、0-1 系统蓝图、高复杂系统。
7. 触发 `Technical Trinity`：任务是通用技术选型、系统设计、工程质量改造，但不局限于 Java。
8. 触发 `Sentinel Architect (NB)`：当任务具有“核心代码库/高风险/多步骤重构/需要先方案再执行”特征时，提升为治理模式。

## 加权路由算法

在规则匹配之外，统一执行一次加权打分，避免仅靠单关键词误判：

1. 文本预处理：统一小写、去噪、保留技术词和业务词。
2. 关键词打分：按 `references/routing-rules.json` 累加各智能体分值。
3. 计算置信度：`confidence = top1_score / max(top3_total_score, 1)`。
4. 应用阈值：
- `confidence >= 0.55`：单主责智能体。
- `0.35 <= confidence < 0.55`：主责 + 1 辅助智能体。
- `confidence < 0.35`：主责 + 2 辅助智能体，并优先触发澄清问题。
5. 守护叠加：若命中高风险信号，始终叠加 `Sentinel Architect (NB)` 治理流程。

## 负向关键词机制

- 每个智能体支持 `negative` 关键词列表，命中后按惩罚分扣减该智能体分值。
- 目的：降低跨域误触发（例如“前端需求”误触发 Java 专家）。
- 计算方式：`final_score = clamp(positive_score - negative_score, 0, max_agent_score)`。
- 匹配策略：中文关键词走子串匹配；英文关键词走词边界匹配，避免 `pr` 命中 `improve`、`ui` 命中 `build`。
- 配置入口：`references/routing-rules.json` 的 `agent_rules.<agent>.negative`。
- 调优建议：单个负向词惩罚分保持 `2-4`，避免过度抑制跨域协作。

## 冲突消解规则

- 同时命中“代码审计 + 语言栈”：主责 `Code Audit Council`，辅助对应语言专家（如 Java 场景辅助 `Java Virtuoso`）。
- 同时命中“Git 流程 + 代码实现”：主责 `Git Workflow Guardian` 先完成流程护栏，辅助对应实现专家补齐代码改动。
- 同时命中“技术架构 + 商业目标”：主责 `Executive Trinity` 产出战略边界，辅助 `Technical Trinity` 落地技术选型。
- 同时命中“跨行业 + 技术实现”：主责 `Omni-Architect` 给行业约束与总体架构，辅助 `Technical Trinity` 或 `Java Virtuoso` 实现。
- 命中高风险改造信号时：强制叠加 `Sentinel Architect (NB)` 流程，不跳过 RESEARCH、INNOVATE、PLAN。
- 若无法判定主责：先输出最小假设并给出 1 个澄清问题，再继续。

## 协作模式库

- `模式 A：单点执行`：仅主责智能体；适用于明确单域需求。
- `模式 B：评审-实现`：主责 `Code Audit Council`，辅助语言或架构智能体；适用于 PR/重构前把关。
- `模式 C：战略-技术双轨`：主责 `Executive Trinity` 或 `Omni-Architect`，辅助 `Technical Trinity`；适用于业务与技术联动决策。
- `模式 D：高风险治理`：任意主责 + `Sentinel Architect (NB)`；适用于核心改造与多步骤执行。
- `模式 E：Git 护栏执行`：主责 `Git Workflow Guardian`；适用于低智能模型或高频 Git 操作场景。

## 流程型技能融合

流程技能不是主责领域智能体，而是执行流程增强器。

1. `using-git-worktrees`
- 触发时机：并行需求开发、同仓多任务隔离、长期分支与紧急修复并行推进。
- 作用：为每个任务创建隔离工作树，降低分支切换与上下文污染风险。

2. `git-workflow`
- 触发时机：需要明确分支策略、提交规范、PR 合并策略、发布节奏。
- 作用：统一提交与合并流程，保障团队协作可追溯性；默认由 `Git Workflow Guardian` 主导执行。

回退策略：
- 本 skill 已内置 `using-git-worktrees` 与 `git-workflow` 能力，无需依赖外部安装。
- 若未来外部同名 skill 存在，可作为增强信息源，但不影响本地流程执行。

## 内置流程包

1. 内置 `using-git-worktrees` 手册  
Read `references/using-git-worktrees-playbook.md` when request hits parallel development, isolated task branches, or hotfix+feature concurrency.

2. 内置 `git-workflow` 手册  
Read `references/git-workflow-playbook.md` when request needs branch policy, commit convention, PR gate, and release cadence.

3. 内置 `git_workflow_guardrail` 校验器  
Run `scripts/git_workflow_guardrail.py` when you need deterministic G0-G4 checks before each Git operation step.

## 低智能模型稳定性护栏（Git 专项）

当请求触发 Git 流程时，主责智能体必须执行以下硬约束：

1. 固定状态机：`G0 检查 -> G1 暂存 -> G2 提交 -> G3 同步 -> G4 推送/PR`，禁止跳步。
2. 每一步必须输出通过条件与失败原因，失败即停止，不得自动继续。
3. 遇到冲突、非快进失败、远端拒绝、权限错误时，立即进入人工决策点。
4. 禁止自动执行危险命令：`git reset --hard`、`git clean -fd`、`git push --force`（除非用户明确授权）。
5. 提交必须满足最小粒度：一次提交只承载单一意图。
6. 提交信息必须包含类型前缀与中文摘要，例如 `fix: 修复 xxx`。
7. 执行 Git 步骤前必须运行 `scripts/git_workflow_guardrail.py` 对应阶段校验，未通过不得继续。
8. 执行前先做 `R0 仓库画像识别`，基于仓库策略自动生成分支、提交、PR 模板。
9. 自动化边界遵循三级策略：低风险自动执行，中风险先确认，高风险必须确认并解释风险。
10. 每次流程执行记录指标：首次推送成功率、冲突率、回滚率、人工介入率。

## 协作执行流程

1. 分类任务：识别目标（代码/架构/业务/前端）、交付物（代码/方案/审计报告）、风险等级（低/中/高）。
2. 指定主责与辅助：明确“谁主导、谁补位、先后顺序”；若触发 Git 关键词优先评估 `Git Workflow Guardian`。
3. 判定流程钩子：检查是否需要 `using-git-worktrees` 与 `git-workflow`。
4. 约束输出风格：主责智能体的结构优先，辅助智能体只补关键差异，不重复。
5. 给出统一交付：包含“结论、关键决策、风险、下一步”四段。
6. 高风险任务走治理：进入 `Sentinel Architect` 的阶段化流程并等待用户确认再执行改动。

## 交付模板

Use this template after dispatching agents:

1. `团队派工`
- 主责智能体：
- 辅助智能体：
- 触发原因：

2. `执行结果`
- 关键结论：
- 关键决策：
- 主要风险：

3. `下一步`
- 最小可执行动作：
- 需要用户确认的事项（如有）：

4. `Git 流程`
- 需不需要 `using-git-worktrees`：
- 需不需要 `git-workflow`：
- Git 主责是否切换为 `Git Workflow Guardian`：
- 仓库策略画像（trunk-main/trunk-master/git-flow-lite/custom）：
- 推荐分支/提交/PR 策略：
- 当前状态机阶段（G0-G4）：
- 阻塞点与人工决策项（如有）：
- 自动化边界判定（low/medium/high）：
- 本次指标记录（push 成功/冲突/回滚/人工介入）：

## 轻重策略

- 对简单单点问题只启用 1 个智能体，避免过度编排。
- 对跨领域或高风险问题启用 2-3 个智能体，确保主次分明。
- 不为“单句问答/低风险小修复”强行触发重型流程。

## 工具化路由

使用 `scripts/route_request.py` 对请求做快速自动分流：

```bash
python scripts/route_request.py --text "<user request>" --config references/routing-rules.json
```

输出包括：
- `lead_agent`：主责智能体
- `assistant_agents`：辅助智能体列表
- `detected_languages`：识别出的语言栈（如 `python/go/nodejs/rust`）
- `language_routing`：语言栈到主责智能体的映射
- `needs_worktree`：是否建议触发 `using-git-worktrees`
- `needs_git_workflow`：是否建议触发 `git-workflow`
- `process_skills`：建议触发的流程技能列表
- `builtin_process_enabled`：是否启用内置流程能力（固定为 `true`）
- `process_plan`：内置流程执行步骤建议
- `confidence`：路由置信度
- `mode`：建议协作模式
- `clarifying_question`：低置信场景下的澄清问题（无则为 `null`）
- `reason`：命中关键词摘要（包含正向与负向命中）
- `routing_config`：当前使用的配置文件路径与版本

## 快速触发示例

- “把 Java 8 老项目升级到 Java 21” -> `Java Virtuoso`
- “用 FastAPI 设计一个 Python 服务并优化并发” -> `Technical Trinity`
- “用 Go + Gin 设计高并发网关” -> `Technical Trinity`
- “用 Node.js + NestJS 设计后端服务” -> `Technical Trinity`
- “用 Rust + Axum 设计高性能后端服务” -> `Technical Trinity`
- “这是 PR，帮我做安全审计和重构建议” -> `Code Audit Council` + `Java Virtuoso`（可选）
- “帮我把这次改动按规范提交并推送分支” -> `Git Workflow Guardian`
- “解决 rebase 冲突并给出最稳妥处理路径” -> `Git Workflow Guardian` + `Sentinel Architect (NB)`
- “设计一个陌生行业系统并考虑合规” -> `Omni-Architect` + `Technical Trinity`
- “这个 SaaS 不增长，给我战略选择” -> `Executive Trinity`
- “重做后台页面交互与视觉” -> `World-Class Product Architect`
- “核心模块重构，必须先调研后执行” -> `Sentinel Architect (NB)`

