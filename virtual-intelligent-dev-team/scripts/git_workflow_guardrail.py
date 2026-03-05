#!/usr/bin/env python3
"""
Deterministic guardrails for Git workflow stages (G0-G4).
"""

from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate deterministic Git workflow guardrail stages")
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument("--stage", required=True, choices=["G0", "G1", "G2", "G3", "G4"], help="Workflow stage")
    parser.add_argument("--commit-message", default=None, help="Commit message for G2 validation")
    parser.add_argument(
        "--max-staged-files",
        type=int,
        default=20,
        help="Maximum allowed staged files for single commit intent",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = Path(args.repo).resolve()
    try:
        result = validate_stage(
            repo=repo,
            stage=args.stage,
            commit_message=args.commit_message,
            max_staged_files=max(args.max_staged_files, 1),
        )
        exit_code = 0
    except Exception as exc:
        result = {
            "stage": args.stage,
            "passed": False,
            "error": str(exc),
        }
        exit_code = 2

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
