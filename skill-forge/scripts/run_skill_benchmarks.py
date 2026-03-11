#!/usr/bin/env python3
"""Run benchmark checks for a skill and emit structured reports."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from quick_validate import extract_frontmatter, read_text

REQUIRED_EVAL_FIELDS = ("id", "prompt", "expected_output", "files")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_evals(evals_path: Path) -> tuple[list[dict], list[str]]:
    if not evals_path.exists():
        return [], ["evals/evals.json not found"]

    try:
        payload = load_json(evals_path)
    except json.JSONDecodeError as exc:
        return [], [f"evals/evals.json is invalid JSON: {exc}"]

    evals = payload.get("evals")
    if not isinstance(evals, list) or not evals:
        return [], ["evals/evals.json must contain a non-empty evals list"]

    errors: list[str] = []
    normalized: list[dict] = []
    seen_ids: set[int] = set()

    for index, item in enumerate(evals, start=1):
        if not isinstance(item, dict):
            errors.append(f"eval #{index} is not an object")
            continue

        item_errors: list[str] = []
        for field in REQUIRED_EVAL_FIELDS:
            if field not in item:
                item_errors.append(f"missing field: {field}")

        eval_id = item.get("id")
        if isinstance(eval_id, int):
            if eval_id in seen_ids:
                item_errors.append(f"duplicate id: {eval_id}")
            else:
                seen_ids.add(eval_id)
        else:
            item_errors.append("field 'id' must be an integer")

        if "prompt" in item and not isinstance(item["prompt"], str):
            item_errors.append("field 'prompt' must be a string")
        if "expected_output" in item and not isinstance(item["expected_output"], str):
            item_errors.append("field 'expected_output' must be a string")
        if "files" in item and not isinstance(item["files"], list):
            item_errors.append("field 'files' must be a list")

        category = item.get("category", "uncategorized")
        if not isinstance(category, str) or not category.strip():
            item_errors.append("field 'category' must be a non-empty string when provided")
            category = "uncategorized"

        normalized.append(
            {
                "id": eval_id if isinstance(eval_id, int) else index,
                "category": category.strip(),
                "prompt": item.get("prompt", ""),
                "expected_output": item.get("expected_output", ""),
                "files": item.get("files", []) if isinstance(item.get("files", []), list) else [],
                "passed": not item_errors,
                "errors": item_errors,
            }
        )
        for item_error in item_errors:
            errors.append(f"eval #{index}: {item_error}")

    return normalized, errors


def run_quick_validate(skill_dir: Path, config: str | None) -> tuple[bool, str]:
    script = Path(__file__).resolve().parent / "quick_validate.py"
    command = [sys.executable, str(script), str(skill_dir)]
    if config:
        command.extend(["--config", config])
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def summarize_categories(evals: list[dict]) -> list[dict]:
    totals = Counter(item["category"] for item in evals)
    passes = Counter(item["category"] for item in evals if item["passed"])
    return [
        {"category": category, "passed": passes.get(category, 0), "total": total}
        for category, total in sorted(totals.items())
    ]


def build_diff(report: dict, previous: dict | None) -> dict | None:
    if not previous:
        return None

    previous_categories = {
        item["category"]: item for item in previous.get("evals", {}).get("category_summary", [])
    }
    current_categories = {item["category"]: item for item in report["evals"]["category_summary"]}
    all_categories = sorted(set(previous_categories) | set(current_categories))

    category_deltas = []
    for category in all_categories:
        current = current_categories.get(category, {"passed": 0, "total": 0})
        old = previous_categories.get(category, {"passed": 0, "total": 0})
        category_deltas.append(
            {
                "category": category,
                "passed_delta": current["passed"] - old["passed"],
                "total_delta": current["total"] - old["total"],
            }
        )

    return {
        "overall_passed_changed": report["overall_passed"] != previous.get("overall_passed"),
        "eval_count_delta": report["evals"]["count"] - previous.get("evals", {}).get("count", 0),
        "category_deltas": category_deltas,
    }


def build_report(skill_dir: Path, config: str | None, previous_output: Path | None) -> dict:
    frontmatter = extract_frontmatter(read_text(skill_dir / "SKILL.md"))
    skill_name = frontmatter.get("name", skill_dir.name)
    valid, validate_output = run_quick_validate(skill_dir, config)
    eval_items, eval_errors = load_evals(skill_dir / "evals" / "evals.json")
    eval_passed = not eval_errors and bool(eval_items) and all(item["passed"] for item in eval_items)
    overall_pass = valid and eval_passed

    report = {
        "skill_name": skill_name,
        "skill_dir": str(skill_dir),
        "quick_validate": {"passed": valid, "output": validate_output},
        "evals": {
            "count": len(eval_items),
            "passed": eval_passed,
            "errors": eval_errors,
            "category_summary": summarize_categories(eval_items),
            "items": eval_items,
        },
        "overall_passed": overall_pass,
    }

    if previous_output and previous_output.exists():
        report["diff_vs_previous"] = build_diff(report, load_json(previous_output))
    else:
        report["diff_vs_previous"] = None
    return report


def render_markdown(report: dict) -> str:
    lines = [
        f"# Benchmark Report: {report['skill_name']}",
        "",
        f"- Skill directory: `{report['skill_dir']}`",
        f"- Quick validate: `{'PASS' if report['quick_validate']['passed'] else 'FAIL'}`",
        f"- Evals: `{'PASS' if report['evals']['passed'] else 'FAIL'}` ({report['evals']['count']} cases)",
        f"- Overall: `{'PASS' if report['overall_passed'] else 'FAIL'}`",
        "",
        "## Quick Validate",
        "",
        "```text",
        report["quick_validate"]["output"] or "(no output)",
        "```",
        "",
        "## Category Summary",
        "",
    ]

    for item in report["evals"]["category_summary"] or []:
        lines.append(f"- `{item['category']}`: {item['passed']}/{item['total']}")
    if not report["evals"]["category_summary"]:
        lines.append("- No eval categories found")

    diff = report.get("diff_vs_previous")
    if diff:
        lines.extend(["", "## Diff Vs Previous", "", f"- Eval count delta: `{diff['eval_count_delta']}`"])
        lines.append(f"- Overall changed: `{diff['overall_passed_changed']}`")
        for item in diff["category_deltas"]:
            lines.append(
                f"- `{item['category']}`: passed delta `{item['passed_delta']}`, total delta `{item['total_delta']}`"
            )

    lines.extend(["", "## Eval Details", ""])
    for item in report["evals"]["items"]:
        status = "PASS" if item["passed"] else "FAIL"
        lines.append(f"### Eval {item['id']} - {status}")
        lines.append(f"- Category: `{item['category']}`")
        lines.append(f"- Prompt: {item['prompt']}")
        lines.append(f"- Expected: {item['expected_output']}")
        lines.append(f"- Files: {len(item['files'])}")
        if item["errors"]:
            lines.append("- Errors:")
            for error in item["errors"]:
                lines.append(f"  - {error}")
        lines.append("")

    if report["evals"]["errors"]:
        lines.extend(["## Eval Errors", ""])
        for error in report["evals"]["errors"]:
            lines.append(f"- {error}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def print_pretty(report: dict) -> None:
    print(f"Skill: {report['skill_name']}")
    print(f"Directory: {report['skill_dir']}")
    print(f"Quick validate: {'PASS' if report['quick_validate']['passed'] else 'FAIL'}")
    if report["quick_validate"]["output"]:
        print(report["quick_validate"]["output"])
    print(f"Evals: {'PASS' if report['evals']['passed'] else 'FAIL'} ({report['evals']['count']} cases)")
    for summary in report["evals"]["category_summary"]:
        print(f"- {summary['category']}: {summary['passed']}/{summary['total']}")
    diff = report.get("diff_vs_previous")
    if diff:
        print(f"Diff vs previous: eval_count_delta={diff['eval_count_delta']}")
        for item in diff["category_deltas"]:
            print(f"- delta {item['category']}: passed {item['passed_delta']}, total {item['total_delta']}")
    for error in report["evals"]["errors"]:
        print(f"- {error}")
    print(f"Overall: {'PASS' if report['overall_passed'] else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark checks for a skill.")
    parser.add_argument("skill_dir", help="Path to skill directory")
    parser.add_argument("--config", help="Optional JSON config file")
    parser.add_argument("--pretty", action="store_true", help="Print a readable report")
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument("--markdown-output", help="Optional Markdown report output path")
    parser.add_argument("--previous-output", help="Optional previous benchmark JSON for diffing")
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    if not skill_dir.is_dir():
        print(f"[ERROR] Skill directory not found: {skill_dir}")
        return 1

    previous_output = Path(args.previous_output).resolve() if args.previous_output else None
    report = build_report(skill_dir, args.config, previous_output)
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown_output:
        markdown_path = Path(args.markdown_output).resolve()
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
    if args.pretty:
        print_pretty(report)
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
