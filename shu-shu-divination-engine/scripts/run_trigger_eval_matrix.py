#!/usr/bin/env python3
"""Run the same trigger eval set across multiple providers/models."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
BATCH_RUNNER = SCRIPT_DIR / "run_trigger_eval_batches.py"
OUTPUT_DIR = SKILL_DIR / "evals" / "trigger-matrix"
RESULTS_FILE = SKILL_DIR / "evals" / "trigger-matrix-results.json"
REPORT_FILE = SKILL_DIR / "evals" / "trigger-matrix-report.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    return value.strip("-") or "target"


def parse_target(spec: str) -> dict[str, str | None]:
    parts = spec.split(":", 1)
    provider = parts[0].strip().lower()
    if provider not in {"claude", "codex"}:
        raise ValueError(f"不支持的 provider: {provider}")
    model = parts[1].strip() if len(parts) == 2 and parts[1].strip() else None
    return {"provider": provider, "model": model}


def run_target(
    *,
    python_executable: str,
    target: dict[str, str | None],
    batch_size: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    provider = str(target["provider"])
    model = target["model"]
    target_slug = slugify(f"{provider}-{model or 'default'}")
    target_dir = OUTPUT_DIR / target_slug
    batch_dir = target_dir / "batches"
    results_file = target_dir / "results.json"
    report_file = target_dir / "report.md"
    status_file = target_dir / "status.md"

    command = [
        python_executable,
        str(BATCH_RUNNER),
        "--provider",
        provider,
        "--batch-size",
        str(batch_size),
        "--timeout",
        str(timeout_seconds),
        "--results-file",
        str(results_file),
        "--report-file",
        str(report_file),
        "--status-file",
        str(status_file),
        "--batch-dir",
        str(batch_dir),
    ]
    if model:
        command.extend(["--model", model])

    completed = subprocess.run(
        command,
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return {
            "provider": provider,
            "model": model,
            "target_slug": target_slug,
            "status": "runner-error",
            "returncode": completed.returncode,
            "stdout_excerpt": completed.stdout[-2000:],
            "stderr_excerpt": completed.stderr[-2000:],
            "summary": None,
            "results_file": str(results_file.relative_to(SKILL_DIR)),
            "report_file": str(report_file.relative_to(SKILL_DIR)),
            "status_file": str(status_file.relative_to(SKILL_DIR)),
        }

    payload = read_json(results_file)
    return {
        "provider": provider,
        "model": model,
        "target_slug": target_slug,
        "status": payload.get("status", "completed"),
        "summary": payload.get("summary"),
        "evaluation_mode": payload.get("evaluation_mode"),
        "results_file": str(results_file.relative_to(SKILL_DIR)),
        "report_file": str(report_file.relative_to(SKILL_DIR)),
        "status_file": str(status_file.relative_to(SKILL_DIR)),
    }


def build_report(target_results: list[dict[str, Any]]) -> str:
    lines = [
        "# Trigger Eval Matrix Report",
        "",
        "## Summary",
        "",
    ]
    for item in target_results:
        label = f"{item['provider']}:{item['model']}" if item["model"] else f"{item['provider']}:default"
        if item["summary"] is None:
            lines.extend(
                [
                    f"### {label}",
                    "",
                    f"- Status: `{item['status']}`",
                    f"- Return code: `{item['returncode']}`",
                    "",
                ]
            )
            continue
        summary = item["summary"]
        lines.extend(
            [
                f"### {label}",
                "",
                f"- Status: `{item['status']}`",
                f"- Pass rate: `{summary['pass_rate']}%`",
                f"- Passed: `{summary['passed']}/{summary['total']}`",
                f"- Should-trigger pass: `{summary['should_trigger_passed']}/{summary['should_trigger_total']}`",
                f"- Should-not-trigger pass: `{summary['should_not_trigger_passed']}/{summary['should_not_trigger_total']}`",
                f"- Results: `{item['results_file']}`",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one trigger eval set across multiple providers/models")
    parser.add_argument(
        "--targets",
        nargs="+",
        required=True,
        help="目标列表，格式为 provider[:model]，例如 claude codex gptx:custom-model",
    )
    parser.add_argument("--batch-size", type=int, default=5, help="每个 target 的批大小，默认 5")
    parser.add_argument("--timeout", type=int, default=60, help="单条 case 超时时间（秒）")
    args = parser.parse_args()

    targets = [parse_target(spec) for spec in args.targets]
    target_results: list[dict[str, Any]] = []

    for target in targets:
        print(json.dumps({"stage": "target-start", **target}, ensure_ascii=False))
        result = run_target(
            python_executable=sys.executable,
            target=target,
            batch_size=args.batch_size,
            timeout_seconds=args.timeout,
        )
        target_results.append(result)
        print(json.dumps({"stage": "target-complete", **{k: result[k] for k in ['provider', 'model', 'status', 'summary']}}, ensure_ascii=False))

    payload = {
        "skill_name": "shu-shu-divination-engine",
        "status": "completed",
        "generated_at": datetime.now().astimezone().isoformat(),
        "targets": target_results,
    }
    write_text(RESULTS_FILE, json.dumps(payload, ensure_ascii=False, indent=2))
    write_text(REPORT_FILE, build_report(target_results))
    print(json.dumps({"stage": "done", "results_file": str(RESULTS_FILE.relative_to(SKILL_DIR))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
