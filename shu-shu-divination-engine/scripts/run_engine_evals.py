#!/usr/bin/env python3
"""Run local engine evals and emit JSON / Markdown reports."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
EVALS_FILE = SKILL_DIR / "evals" / "evals.json"
RESULTS_FILE = SKILL_DIR / "evals" / "engine-eval-results.json"
REPORT_FILE = SKILL_DIR / "evals" / "engine-eval-report.md"
STATUS_FILE = SKILL_DIR / "evals" / "engine-eval-status.md"


def load_engine():
    engine_path = SCRIPT_DIR / "divination_engine.py"
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("shu_shu_divination_engine_eval", engine_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load engine from {engine_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def deep_get(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if part == "__len__":
            current = len(current)
            continue
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


@dataclass
class AssertionResult:
    path: str
    assertion_type: str
    passed: bool
    expected: Any
    actual: Any


def evaluate_assertion(payload: dict[str, Any], assertion: dict[str, Any]) -> AssertionResult:
    actual = deep_get(payload, assertion["path"])
    expected = assertion["value"]
    assertion_type = assertion["type"]

    if assertion_type == "equals":
        passed = actual == expected
    elif assertion_type == "contains":
        passed = expected in actual
    elif assertion_type == "gte":
        passed = actual >= expected
    else:
        raise ValueError(f"Unsupported assertion type: {assertion_type}")

    return AssertionResult(
        path=assertion["path"],
        assertion_type=assertion_type,
        passed=passed,
        expected=expected,
        actual=actual,
    )


def run() -> int:
    engine = load_engine()
    suite = read_json(EVALS_FILE)
    evals = suite["evals"]
    results: list[dict[str, Any]] = []

    for item in evals:
        inputs = item.get("inputs", {})
        payload = engine.analyze_prompt(item["prompt"], **inputs)
        assertion_results = [evaluate_assertion(payload, assertion) for assertion in item.get("assertions", [])]
        passed = all(assertion.passed for assertion in assertion_results)
        results.append(
            {
                "id": item["id"],
                "name": item["name"],
                "category": item["category"],
                "prompt": item["prompt"],
                "expected_output": item["expected_output"],
                "passed": passed,
                "assertions": [
                    {
                        "path": assertion.path,
                        "type": assertion.assertion_type,
                        "passed": assertion.passed,
                        "expected": assertion.expected,
                        "actual": assertion.actual,
                    }
                    for assertion in assertion_results
                ],
                "routing": payload["routing"],
                "execution_status": payload["execution"]["status"],
                "headline": payload["final_response"]["headline"],
            }
        )

    total = len(results)
    passed_count = sum(1 for item in results if item["passed"])
    failed = [item for item in results if not item["passed"]]

    summary = {
        "skill_name": suite["skill_name"],
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "pass_rate": round((passed_count / total) * 100, 2) if total else 0.0,
        "results": results,
    }
    RESULTS_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report_lines = [
        "# Engine Eval Report",
        "",
        f"- Skill: `{suite['skill_name']}`",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Pass rate: {summary['pass_rate']}%",
        "",
        "## Case Results",
        "",
    ]
    for item in results:
        report_lines.append(f"### {item['id']}. {item['name']}")
        report_lines.append("")
        report_lines.append(f"- Category: `{item['category']}`")
        report_lines.append(f"- Result: {'PASS' if item['passed'] else 'FAIL'}")
        report_lines.append(f"- Routing: `{item['routing']['selected_method']}`")
        report_lines.append(f"- Execution: `{item['execution_status']}`")
        report_lines.append(f"- Headline: {item['headline']}")
        report_lines.append("- Assertions:")
        for assertion in item["assertions"]:
            mark = "PASS" if assertion["passed"] else "FAIL"
            report_lines.append(
                f"  - [{mark}] {assertion['path']} {assertion['type']} {assertion['expected']} | actual={assertion['actual']}"
            )
        report_lines.append("")
    REPORT_FILE.write_text("\n".join(report_lines), encoding="utf-8")

    status_lines = [
        "# Engine Eval Status",
        "",
        f"- Skill: `{suite['skill_name']}`",
        f"- Total cases: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Pass rate: {summary['pass_rate']}%",
        f"- Results JSON: `evals/engine-eval-results.json`",
        f"- Report Markdown: `evals/engine-eval-report.md`",
    ]
    if failed:
        status_lines.extend(
            [
                "",
                "## Failed Cases",
                "",
                *[f"- {item['id']}. {item['name']}" for item in failed],
            ]
        )
    else:
        status_lines.extend(["", "## Status", "", "- All local engine evals passed."])
    STATUS_FILE.write_text("\n".join(status_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
