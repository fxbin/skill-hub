#!/usr/bin/env python3
"""Semantic regression validation for virtual-intelligent-dev-team."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
import subprocess
from pathlib import Path
from uuid import uuid4


SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent
TMP_ROOT = REPO_ROOT / ".tmp-validation"
CONFIG_PATH = SKILL_DIR / "references" / "routing-rules.json"
CASES_PATH = SKILL_DIR / "references" / "regression-cases.json"
ROUTE_SCRIPT = SKILL_DIR / "scripts" / "route_request.py"
GUARDRAIL_SCRIPT = SKILL_DIR / "scripts" / "git_workflow_guardrail.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


route_request = load_module("virtual_team_route_request_validator", ROUTE_SCRIPT)
guardrail = load_module("virtual_team_guardrail_validator", GUARDRAIL_SCRIPT)


def load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return data


def load_config() -> dict[str, object]:
    config = load_json(CONFIG_PATH)
    governance = config.setdefault("governance", {})
    if not isinstance(governance, dict):
        raise RuntimeError("routing-rules.json governance must be an object")
    fast_track = governance.setdefault("fast_track_control", {})
    if not isinstance(fast_track, dict):
        raise RuntimeError("routing-rules.json governance.fast_track_control must be an object")
    fast_track["write_event_log"] = False
    return config


def run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    return (proc.stdout or "").strip()


def configure_repo(repo: Path) -> None:
    run_git("config", "user.name", "Codex Validator", cwd=repo)
    run_git("config", "user.email", "codex-validator@example.com", cwd=repo)


@contextmanager
def make_tempdir():
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TMP_ROOT / f"tmp-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    yield str(path)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_routing_cases(config: dict[str, object], cases: list[dict[str, object]]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for case in cases:
        name = str(case.get("name", "unnamed"))
        text = str(case.get("text", ""))
        expect = case.get("expect", {})
        if not isinstance(expect, dict):
            raise AssertionError(f"routing case {name} missing expect object")

        result = route_request.route_request(text=text, config=config, repo_path=REPO_ROOT)
        check(result["lead_agent"] == expect.get("lead_agent"), f"{name}: unexpected lead_agent")

        if "assistant_agents" in expect:
            check(result["assistant_agents"] == expect["assistant_agents"], f"{name}: unexpected assistants")
        if "assistant_agents_contains" in expect:
            expected_agents = expect["assistant_agents_contains"]
            check(isinstance(expected_agents, list), f"{name}: assistant_agents_contains must be a list")
            for agent in expected_agents:
                check(agent in result["assistant_agents"], f"{name}: missing assistant {agent}")
        if "needs_git_workflow" in expect:
            check(result["needs_git_workflow"] == expect["needs_git_workflow"], f"{name}: unexpected needs_git_workflow")
        if "process_skills" in expect:
            check(result["process_skills"] == expect["process_skills"], f"{name}: unexpected process_skills")

        priority_agent = (result["reason"]["priority_routing"] or {}).get("agent")
        check(priority_agent == expect.get("priority_agent"), f"{name}: unexpected priority routing agent")
        results.append({"name": name, "status": "passed"})
    return results


def validate_process_plan_cases(cases: list[dict[str, object]]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for case in cases:
        name = str(case.get("name", "unnamed"))
        repo_strategy = case.get("repo_strategy", {})
        expect = case.get("expect", {})
        if not isinstance(repo_strategy, dict) or not isinstance(expect, dict):
            raise AssertionError(f"process plan case {name} is malformed")

        plan = route_request.build_process_plan(
            needs_worktree=bool(case.get("needs_worktree", False)),
            needs_git_workflow=bool(case.get("needs_git_workflow", False)),
            repo_strategy=repo_strategy,
        )
        check(len(plan) > 0, f"{name}: empty process plan")
        commands = plan[0].get("commands", [])
        check(isinstance(commands, list), f"{name}: commands must be a list")

        for command in expect.get("commands_contains", []):
            check(command in commands, f"{name}: missing command {command}")
        for first, second in expect.get("ordered_pairs", []):
            check(first in commands and second in commands, f"{name}: missing ordered pair commands")
            check(commands.index(first) < commands.index(second), f"{name}: invalid command order")
        results.append({"name": name, "status": "passed"})
    return results


def scenario_g0_staged_should_fail() -> None:
    with make_tempdir() as tmp:
        repo = Path(tmp)
        run_git("init", cwd=repo)
        configure_repo(repo)
        (repo / "demo.txt").write_text("base\n", encoding="utf-8")
        run_git("add", "demo.txt", cwd=repo)
        run_git("commit", "-m", "chore: init repo", cwd=repo)
        (repo / "demo.txt").write_text("base\nchange\n", encoding="utf-8")
        run_git("add", "demo.txt", cwd=repo)

        try:
            guardrail.validate_stage(repo=repo, stage="G0", commit_message=None, max_staged_files=20)
        except RuntimeError as exc:
            check("pre-existing staged changes" in str(exc), "g0 staged case: unexpected error message")
            return
        raise AssertionError("g0 staged case: expected failure did not occur")


def scenario_g3_behind_should_report_sync() -> None:
    with make_tempdir() as tmp:
        repo = Path(tmp)
        run_git("init", cwd=repo)
        configure_repo(repo)
        run_git("checkout", "-b", "main", cwd=repo)
        (repo / "demo.txt").write_text("v1\n", encoding="utf-8")
        run_git("add", "demo.txt", cwd=repo)
        run_git("commit", "-m", "feat: add demo file", cwd=repo)
        base_sha = run_git("rev-parse", "HEAD", cwd=repo)

        run_git("branch", "upstream-main", cwd=repo)
        run_git("checkout", "upstream-main", cwd=repo)
        (repo / "demo.txt").write_text("v1\nv2\n", encoding="utf-8")
        run_git("add", "demo.txt", cwd=repo)
        run_git("commit", "-m", "fix: update demo file", cwd=repo)

        run_git("checkout", "main", cwd=repo)
        run_git("reset", "--hard", base_sha, cwd=repo)
        run_git("branch", "--set-upstream-to=upstream-main", "main", cwd=repo)

        result = guardrail.validate_stage(repo=repo, stage="G3", commit_message=None, max_staged_files=20)
        details = result.get("details", {})
        check(result.get("passed") is True, "g3 behind case: expected pass")
        check(int(details.get("behind", 0)) == 1, "g3 behind case: expected behind=1")
        check(bool(details.get("requires_sync")) is True, "g3 behind case: expected requires_sync=true")


def validate_guardrail_cases(cases: list[dict[str, object]]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for case in cases:
        name = str(case.get("name", "unnamed"))
        case_type = str(case.get("type", ""))
        if case_type == "command_policy":
            expect = case.get("expect", {})
            if not isinstance(expect, dict):
                raise AssertionError(f"{name}: expect must be an object")
            commands = case.get("commands", [])
            check(isinstance(commands, list), f"{name}: commands must be a list")
            policy = guardrail.analyze_command_policy(commands)
            check(policy["max_risk"] == expect.get("max_risk"), f"{name}: unexpected max_risk")
            decisions = expect.get("decisions", {})
            check(isinstance(decisions, dict), f"{name}: decisions must be an object")
            policy_map = {item["command"]: item["risk"] for item in policy["decisions"]}
            for command, risk in decisions.items():
                check(policy_map.get(command) == risk, f"{name}: unexpected risk for {command}")
        elif case_type == "g0_staged_should_fail":
            scenario_g0_staged_should_fail()
        elif case_type == "g3_behind_should_report_sync":
            scenario_g3_behind_should_report_sync()
        else:
            raise AssertionError(f"{name}: unknown guardrail case type {case_type}")
        results.append({"name": name, "status": "passed"})
    return results


def validate() -> dict[str, object]:
    config = load_config()
    cases = load_json(CASES_PATH)

    routing_cases = cases.get("routing_cases", [])
    process_plan_cases = cases.get("process_plan_cases", [])
    guardrail_cases = cases.get("guardrail_cases", [])
    check(isinstance(routing_cases, list), "routing_cases must be a list")
    check(isinstance(process_plan_cases, list), "process_plan_cases must be a list")
    check(isinstance(guardrail_cases, list), "guardrail_cases must be a list")

    sections = {
        "routing_cases": validate_routing_cases(config, routing_cases),
        "process_plan_cases": validate_process_plan_cases(process_plan_cases),
        "guardrail_cases": validate_guardrail_cases(guardrail_cases),
    }
    total_passed = sum(len(items) for items in sections.values())
    return {
        "ok": True,
        "config_version": str(config.get("meta", {}).get("version", "unknown")),
        "cases_file": str(CASES_PATH),
        "passed": total_passed,
        "sections": sections,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate semantic regressions for virtual-intelligent-dev-team")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = validate()
        exit_code = 0
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        exit_code = 2

    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
