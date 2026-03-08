# `agents/openai.yaml` 参考

用于 UI 展示的最小结构：

```yaml
interface:
  display_name: "User-facing skill name"
  short_description: "25-64 chars summary"
  default_prompt: "Use $skill-name to ..."
```

字段约束：

- `display_name`：用户可见标题
- `short_description`：建议 25-64 字符
- `default_prompt`：必须包含 `$skill-name`
- `icon_small`、`icon_large`、`brand_color`：仅在确有 UI 需求时添加

生成方式：

```bash
python skill-forge/scripts/generate_openai_yaml.py /path/to/skill
```

如果外部仓库有不同的字段长度或必填规则，使用：

```bash
python skill-forge/scripts/generate_openai_yaml.py /path/to/skill \
  --config skill-forge/references/generic-skill-config.json
```

覆盖字段：

```bash
python skill-forge/scripts/generate_openai_yaml.py /path/to/skill \
  --interface display_name="My Skill" \
  --interface short_description="Help create or update My Skill" \
  --interface default_prompt="Use $my-skill to ..."
```
