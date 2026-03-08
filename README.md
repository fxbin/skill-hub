# skill-hub

个人技能仓库，用于集中管理可复用的 Skills，以“内容与流程定义”为核心，不绑定具体平台。

## 当前技能

| id | 名称 | 版本 | 路径 | 说明 |
| --- | --- | --- | --- | --- |
| `skill-creator` | Skill 创建器 | `v2.1.0` | `skill-creator/` | 创建新技能的通用工具链，支持脚手架、配置化 openai.yaml 生成与校验。 |
| `virtual-intelligent-dev-team` | 虚拟智能开发团队 | `v3.4` | `virtual-intelligent-dev-team/` | 自动路由到合适技术领域智能体并组织协作交付。 |

## 仓库结构

```text
skill-hub/
├── skill-creator/
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

1. 修改技能内容或路由规则。
2. 更新对应技能的 `VERSION` 与 `skills-index.json`。
3. 执行本地校验。
4. 提交中文 commit 信息。
