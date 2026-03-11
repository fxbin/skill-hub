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

A short explanation of what this skill helps the user do.

## Core goals

- State the main capability of the skill.
- Explain when it should trigger and what its output boundaries are.

## Usage scenarios

- Scenario 1: describe a common request.
- Scenario 2: describe the relevant files, context, or constraints.

## Workflow

1. Confirm the goal, inputs, and boundaries.
2. Load only the resources needed for the task.
3. Produce a stable output format.

## Output template

1. `Conclusion`: one-sentence outcome
2. `Key decisions`: why this approach was chosen
3. `Risks`: limits, assumptions, or edge cases
4. `Next step`: what to do after this
"""

REFERENCE_TEMPLATE = """# References

Place materials here that should only be read for specific tasks.
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
        f"{display_name}. Use this skill when the user wants to create, update, evaluate, "
        f"or refine {display_name}, define its workflow, add evals, or improve its triggering description. "
        f"Users may say things like \"create {display_name}\", \"benchmark {display_name}\", "
        f"\"update {display_name}\", or \"use {skill_name}\"."
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
