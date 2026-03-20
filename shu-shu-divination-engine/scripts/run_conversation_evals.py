#!/usr/bin/env python3
"""Run multi-turn conversation evals against the local divination engine."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
EVALS_FILE = SKILL_DIR / "evals" / "conversation-evals.json"
RESULTS_FILE = SKILL_DIR / "evals" / "conversation-eval-results.json"
REPORT_FILE = SKILL_DIR / "evals" / "conversation-eval-report.md"
STATUS_FILE = SKILL_DIR / "evals" / "conversation-eval-status.md"


def load_engine():
    engine_path = SCRIPT_DIR / "divination_engine.py"
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("shu_shu_divination_engine_conversation_eval", engine_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load engine from {engine_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def evaluate_assertion(payload: dict[str, Any], assertion: dict[str, Any]) -> dict[str, Any]:
    actual = deep_get(payload, assertion["path"])
    expected = assertion["value"]
    assertion_type = assertion["type"]
    if assertion_type == "equals":
        passed = actual == expected
    elif assertion_type == "contains":
        passed = expected in actual
    else:
        raise ValueError(f"Unsupported assertion type: {assertion_type}")
    return {
        "path": assertion["path"],
        "type": assertion_type,
        "expected": expected,
        "actual": actual,
        "passed": passed,
    }


def run() -> int:
    engine = load_engine()
    suite = json.loads(EVALS_FILE.read_text(encoding="utf-8"))
    cases = suite["evals"]
    results: list[dict[str, Any]] = []

    for case in cases:
        running_prompt = ""
        turn_results: list[dict[str, Any]] = []
        case_passed = True
        for turn in case["turns"]:
            prompt = turn.get("prompt")
            if prompt:
                running_prompt = prompt
            elif "prompt_append" in turn:
                running_prompt = f"{running_prompt} {turn['prompt_append']}".strip()
            payload = engine.analyze_prompt(running_prompt, **turn.get("inputs", {}))
            assertion_results = [evaluate_assertion(payload, assertion) for assertion in turn.get("assertions", [])]
            turn_passed = all(item["passed"] for item in assertion_results)
            case_passed = case_passed and turn_passed
            turn_results.append(
                {
                    "prompt": running_prompt,
                    "passed": turn_passed,
                    "assertions": assertion_results,
                    "routing": payload["routing"],
                    "execution_status": payload["execution"]["status"],
                    "headline": payload["final_response"]["headline"],
                }
            )
        results.append(
            {
                "id": case["id"],
                "name": case["name"],
                "passed": case_passed,
                "turns": turn_results,
            }
        )

    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    failed = total - passed
    pass_rate = round((passed / total) * 100, 2) if total else 0.0

    payload = {
        "skill_name": suite["skill_name"],
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "results": results,
    }
    RESULTS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report_lines = [
        "# Conversation Eval Report",
        "",
        f"- Skill: `{suite['skill_name']}`",
        f"- Total: {total}",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        f"- Pass rate: {pass_rate}%",
        "",
        "## Case Results",
        "",
    ]
    for case in results:
        report_lines.append(f"### {case['id']}. {case['name']}")
        report_lines.append("")
        report_lines.append(f"- Result: {'PASS' if case['passed'] else 'FAIL'}")
        for index, turn in enumerate(case["turns"], start=1):
            report_lines.append(f"- Turn {index}: {'PASS' if turn['passed'] else 'FAIL'} | routing={turn['routing']['selected_method']} | execution={turn['execution_status']}")
            for assertion in turn["assertions"]:
                mark = "PASS" if assertion["passed"] else "FAIL"
                report_lines.append(
                    f"  - [{mark}] {assertion['path']} {assertion['type']} {assertion['expected']} | actual={assertion['actual']}"
                )
        report_lines.append("")
    REPORT_FILE.write_text("\n".join(report_lines), encoding="utf-8")

    status_lines = [
        "# Conversation Eval Status",
        "",
        f"- Skill: `{suite['skill_name']}`",
        f"- Total cases: {total}",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        f"- Pass rate: {pass_rate}%",
    ]
    if failed:
        status_lines.extend(["", "## Failed Cases", "", *[f"- {item['id']}. {item['name']}" for item in results if not item["passed"]]])
    else:
        status_lines.extend(["", "## Status", "", "- All multi-turn conversation evals passed."])
    STATUS_FILE.write_text("\n".join(status_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
