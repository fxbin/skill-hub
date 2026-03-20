#!/usr/bin/env python3
"""Adapter for Qimen execution and candidate comparison."""

from __future__ import annotations

from typing import Any

from engine_common import PALACE_DIRECTIONS, load_qimen_class, split_iso_datetime


DOOR_WEIGHTS = {"開": 4, "生": 4, "休": 3, "景": 1, "杜": 0, "驚": -2, "死": -3, "傷": -4}
STAR_WEIGHTS = {"輔": 2, "沖": 2, "任": 1, "英": 1, "心": 1, "禽": 0, "柱": 0, "蓬": -1, "芮": -2}
GOD_WEIGHTS = {"符": 2, "天": 1, "合": 1, "地": 0, "陰": 0, "蛇": -1, "雀": -1, "勾": -1}


def normalize_pan_map(value: Any) -> dict[str, Any]:
    if isinstance(value, tuple):
        if value and isinstance(value[0], dict):
            return value[0]
        return {}
    if isinstance(value, dict):
        return value
    return {}


def rank_palaces(pan: dict[str, Any]) -> list[dict[str, Any]]:
    doors = normalize_pan_map(pan.get("門"))
    stars = normalize_pan_map(pan.get("星"))
    gods = normalize_pan_map(pan.get("神"))

    ranked: list[dict[str, Any]] = []
    for palace, door in doors.items():
        if palace == "中":
            continue
        star = stars.get(palace, "")
        god = gods.get(palace, "")
        score = DOOR_WEIGHTS.get(door, 0) + STAR_WEIGHTS.get(star, 0) + GOD_WEIGHTS.get(god, 0)
        ranked.append(
            {
                "palace": palace,
                "direction": PALACE_DIRECTIONS.get(palace, palace),
                "door": door,
                "star": star,
                "god": god,
                "score": score,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["palace"]))
    return ranked


def evaluate_time_candidate(event_time: str) -> dict[str, Any]:
    Qimen = load_qimen_class()
    year, month, day, hour, minute = split_iso_datetime(event_time)
    pan = Qimen(year, month, day, hour, minute).pan(1)
    ranked = rank_palaces(pan)
    best = next((item for item in ranked if item["door"] in {"開", "生", "休"}), ranked[0] if ranked else None)
    caution = ranked[-1] if ranked else None
    value_gate = pan.get("值符值使", {}).get("值使門宮", ["", ""])
    score = (best["score"] if best else 0) + DOOR_WEIGHTS.get(value_gate[0], 0)

    return {
        "event_time": event_time,
        "score": score,
        "best_palace": best,
        "caution_palace": caution,
        "pan_core": {
            "ganzhi": pan.get("干支"),
            "jieqi": pan.get("節氣"),
            "ju": pan.get("排局"),
            "xun_head": pan.get("旬首"),
            "value_symbol_and_gate": pan.get("值符值使"),
            "doors": normalize_pan_map(pan.get("門")),
            "stars": normalize_pan_map(pan.get("星")),
            "gods": normalize_pan_map(pan.get("神")),
        },
        "ranked_palaces": ranked,
    }


def describe_score_confidence(score_gap: int | None, winner_score: int) -> str:
    if score_gap is None:
        return "single-candidate"
    if score_gap >= 4 and winner_score >= 6:
        return "high"
    if score_gap >= 2 and winner_score >= 4:
        return "medium"
    return "low"


def build_qimen_interpretation(winner: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    best_palace = winner.get("best_palace") or {}
    caution_palace = winner.get("caution_palace") or {}
    score_gap: int | None = None
    if len(candidates) > 1:
        score_gap = winner["score"] - candidates[1]["score"]

    confidence = describe_score_confidence(score_gap, winner["score"])
    if confidence == "high":
        timing_judgment = "当前时点优势明确，可优先推进。"
    elif confidence == "medium":
        timing_judgment = "当前时点略占优势，可以推进，但仍建议结合场地和目标细化。"
    elif confidence == "low":
        timing_judgment = "时间优势有限，成败更依赖你的动作设计和现场发挥。"
    else:
        timing_judgment = "当前只有单一时点，可先按此盘落地，再结合更多条件细化。"

    favorable_signal = (
        f"当前主利位在{best_palace.get('direction', '')}，"
        f"以{best_palace.get('door', '')}门、{best_palace.get('star', '')}星、{best_palace.get('god', '')}神为主。"
    )
    caution_signal = (
        f"当前最需回避的是{caution_palace.get('direction', '')}一带，"
        f"对应{caution_palace.get('door', '')}门、{caution_palace.get('star', '')}星、{caution_palace.get('god', '')}神。"
    )
    action_guidance = [
        f"若要见人谈事，优先把关键动作放在{best_palace.get('direction', '')}方位语境里展开。",
        f"开场方式宜贴近{best_palace.get('door', '')}门气质，先求顺势、资源和合作空间。",
        f"尽量避开{caution_palace.get('direction', '')}方向对应的惊扰、拖滞或硬碰硬节奏。",
    ]

    return {
        "recommended_time": winner["event_time"],
        "recommended_direction": best_palace.get("direction", ""),
        "recommended_door": best_palace.get("door", ""),
        "timing_confidence": confidence,
        "candidate_gap": score_gap,
        "timing_judgment": timing_judgment,
        "favorable_signal": favorable_signal,
        "caution_signal": caution_signal,
        "action_guidance": action_guidance,
    }


def build_answer_card(normalized_question: str, interpretation: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "qimen",
        "question": normalized_question,
        "conclusion": interpretation["timing_judgment"],
        "confidence": interpretation["timing_confidence"],
        "key_signals": [
            interpretation["favorable_signal"],
            interpretation["caution_signal"],
        ],
        "risk_points": [interpretation["caution_signal"]],
        "timing_hint": interpretation["recommended_time"],
        "action_advice": interpretation["action_guidance"],
        "follow_up_focus": [
            "补充见面地点、谈判目标或备选方案，可继续细化场域与动作。",
        ],
    }


def compute_qimen(event_times: list[str], normalized_question: str) -> dict[str, Any]:
    """Compute Qimen readings and compare multiple candidate times when available."""
    evaluations = [evaluate_time_candidate(item) for item in event_times]
    evaluations.sort(key=lambda item: (-item["score"], item["event_time"]))

    winner = evaluations[0]
    best_palace = winner.get("best_palace") or {}
    caution = winner.get("caution_palace") or {}
    value_gate = winner["pan_core"].get("value_symbol_and_gate", {}).get("值使門宮", ["", ""])
    mode = "candidate-comparison" if len(event_times) > 1 else "single-pan"
    interpretation = build_qimen_interpretation(winner, evaluations)
    answer_card = build_answer_card(normalized_question, interpretation)

    return {
        "status": "computed",
        "basis": "candidate_times" if len(event_times) > 1 else "event_time",
        "engine": "kinqimen.Qimen.pan",
        "normalized_question": normalized_question,
        "computed_payload": {
            "mode": mode,
            "winner": winner,
            "candidates": evaluations,
            "interpretation": interpretation,
            "answer_card": answer_card,
        },
        "summary": (
            f"已按奇门起盘比较 {len(event_times)} 个时点，当前以 {winner['event_time']} 更优。"
            f"主看 {best_palace.get('direction', '')} 方的 {best_palace.get('door', '')}门，"
            f"配 {best_palace.get('star', '')}星 {best_palace.get('god', '')}神。"
        ),
        "detail": (
            f"值使落 {value_gate[1]} 宫为 {value_gate[0]}门；"
            f"当前最需回避的是 {caution.get('direction', '')} 方的 {caution.get('door', '')}门，"
            f"配 {caution.get('star', '')}星 {caution.get('god', '')}神。"
        ),
        "next_step": interpretation["action_guidance"][0],
    }
