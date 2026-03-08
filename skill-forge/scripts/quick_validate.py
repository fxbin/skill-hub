#!/usr/bin/env python3
"""Validate a single skill folder quickly."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from skill_config import load_config

NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_frontmatter(content: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md missing valid frontmatter")

    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line.startswith(" ") or line.startswith("\t"):
            continue
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    return frontmatter


def extract_yaml_scalar(content: str, key: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*:\s*(.*?)\s*$", content)
    if not match:
        return ""
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def validate_skill_dir(skill_dir: Path, config: dict) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return ["SKILL.md not found"]

    try:
        frontmatter = extract_frontmatter(read_text(skill_md))
    except ValueError as exc:
        return [str(exc)]

    required_frontmatter = set(config["required_frontmatter_keys"])
    missing = required_frontmatter - set(frontmatter)
    if missing:
        errors.append(f"Missing frontmatter fields: {sorted(missing)}")

    allowed_frontmatter = set(config["allowed_frontmatter_keys"])
    unexpected = set(frontmatter) - allowed_frontmatter
    if unexpected:
        errors.append(f"Unexpected frontmatter fields: {sorted(unexpected)}")

    skill_name = frontmatter.get("name", "")
    if skill_name != skill_dir.name:
        errors.append(f"frontmatter.name '{skill_name}' must match directory '{skill_dir.name}'")
    if not NAME_PATTERN.fullmatch(skill_name):
        errors.append("frontmatter.name must be hyphen-case")
    max_name_length = int(config["max_name_length"])
    if len(skill_name) > max_name_length:
        errors.append(f"frontmatter.name exceeds {max_name_length} characters")

    description = frontmatter.get("description", "")
    if not description:
        errors.append("frontmatter.description is empty")
    max_description_length = int(config["max_description_length"])
    if len(description) > max_description_length:
        errors.append(f"frontmatter.description exceeds {max_description_length} characters")

    version_file = skill_dir / "VERSION"
    if config.get("require_version_file") and (
        not version_file.exists() or not read_text(version_file).strip()
    ):
        errors.append("VERSION file missing or empty")

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if config.get("require_openai_yaml") and not openai_yaml.exists():
        errors.append("agents/openai.yaml missing")
    if openai_yaml.exists():
        content = read_text(openai_yaml)
        if "interface:" not in content:
            errors.append("agents/openai.yaml missing interface")
        required_fields = set(config["required_openai_fields"])
        for field in required_fields:
            value = extract_yaml_scalar(content, field)
            if not value:
                errors.append(f"agents/openai.yaml missing {field}")
        prompt = extract_yaml_scalar(content, "default_prompt")
        if prompt and f"${skill_name}" not in prompt:
            errors.append(f"agents/openai.yaml default_prompt must include ${skill_name}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick validate a single skill directory.")
    parser.add_argument("skill_dir", help="Path to skill directory")
    parser.add_argument("--config", help="Optional JSON config file")
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        print(f"[ERROR] Skill directory not found: {skill_dir}")
        return 1

    config = load_config(args.config)
    errors = validate_skill_dir(skill_dir, config)
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 1

    print("Skill is valid!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
