# Using Git Worktrees Playbook

作者：fxbin  
版本：v1.0  
更新日期：2026-03-04

## 目标

在同一仓库下并行处理多任务，避免频繁切分支造成上下文污染。

## 触发条件

- 同时推进 2 个及以上需求
- 需求开发与 hotfix 并行
- 需要稳定分离实验分支和主线分支

## 标准步骤

1. 在主仓库确认基线分支（如 `main` 或 `develop`）是最新状态。
2. 为每个任务创建独立 worktree 目录和分支。
3. 在对应 worktree 内独立开发、提交、推送。
4. 任务完成后按统一 PR 流程合并。
5. 合并后清理已完成任务的 worktree。

## 命令模板

```bash
git worktree list
git worktree add ../wt-feature-a -b feature/a main
git worktree add ../wt-hotfix-xxx -b hotfix/xxx main
git worktree remove ../wt-feature-a
git worktree prune
```

## 命名约定

- worktree 目录：`wt-<branch>`
- 分支名：
  - 功能：`feature/<name>`
  - 修复：`fix/<name>` 或 `hotfix/<name>`
  - 重构：`refactor/<name>`

## 风险控制

- 不在错误 worktree 提交代码。
- 删除 worktree 前确认已推送或已合并。
- 避免在同一个文件上并行大改，降低冲突成本。
