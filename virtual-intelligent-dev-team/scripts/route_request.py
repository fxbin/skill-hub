#!/usr/bin/env python3
"""
Route a natural-language request to the most suitable agent team configuration.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import re
import subprocess
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "references" / "routing-rules.json"
ASCII_WORD_CLASS = "a-z0-9"
TRACK_REGULAR = "三省六部轨"
TRACK_FAST = "军机处直通轨"


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


def normalize_process_hit(hit: str) -> str:
    if hit.startswith("fallback:"):
        return hit.split(":", 1)[1]
    return hit


def is_git_review_context_only(text: str, git_hits: list[str]) -> bool:
    if len(git_hits) == 0:
        return False
    review_only_hits = {"pr", "mr", "pull request", "merge request", "拉取请求"}
    normalized_hits = {normalize_process_hit(hit) for hit in git_hits}
    if len(normalized_hits) == 0 or not normalized_hits.issubset(review_only_hits):
        return False

    lowered = text.lower()
    audit_context_keywords = [
        "review",
        "code review",
        "pr review",
        "security review",
        "审计",
        "代码审查",
        "安全检查",
        "漏洞",
    ]
    return any(keyword_matches(lowered, keyword.lower()) for keyword in audit_context_keywords)


def is_frontend_checkout_context(text: str, git_hits: list[str]) -> bool:
    if len(git_hits) == 0:
        return False
    normalized_hits = {normalize_process_hit(hit) for hit in git_hits}
    if normalized_hits != {"checkout"}:
        return False

    lowered = text.lower()
    frontend_context_keywords = [
        "ux",
        "ui",
        "accessibility",
        "a11y",
        "mobile",
        "responsive",
        "react",
        "tailwind",
        "design",
        "interaction",
        "dashboard",
        "page",
        "frontend",
        "front-end",
    ]
    return any(keyword_matches(lowered, keyword) for keyword in frontend_context_keywords)


def should_suppress_git_workflow(text: str, process_hits: dict[str, list[str]]) -> bool:
    git_hits = process_hits.get("git-workflow", [])
    return is_git_review_context_only(text, git_hits) or is_frontend_checkout_context(
        text, git_hits
    )


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

    if should_suppress_git_workflow(text, process_hits):
        process_hits.pop("git-workflow", None)

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


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_list_str(value: object, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return default
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
    return result if len(result) > 0 else default


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    for keyword in keywords:
        token = keyword.lower().strip()
        if token != "" and keyword_matches(lowered, token):
            hits.append(keyword)
    return hits


def detect_priority_lead(text: str, config: dict[str, object]) -> dict[str, object] | None:
    lowered = text.lower()
    rules = config.get("priority_routing_rules", [])
    if not isinstance(rules, list):
        return None

    for rule in rules:
        if not isinstance(rule, dict):
            continue

        agent = str(rule.get("agent", "")).strip()
        any_keywords = ensure_list_str(rule.get("any_keywords"), [])
        all_keywords = ensure_list_str(rule.get("all_keywords"), [])
        exclude_keywords = ensure_list_str(rule.get("exclude_if_any_keywords"), [])
        if agent == "" or (len(any_keywords) == 0 and len(all_keywords) == 0):
            continue

        any_hits = [keyword for keyword in any_keywords if keyword_matches(lowered, keyword.lower())]
        all_hits = [keyword for keyword in all_keywords if keyword_matches(lowered, keyword.lower())]
        exclude_hits = [
            keyword for keyword in exclude_keywords if keyword_matches(lowered, keyword.lower())
        ]

        if len(all_keywords) > 0 and len(all_hits) != len(all_keywords):
            continue
        if len(any_keywords) > 0 and len(any_hits) == 0:
            continue
        if agent == "Git Workflow Guardian" and is_frontend_checkout_context(
            text, any_hits + all_hits
        ):
            continue
        if len(exclude_hits) > 0:
            continue

        return {
            "agent": agent,
            "matched_keywords": dedupe_agents(any_hits + all_hits),
        }
    return None


def parse_iso_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def load_governance_events(repo_path: Path, metrics_file: str) -> list[dict[str, object]]:
    file_path = repo_path / metrics_file
    if not file_path.exists():
        return []
    events: list[dict[str, object]] = []
    try:
        with file_path.open("r", encoding="utf-8") as file:
            for line in file:
                raw = line.strip()
                if raw == "":
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    events.append(item)
    except Exception:
        return []
    return events


def append_governance_event(repo_path: Path, metrics_file: str, payload: dict[str, object]) -> None:
    file_path = repo_path / metrics_file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def get_fast_track_stats(
    repo_path: Path,
    metrics_file: str,
    window_hours: int,
) -> dict[str, object]:
    now = datetime.now()
    events = load_governance_events(repo_path, metrics_file)
    window_start = now - timedelta(hours=max(window_hours, 1))

    count_24h = 0
    latest_fast_track: datetime | None = None
    for event in events:
        timestamp = event.get("timestamp")
        track = event.get("selected_track")
        if not isinstance(timestamp, str) or not isinstance(track, str):
            continue
        dt = parse_iso_time(timestamp)
        if dt is None:
            continue
        if track != TRACK_FAST:
            continue
        if dt >= window_start:
            count_24h += 1
        if latest_fast_track is None or dt > latest_fast_track:
            latest_fast_track = dt

    return {
        "count_in_window": count_24h,
        "window_hours": max(window_hours, 1),
        "latest_fast_track_at": latest_fast_track.isoformat(timespec="seconds")
        if latest_fast_track is not None
        else None,
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
    anti_gaming = governance.get("anti_gaming", {})
    if not isinstance(anti_gaming, dict):
        anti_gaming = {}
    fast_track_control = governance.get("fast_track_control", {})
    if not isinstance(fast_track_control, dict):
        fast_track_control = {}
    execution_control = governance.get("execution_control", {})
    if not isinstance(execution_control, dict):
        execution_control = {}
    audit_control = governance.get("audit_control", {})
    if not isinstance(audit_control, dict):
        audit_control = {}

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
    anti_defaults = {
        "min_objective_signals_for_fast_track": 1,
        "urgent_keywords": ["紧急", "立即", "阻塞", "P0", "hotfix", "实验性", "快速验证"],
        "objective_keywords": ["生产故障", "告警", "失败", "回滚", "error", "exception", "500", "timeout"],
    }
    fast_control_defaults = {
        "quota_per_24h": 3,
        "cooldown_minutes": 30,
        "metrics_file": ".skill-metrics/governance_events.jsonl",
        "window_hours": 24,
        "write_event_log": True,
    }
    execution_defaults = {
        "require_dri": True,
        "slo_minutes": {"low": 120, "medium": 60, "high": 30},
    }
    audit_defaults = {
        "archive_levels": ["draft", "verified", "gold"],
        "default_archive_level": "draft",
        "promotion_rules": [
            "双签通过后可从 draft 提升到 verified",
            "连续稳定达标后可从 verified 提升到 gold",
        ],
    }

    return {
        "roundtable": {
            "assistant_count_min": int(roundtable.get("assistant_count_min", defaults["assistant_count_min"])),
            "confidence_max": float(roundtable.get("confidence_max", defaults["confidence_max"])),
            "force_keywords": ensure_list_str(roundtable.get("force_keywords"), defaults["force_keywords"]),
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
            "force_fast_track_keywords": ensure_list_str(
                privy_council.get("force_fast_track_keywords"),
                privy_defaults["force_fast_track_keywords"],
            ),
            "force_regular_keywords": ensure_list_str(
                privy_council.get("force_regular_keywords"),
                privy_defaults["force_regular_keywords"],
            ),
        },
        "anti_gaming": {
            "min_objective_signals_for_fast_track": int(
                anti_gaming.get(
                    "min_objective_signals_for_fast_track",
                    anti_defaults["min_objective_signals_for_fast_track"],
                )
            ),
            "urgent_keywords": ensure_list_str(
                anti_gaming.get("urgent_keywords"),
                anti_defaults["urgent_keywords"],
            ),
            "objective_keywords": ensure_list_str(
                anti_gaming.get("objective_keywords"),
                anti_defaults["objective_keywords"],
            ),
        },
        "fast_track_control": {
            "quota_per_24h": int(
                fast_track_control.get("quota_per_24h", fast_control_defaults["quota_per_24h"])
            ),
            "cooldown_minutes": int(
                fast_track_control.get("cooldown_minutes", fast_control_defaults["cooldown_minutes"])
            ),
            "metrics_file": str(
                fast_track_control.get("metrics_file", fast_control_defaults["metrics_file"])
            ),
            "window_hours": int(
                fast_track_control.get("window_hours", fast_control_defaults["window_hours"])
            ),
            "write_event_log": bool(
                fast_track_control.get("write_event_log", fast_control_defaults["write_event_log"])
            ),
        },
        "execution_control": {
            "require_dri": bool(execution_control.get("require_dri", execution_defaults["require_dri"])),
            "slo_minutes": execution_control.get("slo_minutes", execution_defaults["slo_minutes"]),
        },
        "audit_control": {
            "archive_levels": ensure_list_str(
                audit_control.get("archive_levels"),
                audit_defaults["archive_levels"],
            ),
            "default_archive_level": str(
                audit_control.get("default_archive_level", audit_defaults["default_archive_level"])
            ),
            "promotion_rules": ensure_list_str(
                audit_control.get("promotion_rules"),
                audit_defaults["promotion_rules"],
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
    repo_path: Path,
    governance_defaults: dict[str, object],
) -> dict[str, object]:
    privy = governance_defaults.get("privy_council", {})
    if not isinstance(privy, dict):
        privy = {}
    anti = governance_defaults.get("anti_gaming", {})
    if not isinstance(anti, dict):
        anti = {}
    fast_control = governance_defaults.get("fast_track_control", {})
    if not isinstance(fast_control, dict):
        fast_control = {}

    prefer_regular_for_git = bool(privy.get("prefer_regular_for_git", True))
    allow_high_risk_fast_track = bool(privy.get("allow_high_risk_fast_track", False))
    force_fast_track_keywords = ensure_list_str(privy.get("force_fast_track_keywords"), [])
    force_regular_keywords = ensure_list_str(privy.get("force_regular_keywords"), [])

    min_objective_signals = int(anti.get("min_objective_signals_for_fast_track", 1))
    urgent_keywords = ensure_list_str(anti.get("urgent_keywords"), [])
    objective_keywords = ensure_list_str(anti.get("objective_keywords"), [])

    quota_per_24h = max(int(fast_control.get("quota_per_24h", 3)), 0)
    cooldown_minutes = max(int(fast_control.get("cooldown_minutes", 30)), 0)
    metrics_file = str(fast_control.get("metrics_file", ".skill-metrics/governance_events.jsonl"))
    window_hours = max(int(fast_control.get("window_hours", 24)), 1)

    rationale: list[str] = []
    blockers: list[str] = []
    selected = False

    forced_regular_hits = keyword_hits(text, force_regular_keywords)
    forced_fast_hits = keyword_hits(text, force_fast_track_keywords)
    urgent_hits = keyword_hits(text, urgent_keywords)
    objective_hits = keyword_hits(text, objective_keywords)

    suspicious_manipulation = len(urgent_hits) > 0 and len(objective_hits) < min_objective_signals
    if suspicious_manipulation:
        blockers.append("疑似关键词操纵：紧急词存在但客观信号不足")

    if sentinel_overlay and not allow_high_risk_fast_track:
        blockers.append("命中高风险信号，禁止直通轨")

    if len(forced_regular_hits) > 0:
        blockers.append(f"命中常规轨强制关键词: {', '.join(forced_regular_hits)}")

    if needs_git_workflow and prefer_regular_for_git:
        blockers.append("Git 流程默认走常规轨")

    if len(forced_fast_hits) > 0:
        rationale.append(f"命中直通轨关键词: {', '.join(forced_fast_hits)}")
        selected = True
    elif len(urgent_hits) > 0 and len(objective_hits) >= min_objective_signals:
        rationale.append("命中紧急信号且客观信号达标")
        selected = True

    stats = get_fast_track_stats(
        repo_path=repo_path,
        metrics_file=metrics_file,
        window_hours=window_hours,
    )
    if selected:
        if quota_per_24h > 0 and int(stats.get("count_in_window", 0)) >= quota_per_24h:
            blockers.append("直通轨配额已达上限")
        latest = stats.get("latest_fast_track_at")
        if isinstance(latest, str):
            latest_dt = parse_iso_time(latest)
            if latest_dt is not None and cooldown_minutes > 0:
                until = latest_dt + timedelta(minutes=cooldown_minutes)
                if datetime.now() < until:
                    blockers.append("直通轨处于冷却期")

    enabled = selected and len(blockers) == 0
    return {
        "enabled": enabled,
        "rationale": rationale,
        "blockers": blockers,
        "signals": {
            "forced_fast_hits": forced_fast_hits,
            "forced_regular_hits": forced_regular_hits,
            "urgent_hits": urgent_hits,
            "objective_hits": objective_hits,
            "suspicious_manipulation": suspicious_manipulation,
        },
        "stats": stats,
        "policy": {
            "quota_per_24h": quota_per_24h,
            "cooldown_minutes": cooldown_minutes,
            "metrics_file": metrics_file,
            "window_hours": window_hours,
            "min_objective_signals_for_fast_track": min_objective_signals,
        },
    }


def dedupe_agents(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def apply_assistant_routing_rules(
    text: str,
    lead_agent: str,
    assistants: list[str],
    scores: dict[str, int],
    config: dict[str, object],
) -> list[str]:
    rules = config.get("assistant_routing_rules", [])
    if not isinstance(rules, list):
        return assistants

    lowered = text.lower()
    merged = list(assistants)
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if str(rule.get("lead_agent", "")).strip() != lead_agent:
            continue

        when_any_keywords = rule.get("when_any_keywords", [])
        add_assistants = rule.get("add_assistants", [])
        if not isinstance(when_any_keywords, list) or not isinstance(add_assistants, list):
            continue

        matched = any(
            isinstance(keyword, str) and keyword_matches(lowered, keyword.lower())
            for keyword in when_any_keywords
        )
        if not matched:
            continue

        for agent in add_assistants:
            if not isinstance(agent, str) or agent == lead_agent:
                continue
            if scores.get(agent, 0) > 0 or agent == "Technical Trinity":
                merged.append(agent)

    return dedupe_agents(merged)


def apply_language_copilot_rules(
    lead_agent: str,
    assistants: list[str],
    detected_languages: list[str],
    language_routing: dict[str, str],
    needs_worktree: bool,
    needs_git_workflow: bool,
) -> list[str]:
    merged = list(assistants)

    language_assistants: list[str] = []
    for language in detected_languages:
        candidate = language_routing.get(language)
        if isinstance(candidate, str) and candidate.strip():
            language_assistants.append(candidate)
    language_assistants = dedupe_agents(language_assistants)

    if lead_agent == "Code Audit Council":
        merged.extend(language_assistants)

    if lead_agent == "Git Workflow Guardian" and needs_worktree and needs_git_workflow:
        merged.extend(language_assistants)

    return dedupe_agents([agent for agent in merged if agent != lead_agent])


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
    repo_path: Path,
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
    fast_track_decision = should_use_fast_track(
        text=text,
        sentinel_overlay=sentinel_overlay,
        needs_git_workflow=needs_git_workflow,
        repo_path=repo_path,
        governance_defaults=governance_defaults,
    )
    fast_track_enabled = bool(fast_track_decision.get("enabled", False))
    fast_track_rationale = fast_track_decision.get("rationale", [])
    fast_track_blockers = fast_track_decision.get("blockers", [])
    if not isinstance(fast_track_rationale, list):
        fast_track_rationale = []
    if not isinstance(fast_track_blockers, list):
        fast_track_blockers = []

    execution_control = governance_defaults.get("execution_control", {})
    if not isinstance(execution_control, dict):
        execution_control = {}
    audit_control = governance_defaults.get("audit_control", {})
    if not isinstance(audit_control, dict):
        audit_control = {}

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

    selected_track = TRACK_FAST if fast_track_enabled else TRACK_REGULAR
    if sentinel_overlay:
        risk_level = "high"
    elif len(assistants) > 0 or roundtable_enabled:
        risk_level = "medium"
    else:
        risk_level = "low"

    dual_sign_required = sentinel_overlay or (risk_level == "high")
    post_audit_required = fast_track_enabled
    archive_levels = ensure_list_str(audit_control.get("archive_levels"), ["draft", "verified", "gold"])
    default_archive_level = str(audit_control.get("default_archive_level", "draft"))
    promotion_rules = ensure_list_str(
        audit_control.get("promotion_rules"),
        ["双签通过后可从 draft 提升到 verified"],
    )
    risk_to_slo = execution_control.get("slo_minutes", {"low": 120, "medium": 60, "high": 30})
    if not isinstance(risk_to_slo, dict):
        risk_to_slo = {"low": 120, "medium": 60, "high": 30}
    slo_minutes = int(risk_to_slo.get(risk_level, risk_to_slo.get("medium", 60)))
    require_dri = bool(execution_control.get("require_dri", True))
    dri_agent = lead_agent if require_dri else ""

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
            "blockers": fast_track_blockers,
            "signal_evidence": fast_track_decision.get("signals", {}),
            "track_control": fast_track_decision.get("policy", {}),
            "track_stats": fast_track_decision.get("stats", {}),
            "dual_sign_required": dual_sign_required,
            "post_audit_required": post_audit_required,
        },
        "tracks": {
            "regular": {
                "name": TRACK_REGULAR,
                "flow": ["中书省提案", "门下省审议", "尚书省分发", "六部执行"],
            },
            "fast": {
                "name": TRACK_FAST,
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
        "execution_contract": {
            "dri_required": require_dri,
            "dri_agent": dri_agent,
            "slo_minutes": max(slo_minutes, 1),
            "checkpoints": ["start", "mid", "final"],
        },
        "decision_protocol": decision_protocol,
        "dual_sign": {
            "required": dual_sign_required,
            "signers": ["Sentinel Architect (NB)", "Code Audit Council"] if dual_sign_required else [],
            "evidence_template": [
                "risk_summary",
                "impact_scope",
                "rollback_plan",
                "verification_plan",
            ],
        },
        "post_audit": {
            "required": post_audit_required,
            "flow": ["T+0执行", "T+1审计复盘", "T+2规则回写"],
            "archive_target": "国史馆知识库",
            "archive_level": default_archive_level,
            "archive_levels": archive_levels,
            "promotion_rules": promotion_rules,
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
    base_branch = str(repo_strategy.get("base_branch", "main"))
    if needs_worktree:
        plan.append(
            {
                "skill": "using-git-worktrees",
                "reference": "references/using-git-worktrees-playbook.md",
                "steps": [
                    f"确定基线分支（当前建议为 {base_branch}）",
                    "为每个任务创建独立 worktree 与分支",
                    "在各自 worktree 内开发与提交",
                    "任务完成后清理已合并 worktree",
                ],
                "commands": [
                    "git worktree list",
                    f"git worktree add ../wt-<task> -b <branch> {base_branch}",
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
                    "python scripts/git_workflow_guardrail.py --repo . --stage G3 --pretty",
                    f"git pull --rebase origin {templates['base_branch']}",
                    "python scripts/git_workflow_guardrail.py --repo . --stage G4 --pretty",
                    f"git push -u origin {templates['branch_name']}",
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


def rebalance_git_lead_for_semantic_owner(
    lead_agent: str,
    priority_route: dict[str, object] | None,
    scores: dict[str, int],
    needs_git_workflow: bool,
) -> str:
    if lead_agent != "Git Workflow Guardian" or not needs_git_workflow:
        return lead_agent
    if priority_route is not None:
        return lead_agent

    semantic_owners = [
        "Code Audit Council",
        "World-Class Product Architect",
        "Omni-Architect",
        "Executive Trinity",
    ]
    git_score = scores.get("Git Workflow Guardian", 0)
    for agent in semantic_owners:
        if scores.get(agent, 0) >= max(5, git_score // 2):
            return agent
    return lead_agent


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
    if assistant_count > 0:
        return "模式 B：评审-实现 或 模式 C：战略-技术双轨"
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
    priority_route = detect_priority_lead(text, config)
    if priority_route is not None:
        priority_agent = str(priority_route.get("agent", "")).strip()
        if priority_agent != "":
            lead_agent = priority_agent
            lead_score = scores.get(lead_agent, 0)
    lead_agent = rebalance_git_lead_for_semantic_owner(
        lead_agent=lead_agent,
        priority_route=priority_route,
        scores=scores,
        needs_git_workflow=needs_git_workflow,
    )
    lead_score = scores.get(lead_agent, 0)

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

    assistant_candidates = [agent for agent, _ in sorted_agents if agent != lead_agent]
    if process_only or language_only or unknown_only or confidence >= high_confidence:
        assistants = []
    elif confidence >= medium_confidence:
        assistants = assistant_candidates[:1]
    else:
        assistants = assistant_candidates[:2]

    # Avoid duplicate value-add when assistant score is zero.
    assistants = [
        agent for agent in assistants if scores.get(agent, 0) > 0 and agent != lead_agent
    ]
    assistants = apply_assistant_routing_rules(
        text=text,
        lead_agent=lead_agent,
        assistants=assistants,
        scores=scores,
        config=config,
    )
    assistants = apply_language_copilot_rules(
        lead_agent=lead_agent,
        assistants=assistants,
        detected_languages=detected_languages,
        language_routing=language_routing,
        needs_worktree=needs_worktree,
        needs_git_workflow=needs_git_workflow,
    )
    git_reason_hits = reasons.get("Git Workflow Guardian", {}).get("positive", [])
    if (
        lead_agent != "Git Workflow Guardian"
        and isinstance(git_reason_hits, list)
        and is_git_review_context_only(text, git_reason_hits)
    ):
        assistants = [agent for agent in assistants if agent != "Git Workflow Guardian"]
    if sentinel_overlay and lead_agent != "Sentinel Architect (NB)":
        assistants = dedupe_agents(["Sentinel Architect (NB)"] + assistants)
    governance_defaults = get_governance_defaults(config)
    governance_plan = build_governance_plan(
        text=text,
        repo_path=repo_path,
        lead_agent=lead_agent,
        assistants=assistants,
        scores=scores,
        confidence=confidence,
        sentinel_overlay=sentinel_overlay,
        needs_git_workflow=needs_git_workflow,
        governance_defaults=governance_defaults,
    )
    fast_track_control = governance_defaults.get("fast_track_control", {})
    if not isinstance(fast_track_control, dict):
        fast_track_control = {}
    if bool(fast_track_control.get("write_event_log", True)):
        metrics_file = str(
            fast_track_control.get("metrics_file", ".skill-metrics/governance_events.jsonl")
        )
        try:
            append_governance_event(
                repo_path=repo_path,
                metrics_file=metrics_file,
                payload={
                    "timestamp": now_iso(),
                    "lead_agent": lead_agent,
                    "risk_level": governance_plan.get("risk_level"),
                    "selected_track": ((governance_plan.get("privy_council") or {}).get("selected_track")),
                    "mode_hint": "route_request",
                },
            )
        except Exception:
            pass
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
            (governance_plan.get("privy_council") or {}).get("selected_track") == TRACK_FAST
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
        "priority_routing": priority_route,
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
