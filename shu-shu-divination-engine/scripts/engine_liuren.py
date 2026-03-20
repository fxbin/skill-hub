#!/usr/bin/env python3
"""Adapter for Da Liu Ren execution."""

from __future__ import annotations

from typing import Any

from engine_common import load_kinqimen_config, load_liuren_class, split_iso_datetime


MONTH_NAMES = {
    1: "正",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
    10: "十",
    11: "十一",
    12: "十二",
}

PATTERN_HINTS = {
    "賊尅": "局中带明显冲突或牵制，表层说法未必等于真实走向。",
    "比用": "同类力量抱团，关键在谁先定立场，而不是谁先发声。",
    "涉害": "暗线埋得更深，后续更要盯代价和隐藏损耗。",
    "遙尅": "牵制不一定在台面上，但远端压力一直存在。",
    "昴星": "外部变量和第三方因素会强力介入。",
    "別責": "责任、名分或条件边界会成为卡点。",
    "八專": "局势围绕单一点反复打转，不容易快速改线。",
    "伏吟": "事态偏停滞和重复，短期推进感有限。",
}

RELATION_HINTS = {
    "兄": "先看同辈、同类或竞争方的动作。",
    "子": "中段更容易出现消息、产出或拖延中的转机。",
    "財": "末段往往落到利益、资源或实际交换条件上。",
    "官": "后续重点会落到规则、压力或责任归属。",
    "父": "文书、流程、上层条件或背景框架会更关键。",
}


def build_liuren_interpretation(pattern: list[str], pass_chain: list[list[str]]) -> dict[str, Any]:
    first_pass = pass_chain[0] if pass_chain else ["", "", "", ""]
    middle_pass = pass_chain[1] if len(pass_chain) > 1 else ["", "", "", ""]
    last_pass = pass_chain[2] if len(pass_chain) > 2 else ["", "", "", ""]

    first_relation = first_pass[2] if len(first_pass) > 2 else ""
    middle_relation = middle_pass[2] if len(middle_pass) > 2 else ""
    last_relation = last_pass[2] if len(last_pass) > 2 else ""

    core_dynamic = PATTERN_HINTS.get(pattern[0], "盘面已落到三传四课，可据此追踪人物动机与后续演变。")
    development_path = " -> ".join(item[0] for item in pass_chain if item and item[0])
    relation_path = " / ".join(item[2] for item in pass_chain if len(item) > 2 and item[2])
    surface_vs_hidden = RELATION_HINTS.get(first_relation, "先看最先冒头的那股力量，再看它如何转入后续传递。")

    action_guidance = [
        f"先盯初传的{first_pass[0]}位和{first_relation or '首个'}关系，看谁先出手、谁先表态。",
        f"再看中传的{middle_pass[0]}位是否把局面带向{middle_relation or '新的'}层级，判断有没有遮掩或转口。",
        f"最后把末传的{last_pass[0]}位与{last_relation or '末段结果'}关系落回现实利益、责任或态度变化上。",
    ]

    return {
        "core_dynamic": core_dynamic,
        "development_path": development_path,
        "relation_path": relation_path,
        "surface_vs_hidden": surface_vs_hidden,
        "final_focus": RELATION_HINTS.get(last_relation, "最后要把末传落回真实结果和利益位置上。"),
        "action_guidance": action_guidance,
    }


def build_answer_card(normalized_question: str, interpretation: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "liuren",
        "question": normalized_question,
        "conclusion": interpretation["core_dynamic"],
        "confidence": "medium",
        "key_signals": [
            f"发展路径：{interpretation['development_path']}",
            f"六亲路径：{interpretation['relation_path']}",
            interpretation["surface_vs_hidden"],
        ],
        "risk_points": [interpretation["surface_vs_hidden"]],
        "timing_hint": interpretation["development_path"],
        "action_advice": interpretation["action_guidance"],
        "follow_up_focus": [
            f"末传关注：{interpretation['final_focus']}",
        ],
    }


def compute_liuren(event_time: str, normalized_question: str) -> dict[str, Any]:
    """Compute a Da Liu Ren reading for hidden motives and unfolding dynamics."""
    config = load_kinqimen_config()
    Liuren = load_liuren_class()
    year, month, day, hour, minute = split_iso_datetime(event_time)
    jieqi = config.jq(year, month, day, hour, minute)
    lunar = config.lunar_date_d(year, month, day)
    lunar_month = MONTH_NAMES.get(lunar["月"], str(lunar["月"]))
    ganzhi = config.gangzhi(year, month, day, hour, minute)

    reading = Liuren(jieqi, lunar_month, ganzhi[2], ganzhi[3]).result(0)
    pattern = reading.get("格局", ["", ""])
    three_pass = reading.get("三傳", {})
    pass_chain = [
        three_pass.get("初傳", ["", "", "", ""]),
        three_pass.get("中傳", ["", "", "", ""]),
        three_pass.get("末傳", ["", "", "", ""]),
    ]
    pass_summary = " -> ".join(item[0] for item in pass_chain if item and item[0])
    relation_summary = " / ".join(item[2] for item in pass_chain if len(item) > 2 and item[2])
    interpretation = build_liuren_interpretation(pattern, pass_chain)
    answer_card = build_answer_card(normalized_question, interpretation)

    return {
        "status": "computed",
        "basis": "event_time",
        "engine": "kinliuren.Liuren.result",
        "normalized_question": normalized_question,
        "event_time": event_time,
        "computed_payload": {
            "jieqi": reading.get("節氣"),
            "lunar_month": reading.get("農曆月"),
            "ganzhi": reading.get("日期"),
            "pattern": pattern,
            "three_pass": three_pass,
            "four_lessons": reading.get("四課"),
            "sky_earth_board": reading.get("天地盤"),
            "earth_to_sky": reading.get("地轉天盤"),
            "earth_to_general": reading.get("地轉天將"),
            "interpretation": interpretation,
            "answer_card": answer_card,
        },
        "summary": (
            f"已按 {event_time} 起大六壬，格局为 {pattern[0]} / {pattern[1]}。"
            f"{interpretation['core_dynamic']}"
        ),
        "detail": (
            f"三传从 {pass_summary} 推进，六亲关系依次呈现 {relation_summary}。"
            f"{interpretation['surface_vs_hidden']}"
        ),
        "next_step": interpretation["action_guidance"][0],
    }
