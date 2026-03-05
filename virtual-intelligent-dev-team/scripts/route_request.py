#!/usr/bin/env python3
"""
Route a natural-language request to the most suitable agent team configuration.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "references" / "routing-rules.json"
ASCII_WORD_CLASS = "a-z0-9"


def load_config(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        raise FileNotFoundError(f"Routing config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    required_keys = ("thresholds", "agent_order", "agent_rules", "process_skill_rules")
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Routing config missing required key: {key}")
    return config


def get_threshold(config: dict[str, object], name: str, default: float) -> float:
    thresholds = config.get("thresholds", {})
    if not isinstance(thresholds, dict):
        return default
    value = thresholds.get(name, default)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def has_cjk(text: str) -> bool:
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            return True
    return False


def keyword_matches(text: str, keyword: str) -> bool:
    token = keyword.lower().strip()
    if token == "":
        return False

    # Chinese or mixed Chinese keywords keep substring semantics.
    if has_cjk(token):
        return token in text

    # English keywords use word-boundary-like matching to avoid
    # false positives such as "pr" in "improve" or "ui" in "build".
    pattern = rf"(?<![{ASCII_WORD_CLASS}]){re.escape(token)}(?![{ASCII_WORD_CLASS}])"
    return re.search(pattern, text) is not None


def compute_scores(
    text: str, config: dict[str, object]
) -> tuple[dict[str, int], dict[str, dict[str, list[str]]]]:
    lowered = text.lower()
    agent_order = config.get("agent_order", [])
    if not isinstance(agent_order, list):
        raise ValueError("routing config key 'agent_order' must be a list")

    agent_rules = config.get("agent_rules", {})
    if not isinstance(agent_rules, dict):
        raise ValueError("routing config key 'agent_rules' must be a map")

    max_score = int(get_threshold(config, "max_agent_score", 20))
    scores: dict[str, int] = {}
    hits: dict[str, dict[str, list[str]]] = {}

    for agent in agent_order:
        if not isinstance(agent, str):
            continue

        rules = agent_rules.get(agent, {})
        if not isinstance(rules, dict):
            rules = {}

        positive_rules = rules.get("positive", [])
        negative_rules = rules.get("negative", [])
        if not isinstance(positive_rules, list):
            positive_rules = []
        if not isinstance(negative_rules, list):
            negative_rules = []

        positive_hits: list[str] = []
        negative_hits: list[str] = []
        positive_score = 0
        negative_score = 0

        for item in positive_rules:
            if not isinstance(item, dict):
                continue
            keyword = str(item.get("keyword", "")).lower()
            rule_score = int(item.get("score", 0))
            if keyword and keyword_matches(lowered, keyword):
                positive_hits.append(keyword)
                positive_score += max(rule_score, 0)

        for item in negative_rules:
            if not isinstance(item, dict):
                continue
            keyword = str(item.get("keyword", "")).lower()
            penalty = abs(int(item.get("score", 0)))
            if keyword and keyword_matches(lowered, keyword):
                negative_hits.append(keyword)
                negative_score += penalty

        final_score = max(0, min(max_score, positive_score - negative_score))
        scores[agent] = final_score
        hits[agent] = {"positive": positive_hits, "negative": negative_hits}

    return scores, hits


def detect_process_skills(
    text: str, config: dict[str, object]
) -> tuple[bool, bool, list[str], dict[str, list[str]]]:
    lowered = text.lower()
    process_rules = config.get("process_skill_rules", {})
    if not isinstance(process_rules, dict):
        raise ValueError("routing config key 'process_skill_rules' must be a map")

    process_hits: dict[str, list[str]] = {}
    for skill_name, rules in process_rules.items():
        if not isinstance(skill_name, str) or not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            keyword = str(rule.get("keyword", "")).lower()
            if keyword and keyword_matches(lowered, keyword):
                process_hits.setdefault(skill_name, []).append(keyword)

    # Fallback: infer git workflow intent from common command-like expressions,
    # even when explicit process keywords are not provided.
    if "git-workflow" not in process_hits:
        git_anchor = keyword_matches(lowered, "git")
        git_action_keywords = [
            "commit",
            "push",
            "branch",
            "checkout",
            "merge",
            "rebase",
            "tag",
            "pull request",
            "merge request",
            "pr",
            "mr",
            "提交",
            "推送",
            "分支",
            "合并",
            "拉取请求",
        ]
        action_hits = [
            keyword for keyword in git_action_keywords if keyword_matches(lowered, keyword)
        ]
        strong_action_count = len(set(action_hits))
        if (git_anchor and strong_action_count > 0) or strong_action_count >= 2:
            process_hits["git-workflow"] = [
                f"fallback:{keyword}" for keyword in sorted(set(action_hits))
            ]

    needs_worktree = "using-git-worktrees" in process_hits
    needs_git_workflow = "git-workflow" in process_hits
    process_skills = [
        skill for skill in ("using-git-worktrees", "git-workflow") if skill in process_hits
    ]
    return needs_worktree, needs_git_workflow, process_skills, process_hits


def detect_languages(
    text: str, config: dict[str, object]
) -> tuple[list[str], dict[str, list[str]], dict[str, str]]:
    lowered = text.lower()
    profiles = config.get("language_profiles", {})
    if not isinstance(profiles, dict):
        return [], {}, {}

    language_hits: dict[str, list[str]] = {}
    language_routing: dict[str, str] = {}

    for language, profile in profiles.items():
        if not isinstance(language, str) or not isinstance(profile, dict):
            continue
        keywords = profile.get("keywords", [])
        context_keywords = profile.get("context_keywords", [])
        bare_keyword = profile.get("bare_keyword")
        if not isinstance(keywords, list):
            continue
        if not isinstance(context_keywords, list):
            context_keywords = []
        if not isinstance(bare_keyword, str):
            bare_keyword = ""
        hits: list[str] = []
        for keyword in keywords:
            if not isinstance(keyword, str):
                continue
            token = keyword.lower()
            if token and keyword_matches(lowered, token):
                hits.append(token)

        # Optional bare language word with context constraint.
        if bare_keyword:
            bare = bare_keyword.lower()
            if keyword_matches(lowered, bare):
                context_hits = []
                for ctx in context_keywords:
                    if not isinstance(ctx, str):
                        continue
                    ctx_token = ctx.lower()
                    if ctx_token and keyword_matches(lowered, ctx_token):
                        context_hits.append(ctx_token)
                if len(context_hits) > 0:
                    hits.append(bare)
                    hits.extend([f"context:{ctx}" for ctx in context_hits])
        if hits:
            language_hits[language] = hits
            lead_agent = str(profile.get("lead_agent", "Technical Trinity"))
            language_routing[language] = lead_agent

    detected_languages = list(language_hits.keys())
    return detected_languages, language_hits, language_routing


def detect_repo_strategy(repo_path: Path) -> dict[str, str]:
    default = {"strategy": "unknown", "base_branch": "main"}
    cmd = [
        "git",
        "-C",
        str(repo_path),
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    except Exception:
        return default
    if proc.returncode != 0:
        return default

    branches = {line.strip() for line in (proc.stdout or "").splitlines() if line.strip()}
    has_main = "main" in branches
    has_master = "master" in branches
    has_develop = "develop" in branches

    if has_develop and (has_main or has_master):
        return {"strategy": "git-flow-lite", "base_branch": "main" if has_main else "master"}
    if has_main:
        return {"strategy": "trunk-main", "base_branch": "main"}
    if has_master:
        return {"strategy": "trunk-master", "base_branch": "master"}
    if has_develop:
        return {"strategy": "develop-only", "base_branch": "develop"}
    return default


def build_git_templates(repo_strategy: dict[str, str]) -> dict[str, object]:
    strategy = repo_strategy.get("strategy", "unknown")
    base_branch = repo_strategy.get("base_branch", "main")
    branch_prefix = "feature" if strategy == "git-flow-lite" else "feat"
    return {
        "branch_name": f"{branch_prefix}/<ticket>-<summary>",
        "commit_message": "fix: 修复 <模块> 的 <问题>",
        "pr_title": "fix: <模块> - <变更摘要>",
        "pr_sections": ["背景", "改动点", "风险与回滚", "验证结果"],
        "base_branch": base_branch,
    }


def build_auto_execute_policy() -> dict[str, str]:
    return {
        "low_risk": "auto_execute",
        "medium_risk": "confirm_before_execute",
        "high_risk": "must_confirm_and_explain_risk",
    }


def get_governance_defaults(config: dict[str, object]) -> dict[str, object]:
    governance = config.get("governance", {})
    if not isinstance(governance, dict):
        governance = {}
    roundtable = governance.get("roundtable", {})
    if not isinstance(roundtable, dict):
        roundtable = {}
    privy_council = governance.get("privy_council", {})
    if not isinstance(privy_council, dict):
        privy_council = {}
    defaults = {
        "assistant_count_min": 1,
        "confidence_max": 0.75,
        "force_keywords": ["圆桌会议", "三省六部", "多智能体治理", "cross-functional", "governance"],
    }
    privy_defaults = {
        "prefer_regular_for_git": True,
        "allow_high_risk_fast_track": False,
        "force_fast_track_keywords": ["紧急", "立即", "阻塞", "P0", "hotfix", "实验性", "快速验证"],
        "force_regular_keywords": ["审计", "合规", "高风险", "核心模块", "双签"],
    }
    return {
        "roundtable": {
            "assistant_count_min": int(roundtable.get("assistant_count_min", defaults["assistant_count_min"])),
            "confidence_max": float(roundtable.get("confidence_max", defaults["confidence_max"])),
            "force_keywords": roundtable.get("force_keywords", defaults["force_keywords"]),
        },
        "privy_council": {
            "prefer_regular_for_git": bool(
                privy_council.get("prefer_regular_for_git", privy_defaults["prefer_regular_for_git"])
            ),
            "allow_high_risk_fast_track": bool(
                privy_council.get(
                    "allow_high_risk_fast_track",
                    privy_defaults["allow_high_risk_fast_track"],
                )
            ),
            "force_fast_track_keywords": privy_council.get(
                "force_fast_track_keywords",
                privy_defaults["force_fast_track_keywords"],
            ),
            "force_regular_keywords": privy_council.get(
                "force_regular_keywords",
                privy_defaults["force_regular_keywords"],
            ),
        },
    }


def should_enable_roundtable(
    text: str,
    assistants: list[str],
    confidence: float,
    sentinel_overlay: bool,
    governance_defaults: dict[str, object],
) -> bool:
    roundtable = governance_defaults.get("roundtable", {})
    if not isinstance(roundtable, dict):
        roundtable = {}
    assistant_count_min = int(roundtable.get("assistant_count_min", 1))
    confidence_max = float(roundtable.get("confidence_max", 0.75))
    force_keywords = roundtable.get("force_keywords", [])
    if not isinstance(force_keywords, list):
        force_keywords = []

    if sentinel_overlay:
        return True
    if len(assistants) >= assistant_count_min and confidence <= confidence_max:
        return True
    lowered = text.lower()
    for keyword in force_keywords:
        if not isinstance(keyword, str):
            continue
        if keyword_matches(lowered, keyword.lower()):
            return True
    return False


def should_use_fast_track(
    text: str,
    sentinel_overlay: bool,
    needs_git_workflow: bool,
    governance_defaults: dict[str, object],
) -> tuple[bool, list[str]]:
    privy = governance_defaults.get("privy_council", {})
    if not isinstance(privy, dict):
        privy = {}
    prefer_regular_for_git = bool(privy.get("prefer_regular_for_git", True))
    allow_high_risk_fast_track = bool(privy.get("allow_high_risk_fast_track", False))
    force_fast_track_keywords = privy.get("force_fast_track_keywords", [])
    force_regular_keywords = privy.get("force_regular_keywords", [])
    if not isinstance(force_fast_track_keywords, list):
        force_fast_track_keywords = []
    if not isinstance(force_regular_keywords, list):
        force_regular_keywords = []

    lowered = text.lower()
    rationale: list[str] = []

    if sentinel_overlay and not allow_high_risk_fast_track:
        rationale.append("命中高风险信号，禁止直通轨")
        return False, rationale

    for keyword in force_regular_keywords:
        if isinstance(keyword, str) and keyword_matches(lowered, keyword.lower()):
            rationale.append(f"命中常规轨强制关键词: {keyword}")
            return False, rationale

    for keyword in force_fast_track_keywords:
        if isinstance(keyword, str) and keyword_matches(lowered, keyword.lower()):
            rationale.append(f"命中直通轨关键词: {keyword}")
            return True, rationale

    if needs_git_workflow and prefer_regular_for_git:
        rationale.append("Git 流程默认走常规轨")
        return False, rationale

    return False, rationale


def dedupe_agents(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def pick_ministry_owner(
    ministry: str,
    lead_agent: str,
    assistants: list[str],
    scores: dict[str, int],
    sentinel_overlay: bool,
    needs_git_workflow: bool,
) -> str:
    if ministry == "吏部":
        return lead_agent
    if ministry == "户部":
        return "Git Workflow Guardian" if needs_git_workflow else "Technical Trinity"
    if ministry == "礼部":
        if scores.get("World-Class Product Architect", 0) > 0:
            return "World-Class Product Architect"
        return "Executive Trinity" if scores.get("Executive Trinity", 0) > 0 else lead_agent
    if ministry == "兵部":
        if sentinel_overlay:
            return "Sentinel Architect (NB)"
        return "Code Audit Council"
    if ministry == "刑部":
        return "Code Audit Council"
    if ministry == "工部":
        engineering_agents = {
            "Java Virtuoso",
            "Technical Trinity",
            "Git Workflow Guardian",
            "World-Class Product Architect",
        }
        if lead_agent in engineering_agents:
            return lead_agent
        for agent in assistants:
            if agent in engineering_agents:
                return agent
        return "Technical Trinity"
    return lead_agent


def build_governance_plan(
    text: str,
    lead_agent: str,
    assistants: list[str],
    scores: dict[str, int],
    confidence: float,
    sentinel_overlay: bool,
    needs_git_workflow: bool,
    governance_defaults: dict[str, object],
) -> dict[str, object]:
    roundtable_enabled = should_enable_roundtable(
        text=text,
        assistants=assistants,
        confidence=confidence,
        sentinel_overlay=sentinel_overlay,
        governance_defaults=governance_defaults,
    )
    fast_track_enabled, fast_track_rationale = should_use_fast_track(
        text=text,
        sentinel_overlay=sentinel_overlay,
        needs_git_workflow=needs_git_workflow,
        governance_defaults=governance_defaults,
    )

    proposal_agents = dedupe_agents([lead_agent] + assistants[:1])
    review_agents = dedupe_agents(
        [
            "Code Audit Council",
            "Sentinel Architect (NB)" if sentinel_overlay else "",
        ]
    )
    review_agents = [agent for agent in review_agents if agent != ""]
    execution_agents = dedupe_agents([lead_agent] + assistants)

    ministries = [
        ("吏部", "智能体选派与优先级"),
        ("户部", "预算与资源编排"),
        ("礼部", "输出规范与对齐"),
        ("兵部", "安全与风险防线"),
        ("刑部", "质量门禁与裁决"),
        ("工部", "工程实施与交付"),
    ]
    ministry_assignments: list[dict[str, str]] = []
    for name, duty in ministries:
        owner = pick_ministry_owner(
            ministry=name,
            lead_agent=lead_agent,
            assistants=assistants,
            scores=scores,
            sentinel_overlay=sentinel_overlay,
            needs_git_workflow=needs_git_workflow,
        )
        ministry_assignments.append(
            {
                "name": name,
                "owner_agent": owner,
                "duty": duty,
            }
        )

    selected_track = "军机处直通轨" if fast_track_enabled else "三省六部轨"
    if sentinel_overlay:
        risk_level = "high"
    elif len(assistants) > 0 or roundtable_enabled:
        risk_level = "medium"
    else:
        risk_level = "low"

    dual_sign_required = sentinel_overlay or (risk_level == "high")
    post_audit_required = fast_track_enabled

    if dual_sign_required:
        decision_protocol = "双签通过：Sentinel Architect (NB) + Code Audit Council"
    elif fast_track_enabled:
        decision_protocol = "先执行后审计：军机直通后进入时限回审"
    elif roundtable_enabled:
        decision_protocol = "圆桌共识 + 主责智能体拍板"
    elif len(assistants) > 0:
        decision_protocol = "多方会签后主责拍板"
    else:
        decision_protocol = "主责智能体直接决策"

    return {
        "roundtable_enabled": roundtable_enabled,
        "risk_level": risk_level,
        "privy_council": {
            "name": "枢机院",
            "selected_track": selected_track,
            "rationale": fast_track_rationale,
            "dual_sign_required": dual_sign_required,
            "post_audit_required": post_audit_required,
        },
        "tracks": {
            "regular": {
                "name": "三省六部轨",
                "flow": ["中书省提案", "门下省审议", "尚书省分发", "六部执行"],
            },
            "fast": {
                "name": "军机处直通轨",
                "flow": ["军机处下达", "执行部门直达", "快速反馈", "结果回奏"],
            },
        },
        "agenda": [
            "议题定义",
            "方案辩论（中书省提案）",
            "风险投票（门下省审议）",
            "执行决议（尚书省落地）",
        ],
        "three_departments": {
            "中书省": {"role": "提案", "agents": proposal_agents},
            "门下省": {"role": "审议", "agents": review_agents},
            "尚书省": {"role": "执行", "agents": execution_agents},
        },
        "six_ministries": ministry_assignments,
        "decision_protocol": decision_protocol,
        "post_audit": {
            "required": post_audit_required,
            "flow": ["T+0执行", "T+1审计复盘", "T+2规则回写"],
            "archive_target": "国史馆知识库",
        },
        "feedback_loop": {
            "enabled": True,
            "loop": ["结果回奏", "指标归档", "规则调优"],
        },
        "minority_report": "允许记录少数意见，写入最终决议作为风险备忘",
    }


def build_process_plan(
    needs_worktree: bool,
    needs_git_workflow: bool,
    repo_strategy: dict[str, str],
) -> list[dict[str, object]]:
    plan: list[dict[str, object]] = []
    if needs_worktree:
        plan.append(
            {
                "skill": "using-git-worktrees",
                "reference": "references/using-git-worktrees-playbook.md",
                "steps": [
                    "确定基线分支（main/develop）",
                    "为每个任务创建独立 worktree 与分支",
                    "在各自 worktree 内开发与提交",
                    "任务完成后清理已合并 worktree",
                ],
                "commands": [
                    "git worktree list",
                    "git worktree add ../wt-<task> -b <branch> main",
                    "git worktree remove ../wt-<task>",
                    "git worktree prune",
                ],
            }
        )
    if needs_git_workflow:
        templates = build_git_templates(repo_strategy)
        plan.append(
            {
                "skill": "git-workflow",
                "reference": "references/git-workflow-playbook.md",
                "steps": [
                    "R0 画像：识别仓库分支策略与基线分支",
                    "G0 检查：确认分支、工作区、远端状态",
                    "G1 暂存：仅暂存本次任务必需改动",
                    "G2 提交：按语义前缀提交单一意图变更",
                    "G3 同步：与远端同步并处理冲突",
                    "G4 推送/PR：推送分支并按门禁发起评审",
                ],
                "commands": [
                    "python scripts/git_workflow_guardrail.py --repo . --detect-repo-strategy --print-templates --pretty",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G0 --pretty",
                    "git status --short --branch",
                    f"git checkout -b {templates['branch_name']}",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G1 --pretty",
                    "git add <files>",
                    f"python scripts/git_workflow_guardrail.py --repo . --stage G2 --commit-message \"{templates['commit_message']}\" --pretty",
                    f"git commit -m \"{templates['commit_message']}\"",
                    f"git pull --rebase origin {templates['base_branch']}",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G3 --pretty",
                    f"git push -u origin {templates['branch_name']}",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G4 --pretty",
                ],
                "auto_execute_policy": build_auto_execute_policy(),
                "repo_strategy": repo_strategy,
                "templates": templates,
                "kpis": [
                    "first_push_success_rate",
                    "rebase_conflict_rate",
                    "rollback_rate",
                    "manual_intervention_rate",
                ],
            }
        )
    return plan


def pick_process_lead_agent(process_skills: list[str], config: dict[str, object]) -> str:
    mapping = config.get("process_skill_lead_agents", {})
    if isinstance(mapping, dict):
        for skill in process_skills:
            candidate = mapping.get(skill)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return str(config.get("default_process_lead_agent", "Technical Trinity"))


def pick_mode(
    confidence: float,
    sentinel_overlay: bool,
    process_only: bool,
    language_only: bool,
    unknown_only: bool,
    roundtable_enabled: bool,
    fast_track_enabled: bool,
    assistant_count: int,
    high_confidence: float,
    medium_confidence: float,
) -> str:
    if fast_track_enabled:
        return "模式 G：枢机快反（军机处直通）"
    if roundtable_enabled:
        return "模式 F：圆桌治理（三省六部）"
    if process_only:
        return "流程驱动模式：按流程技能执行"
    if language_only:
        return "语言驱动模式：按语言栈执行"
    if unknown_only:
        return "低置信分流：等待用户补充信息"
    if sentinel_overlay:
        return "模式 D：高风险治理"
    if confidence >= high_confidence:
        return "模式 A：单点执行"
    if confidence >= medium_confidence:
        return "模式 B：评审-实现 或 模式 C：战略-技术双轨"
    if assistant_count == 0:
        return "低置信分流：需要澄清问题"
    return "低置信分流：主责+2辅助并补澄清问题"


def build_clarifying_question(text: str, need_clarify: bool) -> str | None:
    if not need_clarify:
        return None
    if has_cjk(text):
        return "请补充技术栈、目标和期望产出（代码、方案或审计）？"
    return "Please share tech stack, target outcome, and expected output type (code, architecture, or review)."


def route_request(text: str, config: dict[str, object], repo_path: Path) -> dict[str, object]:
    scores, reasons = compute_scores(text, config)
    needs_worktree, needs_git_workflow, process_skills, process_hits = detect_process_skills(text, config)
    detected_languages, language_hits, language_routing = detect_languages(text, config)
    repo_strategy = detect_repo_strategy(repo_path)
    git_templates = build_git_templates(repo_strategy)

    agent_order = config.get("agent_order", [])
    if not isinstance(agent_order, list) or len(agent_order) == 0:
        raise ValueError("routing config key 'agent_order' must be a non-empty list")
    order_index = {str(name): index for index, name in enumerate(agent_order)}

    sorted_agents = sorted(
        scores.items(),
        key=lambda item: (-item[1], order_index.get(item[0], 999)),
    )
    lead_agent, lead_score = sorted_agents[0]

    process_only = lead_score == 0 and len(process_skills) > 0
    language_only = lead_score == 0 and len(process_skills) == 0 and len(detected_languages) > 0
    unknown_only = lead_score == 0 and len(process_skills) == 0 and len(detected_languages) == 0
    if process_only:
        lead_agent = pick_process_lead_agent(process_skills=process_skills, config=config)
        lead_score = scores.get(lead_agent, 0)
    elif language_only:
        lead_agent = language_routing.get(detected_languages[0], "Technical Trinity")
        lead_score = scores.get(lead_agent, 0)
    elif unknown_only:
        default_lead = str(config.get("default_unknown_lead_agent", "Technical Trinity"))
        lead_agent = default_lead
        lead_score = scores.get(lead_agent, 0)

    top_three_total = sum(score for _, score in sorted_agents[:3])
    confidence = round(lead_score / max(top_three_total, 1), 3) if top_three_total > 0 else 0.0

    high_confidence = get_threshold(config, "high_confidence", 0.55)
    medium_confidence = get_threshold(config, "medium_confidence", 0.35)
    sentinel_threshold = int(get_threshold(config, "sentinel_overlay_threshold", 6))
    sentinel_score = scores.get("Sentinel Architect (NB)", 0)
    sentinel_overlay = sentinel_score >= sentinel_threshold and sentinel_score > 0

    if process_only or language_only or unknown_only or confidence >= high_confidence:
        assistants = []
    elif confidence >= medium_confidence:
        assistants = [sorted_agents[1][0]]
    else:
        assistants = [sorted_agents[1][0], sorted_agents[2][0]]

    # Avoid duplicate value-add when assistant score is zero.
    assistants = [
        agent for agent in assistants if scores.get(agent, 0) > 0 and agent != lead_agent
    ]
    governance_defaults = get_governance_defaults(config)
    governance_plan = build_governance_plan(
        text=text,
        lead_agent=lead_agent,
        assistants=assistants,
        scores=scores,
        confidence=confidence,
        sentinel_overlay=sentinel_overlay,
        needs_git_workflow=needs_git_workflow,
        governance_defaults=governance_defaults,
    )
    process_plan = build_process_plan(
        needs_worktree=needs_worktree,
        needs_git_workflow=needs_git_workflow,
        repo_strategy=repo_strategy,
    )

    mode = pick_mode(
        confidence=confidence,
        sentinel_overlay=sentinel_overlay,
        process_only=process_only,
        language_only=language_only,
        unknown_only=unknown_only,
        roundtable_enabled=bool(governance_plan.get("roundtable_enabled", False)),
        fast_track_enabled=(
            (governance_plan.get("privy_council") or {}).get("selected_track") == "军机处直通轨"
        ),
        assistant_count=len(assistants),
        high_confidence=high_confidence,
        medium_confidence=medium_confidence,
    )
    need_clarify = unknown_only or (
        confidence < medium_confidence
        and len(assistants) == 0
        and not process_only
        and not language_only
    )
    clarifying_question = build_clarifying_question(text=text, need_clarify=need_clarify)

    reason = {
        "lead_positive_hits": reasons.get(lead_agent, {}).get("positive", []),
        "lead_negative_hits": reasons.get(lead_agent, {}).get("negative", []),
        "assistant_hits": {agent: reasons.get(agent, {}) for agent in assistants},
        "sentinel_overlay": sentinel_overlay,
        "process_only_fallback": process_only,
        "language_only_fallback": language_only,
        "unknown_only_fallback": unknown_only,
        "language_hits": language_hits,
        "process_skill_hits": process_hits,
    }

    return {
        "lead_agent": lead_agent,
        "assistant_agents": assistants,
        "detected_languages": detected_languages,
        "language_routing": language_routing,
        "needs_worktree": needs_worktree,
        "needs_git_workflow": needs_git_workflow,
        "process_skills": process_skills,
        "builtin_process_enabled": True,
        "process_plan": process_plan,
        "governance_plan": governance_plan,
        "git_workflow_profile": {
            "repo_strategy": repo_strategy,
            "auto_execute_policy": build_auto_execute_policy(),
            "templates": git_templates,
            "kpis": [
                "first_push_success_rate",
                "rebase_conflict_rate",
                "rollback_rate",
                "manual_intervention_rate",
            ],
        },
        "confidence": confidence,
        "mode": mode,
        "clarifying_question": clarifying_question,
        "scores": scores,
        "reason": reason,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route request to virtual-intelligent-dev-team.")
    parser.add_argument("--text", required=True, help="User request text.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to routing config JSON.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository path for strategy detection.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    repo_path = Path(args.repo).resolve()
    config = load_config(config_path)
    result = route_request(args.text, config, repo_path=repo_path)
    result["routing_config"] = {
        "path": str(config_path),
        "version": str(config.get("meta", {}).get("version", "unknown")),
    }
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

