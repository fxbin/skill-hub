#!/usr/bin/env python3
"""Run benchmark suite and generate machine/human-readable reports."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent
TEST_SCRIPT = SKILL_DIR / "tests" / "test_routing_and_guardrails.py"
VALIDATOR_SCRIPT = SKILL_DIR / "scripts" / "validate_virtual_team.py"
ROUTE_SCRIPT = SKILL_DIR / "scripts" / "route_request.py"
CONFIG_PATH = SKILL_DIR / "references" / "routing-rules.json"
EVALS_PATH = SKILL_DIR / "evals" / "evals.json"
DEFAULT_OUTPUT_DIR = SKILL_DIR / "evals" / "benchmark-results"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


route_request = load_module("virtual_team_route_request_benchmark", ROUTE_SCRIPT)


def load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return data


def load_config() -> dict[str, object]:
    config = load_json(CONFIG_PATH)
    governance = config.setdefault("governance", {})
    if isinstance(governance, dict):
        fast_track = governance.setdefault("fast_track_control", {})
        if isinstance(fast_track, dict):
            fast_track["write_event_log"] = False
    return config


def classify_prompt(text: str) -> list[str]:
    lowered = text.lower()
    tags: list[str] = []

    if any(route_request.keyword_matches(lowered, token) for token in ["react", "next.js", "tailwind", "shadcn", "ui", "ux", "dashboard", "frontend", "front-end", "framer motion"]):
        tags.append("frontend")
    if any(route_request.keyword_matches(lowered, token) for token in ["python", "django", "flask", "fastapi", "celery", "go", "gin", "node", "nestjs", "java", "spring", "rust"]):
        tags.append("backend-stack")
    if any(route_request.keyword_matches(lowered, token) for token in ["commit", "push", "worktree", "branch", "git", "rebase", "merge"]):
        tags.append("git-workflow")
    if any(route_request.keyword_matches(lowered, token) for token in ["review", "audit", "security review", "ux review", "code review"]):
        tags.append("review")
    if any(route_request.keyword_matches(lowered, token) for token in ["strategy", "growth", "saas", "industry", "compliance"]):
        tags.append("strategy-domain")
    if any(route_request.keyword_matches(lowered, token) for token in ["backend", "api contract", "auth", "implementation", "technical plan", "tech plan"]):
        tags.append("cross-domain")
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        tags.append("chinese")
    if any(ch.isascii() and ch.isalpha() for ch in text) and any("\u4e00" <= ch <= "\u9fff" for ch in text):
        tags.append("mixed-language")
    if len(text.strip()) <= 24:
        tags.append("short-prompt")
    if len(tags) == 0:
        tags.append("general")
    return tags


def run_command(command: list[str], cwd: Path) -> dict[str, object]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "passed": proc.returncode == 0,
    }


def read_nested(data: object, path: str) -> object:
    aliases = {
        "priority_routing agent": "reason.priority_routing.agent",
    }
    path = aliases.get(path, path)
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def parse_expectation(expectation: str, result: dict[str, object]) -> tuple[bool, str]:
    if expectation == "assistant_agents is empty":
        value = result.get("assistant_agents")
        return value == [], f"assistant_agents={value!r}"
    if expectation == "process_skills is empty":
        value = result.get("process_skills")
        return value == [], f"process_skills={value!r}"
    if expectation == "clarifying_question is not null":
        value = result.get("clarifying_question")
        return value is not None, f"clarifying_question={value!r}"
    if expectation == "mode is not single-agent execution":
        value = str(result.get("mode"))
        return "模式 A" not in value and "single-agent" not in value.lower(), f"mode={value!r}"
    if expectation.startswith("process_plan first commands contain "):
        expected = expectation.removeprefix("process_plan first commands contain ")
        plans = result.get("process_plan")
        if not isinstance(plans, list) or len(plans) == 0:
            return False, f"process_plan={plans!r}"
        commands = plans[0].get("commands") if isinstance(plans[0], dict) else None
        if not isinstance(commands, list):
            return False, f"process_plan[0].commands={commands!r}"
        return expected in commands, f"process_plan[0].commands={commands!r}"

    if " contains " in expectation:
        field, expected = expectation.split(" contains ", 1)
        value = read_nested(result, field.strip())
        if isinstance(value, list):
            return expected in value, f"{field.strip()}={value!r}"
        return False, f"{field.strip()}={value!r}"

    if " is not " in expectation:
        field, expected = expectation.split(" is not ", 1)
        value = read_nested(result, field.strip())
        return str(value) != expected, f"{field.strip()}={value!r}"

    if " is " in expectation:
        field, expected = expectation.split(" is ", 1)
        value = read_nested(result, field.strip())
        if expected == "true":
            return value is True, f"{field.strip()}={value!r}"
        if expected == "false":
            return value is False, f"{field.strip()}={value!r}"
        if expected == "0.0":
            return float(value) == 0.0, f"{field.strip()}={value!r}"
        if expected == "regular track":
            return str(value) in {"regular track", "三省六部轨"}, f"{field.strip()}={value!r}"
        if expected == "fast track":
            return str(value) in {"fast track", "军机处直通轨"}, f"{field.strip()}={value!r}"
        return str(value) == expected, f"{field.strip()}={value!r}"

    return False, "unsupported expectation"


def evaluate_evals(config: dict[str, object]) -> dict[str, object]:
    payload = load_json(EVALS_PATH)
    evals = payload.get("evals", [])
    if not isinstance(evals, list):
        raise RuntimeError("evals.json evals must be a list")

    cases: list[dict[str, object]] = []
    category_totals: Counter[str] = Counter()
    category_passed: Counter[str] = Counter()

    for item in evals:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt", ""))
        expectations = item.get("expectations", [])
        if not isinstance(expectations, list):
            expectations = []
        result = route_request.route_request(prompt, config, repo_path=REPO_ROOT)
        failures: list[str] = []
        for raw in expectations:
            ok, detail = parse_expectation(str(raw), result)
            if not ok:
                failures.append(f"{raw} [{detail}]")
        raw_categories = item.get("categories")
        if isinstance(raw_categories, list) and all(isinstance(category, str) for category in raw_categories):
            tags = [str(category) for category in raw_categories]
        else:
            tags = classify_prompt(prompt)
        passed = len(failures) == 0
        for tag in tags:
            category_totals[tag] += 1
            if passed:
                category_passed[tag] += 1
        cases.append(
            {
                "id": item.get("id"),
                "prompt": prompt,
                "tags": tags,
                "lead_agent": result.get("lead_agent"),
                "assistant_agents": result.get("assistant_agents"),
                "passed": passed,
                "failures": failures,
            }
        )

    return {
        "passed": sum(1 for case in cases if case["passed"]),
        "total": len(cases),
        "cases": cases,
        "category_breakdown": [
            {
                "category": category,
                "passed": category_passed[category],
                "total": category_totals[category],
                "pass_rate": round(category_passed[category] / max(category_totals[category], 1), 3),
            }
            for category in sorted(category_totals)
        ],
    }


def build_summary(test_run: dict[str, object], validator_run: dict[str, object], eval_run: dict[str, object]) -> dict[str, object]:
    lead_counter = Counter()
    assistant_counter = Counter()
    failures: list[dict[str, object]] = []

    for case in eval_run["cases"]:
        lead_counter[str(case["lead_agent"])] += 1
        for assistant in case["assistant_agents"]:
            assistant_counter[str(assistant)] += 1
        if not case["passed"]:
            failures.append(
                {
                    "id": case["id"],
                    "prompt": case["prompt"],
                    "failures": case["failures"],
                }
            )

    return {
        "tests_passed": bool(test_run["passed"]),
        "validator_passed": bool(validator_run["passed"]),
        "evals_passed": int(eval_run["passed"]) == int(eval_run["total"]),
        "overall_passed": bool(test_run["passed"]) and bool(validator_run["passed"]) and int(eval_run["passed"]) == int(eval_run["total"]),
        "lead_distribution": dict(lead_counter.most_common()),
        "assistant_distribution": dict(assistant_counter.most_common()),
        "eval_failures": failures,
    }


def render_markdown(result: dict[str, object]) -> str:
    lines: list[str] = []
    summary = result["summary"]
    tests = result["test_run"]
    validator = result["validator_run"]
    evals = result["eval_run"]
    diff = result.get("diff")

    lines.append("# Benchmark Report")
    lines.append("")
    lines.append(f"- Generated: `{result['generated_at']}`")
    lines.append(f"- Overall: `{'PASS' if summary['overall_passed'] else 'FAIL'}`")
    lines.append(f"- Unit tests: `{'PASS' if summary['tests_passed'] else 'FAIL'}`")
    lines.append(f"- Semantic regression: `{'PASS' if summary['validator_passed'] else 'FAIL'}`")
    lines.append(f"- Eval prompts: `{evals['passed']}/{evals['total']}`")
    lines.append("")
    lines.append("## Breakdown")
    lines.append("")
    for item in evals["category_breakdown"]:
        lines.append(f"- `{item['category']}`: `{item['passed']}/{item['total']}`")
    if isinstance(diff, dict):
        lines.append("")
        lines.append("## Diff Vs Previous")
        lines.append("")
        previous = diff.get("previous_summary", {})
        if isinstance(previous, dict):
            lines.append(
                f"- Previous evals: `{previous.get('evals_passed', 0)}/{previous.get('evals_total', 0)}`"
            )
            lines.append(
                f"- Current evals: `{evals['passed']}/{evals['total']}`"
            )
        new_failures = diff.get("new_failures", [])
        resolved_failures = diff.get("resolved_failures", [])
        category_changes = diff.get("category_changes", [])
        lines.append(f"- New failures: `{len(new_failures)}`")
        lines.append(f"- Resolved failures: `{len(resolved_failures)}`")
        if category_changes:
            lines.append("")
            lines.append("### Category Changes")
            lines.append("")
            for item in category_changes:
                lines.append(
                    f"- `{item['category']}`: `{item['previous_passed']}/{item['previous_total']}` -> `{item['current_passed']}/{item['current_total']}`"
                )
    lines.append("")
    lines.append("## Lead Distribution")
    lines.append("")
    for lead, count in summary["lead_distribution"].items():
        lines.append(f"- `{lead}`: `{count}`")
    lines.append("")
    lines.append("## Assistant Distribution")
    lines.append("")
    if summary["assistant_distribution"]:
        for assistant, count in summary["assistant_distribution"].items():
            lines.append(f"- `{assistant}`: `{count}`")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Commands")
    lines.append("")
    lines.append(f"- Tests: `{' '.join(tests['command'])}` -> return code `{tests['returncode']}`")
    lines.append(f"- Validator: `{' '.join(validator['command'])}` -> return code `{validator['returncode']}`")
    lines.append("")
    lines.append("## Eval Failures")
    lines.append("")
    if summary["eval_failures"]:
        for item in summary["eval_failures"]:
            lines.append(f"- `#{item['id']}` {item['prompt']}")
            for failure in item["failures"]:
                lines.append(f"  - {failure}")
    else:
        lines.append("- None")
    if isinstance(diff, dict):
        new_failures = diff.get("new_failures", [])
        resolved_failures = diff.get("resolved_failures", [])
        lines.append("")
        lines.append("## Failure Delta")
        lines.append("")
        if new_failures:
            lines.append("### New Failures")
            lines.append("")
            for item in new_failures:
                lines.append(f"- `#{item['id']}` {item['prompt']}")
        else:
            lines.append("- New failures: None")
        lines.append("")
        if resolved_failures:
            lines.append("### Resolved Failures")
            lines.append("")
            for item in resolved_failures:
                lines.append(f"- `#{item['id']}` {item['prompt']}")
        else:
            lines.append("- Resolved failures: None")
    return "\n".join(lines) + "\n"


def load_previous_result(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    data = load_json(path)
    if "eval_run" not in data or "summary" not in data:
        return None
    return data


def build_diff(current: dict[str, object], previous: dict[str, object]) -> dict[str, object]:
    current_cases = {
        str(case.get("id")): case for case in current["eval_run"]["cases"] if isinstance(case, dict)
    }
    previous_cases = {
        str(case.get("id")): case for case in previous["eval_run"]["cases"] if isinstance(case, dict)
    }
    new_failures: list[dict[str, object]] = []
    resolved_failures: list[dict[str, object]] = []
    for case_id, case in current_cases.items():
        prev = previous_cases.get(case_id)
        if prev is None:
            continue
        if bool(prev.get("passed")) and not bool(case.get("passed")):
            new_failures.append({"id": case.get("id"), "prompt": case.get("prompt")})
        if not bool(prev.get("passed")) and bool(case.get("passed")):
            resolved_failures.append({"id": case.get("id"), "prompt": case.get("prompt")})

    prev_categories = {
        item["category"]: item
        for item in previous["eval_run"].get("category_breakdown", [])
        if isinstance(item, dict) and "category" in item
    }
    curr_categories = {
        item["category"]: item
        for item in current["eval_run"].get("category_breakdown", [])
        if isinstance(item, dict) and "category" in item
    }
    all_categories = sorted(set(prev_categories) | set(curr_categories))
    category_changes: list[dict[str, object]] = []
    for category in all_categories:
        prev = prev_categories.get(category, {"passed": 0, "total": 0})
        curr = curr_categories.get(category, {"passed": 0, "total": 0})
        if prev.get("passed") != curr.get("passed") or prev.get("total") != curr.get("total"):
            category_changes.append(
                {
                    "category": category,
                    "previous_passed": prev.get("passed", 0),
                    "previous_total": prev.get("total", 0),
                    "current_passed": curr.get("passed", 0),
                    "current_total": curr.get("total", 0),
                }
            )

    prev_summary = previous.get("summary", {})
    return {
        "previous_summary": {
            "evals_passed": previous["eval_run"].get("passed", 0),
            "evals_total": previous["eval_run"].get("total", 0),
            "overall_passed": prev_summary.get("overall_passed"),
        },
        "new_failures": new_failures,
        "resolved_failures": resolved_failures,
        "category_changes": category_changes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run benchmark suite for virtual-intelligent-dev-team")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for benchmark artifacts")
    parser.add_argument("--previous-output", help="Previous benchmark JSON report for diff comparison")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON summary to stdout")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()
    test_run = run_command([sys.executable, str(TEST_SCRIPT)], cwd=SKILL_DIR)
    validator_run = run_command([sys.executable, str(VALIDATOR_SCRIPT), "--pretty"], cwd=SKILL_DIR)
    eval_run = evaluate_evals(config)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "skill_name": "virtual-intelligent-dev-team",
        "test_run": test_run,
        "validator_run": validator_run,
        "eval_run": eval_run,
    }
    result["summary"] = build_summary(test_run, validator_run, eval_run)
    if args.previous_output:
        previous = load_previous_result(Path(args.previous_output).resolve())
        if previous is not None:
            result["diff"] = build_diff(result, previous)

    json_path = output_dir / "benchmark-results.json"
    md_path = output_dir / "benchmark-report.md"
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    with md_path.open("w", encoding="utf-8") as file:
        file.write(render_markdown(result))

    stdout_payload = {
        "ok": result["summary"]["overall_passed"],
        "json_report": str(json_path),
        "markdown_report": str(md_path),
        "evals_passed": eval_run["passed"],
        "evals_total": eval_run["total"],
        "tests_passed": test_run["passed"],
        "validator_passed": validator_run["passed"],
    }
    if "diff" in result:
        stdout_payload["new_failures"] = len(result["diff"].get("new_failures", []))
        stdout_payload["resolved_failures"] = len(result["diff"].get("resolved_failures", []))
    if args.pretty:
        print(json.dumps(stdout_payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(stdout_payload, ensure_ascii=False))
    raise SystemExit(0 if result["summary"]["overall_passed"] else 2)


if __name__ == "__main__":
    main()
