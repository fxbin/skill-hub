#!/usr/bin/env python3
"""
Deterministic guardrails for Git workflow stages (G0-G4).
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import re
import subprocess
from pathlib import Path


COMMIT_PREFIX_PATTERN = re.compile(
    r"^(feat|fix|refactor|docs|chore|perf|test|build|ci|style)(\([^)]+\))?:\s+\S.+$"
)
SENSITIVE_FILE_PATTERNS = (
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"(^|/).*\.pem$"),
    re.compile(r"(^|/).*\.key$"),
    re.compile(r"(^|/)id_rsa(\.|$)"),
    re.compile(r"(^|/)secrets?(\.|/|$)"),
)
HIGH_RISK_COMMAND_PATTERNS = (
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\s+-[^\n]*f[^\n]*\b"),
    re.compile(r"\bgit\s+push\s+--force(?:-with-lease)?\b"),
)
MEDIUM_RISK_COMMAND_PATTERNS = (
    re.compile(r"\bgit\s+pull\b"),
    re.compile(r"\bgit\s+push\b"),
    re.compile(r"\bgit\s+merge\b"),
    re.compile(r"\bgit\s+rebase\b"),
    re.compile(r"\bgit\s+cherry-pick\b"),
    re.compile(r"\bgit\s+commit\b"),
)
LOW_RISK_COMMAND_PATTERNS = (
    re.compile(r"\bgit\s+status\b"),
    re.compile(r"\bgit\s+log\b"),
    re.compile(r"\bgit\s+diff\b"),
    re.compile(r"\bgit\s+branch\b"),
    re.compile(r"\bgit\s+show\b"),
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_git(repo: Path, *args: str) -> str:
    cmd = ["git", "-C", str(repo), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"Command failed: {' '.join(cmd)}; stderr={stderr}")
    return (proc.stdout or "").strip()


def run_git_optional(repo: Path, *args: str) -> tuple[int, str]:
    cmd = ["git", "-C", str(repo), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    output = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode, output


def check_repo(repo: Path) -> None:
    output = run_git(repo, "rev-parse", "--is-inside-work-tree")
    if output.lower() != "true":
        raise RuntimeError(f"Not a git repo: {repo}")


def current_branch(repo: Path) -> str:
    branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        raise RuntimeError("Detached HEAD is not allowed for guarded workflow")
    return branch


def list_staged_files(repo: Path) -> list[str]:
    output = run_git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if output == "":
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def get_head_sha(repo: Path) -> str:
    return run_git(repo, "rev-parse", "HEAD")


def get_stash_count(repo: Path) -> int:
    output = run_git(repo, "stash", "list")
    if output == "":
        return 0
    return len([line for line in output.splitlines() if line.strip()])


def get_repo_checkpoint(repo: Path) -> dict[str, object]:
    branch = current_branch(repo)
    head = get_head_sha(repo)
    porcelain = run_git(repo, "status", "--porcelain")
    staged = 0
    unstaged = 0
    untracked = 0
    for line in porcelain.splitlines():
        if line.startswith("??"):
            untracked += 1
            continue
        if len(line) >= 2:
            x = line[0]
            y = line[1]
            if x != " ":
                staged += 1
            if y != " ":
                unstaged += 1
    return {
        "branch": branch,
        "head": head,
        "staged_changes": staged,
        "unstaged_changes": unstaged,
        "untracked_files": untracked,
        "stash_count": get_stash_count(repo),
    }


def detect_repo_strategy(repo: Path) -> dict[str, str]:
    branches_output = run_git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    branches = {line.strip() for line in branches_output.splitlines() if line.strip()}
    has_main = "main" in branches
    has_master = "master" in branches
    has_develop = "develop" in branches

    if has_develop and (has_main or has_master):
        base_branch = "main" if has_main else "master"
        return {"strategy": "git-flow-lite", "base_branch": base_branch}
    if has_main:
        return {"strategy": "trunk-main", "base_branch": "main"}
    if has_master:
        return {"strategy": "trunk-master", "base_branch": "master"}
    fallback = "develop" if has_develop else "main"
    return {"strategy": "custom", "base_branch": fallback}


def build_git_templates(strategy: str, base_branch: str) -> dict[str, object]:
    if strategy == "git-flow-lite":
        branch_template = "feature/<ticket>-<summary>"
    else:
        branch_template = "feat/<ticket>-<summary>"
    return {
        "branch_template": branch_template,
        "commit_template": "fix: 修复 <模块> 的 <问题>",
        "pr_title_template": "fix: <模块> - <变更摘要>",
        "pr_description_sections": ["背景", "改动点", "风险与回滚", "验证结果"],
        "base_branch": base_branch,
    }


def analyze_command_policy(commands: list[str]) -> dict[str, object]:
    decisions: list[dict[str, object]] = []
    for command in commands:
        lowered = command.lower().strip()
        risk = "unknown"
        auto_execute = False
        requires_confirmation = True

        if any(pattern.search(lowered) for pattern in HIGH_RISK_COMMAND_PATTERNS):
            risk = "high"
        elif any(pattern.search(lowered) for pattern in MEDIUM_RISK_COMMAND_PATTERNS):
            risk = "medium"
        elif any(pattern.search(lowered) for pattern in LOW_RISK_COMMAND_PATTERNS):
            risk = "low"
            auto_execute = True
            requires_confirmation = False

        decisions.append(
            {
                "command": command,
                "risk": risk,
                "auto_execute": auto_execute,
                "requires_confirmation": requires_confirmation,
            }
        )

    risk_order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    max_risk = "low"
    for item in decisions:
        current = item["risk"]
        if risk_order[current] > risk_order[max_risk]:
            max_risk = current
    return {"max_risk": max_risk, "decisions": decisions}


def list_unmerged_files(repo: Path) -> list[str]:
    output = run_git(repo, "diff", "--name-only", "--diff-filter=U")
    if output == "":
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def upstream_relation(repo: Path) -> tuple[int, int]:
    code, _ = run_git_optional(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if code != 0:
        raise RuntimeError("No upstream configured for current branch")
    counts = run_git(repo, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    parts = counts.split()
    if len(parts) != 2:
        raise RuntimeError(f"Unexpected rev-list output: {counts}")
    behind = int(parts[0])
    ahead = int(parts[1])
    return behind, ahead


def contains_sensitive_files(files: list[str]) -> list[str]:
    blocked: list[str] = []
    for name in files:
        normalized = name.replace("\\", "/").lower()
        for pattern in SENSITIVE_FILE_PATTERNS:
            if pattern.search(normalized):
                blocked.append(name)
                break
    return blocked


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_g0(repo: Path) -> dict[str, object]:
    branch = current_branch(repo)
    unmerged = list_unmerged_files(repo)
    ensure(len(unmerged) == 0, f"Unmerged files found: {', '.join(unmerged)}")
    return {"branch": branch}


def validate_g1(repo: Path, max_staged_files: int) -> dict[str, object]:
    staged = list_staged_files(repo)
    ensure(len(staged) > 0, "No staged files found")
    ensure(len(staged) <= max_staged_files, f"Too many staged files: {len(staged)} > {max_staged_files}")
    blocked = contains_sensitive_files(staged)
    ensure(len(blocked) == 0, f"Sensitive files detected in staged set: {', '.join(blocked)}")
    return {"staged_files": staged, "staged_count": len(staged)}


def validate_g2(repo: Path, commit_message: str | None, max_staged_files: int) -> dict[str, object]:
    staged_result = validate_g1(repo, max_staged_files)
    ensure(commit_message is not None and commit_message.strip() != "", "Commit message is required for G2")
    normalized_message = commit_message.strip()
    ensure(
        COMMIT_PREFIX_PATTERN.match(normalized_message) is not None,
        "Commit message must use semantic prefix, for example: fix: correct xxx",
    )
    return {"commit_message": normalized_message, **staged_result}


def validate_g3(repo: Path) -> dict[str, object]:
    unmerged = list_unmerged_files(repo)
    ensure(len(unmerged) == 0, f"Unmerged files found: {', '.join(unmerged)}")
    behind, ahead = upstream_relation(repo)
    ensure(behind == 0, f"Branch is behind upstream by {behind} commits")
    return {"behind": behind, "ahead": ahead}


def validate_g4(repo: Path) -> dict[str, object]:
    g3_result = validate_g3(repo)
    ahead = int(g3_result["ahead"])
    ensure(ahead > 0, "No commits ahead of upstream, nothing to push or open PR for")
    return g3_result


def validate_stage(
    repo: Path,
    stage: str,
    commit_message: str | None,
    max_staged_files: int,
) -> dict[str, object]:
    check_repo(repo)
    current_branch(repo)

    validators = {
        "G0": lambda: validate_g0(repo),
        "G1": lambda: validate_g1(repo, max_staged_files),
        "G2": lambda: validate_g2(repo, commit_message, max_staged_files),
        "G3": lambda: validate_g3(repo),
        "G4": lambda: validate_g4(repo),
    }
    if stage not in validators:
        raise RuntimeError(f"Unknown stage: {stage}")

    details = validators[stage]()
    return {
        "stage": stage,
        "passed": True,
        "details": details,
    }


def build_recovery_plan(stage: str, checkpoint: dict[str, object]) -> list[str]:
    branch = str(checkpoint.get("branch", "<current-branch>"))
    head = str(checkpoint.get("head", "<head-sha>"))
    common = [
        f"git checkout {branch}",
        f"git reset --soft {head}",
    ]
    stage_specific = {
        "G0": [
            "git status --short --branch",
            "确认当前分支是否正确",
        ],
        "G1": [
            "git restore --staged <file>",
            "缩小暂存范围后重试 G1",
        ],
        "G2": [
            "调整提交信息并重新执行 G2 校验",
            "按单一意图拆分提交",
        ],
        "G3": [
            "git pull --rebase origin <base-branch>",
            "若冲突无法判断，停止并请求人工决策",
        ],
        "G4": [
            "git push -u origin <branch>",
            "若远端拒绝，检查权限或保护分支策略",
        ],
    }
    return common + stage_specific.get(stage, [])


def append_metrics(metrics_file: Path, payload: dict[str, object]) -> None:
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    with metrics_file.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate deterministic Git workflow guardrail stages")
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument("--stage", choices=["G0", "G1", "G2", "G3", "G4"], help="Workflow stage")
    parser.add_argument("--commit-message", default=None, help="Commit message for G2 validation")
    parser.add_argument(
        "--analyze-command",
        action="append",
        default=[],
        help="Analyze command risk policy, can be repeated",
    )
    parser.add_argument(
        "--detect-repo-strategy",
        action="store_true",
        help="Detect repository strategy and recommended base branch",
    )
    parser.add_argument(
        "--print-templates",
        action="store_true",
        help="Print branch/commit/PR templates from detected repository strategy",
    )
    parser.add_argument(
        "--max-staged-files",
        type=int,
        default=20,
        help="Maximum allowed staged files for single commit intent",
    )
    parser.add_argument(
        "--metrics-file",
        default=".skill-metrics/git_guardrail_metrics.jsonl",
        help="Metrics output file path",
    )
    parser.add_argument(
        "--disable-metrics",
        action="store_true",
        help="Disable metrics writing",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = Path(args.repo).resolve()
    if args.stage is None and not args.detect_repo_strategy and not args.print_templates and len(args.analyze_command) == 0:
        raise SystemExit("At least one action is required: --stage, --detect-repo-strategy, --print-templates, --analyze-command")

    strategy_info: dict[str, str] | None = None
    templates: dict[str, object] | None = None
    command_policy: dict[str, object] | None = None
    checkpoint: dict[str, object] | None = None
    stage_result: dict[str, object] | None = None

    try:
        check_repo(repo)
        checkpoint = get_repo_checkpoint(repo)

        if args.detect_repo_strategy or args.print_templates:
            strategy_info = detect_repo_strategy(repo)

        if args.print_templates:
            if strategy_info is None:
                strategy_info = detect_repo_strategy(repo)
            templates = build_git_templates(
                strategy=strategy_info["strategy"],
                base_branch=strategy_info["base_branch"],
            )

        if len(args.analyze_command) > 0:
            command_policy = analyze_command_policy(args.analyze_command)

        if args.stage is not None:
            stage_result = validate_stage(
                repo=repo,
                stage=args.stage,
                commit_message=args.commit_message,
                max_staged_files=max(args.max_staged_files, 1),
            )

        result = {
            "timestamp": now_iso(),
            "repo": str(repo),
            "checkpoint": checkpoint,
            "stage_result": stage_result,
            "repo_strategy": strategy_info,
            "templates": templates,
            "command_policy": command_policy,
            "passed": True if stage_result is None else bool(stage_result.get("passed", False)),
        }
        exit_code = 0
    except Exception as exc:
        if checkpoint is None:
            try:
                checkpoint = get_repo_checkpoint(repo)
            except Exception:
                checkpoint = None
        recovery_plan = build_recovery_plan(args.stage or "G0", checkpoint or {})
        result = {
            "timestamp": now_iso(),
            "repo": str(repo),
            "checkpoint": checkpoint,
            "stage_result": {
                "stage": args.stage,
                "passed": False,
            },
            "error": str(exc),
            "recovery_plan": recovery_plan,
            "passed": False,
        }
        exit_code = 2

    if not args.disable_metrics:
        try:
            metrics_payload = {
                "timestamp": result.get("timestamp"),
                "repo": result.get("repo"),
                "stage": (result.get("stage_result") or {}).get("stage"),
                "passed": result.get("passed"),
                "strategy": (result.get("repo_strategy") or {}).get("strategy"),
                "base_branch": (result.get("repo_strategy") or {}).get("base_branch"),
                "max_risk": (result.get("command_policy") or {}).get("max_risk"),
            }
            append_metrics(Path(args.metrics_file), metrics_payload)
            result["metrics_file"] = str(Path(args.metrics_file).resolve())
        except Exception as metrics_exc:
            result["metrics_error"] = str(metrics_exc)

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
