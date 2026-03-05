# Git Workflow Playbook

作者：fxbin  
版本：v1.1  
更新日期：2026-03-05

## 目标

统一团队分支、提交、合并和发布流程，确保可追溯和可回滚。  
为低智能模型提供确定性执行护栏，降低误操作概率。

## 触发条件

- 需要建立分支策略
- 需要统一 commit message 规范
- 需要定义 PR 门禁与发布节奏
- 需要执行具体 Git 操作（commit/pull/rebase/push/tag 等）

## 专职角色

- 主责：`Git Workflow Guardian`
- 职责：流程门禁、命令顺序、异常停止、人工接管提示

## 固定状态机（必须顺序执行）

1. `G0 检查`
- 执行要点：确认当前分支、工作区、远端同步状态。
- 通过条件：分支明确、工作区状态明确、无未知来源改动。
- 失败处理：立即停止，先处理脏工作区或分支错误。
- 校验命令：`python scripts/git_workflow_guardrail.py --repo . --stage G0 --pretty`

2. `G1 暂存`
- 执行要点：仅暂存当前任务相关文件。
- 通过条件：暂存集与任务范围一致，不混入无关文件。
- 失败处理：立即停止，回到变更筛选。
- 校验命令：`python scripts/git_workflow_guardrail.py --repo . --stage G1 --pretty`

3. `G2 提交`
- 执行要点：单一意图提交，提交信息使用语义前缀 + 中文摘要。
- 通过条件：一次提交只表达一个变更意图。
- 失败处理：立即停止，拆分提交后重试。
- 校验命令：`python scripts/git_workflow_guardrail.py --repo . --stage G2 --commit-message "fix: 修复 xxx" --pretty`

4. `G3 同步`
- 执行要点：与目标基线分支同步，优先小步解决冲突。
- 通过条件：本地分支与远端关系清晰，可安全继续推送。
- 失败处理：出现冲突、非快进失败、远端拒绝时立即停止并请求人工决策。
- 校验命令：`python scripts/git_workflow_guardrail.py --repo . --stage G3 --pretty`

5. `G4 推送/PR`
- 执行要点：推送分支并按门禁发起评审流程。
- 通过条件：推送成功，PR 信息完整，门禁策略明确。
- 失败处理：权限不足或策略阻断时停止并反馈阻塞点。
- 校验命令：`python scripts/git_workflow_guardrail.py --repo . --stage G4 --pretty`

## 低模型稳定性约束

- 禁止跳步执行，必须从 `G0` 顺序推进到 `G4`。
- 每一步都要给出“是否通过 + 原因”。
- 每一步都要先过 `git_workflow_guardrail.py` 的对应阶段校验。
- 未经用户明确授权，禁止执行危险命令：
  - `git reset --hard`
  - `git clean -fd`
  - `git push --force`
- 遇到不确定场景，默认保守：停止并请求人工决策。

## 推荐策略

1. 分支模型
- 主干分支：`main`（可发布）
- 集成分支：`develop`（可选）
- 任务分支：`feature/*`、`fix/*`、`hotfix/*`

2. 提交规范
- 使用语义前缀：`feat:`、`fix:`、`refactor:`、`docs:`、`chore:`
- 单次提交聚焦单一意图，避免混合提交

3. PR 门禁
- 至少 1 位 Reviewer
- 关键模块建议 2 位 Reviewer
- 合并前满足编译/静态检查/必要验证

4. 合并策略
- 保持主分支整洁时使用 `squash merge`
- 需要保留完整提交链路时使用 `merge commit`
- 对共享分支避免随意 `rebase` 改写历史

5. 发布策略
- 发布前打标签：`v<major>.<minor>.<patch>`
- 生产 hotfix 从 `main` 拉出，修复后回合并到 `main` 与 `develop`

## 最小命令序列（参考）

```bash
git status --short --branch
git checkout -b feature/xxx
git add <files>
git commit -m "feat: add xxx capability"
git pull --rebase origin <base-branch>
git push -u origin feature/xxx
```

## 风险控制

- 禁止直接推送高风险改动到 `main`。
- 遇到冲突优先小步回放，不做大范围一次性冲突解决。
- 发布标签必须与发布记录一致，避免版本漂移。
- 流程出现冲突或不确定时，优先中止并升级到人工处理。
