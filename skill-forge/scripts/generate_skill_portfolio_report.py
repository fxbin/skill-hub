#!/usr/bin/env python3
"""Generate a repository-wide skill portfolio report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def find_skills(repo_root: Path) -> list[Path]:
    return sorted(
        path.parent
        for path in repo_root.rglob("SKILL.md")
        if ".codex" not in str(path) and "tmp-skill-forge" not in str(path)
    )


def run_benchmark(skill_dir: Path) -> dict:
    script = Path(__file__).resolve().parent / "run_skill_benchmarks.py"
    result = subprocess.run(
        [sys.executable, str(script), str(skill_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def render_markdown(report: dict) -> str:
    lines = ["# Skill Portfolio Report", ""]
    lines.append(f"- Repository: `{report['repo_root']}`")
    lines.append(f"- Skills: `{report['skill_count']}`")
    lines.append(f"- Passing: `{report['passing_count']}`")
    lines.append("")
    lines.append("## Skills")
    lines.append("")
    for item in report["skills"]:
        lines.append(
            f"- `{item['skill_name']}`: overall `{'PASS' if item['overall_passed'] else 'FAIL'}`, "
            f"evals `{item['eval_count']}`, categories `{', '.join(item['categories']) or 'none'}`"
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a repository-wide skill portfolio report.")
    parser.add_argument("repo_root", help="Repository root")
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument("--markdown-output", help="Optional Markdown output path")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"[ERROR] Repository root not found: {repo_root}")
        return 1

    skills = []
    for skill_dir in find_skills(repo_root):
        benchmark = run_benchmark(skill_dir)
        skills.append(
            {
                "skill_name": benchmark["skill_name"],
                "skill_dir": str(skill_dir),
                "overall_passed": benchmark["overall_passed"],
                "eval_count": benchmark["evals"]["count"],
                "categories": [item["category"] for item in benchmark["evals"]["category_summary"]],
            }
        )

    report = {
        "repo_root": str(repo_root),
        "skill_count": len(skills),
        "passing_count": sum(1 for item in skills if item["overall_passed"]),
        "skills": skills,
    }

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown_output:
        markdown_path = Path(args.markdown_output).resolve()
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
