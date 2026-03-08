#!/usr/bin/env python3
"""Initialize a new skill scaffold."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from generate_openai_yaml import build_openai_yaml, write_text
from skill_config import load_config

MAX_NAME_LENGTH = 64
NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
SKILL_TEMPLATE = """---
name: {skill_name}
description: {description}
---

# {display_name}

一句话概述这个技能解决什么问题。

## 核心目标

- 明确本技能的核心能力
- 说明何时触发以及输出边界

## 使用场景

- 场景 1：填写典型请求
- 场景 2：填写相关文件或上下文

## 工作流程

1. 先确认目标和输入边界。
2. 再选择资源目录与执行步骤。
3. 最后给出固定交付格式。

## 交付模板

1. `结论`：一句话结论
2. `关键决策`：为什么这样做
3. `风险`：边界条件或限制
4. `下一步`：建议动作
"""

REFERENCE_TEMPLATE = """# References

将只在特定任务下才需要读取的资料放在这里。
"""

ASSET_PLACEHOLDER = """Place templates, images, or boilerplate assets here.
"""

SCRIPT_PLACEHOLDER = """#!/usr/bin/env python3
\"\"\"Example helper script for this skill.\"\"\"


def main() -> None:
    print("Replace this placeholder script or delete it.")


if __name__ == "__main__":
    main()
"""


def normalize_skill_name(raw_name: str) -> str:
    normalized = raw_name.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def validate_skill_name(skill_name: str) -> None:
    if not skill_name:
        raise ValueError("Skill name must include letters or digits")
    if len(skill_name) > MAX_NAME_LENGTH:
        raise ValueError(f"Skill name exceeds {MAX_NAME_LENGTH} characters")
    if not NAME_PATTERN.fullmatch(skill_name):
        raise ValueError("Skill name must use lowercase letters, digits, and hyphens")


def title_case(skill_name: str) -> str:
    return " ".join(part.capitalize() for part in skill_name.split("-") if part)


def create_resource_dirs(skill_dir: Path, resource_dirs: list[str], examples: bool) -> None:
    for name in resource_dirs:
        directory = skill_dir / name
        directory.mkdir(exist_ok=True)
        if not examples:
            continue
        if name == "references":
            write_text(directory / "README.md", REFERENCE_TEMPLATE)
        elif name == "assets":
            write_text(directory / "placeholder.txt", ASSET_PLACEHOLDER)
        elif name == "scripts":
            script_path = directory / "example.py"
            write_text(script_path, SCRIPT_PLACEHOLDER)
            script_path.chmod(0o755)


def build_skill_md(skill_name: str, display_name: str) -> str:
    description = (
        f"{display_name}。用于补充此技能的功能说明、适用场景和触发关键词。"
        f" 用户会说“{display_name}”、“更新 {display_name}”、“使用 {skill_name}”等。"
    )
    return SKILL_TEMPLATE.format(
        skill_name=skill_name,
        description=description,
        display_name=display_name,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a reusable skill scaffold.")
    parser.add_argument("skill_name", help="Skill name; will be normalized to hyphen-case")
    parser.add_argument("--path", required=True, help="Output directory")
    parser.add_argument("--version", default="v1.0.0", help="Initial version")
    parser.add_argument("--config", help="Optional JSON config file")
    parser.add_argument(
        "--with-examples",
        action="store_true",
        help="Add placeholder files to references/scripts/assets",
    )
    args = parser.parse_args()

    raw_name = args.skill_name
    skill_name = normalize_skill_name(raw_name)

    try:
        config = load_config(args.config)
        validate_skill_name(skill_name)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    root = Path(args.path).resolve()
    skill_dir = root / skill_name
    if skill_dir.exists():
        print(f"[ERROR] Skill directory already exists: {skill_dir}")
        return 1

    display_name = title_case(skill_name)
    skill_dir.mkdir(parents=True, exist_ok=False)
    emit_openai_yaml = bool(config.get("emit_openai_yaml", True))
    if emit_openai_yaml:
        (skill_dir / "agents").mkdir(exist_ok=True)
    create_resource_dirs(skill_dir, list(config.get("resource_dirs", [])), args.with_examples)

    write_text(skill_dir / "SKILL.md", build_skill_md(skill_name, display_name))
    if bool(config.get("require_version_file", False)):
        write_text(skill_dir / "VERSION", args.version.strip() + "\n")
    if emit_openai_yaml:
        openai_yaml = build_openai_yaml(skill_name, {}, config)
        write_text(skill_dir / "agents" / "openai.yaml", openai_yaml)

    print(f"[OK] Initialized skill at {skill_dir}")
    print("[OK] Next step: edit SKILL.md and run quick_validate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
