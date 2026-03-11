# skill-hub

个人技能仓库，用于集中管理可复用的 Skills，以“内容与流程定义”为核心，不绑定具体平台。

## 当前技能

| id | 名称 | 版本 | 路径 | 说明 |
| --- | --- | --- | --- | --- |
| `skill-forge` | Skill Forge | `v5.1.0` | `skill-forge/` | 仓库内统一的 skill 工程平台，覆盖脚手架、修复、eval、benchmark、portfolio 报告与迭代优化。 |
| `webnovel-style-forge` | Webnovel Style Forge | `v2.0.0` | `webnovel-style-forge/` | 提炼网文文风、降低 AI 味、构建可复用风格提示词，并通过对照与迭代持续打磨。 |
| `virtual-intelligent-dev-team` | Virtual Intelligent Dev Team | `v4.0` | `virtual-intelligent-dev-team/` | 自动路由到合适专家智能体并组织协作交付，覆盖开发、架构、安全、Git 流程、业务策略和前端 UX。 |

## 仓库结构

```text
skill-hub/
├── skill-forge/
├── webnovel-style-forge/
├── virtual-intelligent-dev-team/
├── scripts/
│   └── validate_skills.py
├── .github/
│   └── workflows/
│       └── validate-skills.yml
├── skills-index.json
└── README.md
```

## 本地校验

```powershell
python scripts/validate_skills.py
```

## 提交流程

1. 修改技能内容、规则或评估资产。
2. 更新对应技能的 `VERSION`，以及 `skills-index.json` 和 `README.md`。
3. 执行本地校验或 benchmark。
4. 提交规范化 commit。
