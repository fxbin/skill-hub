#!/usr/bin/env python3
"""Run trigger evals in smaller batches and aggregate the final result."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RUNNER_PATH = SCRIPT_DIR / "run_trigger_evals.py"
EVALS_FILE = SKILL_DIR / "evals" / "trigger-evals.json"
RESULTS_FILE = SKILL_DIR / "evals" / "trigger-eval-results.json"
STATUS_FILE = SKILL_DIR / "evals" / "trigger-eval-status.md"
REPORT_FILE = SKILL_DIR / "evals" / "trigger-eval-report.md"
TMP_DIR = SKILL_DIR / "evals" / "trigger-batches"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("shu_shu_trigger_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load runner from {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_batch(
    *,
    python_executable: str,
    provider: str,
    model: str | None,
    timeout_seconds: int,
    offset: int,
    limit: int,
    batch_index: int,
    batch_dir: Path,
) -> dict[str, Any]:
    batch_dir.mkdir(parents=True, exist_ok=True)
    results_file = batch_dir / f"batch-{batch_index:02d}-results.json"
    report_file = batch_dir / f"batch-{batch_index:02d}-report.md"
    status_file = batch_dir / f"batch-{batch_index:02d}-status.md"

    command = [
        python_executable,
        str(RUNNER_PATH),
        "--provider",
        provider,
        "--offset",
        str(offset),
        "--limit",
        str(limit),
        "--timeout",
        str(timeout_seconds),
        "--results-file",
        str(results_file),
        "--report-file",
        str(report_file),
        "--status-file",
        str(status_file),
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
        raise RuntimeError(
            f"Batch {batch_index} 执行失败，returncode={completed.returncode}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    if not results_file.exists():
        raise RuntimeError(f"Batch {batch_index} 未生成结果文件: {results_file}")

    payload = read_json(results_file)
    payload["_batch_index"] = batch_index
    payload["_stdout"] = completed.stdout
    payload["_stderr"] = completed.stderr
    return payload


def aggregate_batches(
    batch_payloads: list[dict[str, Any]],
    *,
    provider: str,
    model: str | None,
    batch_size: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    runner = load_runner_module()
    skill_name, skill_description = runner.load_skill_metadata()
    all_eval_items = runner.normalize_eval_items(read_json(EVALS_FILE))

    results: list[dict[str, Any]] = []
    for payload in batch_payloads:
        results.extend(payload.get("results", []))
    results.sort(key=lambda item: int(item["id"]))

    payload = {
        "skill_name": skill_name,
        "status": "completed",
        "trustworthy": False,
        "evaluation_mode": f"proxy-trigger-eval-via-{provider}-cli-batched",
        "description": skill_description,
        "run_meta": {
            "provider": provider,
            "model": model,
            "timeout_seconds": timeout_seconds,
            "run_mode": "formal-batched",
            "batch_size": batch_size,
            "total_batches": len(batch_payloads),
            "total_eval_set_size": len(all_eval_items),
            "started_at": batch_payloads[0]["run_meta"].get("started_at", ""),
            "completed_at": datetime.now().astimezone().isoformat(),
        },
        "summary": runner.compute_summary(results),
        "results": results,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run trigger evals in batches and aggregate the result")
    parser.add_argument("--provider", choices=["claude", "codex"], default="claude")
    parser.add_argument("--model", help="可选 model override")
    parser.add_argument("--timeout", type=int, default=60, help="单条 case 超时时间（秒）")
    parser.add_argument("--batch-size", type=int, default=5, help="每批跑多少条，默认 5")
    parser.add_argument("--results-file", default=str(RESULTS_FILE), help="聚合结果 JSON 输出路径")
    parser.add_argument("--report-file", default=str(REPORT_FILE), help="聚合报告 Markdown 输出路径")
    parser.add_argument("--status-file", default=str(STATUS_FILE), help="聚合状态 Markdown 输出路径")
    parser.add_argument("--batch-dir", default=str(TMP_DIR), help="批次中间文件输出目录")
    args = parser.parse_args()

    runner = load_runner_module()
    all_eval_items = runner.normalize_eval_items(read_json(EVALS_FILE))
    total = len(all_eval_items)
    batch_payloads: list[dict[str, Any]] = []
    batch_dir = Path(args.batch_dir).resolve()

    for batch_index, offset in enumerate(range(0, total, args.batch_size), start=1):
        current_limit = min(args.batch_size, total - offset)
        print(
            json.dumps(
                {
                    "stage": "batch-start",
                    "batch_index": batch_index,
                    "offset": offset,
                    "limit": current_limit,
                },
                ensure_ascii=False,
            )
        )
        batch_payload = run_batch(
            python_executable=sys.executable,
            provider=args.provider,
            model=args.model,
            timeout_seconds=args.timeout,
            offset=offset,
            limit=current_limit,
            batch_index=batch_index,
            batch_dir=batch_dir,
        )
        batch_payloads.append(batch_payload)
        print(
            json.dumps(
                {
                    "stage": "batch-complete",
                    "batch_index": batch_index,
                    "summary": batch_payload.get("summary", {}),
                },
                ensure_ascii=False,
            )
        )

    final_payload = aggregate_batches(
        batch_payloads,
        provider=args.provider,
        model=args.model,
        batch_size=args.batch_size,
        timeout_seconds=args.timeout,
    )
    results_file = Path(args.results_file).resolve()
    report_file = Path(args.report_file).resolve()
    status_file = Path(args.status_file).resolve()
    write_text(results_file, json.dumps(final_payload, ensure_ascii=False, indent=2))
    write_text(report_file, runner.build_report(final_payload))
    write_text(status_file, runner.build_status(final_payload))

    print(
        json.dumps(
            {
                "stage": "done",
                "provider": args.provider,
                "batch_size": args.batch_size,
                "summary": final_payload["summary"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
