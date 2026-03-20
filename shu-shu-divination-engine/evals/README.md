# Evals

这个目录现在分成两条评测链：

## 1. 本地引擎评测

用于验证：

- 路由是否正确
- 复合问题拆分是否正确
- 相邻体系是否能分流出去
- 信息不足时是否进入补锚点状态
- 四术数执行后是否输出统一答复层

关键文件：

- `evals.json`
- `engine-eval-results.json`
- `engine-eval-report.md`
- `engine-eval-status.md`
- `conversation-evals.json`
- `conversation-eval-results.json`
- `conversation-eval-report.md`
- `conversation-eval-status.md`

运行命令：

```powershell
.\.venv\Scripts\python scripts\run_engine_evals.py
.\.venv\Scripts\python scripts\run_conversation_evals.py
```

## 2. 技能触发评测

用于验证：

- 这个 skill 会不会被正确触发
- 哪些近邻问题不该触发
- 哪些复杂、真实、口语化问题应该触发

关键文件：

- `trigger-evals.json`
- `trigger-eval-status.md`
- `trigger-eval-results.json`
- `trigger-eval-report.md`

运行命令：

```powershell
.\.venv\Scripts\python scripts\run_trigger_evals.py
.\.venv\Scripts\python scripts\run_trigger_evals.py --provider claude --smoke
.\.venv\Scripts\python scripts\run_trigger_eval_batches.py --provider claude --batch-size 5
.\.venv\Scripts\python scripts\run_trigger_eval_matrix.py --targets claude codex --batch-size 5
```

推荐口径：

- 样本集只维护一份：`trigger-evals.json`
- 单模型正式复跑：用 `run_trigger_eval_batches.py`
- 多模型横向比较：用 `run_trigger_eval_matrix.py`
- 报告要按 provider / model 分开解释，不把不同模型的 proxy 分数混成一个结论

当前状态：

- 样本集已准备
- 代理 trigger runner 已补齐，并默认自动优先选择 `claude`
- 已补充分批执行脚本 `run_trigger_eval_batches.py`，用于降低长跑中断对正式复跑的影响
- 已完成过一轮 `20` 条正式代理评测，最近一次完整已验证分数为 `19/20`
- 唯一失分样本已完成定向修正与复测
- 后修正文案的完整 `20` 条正式复跑仍待在更稳定环境中补齐

## 当前闭环状态

当前已经闭合的是：

1. 本地引擎逻辑
2. 路由与执行正确率
3. 文档与评测资产一致性

当前尚未彻底闭合的是：

1. 外部真实技能触发率
2. 基于真实 trigger run 的最终 description 优化闭环
