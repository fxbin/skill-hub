import importlib.util
from contextlib import contextmanager
import json
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import uuid4


SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parent
TMP_ROOT = REPO_ROOT / ".tmp-validation"
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


@contextmanager
def make_tempdir():
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TMP_ROOT / f"tmp-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    yield str(path)


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

    def test_checkout_ux_audit_stays_with_product_architect(self) -> None:
        result = route_request.route_request(
            "Audit this checkout UX for accessibility and mobile responsiveness.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertFalse(result["needs_git_workflow"])
        self.assertEqual([], result["process_skills"])

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

    def test_strategy_request_adds_technical_trinity_copilot(self) -> None:
        result = route_request.route_request(
            "This SaaS is not growing. Set the strategy and also land the technical plan.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Executive Trinity", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertNotEqual("模式 A：单点执行", result["mode"])

    def test_omni_request_adds_technical_trinity_copilot(self) -> None:
        result = route_request.route_request(
            "Design a system for an unfamiliar industry, including compliance and technical landing.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Omni-Architect", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])

    def test_python_fastapi_routes_to_technical_trinity(self) -> None:
        result = route_request.route_request(
            "Use Python and FastAPI to build a backend service.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Technical Trinity", result["lead_agent"])
        self.assertIn("python", result["detected_languages"])
        self.assertFalse(result["needs_git_workflow"])

    def test_python_django_review_routes_to_audit_with_python_assistant(self) -> None:
        result = route_request.route_request(
            "Review this Django API for security issues.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Code Audit Council", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertEqual(
            "Code Audit Council",
            (result["reason"]["priority_routing"] or {}).get("agent"),
        )

    def test_python_flask_git_workflow_routes_to_git_guardian(self) -> None:
        result = route_request.route_request(
            "Refactor this Flask service and then commit and push the branch.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Git Workflow Guardian", result["lead_agent"])
        self.assertTrue(result["needs_git_workflow"])
        self.assertIn("git-workflow", result["process_skills"])

    def test_python_celery_design_routes_to_technical_trinity(self) -> None:
        result = route_request.route_request(
            "Design a Python service with Celery workers and reliability guardrails.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Technical Trinity", result["lead_agent"])
        self.assertIn("python", result["detected_languages"])
        self.assertFalse(result["needs_git_workflow"])

    def test_python_pr_audit_keeps_audit_lead_with_git_and_python_assistants(self) -> None:
        result = route_request.route_request(
            "This is a PR. Review this Django service for security issues before merge.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Code Audit Council", result["lead_agent"])
        self.assertIn("Git Workflow Guardian", result["assistant_agents"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertTrue(result["needs_git_workflow"])

    def test_python_fastapi_worktree_and_git_routes_to_git_guardian(self) -> None:
        result = route_request.route_request(
            "Use FastAPI for a backend service, then commit, push, and isolate the work in a worktree.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Git Workflow Guardian", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertTrue(result["needs_git_workflow"])
        self.assertTrue(result["needs_worktree"])
        self.assertIn("using-git-worktrees", result["process_skills"])
        self.assertIn("git-workflow", result["process_skills"])

    def test_go_gin_design_routes_to_technical_trinity(self) -> None:
        result = route_request.route_request(
            "Design a Go service with Gin and improve concurrency.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Technical Trinity", result["lead_agent"])
        self.assertIn("go", result["detected_languages"])
        self.assertFalse(result["needs_git_workflow"])

    def test_go_pr_audit_review_keeps_audit_lead(self) -> None:
        result = route_request.route_request(
            "Review this Go API for security issues before merge.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Code Audit Council", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertTrue(result["needs_git_workflow"])
        self.assertEqual(
            "Code Audit Council",
            (result["reason"]["priority_routing"] or {}).get("agent"),
        )

    def test_go_gin_worktree_and_git_routes_to_git_guardian(self) -> None:
        result = route_request.route_request(
            "Use Go with Gin, then commit, push, and isolate the work in a worktree.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Git Workflow Guardian", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertTrue(result["needs_worktree"])
        self.assertTrue(result["needs_git_workflow"])
        self.assertIn("using-git-worktrees", result["process_skills"])
        self.assertIn("git-workflow", result["process_skills"])

    def test_node_nest_design_routes_to_technical_trinity(self) -> None:
        result = route_request.route_request(
            "Design a Node.js service with NestJS.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Technical Trinity", result["lead_agent"])
        self.assertIn("nodejs", result["detected_languages"])
        self.assertFalse(result["needs_git_workflow"])

    def test_node_pr_audit_review_adds_node_assistant(self) -> None:
        result = route_request.route_request(
            "Review this NestJS API for security issues before merge.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Code Audit Council", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertTrue(result["needs_git_workflow"])

    def test_node_nest_worktree_and_git_routes_to_git_guardian(self) -> None:
        result = route_request.route_request(
            "Use Node.js with NestJS, then commit, push, and isolate the work in a worktree.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Git Workflow Guardian", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertTrue(result["needs_worktree"])
        self.assertTrue(result["needs_git_workflow"])

    def test_frontend_react_redesign_stays_with_product_architect(self) -> None:
        result = route_request.route_request(
            "Redesign this React dashboard UI and improve the interaction flow.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertEqual([], result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_dashboard_responsive_routes_to_product_architect(self) -> None:
        result = route_request.route_request(
            "Redesign this analytics dashboard for mobile responsiveness and better information hierarchy.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertEqual([], result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_next_shadcn_design_routes_to_product_architect(self) -> None:
        result = route_request.route_request(
            "Design a Next.js admin console with shadcn/ui and Tailwind.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertEqual([], result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_motion_design_routes_to_product_architect(self) -> None:
        result = route_request.route_request(
            "Improve the Framer Motion transitions and loading states in this React onboarding flow.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertEqual([], result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_form_ux_accessibility_routes_to_product_architect(self) -> None:
        result = route_request.route_request(
            "Audit this signup form UX for accessibility, validation, and conversion friction.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertEqual([], result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_backend_contract_adds_technical_trinity(self) -> None:
        result = route_request.route_request(
            "Redesign this React admin page and align the frontend flow with the backend API contract.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_auth_api_error_states_adds_technical_trinity(self) -> None:
        result = route_request.route_request(
            "Redesign the login flow, align auth UX with the backend API, and handle error states clearly.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_chinese_next_tailwind_routes_to_product_architect(self) -> None:
        result = route_request.route_request(
            "用 Next.js 和 Tailwind 重做这个后台页面的交互和视觉层次。",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertEqual([], result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_chinese_form_api_feedback_adds_technical_trinity(self) -> None:
        result = route_request.route_request(
            "优化这个表单的错误提示、空状态和接口失败反馈，并和后端 API 契约对齐。",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_git_dashboard_mixed_request_keeps_product_lead_with_git_assistant(self) -> None:
        result = route_request.route_request(
            "帮我提个 commit 然后 push，那个 dashboard 也顺手改下。",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertIn("Git Workflow Guardian", result["assistant_agents"])
        self.assertTrue(result["needs_git_workflow"])

    def test_strategy_colloquial_tech_plan_adds_technical_trinity(self) -> None:
        result = route_request.route_request(
            "做个 saas 增长方案，然后把 tech plan 也落一下。",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Executive Trinity", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_review_nest_auth_flow_adds_technical_trinity(self) -> None:
        result = route_request.route_request(
            "review 下这个 nest 接口，顺便看下 auth flow。",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Code Audit Council", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_review_djagno_form_api_contract_adds_technical_trinity(self) -> None:
        result = route_request.route_request(
            "给这个 djagno 登录表单做个 ux review，并和后端 api 对齐。",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertIn("Technical Trinity", result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_frontend_tailwind_git_worktree_routes_to_product_lead_with_git_assistant(self) -> None:
        result = route_request.route_request(
            "Improve the Tailwind admin UI, then commit, push, and isolate the work in a worktree.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("World-Class Product Architect", result["lead_agent"])
        self.assertIn("Git Workflow Guardian", result["assistant_agents"])
        self.assertTrue(result["needs_worktree"])
        self.assertTrue(result["needs_git_workflow"])
        self.assertIn("using-git-worktrees", result["process_skills"])
        self.assertIn("git-workflow", result["process_skills"])

    def test_java_spring_design_routes_to_java_virtuoso(self) -> None:
        result = route_request.route_request(
            "Design a Java Spring Boot service for order processing.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Java Virtuoso", result["lead_agent"])
        self.assertEqual([], result["assistant_agents"])
        self.assertFalse(result["needs_git_workflow"])

    def test_java_spring_pr_audit_review_adds_java_and_git_assistants(self) -> None:
        result = route_request.route_request(
            "Review this Spring Boot API for security issues before merge.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Code Audit Council", result["lead_agent"])
        self.assertIn("Java Virtuoso", result["assistant_agents"])
        self.assertIn("Git Workflow Guardian", result["assistant_agents"])
        self.assertTrue(result["needs_git_workflow"])
        self.assertEqual(
            "Code Audit Council",
            (result["reason"]["priority_routing"] or {}).get("agent"),
        )

    def test_java_spring_worktree_and_git_routes_to_git_guardian(self) -> None:
        result = route_request.route_request(
            "Use Java with Spring Boot, then commit, push, and isolate the work in a worktree.",
            load_config(),
            repo_path=REPO_ROOT,
        )

        self.assertEqual("Git Workflow Guardian", result["lead_agent"])
        self.assertIn("Java Virtuoso", result["assistant_agents"])
        self.assertTrue(result["needs_worktree"])
        self.assertTrue(result["needs_git_workflow"])
        self.assertIn("using-git-worktrees", result["process_skills"])
        self.assertIn("git-workflow", result["process_skills"])


class GuardrailTests(unittest.TestCase):
    def test_g0_blocks_preexisting_staged_changes(self) -> None:
        with make_tempdir() as tmp:
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
        with make_tempdir() as tmp:
            repo = Path(tmp)
            git("init", cwd=repo)
            configure_repo(repo)
            git("checkout", "-b", "main", cwd=repo)
            (repo / "demo.txt").write_text("v1\n", encoding="utf-8")
            git("add", "demo.txt", cwd=repo)
            git("commit", "-m", "feat: add demo file", cwd=repo)
            base_sha = git("rev-parse", "HEAD", cwd=repo).stdout.strip()

            git("branch", "upstream-main", cwd=repo)
            git("checkout", "upstream-main", cwd=repo)
            (repo / "demo.txt").write_text("v1\nv2\n", encoding="utf-8")
            git("add", "demo.txt", cwd=repo)
            git("commit", "-m", "fix: update demo file", cwd=repo)

            git("checkout", "main", cwd=repo)
            git("reset", "--hard", base_sha, cwd=repo)
            git("branch", "--set-upstream-to=upstream-main", "main", cwd=repo)
            result = guardrail.validate_stage(
                repo=repo,
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
            [sys.executable, str(VALIDATOR_SCRIPT)],
            cwd=str(REPO_ROOT),
            check=False,
            text=True,
            capture_output=True,
            encoding="utf-8",
        )

        self.assertEqual(0, proc.returncode, msg=proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
