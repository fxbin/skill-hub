#!/usr/bin/env python3
"""Generate agents/openai.yaml for a skill directory."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from skill_config import load_config, read_text, write_text

ALLOWED_INTERFACE_KEYS = {
    "display_name",
    "short_description",
    "icon_small",
    "icon_large",
    "brand_color",
    "default_prompt",
}


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def parse_frontmatter_name(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise ValueError("SKILL.md not found")

    content = read_text(skill_md)
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md has invalid frontmatter")

    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        if key.strip() == "name":
            name = value.strip().strip('"').strip("'")
            if name:
                return name
    raise ValueError("SKILL.md frontmatter missing name")


def format_display_name(skill_name: str) -> str:
    return " ".join(part.capitalize() for part in skill_name.split("-") if part)


def default_short_description(display_name: str, min_len: int, max_len: int) -> str:
    options = [
        f"Help create or refine {display_name}",
        f"{display_name} skill creation helper",
        f"Build or update {display_name} skills",
    ]
    for value in options:
        if min_len <= len(value) <= max_len:
            return value
    trimmed = f"{display_name} skill helper"
    return trimmed[:max_len].rstrip()


def default_prompt(skill_name: str) -> str:
    return f"Use ${skill_name} to create or refine a reusable skill with correct structure and metadata."


def parse_interface_overrides(items: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --interface value: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key not in ALLOWED_INTERFACE_KEYS:
            allowed = ", ".join(sorted(ALLOWED_INTERFACE_KEYS))
            raise ValueError(f"Unknown interface key '{key}'. Allowed: {allowed}")
        overrides[key] = value
    return overrides


def build_openai_yaml(skill_name: str, overrides: dict[str, str], config: dict | None = None) -> str:
    resolved = config or load_config()
    min_len = int(resolved["short_description_min"])
    max_len = int(resolved["short_description_max"])
    display_name = overrides.get("display_name") or format_display_name(skill_name)
    short_description = overrides.get("short_description") or default_short_description(
        display_name, min_len, max_len
    )
    prompt = overrides.get("default_prompt") or default_prompt(skill_name)

    if not (min_len <= len(short_description) <= max_len):
        raise ValueError(
            f"short_description length must be {min_len}-{max_len}"
        )
    if f"${skill_name}" not in prompt:
        raise ValueError(f"default_prompt must contain ${skill_name}")

    ordered_keys = ["display_name", "short_description", "default_prompt"]
    optional_keys = ["icon_small", "icon_large", "brand_color"]

    lines = ["interface:"]
    values = {
        "display_name": display_name,
        "short_description": short_description,
        "default_prompt": prompt,
        **{key: value for key, value in overrides.items() if key in optional_keys},
    }
    for key in ordered_keys + optional_keys:
        value = values.get(key)
        if value:
            lines.append(f"  {key}: {yaml_quote(value)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate agents/openai.yaml for a skill.")
    parser.add_argument("skill_dir", help="Path to skill directory")
    parser.add_argument("--name", help="Override skill name")
    parser.add_argument(
        "--interface",
        action="append",
        default=[],
        help="Override interface field with key=value",
    )
    parser.add_argument("--config", help="Optional JSON config file")
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        print(f"[ERROR] Skill directory not found: {skill_dir}")
        return 1

    try:
        skill_name = args.name or parse_frontmatter_name(skill_dir)
        config = load_config(args.config)
        overrides = parse_interface_overrides(args.interface)
        content = build_openai_yaml(skill_name, overrides, config)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    agents_dir = skill_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    output = agents_dir / "openai.yaml"
    write_text(output, content)
    print(f"[OK] Generated {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
