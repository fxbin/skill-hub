# Skill Tooling Configuration

`skill-creator` 的脚本支持通过 JSON 配置切换“通用模式”和“仓库特定模式”。

最小示例：

```json
{
  "require_version_file": false,
  "require_skills_index": false,
  "require_openai_yaml": false
}
```

完整通用配置参考：

- [generic-skill-config.json](generic-skill-config.json)

常用字段：

- `required_frontmatter_keys`：必须存在的 frontmatter 字段
- `allowed_frontmatter_keys`：允许的 frontmatter 字段白名单
- `required_openai_fields`：若存在 `agents/openai.yaml`，要求出现的字段
- `require_openai_yaml`：是否强制要求 `agents/openai.yaml`
- `require_version_file`：是否强制要求 `VERSION`
- `require_skills_index`：是否强制要求仓库根目录 `skills-index.json`
- `resource_dirs`：`init_skill.py` 要初始化的资源目录
- `emit_openai_yaml`：初始化时是否自动生成 `agents/openai.yaml`
- `short_description_min` / `short_description_max`：`openai.yaml` 文本约束
- `max_name_length` / `max_description_length`：frontmatter 约束

示例：

```bash
python skill-creator/scripts/init_skill.py my-skill --path . \
  --config skill-creator/references/generic-skill-config.json

python skill-creator/scripts/quick_validate.py ./my-skill \
  --config skill-creator/references/generic-skill-config.json

python scripts/validate_skills.py --repo-root . \
  --config skill-creator/references/generic-skill-config.json
```
