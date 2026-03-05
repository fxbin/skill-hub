#!/usr/bin/env python3
"""
Route a natural-language request to the most suitable agent team configuration.
"""

from __future__ import annotations

import argparse
import json
import re
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


def build_process_plan(needs_worktree: bool, needs_git_workflow: bool) -> list[dict[str, object]]:
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
        plan.append(
            {
                "skill": "git-workflow",
                "reference": "references/git-workflow-playbook.md",
                "steps": [
                    "G0 检查：确认分支、工作区、远端状态",
                    "G1 暂存：仅暂存本次任务必需改动",
                    "G2 提交：按语义前缀提交单一意图变更",
                    "G3 同步：与远端同步并处理冲突",
                    "G4 推送/PR：推送分支并按门禁发起评审",
                ],
                "commands": [
                    "python scripts/git_workflow_guardrail.py --repo . --stage G0 --pretty",
                    "git status --short --branch",
                    "git checkout -b feature/<task>",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G1 --pretty",
                    "git add <files>",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G2 --commit-message \"feat: <summary>\" --pretty",
                    "git commit -m \"feat: <summary>\"",
                    "git pull --rebase origin <base-branch>",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G3 --pretty",
                    "git push -u origin feature/<task>",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G4 --pretty",
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
    assistant_count: int,
    high_confidence: float,
    medium_confidence: float,
) -> str:
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


def route_request(text: str, config: dict[str, object]) -> dict[str, object]:
    scores, reasons = compute_scores(text, config)
    needs_worktree, needs_git_workflow, process_skills, process_hits = detect_process_skills(text, config)
    detected_languages, language_hits, language_routing = detect_languages(text, config)

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
    process_plan = build_process_plan(
        needs_worktree=needs_worktree,
        needs_git_workflow=needs_git_workflow,
    )

    mode = pick_mode(
        confidence=confidence,
        sentinel_overlay=sentinel_overlay,
        process_only=process_only,
        language_only=language_only,
        unknown_only=unknown_only,
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    result = route_request(args.text, config)
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

