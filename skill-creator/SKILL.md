---
name: skill-creator
description: 创建可复用技能的核心指南。当用户想要创建新技能、更新现有技能、定义技能结构、编写 SKILL.md、设置 frontmatter 或设计技能工作流时使用此技能。
---

# Skill Creator

本技能指导你创建有效的可复用技能。

## 何时使用此技能

在以下情况下使用：
- 创建新的可复用技能
- 更新现有技能的 SKILL.md
- 定义技能结构和 frontmatter 元数据
- 设计技能工作流和触发规则
- 将技能接入 AI 助手

## 核心原则

### 1. 保持专注

一个技能应该聚焦于单一能力：
- ✅ 好的示例：`pdf-form-filler`、`git-workflow-helper`、`java-migration-guide`
- ❌ 过宽示例：`document-processor`、`development-tools`

### 2. 描述要具体

description 是技能被触发的关键，必须包含：
- **做什么**：技能的具体功能
- **何时使用**：用户在什么场景下会使用这个技能
- **触发关键词**：中文和英文的常见表达

### 3. 遵循标准结构

```
skill-name/
├── SKILL.md (必需)
├── VERSION (可选)
├── references/ (可选)
│   └── *.md
├── scripts/ (可选)
│   └── *.py/*.js/*.sh
├── assets/ (可选)
└── agents/ (可选)
    └── openai.yaml
```

## 技能创建流程

### 步骤 1：确定技能范围

首先明确技能的功能：

1. **提出澄清问题**：
   - 这个技能提供什么具体能力？
   - 用户在什么场景下会使用这个技能？
   - 需要哪些工具或资源？
   - 是个人使用还是团队共享？

2. **保持聚焦**：一个技能 = 一个核心能力

### 步骤 2：初始化技能脚手架

```bash
python skill-creator/scripts/init_skill.py skill-name --path .
```

需要占位示例文件时：

```bash
python skill-creator/scripts/init_skill.py skill-name --path . --with-examples
```

该脚本会自动生成：
- `SKILL.md`
- `VERSION`
- `agents/openai.yaml`
- `references/`、`scripts/`、`assets/`（以及可选示例文件）

如需按外部仓库规范生成，传入配置文件：

```bash
python skill-creator/scripts/init_skill.py skill-name --path . \
  --config skill-creator/references/generic-skill-config.json
```

### 步骤 3：编写 SKILL.md frontmatter

YAML frontmatter 是必需部分：

```yaml
---
name: skill-name
description: 技能功能描述 + 使用场景 + 触发关键词
---
```

**字段要求**：

| 字段 | 要求 |
|------|------|
| `name` | 小写字母、数字、中划线；最大 64 字符；与目录名一致 |
| `description` | 最大 1024 字符；包含"做什么"+"何时使用"+触发关键词 |

**描述公式**：`[功能] + [使用场景] + [触发关键词]`

✅ **好的示例**：
```yaml
description: Java 21 与 Spring Boot 3.2+ 迁移指南。用于 Java 版本升级、依赖兼容性评估、遗留代码现代化改造。用户会说"升级 Java"、"Java 迁移"、"Spring Boot 升级"等。
```

❌ **不好的示例**：
```yaml
description: 帮助 Java 开发
description: 代码重构工具
```

### 步骤 4：编写 SKILL.md 正文

使用清晰的 Markdown 结构：

```markdown
# 技能名称

一句话概述技能功能。

## 核心目标

- 目标 1
- 目标 2

## 使用场景

- 场景 1：具体描述
- 场景 2：具体描述

## 自动触发规则

描述技能在什么条件下会被激活。

## 交付模板

使用统一的输出格式：

1. `结论`：xxx
2. `决策`：xxx
3. `风险`：xxx
4. `下一步`：xxx

## 快速触发示例

- "触发短语 1" -> 预期行为
- "触发短语 2" -> 预期行为
```

### 步骤 5：编写 VERSION 文件（可选）

内容为语义化版本号：
```
v1.0.0
```

### 步骤 6：添加支持文件（可选）

- **references/**：参考资料、路由规则、模式库
- **scripts/**：可执行脚本、路由工具
- **assets/**：模板文件、配置文件
- **agents/**：智能体定义配置

### 步骤 7：生成或刷新 `agents/openai.yaml`

```bash
python skill-creator/scripts/generate_openai_yaml.py ./skill-name
```

如需覆盖展示字段：

```bash
python skill-creator/scripts/generate_openai_yaml.py ./skill-name \
  --interface display_name="My Skill" \
  --interface short_description="Help create or update My Skill" \
  --interface default_prompt="Use $my-skill to ..."
```

字段定义见 [references/openai_yaml.md](references/openai_yaml.md)。
配置覆盖见 [references/configuration.md](references/configuration.md)。

### 步骤 8：快速校验技能

```bash
python skill-creator/scripts/quick_validate.py ./skill-name
python scripts/validate_skills.py
```

先跑单技能快速校验，再跑仓库全量校验。

外部仓库建议显式传入配置：

```bash
python skill-creator/scripts/quick_validate.py ./skill-name \
  --config skill-creator/references/generic-skill-config.json

python scripts/validate_skills.py --repo-root . \
  --config skill-creator/references/generic-skill-config.json
```

## Frontmatter 最佳实践

### 必需字段

```yaml
---
name: skill-name
description: 功能描述 + 使用场景 + 触发关键词
---
```

### 可选字段

- `metadata`：
  - `short-description`：简短描述（用于列表展示）
- `allowed-tools`：限制可用工具
- `license`：技能许可证标识（可选）

仅在确实需要时添加可选字段，避免 frontmatter 过载。

### `agents/openai.yaml`（推荐）

如果技能需要在 UI 中展示，创建 `agents/openai.yaml`，至少包含：

```yaml
interface:
  display_name: "用户可读名称"
  short_description: "25-64 字符简述"
  default_prompt: "Use $skill-name to ..."
```

约束：
- `short_description` 建议 25-64 字符
- `default_prompt` 必须包含 `$skill-name`（例如 `$skill-creator`）
- 字符串值统一使用引号包裹

### 描述优化技巧

- 包含具体的触发短语
- 提及文件类型或格式
- 使用"用于"、"当...时"、"用户会说"等句式

## 常见模式

### 模式 1：路由型技能

```yaml
---
name: java-virtuoso
description: Java 21、Spring Boot 3.2+、JVM 性能调优专家。用于 Java 开发、框架选型、性能优化、版本升级。用户会说"Java 开发"、"Spring Boot"、"JVM 调优"等。
---

# Java Virtuoso

## 核心目标

- 提供 Java 技术决策
- 优化代码性能和并发能力
```

### 模式 2：流程型技能

```yaml
---
name: git-workflow-guardian
description: Git 工作流守护者。用于分支策略、提交规范、PR 合并、冲突处理。用户会说"提交代码"、"解决冲突"、"创建分支"、"PR 审核"等。
---

# Git Workflow Guardian

## 核心目标

- 保障 Git 流程规范性
- 提供冲突处理决策
```

### 模式 3：多智能体协作技能

```yaml
---
name: virtual-intelligent-dev-team
description: 智能专家团队路由器。自动调度多个专业智能体，协作完成复杂任务。用于多角色协作、跨领域决策、复杂任务分解。
---

# Virtual Intelligent Dev Team

## 团队成员

- xxx
```

## 校验清单

创建完技能后，验证以下内容：

- [ ] 目录名与 frontmatter `name` 一致
- [ ] `VERSION` 文件存在且格式正确（如果需要）
- [ ] description 包含功能 + 使用场景 + 触发关键词
- [ ] description 不超过 1024 字符
- [ ] YAML frontmatter 格式正确
- [ ] frontmatter 仅使用允许字段（`name`、`description`、`metadata`、`allowed-tools`、`license`）
- [ ] 如果存在 `agents/openai.yaml`，包含 `display_name`、`short_description`、`default_prompt`
- [ ] `default_prompt` 包含 `$<skill-name>`
- [ ] 技能能在相关场景下被正确触发

## 输出格式

创建技能时，我会：

1. 询问技能的核心功能和触发场景
2. 建议技能名称和目录结构
3. 优先运行 `skill-creator/scripts/init_skill.py` 初始化脚手架
4. 编写或更新符合规范的 `SKILL.md`
5. 生成 `agents/openai.yaml` 并补齐支持文件
6. 运行 `quick_validate.py` 和仓库级校验
7. 给出使用示例和触发规则
