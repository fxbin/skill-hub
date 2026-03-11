#!/usr/bin/env python3
"""Initialize evals/evals.json for a skill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quick_validate import extract_frontmatter, read_text


def build_eval_template(skill_name: str) -> dict:
    return {
        "skill_name": skill_name,
        "evals": [
            {
                "id": 1,
                "category": "create",
                "prompt": f"Use ${skill_name} for its primary workflow.",
                "expected_output": "Covers the main path for this skill.",
                "files": [],
            },
            {
                "id": 2,
                "category": "edge-case",
                "prompt": f"Use ${skill_name} for an edge case or mixed request.",
                "expected_output": "Handles the edge case without breaking the main workflow.",
                "files": [],
            },
            {
                "id": 3,
                "category": "iterate",
                "prompt": f"Use ${skill_name} to repair or improve an existing result.",
                "expected_output": "Shows iterative improvement behavior.",
                "files": [],
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize evals/evals.json for a skill.")
    parser.add_argument("skill_dir", help="Path to skill directory")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite evals/evals.json if it already exists",
    )
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        print(f"[ERROR] SKILL.md not found: {skill_md}")
        return 1

    frontmatter = extract_frontmatter(read_text(skill_md))
    skill_name = frontmatter.get("name")
    if not skill_name:
        print("[ERROR] frontmatter.name not found")
        return 1

    evals_dir = skill_dir / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    evals_path = evals_dir / "evals.json"
    if evals_path.exists() and not args.force:
        print(f"[ERROR] File already exists: {evals_path}")
        print("[ERROR] Use --force to overwrite it")
        return 1

    payload = build_eval_template(skill_name)
    evals_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] Wrote {evals_path}")
    print("[OK] Next step: replace starter prompts with realistic repository scenarios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
