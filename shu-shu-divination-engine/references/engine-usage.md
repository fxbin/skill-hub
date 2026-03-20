# 引擎使用

本地引擎为这个 skill 提供了一个稳定、可重复的执行层。

当仓库可用，且你希望获得稳定的分流、起测、结构化输出时，优先使用它，而不是只停留在叙述式判断。

## 安装依赖

推荐优先使用 `uv` 创建虚拟环境，再补齐运行时依赖：

```powershell
uv venv
.\.venv\Scripts\python scripts\install_runtime.py
```

如果你使用 `pip`：

```powershell
python -m venv .venv
.\.venv\Scripts\python scripts\install_runtime.py
```

安装脚本会：

- 安装 `requirements.txt` 中的公共依赖
- 单独安装 `kinqimen==0.0.6.6 --no-deps`
- 避开上游错误依赖元数据带来的安装失败
- 使用仓库内置的六爻静态资产与本地原生实现

目前六爻已经由原生代码负责：

- 年月日时起卦
- 卦码生成
- 本卦 / 之卦判定
- 动爻定位
- 基础盘面结构输出

这些状态会记录在输出结果的 `computed_payload.provider` 和 `computed_payload.native_core` 中。

## 基本命令

```powershell
.\.venv\Scripts\python scripts\divination_engine.py --prompt "用户问题"
```

## 带显式锚点执行

```powershell
.\.venv\Scripts\python scripts\divination_engine.py ^
  --prompt "今天下午 3 点我发现钥匙不见了，最后在卧室书桌见过，请直接往下测。" ^
  --numbers 3,8,2 ^
  --event-time 2026-03-18T15:00:00
```

## 比较多个奇门候选时间

```powershell
.\.venv\Scripts\python scripts\divination_engine.py ^
  --prompt "这两个时间哪个更适合去见客户谈合作？" ^
  --candidate-times 2026-03-20T09:00:00,2026-03-22T15:00:00
```

## 引擎在做什么

引擎默认会按这个顺序工作：

1. 拆分复合问题
2. 判断是否属于四术数、相邻体系或高风险内容
3. 选择这轮最值得执行的主问题，而不是机械取第一句
4. 选择最合适的术数
5. 把剩余问题写入 `deferred_questions`
6. 进入起测与测算
7. 输出结构化 JSON 或文本报告

## 复合问题处理

当用户一次问很多件事时，引擎会额外输出 `compound_analysis`：

- `primary_question`
  本轮真正进入起测的主问题
- `breakdown`
  每个子问题的分类、候选术数、缺失信息和优先级信息
- `supporting_fragments`
  只作为补充输入的片段，例如“数字是 3、8、2”
- `deferred_questions`
  本轮暂不执行、留待下一轮的问题

这一层的目标是避免：

- 机械按第一句路由
- 把八字 / 总运类问题硬塞进四术数
- 一轮同时回答多个体系、多个层级的问题

## 统一答复层

当四术数进入可计算输出后，引擎会尽量收敛成统一的 `answer_card`，用于直接面向用户答复。

当前统一结构至少包含：

- `method`
- `question`
- `conclusion`
- `confidence`
- `key_signals`
- `risk_points`
- `timing_hint`
- `action_advice`
- `follow_up_focus`

另外还会生成：

- `final_response.sections`
- `final_response.reply`
- `final_response.text`

也就是既有结构化层，也有更自然的中文答复层。

## 当前覆盖范围

- 梅花易数：支持基于时间或数字锚点的短期应事判断
- 六爻：支持基于正式时间起卦，并输出稳定协议与结构化盘面
- 奇门遁甲：支持明确时点起盘与多时点比较
- 大六壬：支持基于正式时间起课与三传四课摘要输出

引擎会明确区分：

- 已经完成的可计算部分
- 仍然只是暂定或待补输入的部分

不要伪造完整传统盘局。

## 输入规则

- 梅花易数：给 `--numbers` 或 `--event-time`；也支持在 `prompt` 中直接写时间，包括“今天下午 3 点”这类相对时间
- 六爻：优先给 `--event-time`，或在 `prompt` 中直接写绝对时间
- 奇门遁甲：单时点可给 `--event-time`；多时点比较优先给 `--candidate-times`
- 大六壬：优先给 `--event-time`，并在 `prompt` 中说明关键人物与暗线问题

## 输出建议

对外答复时，优先使用这些字段：

- `routing.selected_method`
- `execution.status`
- `execution.answer_card`
- `compound_analysis`
- `final_response`

如果用户只要人话答复，优先使用 `final_response.reply`。

如果用户要结构化结果或做测试，优先使用 `json` 输出。
