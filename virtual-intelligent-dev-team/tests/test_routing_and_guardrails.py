import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parent
ROUTE_SCRIPT = SKILL_DIR / "scripts" / "route_request.py"
GUARDRAIL_SCRIPT = SKILL_DIR / "scripts" / "git_workflow_guardrail.py"
VALIDATOR_SCRIPT = SKILL_DIR / "scripts" / "validate_virtual_team.py"
CONFIG_PATH = SKILL_DIR / "references" / "routing-rules.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


route_request = load_module("virtual_intelligent_dev_team_route_request", ROUTE_SCRIPT)
guardrail = load_module("virtual_intelligent_dev_team_guardrail", GUARDRAIL_SCRIPT)


def load_config() -> dict[str, object]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)
    config["governance"]["fast_track_control"]["write_event_log"] = False
    return config


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )


def configure_repo(repo: Path) -> None:
    git("config", "user.name", "Codex Test", cwd=repo)
    git("config", "user.email", "codex@example.com", cwd=repo)


class RoutingTests(unittest.TestCase):
    def test_review_java_routes_to_code_audit_with_java_assistant(self) -> None:
        result = route_request.route_request(
            "请 review 这个 Java GC 问题并给出建议",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Code Audit Council", result["lead_agent"])
        self.assertIn("Java Virtuoso", result["assistant_agents"])
        self.assertEqual(
            "Code Audit Council",
            (result["reason"]["priority_routing"] or {}).get("agent"),
        )

    def test_pr_audit_does_not_trigger_git_workflow(self) -> None:
        result = route_request.route_request(
            "这是 PR，帮我做安全审计和重构建议",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Code Audit Council", result["lead_agent"])
        self.assertFalse(result["needs_git_workflow"])
        self.assertEqual([], result["assistant_agents"])
        self.assertEqual([], result["process_skills"])

    def test_ui_review_stays_with_product_architect(self) -> None:
        result = route_request.route_request(
            "给 React 页面做 UI review",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertIsNone(result["reason"]["priority_routing"])

    def test_worktree_plan_uses_repo_base_branch(self) -> None:
        plan = route_request.build_process_plan(
            needs_worktree=True,
            needs_git_workflow=False,
            repo_strategy={"strategy": "trunk-master", "base_branch": "master"},
        )

        self.assertEqual(
            "git worktree add ../wt-<task> -b <branch> master",
            plan[0]["commands"][1],
        )

    def test_git_workflow_plan_checks_before_sync_and_push(self) -> None:
        plan = route_request.build_process_plan(
            needs_worktree=False,
            needs_git_workflow=True,
            repo_strategy={"strategy": "trunk-master", "base_branch": "master"},
        )
        commands = plan[0]["commands"]

        self.assertLess(
            commands.index("python scripts/git_workflow_guardrail.py --repo . --stage G3 --pretty"),
            commands.index("git pull --rebase origin master"),
        )
        self.assertLess(
            commands.index("python scripts/git_workflow_guardrail.py --repo . --stage G4 --pretty"),
            commands.index("git push -u origin feat/<ticket>-<summary>"),
        )

    def test_rebase_conflict_adds_sentinel_assistant(self) -> None:
        result = route_request.route_request(
            "解决 rebase 冲突并给出最稳妥处理路径",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Git Workflow Guardian", result["lead_agent"])
        self.assertIn("Sentinel Architect (NB)", result["assistant_agents"])


class GuardrailTests(unittest.TestCase):
    def test_g0_blocks_preexisting_staged_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git("init", cwd=repo)
            configure_repo(repo)
            (repo / "demo.txt").write_text("base\n", encoding="utf-8")
            git("add", "demo.txt", cwd=repo)
            git("commit", "-m", "chore: init repo", cwd=repo)
            (repo / "demo.txt").write_text("base\nchange\n", encoding="utf-8")
            git("add", "demo.txt", cwd=repo)

            with self.assertRaisesRegex(RuntimeError, "pre-existing staged changes"):
                guardrail.validate_stage(repo=repo, stage="G0", commit_message=None, max_staged_files=20)

    def test_g3_reports_when_branch_is_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            local_a = root / "local-a"
            local_b = root / "local-b"

            git("init", "--bare", str(remote), cwd=root)
            git("clone", str(remote), str(local_a), cwd=root)
            configure_repo(local_a)
            git("checkout", "-b", "main", cwd=local_a)
            (local_a / "demo.txt").write_text("v1\n", encoding="utf-8")
            git("add", "demo.txt", cwd=local_a)
            git("commit", "-m", "feat: add demo file", cwd=local_a)
            git("push", "-u", "origin", "main", cwd=local_a)

            git("clone", str(remote), str(local_b), cwd=root)
            configure_repo(local_b)
            (local_b / "demo.txt").write_text("v1\nv2\n", encoding="utf-8")
            git("add", "demo.txt", cwd=local_b)
            git("commit", "-m", "fix: update demo file", cwd=local_b)
            git("push", "origin", "main", cwd=local_b)

            git("fetch", "origin", cwd=local_a)
            result = guardrail.validate_stage(
                repo=local_a,
                stage="G3",
                commit_message=None,
                max_staged_files=20,
            )

            self.assertTrue(result["passed"])
            self.assertEqual(1, result["details"]["behind"])
            self.assertTrue(result["details"]["requires_sync"])


class ValidatorScriptTests(unittest.TestCase):
    def test_validator_script_passes(self) -> None:
        proc = subprocess.run(
            ["python3", str(VALIDATOR_SCRIPT)],
            cwd=str(REPO_ROOT),
            check=False,
            text=True,
            capture_output=True,
            encoding="utf-8",
        )

        self.assertEqual(0, proc.returncode, msg=proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
