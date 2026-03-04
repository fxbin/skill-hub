# Routing Score Matrix

作者：fxbin  
版本：v2.5  
更新日期：2026-03-04

## 说明

- 本文档用于解释路由机制，不再作为机器可执行配置。
- 机器可执行配置以 `references/routing-rules.json` 为准。
- 推荐维护方式：只改 `routing-rules.json`，本文档按需更新说明。

## 评分模型

1. 正向关键词加分  
- 命中 `positive` 关键词，按权重累加。

2. 负向关键词扣分  
- 命中 `negative` 关键词，按惩罚分扣减。
- 目标：减少误触发和跨域串线。

3. 分值裁剪  
- `final_score = clamp(positive_score - negative_score, 0, max_agent_score)`。

4. 置信度  
- `confidence = top1_score / max(top3_total_score, 1)`。

5. 语言识别  
- `language_profiles` 用于识别 `python/go/nodejs/rust` 等语言栈并给出主责映射。
- 当仅命中语言信号且领域分值不足时，进入“语言驱动模式”。

6. 匹配边界  
- 中文关键词：子串匹配。
- 英文关键词：词边界匹配，避免短词误触发（如 `pr`、`ui`、`go`）。
- Go 语言：裸词 `go` 必须同时命中技术上下文词（如 `backend/api/service`）才生效。

## 阈值策略（可配置）

- `high_confidence`：默认 `0.55`，单主责。
- `medium_confidence`：默认 `0.35`，主责 + 1 辅助。
- 低于 `medium_confidence`：主责 + 2 辅助，并建议澄清。
- `sentinel_overlay_threshold`：默认 `6`，命中即叠加治理流程。
- `default_unknown_lead_agent`：默认 `Technical Trinity`，全 0 分时用于兜底主责。

## 流程技能路由（非主责评分）

- `using-git-worktrees` 与 `git-workflow` 仅作为流程增强，不参与主责智能体打分。
- 当仅命中流程技能而未命中领域智能体时，回退主责为 `Technical Trinity`，进入流程驱动模式。

## 内置执行能力

- 本 skill 已内置：
  - `references/using-git-worktrees-playbook.md`
  - `references/git-workflow-playbook.md`
- 脚本输出 `process_plan` 可直接执行，无需外部同名 skill。
- 脚本输出 `detected_languages` 与 `language_routing` 可直接用于多语言任务派工。
