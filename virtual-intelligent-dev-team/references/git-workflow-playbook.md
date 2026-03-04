# Git Workflow Playbook

作者：fxbin  
版本：v1.0  
更新日期：2026-03-04

## 目标

统一团队分支、提交、合并和发布流程，确保可追溯和可回滚。

## 触发条件

- 需要建立分支策略
- 需要统一 commit message 规范
- 需要定义 PR 门禁与发布节奏

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

## 命令模板

```bash
git checkout -b feature/xxx
git commit -m "feat: add xxx capability"
git push -u origin feature/xxx
git tag v1.2.3
git push origin v1.2.3
```

## 风险控制

- 禁止直接推送高风险改动到 `main`。
- 遇到冲突优先小步回放，不做大范围一次性冲突解决。
- 发布标签必须与发布记录一致，避免版本漂移。
