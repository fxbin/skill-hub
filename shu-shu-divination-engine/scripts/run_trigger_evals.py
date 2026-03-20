#!/usr/bin/env python3
"""Run trigger-eval proxy tests through Claude CLI or Codex CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILL_FILE = SKILL_DIR / "SKILL.md"
EVALS_FILE = SKILL_DIR / "evals" / "trigger-evals.json"
RESULTS_FILE = SKILL_DIR / "evals" / "trigger-eval-results.json"
STATUS_FILE = SKILL_DIR / "evals" / "trigger-eval-status.md"
REPORT_FILE = SKILL_DIR / "evals" / "trigger-eval-report.md"

DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_SMOKE_COUNT = 3
MAX_EXCERPT_LENGTH = 1200
CONFIDENCE_LEVELS = {"high", "medium", "low"}

DECISION_INSTRUCTIONS = """
任务：执行一项 skill 触发二分类评测。

你接下来看到的是“评测材料”，不是用户要你完成的真实任务。不要回答 query，不要解释角色，不要确认边界；只做触发判断。

严格要求：
1. 只输出一个 JSON 对象。
2. 不要输出 markdown。
3. 不要输出解释性前言、后记、代码块。
4. 输出格式必须是：
{"trigger": true, "confidence": "high", "reason": "一句中文理由"}

判定原则：
- 只根据 <skill_name>、<skill_description>、<user_query> 里的内容做判断。
- 不要把本条提示本身当成用户 query。
- 如果 user_query 明显属于这个 skill 的核心处理范围，而且调用该 skill 能明显提升处理质量，返回 true。
- 如果 user_query 本质属于相邻体系、普通闲聊、其他任务类型，或没有必要动用该 skill，返回 false。
- confidence 只能是 high / medium / low。
- reason 用一句简洁中文说明判断依据。
""".strip()


class RunnerError(RuntimeError):
    """Raised when a provider command cannot complete normally."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@dataclass
class ProviderCommand:
    provider: str
    command: list[str]


@dataclass
class DecisionOutput:
    decision: dict[str, Any]
    raw_result: str
    stdout: str
    stderr: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def truncate_text(text: str, limit: int = MAX_EXCERPT_LENGTH) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def extract_frontmatter_scalar(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", text)
    if not match:
        raise RuntimeError(f"SKILL.md 缺少 frontmatter 字段: {key}")
    return match.group(1).strip().strip('"').strip("'")


def load_skill_metadata() -> tuple[str, str]:
    skill_text = read_text(SKILL_FILE)
    if not skill_text.startswith("---"):
        raise RuntimeError("SKILL.md 缺少 YAML frontmatter")
    return (
        extract_frontmatter_scalar(skill_text, "name"),
        extract_frontmatter_scalar(skill_text, "description"),
    )


def which_command(candidates: list[str]) -> list[str] | None:
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if not resolved:
            continue
        lowered = resolved.lower()
        if lowered.endswith(".ps1"):
            return ["powershell", "-NoProfile", "-File", resolved]
        return [resolved]
    return None


def resolve_provider_command(provider: str) -> ProviderCommand:
    claude_command = which_command(["claude.cmd", "claude.exe", "claude", "claude.ps1"])
    codex_command = which_command(["codex.cmd", "codex.exe", "codex", "codex.ps1"])

    if provider == "claude":
        if not claude_command:
            raise RuntimeError("未在 PATH 中找到 Claude CLI")
        return ProviderCommand(provider="claude", command=claude_command)

    if provider == "codex":
        if not codex_command:
            raise RuntimeError("未在 PATH 中找到 Codex CLI")
        return ProviderCommand(provider="codex", command=codex_command)

    if claude_command:
        return ProviderCommand(provider="claude", command=claude_command)
    if codex_command:
        return ProviderCommand(provider="codex", command=codex_command)
    raise RuntimeError("未在 PATH 中找到可用的 trigger-eval provider（Claude CLI / Codex CLI）")


def build_prompt(skill_name: str, skill_description: str, query: str) -> str:
    return "\n".join(
        [
            DECISION_INSTRUCTIONS,
            "",
            "下面开始提供评测材料。",
            "",
            "<skill_name>",
            skill_name,
            "</skill_name>",
            "",
            "<skill_description>",
            skill_description,
            "</skill_description>",
            "",
            "<user_query>",
            query,
            "</user_query>",
            "",
            "输出要求：现在只返回判定 JSON，不要回答 user_query 本身，也不要复述任务说明。",
        ]
    )


def parse_decision_json(raw_text: str) -> dict[str, Any]:
    candidate_text = raw_text.strip()
    if not candidate_text:
        raise ValueError("模型输出为空")

    try:
        candidate = json.loads(candidate_text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", candidate_text)
        if not match:
            raise ValueError("模型输出中未找到 JSON 对象") from None
        candidate = json.loads(match.group(0))

    if not isinstance(candidate, dict):
        raise ValueError("模型输出不是 JSON 对象")

    trigger = candidate.get("trigger")
    if isinstance(trigger, str):
        lowered = trigger.strip().lower()
        if lowered == "true":
            trigger = True
        elif lowered == "false":
            trigger = False
    if not isinstance(trigger, bool):
        raise ValueError("trigger 字段不是布尔值")

    confidence = str(candidate.get("confidence", "")).strip().lower()
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError("confidence 字段不是 high / medium / low")

    reason = str(candidate.get("reason", "")).strip()
    if not reason:
        raise ValueError("reason 字段为空")

    return {
        "trigger": trigger,
        "confidence": confidence,
        "reason": reason,
    }


def run_subprocess(
    command: list[str],
    *,
    timeout_seconds: int,
    cwd: Path,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    creationflags = 0
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
        return subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        else:
            process.kill()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = ""
        raise RunnerError(
            f"命令执行超时（>{timeout_seconds}s）",
            error_type="timeout",
            stdout=stdout,
            stderr=stderr,
        )


def call_claude(
    provider: ProviderCommand,
    prompt: str,
    *,
    model: str | None,
    timeout_seconds: int,
) -> DecisionOutput:
    command = provider.command + [
        "-p",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        "--system-prompt",
        DECISION_INSTRUCTIONS,
    ]
    if model:
        command.extend(["--model", model])

    completed = run_subprocess(
        command,
        timeout_seconds=timeout_seconds,
        cwd=SKILL_DIR,
        input_text=prompt,
    )
    if completed.returncode != 0:
        raise RunnerError(
            "Claude CLI 执行失败",
            error_type="process_error",
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RunnerError(
            f"Claude CLI 返回的外层 JSON 无法解析: {exc}",
            error_type="outer_json_parse_error",
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        ) from exc

    raw_result = payload.get("result", "")
    if not isinstance(raw_result, str):
        raw_result = json.dumps(raw_result, ensure_ascii=False)

    try:
        decision = parse_decision_json(raw_result)
    except ValueError as exc:
        raise RunnerError(
            f"Claude CLI 返回结果无法解析为判定 JSON: {exc}",
            error_type="decision_parse_error",
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        ) from exc

    return DecisionOutput(
        decision=decision,
        raw_result=raw_result,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_codex_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "trigger": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "reason": {"type": "string", "minLength": 1},
        },
        "required": ["trigger", "confidence", "reason"],
    }


def call_codex(
    provider: ProviderCommand,
    prompt: str,
    *,
    model: str | None,
    timeout_seconds: int,
) -> DecisionOutput:
    with tempfile.TemporaryDirectory(prefix="trigger-eval-") as temp_dir:
        temp_path = Path(temp_dir)
        schema_path = temp_path / "decision-schema.json"
        output_path = temp_path / "last-message.json"
        write_text(schema_path, json.dumps(build_codex_schema(), ensure_ascii=False, indent=2))

        command = provider.command + [
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--json",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            prompt,
        ]
        if model:
            command[1:1] = ["--model", model]

        completed = run_subprocess(command, timeout_seconds=timeout_seconds, cwd=temp_path)
        if completed.returncode != 0:
            raise RunnerError(
                "Codex CLI 执行失败",
                error_type="process_error",
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        if not output_path.exists():
            raise RunnerError(
                "Codex CLI 没有写出最终消息文件",
                error_type="missing_output_file",
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        raw_result = read_text(output_path)
        try:
            decision = parse_decision_json(raw_result)
        except ValueError as exc:
            raise RunnerError(
                f"Codex CLI 返回结果无法解析为判定 JSON: {exc}",
                error_type="decision_parse_error",
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            ) from exc

        return DecisionOutput(
            decision=decision,
            raw_result=raw_result,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def call_provider(
    provider: ProviderCommand,
    prompt: str,
    *,
    model: str | None,
    timeout_seconds: int,
) -> DecisionOutput:
    if provider.provider == "claude":
        return call_claude(provider, prompt, model=model, timeout_seconds=timeout_seconds)
    if provider.provider == "codex":
        return call_codex(provider, prompt, model=model, timeout_seconds=timeout_seconds)
    raise RuntimeError(f"不支持的 provider: {provider.provider}")


def normalize_eval_items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise RuntimeError("trigger-evals.json 必须是数组")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"trigger-evals.json 第 {index} 项不是对象")
        query = str(item.get("query", "")).strip()
        if not query:
            raise RuntimeError(f"trigger-evals.json 第 {index} 项缺少 query")
        normalized.append(
            {
                "id": item.get("id", index),
                "query": query,
                "should_trigger": bool(item.get("should_trigger")),
            }
        )
    return normalized


def select_eval_items(
    eval_items: list[dict[str, Any]],
    *,
    offset: int,
    limit: int | None,
    smoke: bool,
    smoke_count: int,
) -> list[dict[str, Any]]:
    selected = eval_items[offset:]
    if smoke and limit is None:
        limit = smoke_count
    if limit is not None:
        selected = selected[:limit]
    return selected


def build_case_result(
    item: dict[str, Any],
    *,
    provider_name: str,
    duration_ms: int,
    decision_output: DecisionOutput | None = None,
    error: RunnerError | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": item["id"],
        "query": item["query"],
        "should_trigger": item["should_trigger"],
        "provider": provider_name,
        "duration_ms": duration_ms,
    }

    if decision_output is not None:
        triggered = bool(decision_output.decision["trigger"])
        should_trigger = bool(item["should_trigger"])
        base.update(
            {
                "status": "completed",
                "triggered": triggered,
                "pass": triggered == should_trigger,
                "confidence": decision_output.decision["confidence"],
                "reason": decision_output.decision["reason"],
                "raw_result": decision_output.raw_result,
                "stdout_excerpt": truncate_text(decision_output.stdout),
                "stderr_excerpt": truncate_text(decision_output.stderr),
            }
        )
        return base

    assert error is not None
    base.update(
        {
            "status": "error",
            "triggered": None,
            "pass": False,
            "confidence": "",
            "reason": "",
            "raw_result": "",
            "error_type": error.error_type,
            "error_message": str(error),
            "returncode": error.returncode,
            "stdout_excerpt": truncate_text(error.stdout),
            "stderr_excerpt": truncate_text(error.stderr),
        }
    )
    return base


def compute_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    completed = [item for item in results if item["status"] == "completed"]
    errors = [item for item in results if item["status"] == "error"]
    passed = sum(1 for item in results if item["pass"])
    failed = total - passed

    should_trigger_results = [item for item in completed if item["should_trigger"]]
    should_not_trigger_results = [item for item in completed if not item["should_trigger"]]

    return {
        "total": total,
        "completed": len(completed),
        "errored": len(errors),
        "passed": passed,
        "failed": failed,
        "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
        "should_trigger_total": sum(1 for item in results if item["should_trigger"]),
        "should_trigger_passed": sum(1 for item in results if item["pass"] and item["should_trigger"]),
        "should_not_trigger_total": sum(1 for item in results if not item["should_trigger"]),
        "should_not_trigger_passed": sum(1 for item in results if item["pass"] and not item["should_trigger"]),
        "mean_duration_ms": round(sum(item["duration_ms"] for item in results) / total, 2) if total else 0.0,
        "completed_should_trigger": len(should_trigger_results),
        "completed_should_not_trigger": len(should_not_trigger_results),
    }


def write_outputs(
    payload: dict[str, Any],
    *,
    results_file: Path,
    report_file: Path,
    status_file: Path,
) -> None:
    write_text(results_file, json.dumps(payload, ensure_ascii=False, indent=2))
    write_text(report_file, build_report(payload))
    write_text(status_file, build_status(payload))


def build_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    run_meta = payload["run_meta"]
    lines = [
        "# Trigger Eval Report",
        "",
        f"- Skill: `{payload['skill_name']}`",
        f"- Provider: `{run_meta['provider']}`",
        f"- Run mode: `{run_meta['run_mode']}`",
        f"- Total eval set size: {run_meta['total_eval_set_size']}",
        f"- Selected cases: {summary['total']}",
        f"- Completed: {summary['completed']}",
        f"- Errors: {summary['errored']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Pass rate: {summary['pass_rate']}%",
        f"- Mean duration: {summary['mean_duration_ms']} ms",
        f"- Should-trigger pass: {summary['should_trigger_passed']}/{summary['should_trigger_total']}",
        f"- Should-not-trigger pass: {summary['should_not_trigger_passed']}/{summary['should_not_trigger_total']}",
        "",
        "## 结果含义",
        "",
        "- 这是 CLI 代理评测，不等于产品内核中的真实自动触发率。",
        "- 该结果适合做描述迭代、样本集迭代和烟测回归，不应冒充最终产品触发分数。",
        "",
        "## Case Results",
        "",
    ]

    for item in payload["results"]:
        title = "PASS" if item["pass"] else "FAIL"
        if item["status"] == "error":
            title = "ERROR"
        lines.extend(
            [
                f"### {item['id']}. {title}",
                "",
                f"- Query: {item['query']}",
                f"- Should trigger: `{item['should_trigger']}`",
                f"- Triggered: `{item['triggered']}`",
                f"- Provider: `{item['provider']}`",
                f"- Duration: `{item['duration_ms']} ms`",
            ]
        )
        if item["status"] == "completed":
            lines.extend(
                [
                    f"- Confidence: `{item['confidence']}`",
                    f"- Reason: {item['reason']}",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Error type: `{item['error_type']}`",
                    f"- Error message: {item['error_message']}",
                ]
            )
        lines.append("")

    return "\n".join(lines)


def build_status(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    run_meta = payload["run_meta"]
    if payload.get("status") == "running":
        current_state = "running"
    elif run_meta["run_mode"] == "smoke":
        current_state = "smoke-tested"
    elif summary["errored"] > 0:
        current_state = "completed-with-errors"
    else:
        current_state = "completed"

    lines = [
        "# Trigger Eval Status",
        "",
        f"- Skill: `{payload['skill_name']}`",
        f"- Eval mode: `{payload['evaluation_mode']}`",
        f"- Provider: `{run_meta['provider']}`",
        f"- Current state: `{current_state}`",
        f"- Selected cases: {summary['total']}/{run_meta['total_eval_set_size']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Errors: {summary['errored']}",
        f"- Pass rate: {summary['pass_rate']}%",
        "- Trustworthy product-native pass rate: `not available yet`",
        "",
        "## 当前结论",
        "",
        "- trigger 代理 runner 已具备可执行能力，并支持 Claude CLI / Codex CLI 两种入口。",
        "- 当前结果只可用作 smoke test 或 description 方向评估，不能替代真实产品触发率。",
        "- 如果要形成更可信的结论，仍需要在稳定环境中完成完整样本集正式跑分。",
        "",
        "## 建议下一步",
        "",
        "- 先用 `--smoke` 做小样本回归，确认 provider 与输出格式稳定。",
        "- 再用完整样本集正式跑一轮，并观察 should-trigger / should-not-trigger 两侧是否失衡。",
        "- 若结果偏差集中在某类 query，再回头精修 `SKILL.md` 的 description 与触发语料。",
    ]
    return "\n".join(lines)


def run(
    *,
    provider_name: str,
    model: str | None,
    limit: int | None,
    offset: int,
    timeout_seconds: int,
    smoke: bool,
    smoke_count: int,
    results_file: Path,
    report_file: Path,
    status_file: Path,
) -> int:
    provider = resolve_provider_command(provider_name)
    skill_name, skill_description = load_skill_metadata()
    all_eval_items = normalize_eval_items(read_json(EVALS_FILE))
    selected_items = select_eval_items(
        all_eval_items,
        offset=offset,
        limit=limit,
        smoke=smoke,
        smoke_count=smoke_count,
    )

    if not selected_items:
        raise RuntimeError("本次没有选中任何 trigger eval case")

    results: list[dict[str, Any]] = []
    payload = {
        "skill_name": skill_name,
        "status": "running",
        "trustworthy": False,
        "evaluation_mode": f"proxy-trigger-eval-via-{provider.provider}-cli",
        "description": skill_description,
        "run_meta": {
            "provider": provider.provider,
            "model": model,
            "timeout_seconds": timeout_seconds,
            "run_mode": "smoke" if smoke or limit is not None or offset > 0 or len(selected_items) < len(all_eval_items) else "formal",
            "offset": offset,
            "limit": limit,
            "smoke_count": smoke_count if smoke else None,
            "total_eval_set_size": len(all_eval_items),
            "selected_case_count": len(selected_items),
            "started_at": datetime.now().astimezone().isoformat(),
        },
        "summary": compute_summary(results),
        "results": results,
    }
    write_outputs(
        payload,
        results_file=results_file,
        report_file=report_file,
        status_file=status_file,
    )

    for item in selected_items:
        start = time.perf_counter()
        prompt = build_prompt(skill_name, skill_description, item["query"])
        try:
            decision_output = call_provider(
                provider,
                prompt,
                model=model,
                timeout_seconds=timeout_seconds,
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                build_case_result(
                    item,
                    provider_name=provider.provider,
                    duration_ms=duration_ms,
                    decision_output=decision_output,
                )
            )
        except RunnerError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            results.append(
                build_case_result(
                    item,
                    provider_name=provider.provider,
                    duration_ms=duration_ms,
                    error=exc,
                )
            )
        payload["summary"] = compute_summary(results)
        write_outputs(
            payload,
            results_file=results_file,
            report_file=report_file,
            status_file=status_file,
        )

    payload["status"] = "completed"
    payload["run_meta"]["completed_at"] = datetime.now().astimezone().isoformat()
    payload["summary"] = compute_summary(results)
    write_outputs(
        payload,
        results_file=results_file,
        report_file=report_file,
        status_file=status_file,
    )

    print(
        json.dumps(
            {
                "provider": provider.provider,
                "run_mode": payload["run_meta"]["run_mode"],
                "selected_cases": payload["summary"]["total"],
                "passed": payload["summary"]["passed"],
                "failed": payload["summary"]["failed"],
                "errored": payload["summary"]["errored"],
                "pass_rate": payload["summary"]["pass_rate"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run trigger evals through Claude CLI or Codex CLI")
    parser.add_argument(
        "--provider",
        choices=["auto", "claude", "codex"],
        default="auto",
        help="选择 trigger 代理 provider，默认自动优先选 Claude CLI",
    )
    parser.add_argument("--model", help="可选 model override")
    parser.add_argument("--limit", type=int, help="只跑前 N 条（配合 smoke 或局部回归）")
    parser.add_argument("--offset", type=int, default=0, help="从第 N 条开始跑")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"单条 case 超时时间（秒），默认 {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument("--smoke", action="store_true", help="启用烟测模式")
    parser.add_argument(
        "--smoke-count",
        type=int,
        default=DEFAULT_SMOKE_COUNT,
        help=f"烟测模式默认跑多少条，默认 {DEFAULT_SMOKE_COUNT}",
    )
    parser.add_argument(
        "--results-file",
        default=str(RESULTS_FILE),
        help="结果 JSON 输出路径",
    )
    parser.add_argument(
        "--report-file",
        default=str(REPORT_FILE),
        help="报告 Markdown 输出路径",
    )
    parser.add_argument(
        "--status-file",
        default=str(STATUS_FILE),
        help="状态 Markdown 输出路径",
    )
    args = parser.parse_args()
    return run(
        provider_name=args.provider,
        model=args.model,
        limit=args.limit,
        offset=args.offset,
        timeout_seconds=args.timeout,
        smoke=args.smoke,
        smoke_count=args.smoke_count,
        results_file=Path(args.results_file).resolve(),
        report_file=Path(args.report_file).resolve(),
        status_file=Path(args.status_file).resolve(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
