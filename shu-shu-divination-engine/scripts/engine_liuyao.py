#!/usr/bin/env python3
"""Adapter for time-based Liuyao execution."""

from __future__ import annotations

import re
from typing import Any

from liuyao_provider_native import load_reading as load_native_reading


LINE_LABELS = ["初", "二", "三", "四", "五", "上"]
YIN_YANG_BY_VALUE = {6: "阴", 7: "阳", 8: "阴", 9: "阳"}
MOVEMENT_BY_VALUE = {6: "阴变阳", 9: "阳变阴"}


def _stringify_sequence(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _normalize_text_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _safe_int(text: str) -> int | None:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _change_line_code(line_code: str) -> str:
    return line_code.replace("6", "7").replace("9", "8")


def _line_display(label: str, raw_value: int | None) -> str:
    if raw_value not in {6, 7, 8, 9}:
        return label
    prefix = "九" if raw_value in {7, 9} else "六"
    if label in {"初", "上"}:
        return f"{label}{prefix}"
    return f"{prefix}{label}"


def _parse_focus_line(explanation_lines: list[str]) -> str:
    for line in explanation_lines:
        match = re.search(r"主要看【([^】]+)】", line)
        if match:
            return match.group(1)
    return ""


def _extract_pair_name(explanation_lines: list[str]) -> str:
    for line in explanation_lines:
        if line.startswith("【") and line.endswith("】"):
            return line.strip("【】")
    return ""


def _normalize_hidden_spirit(value: Any) -> dict[str, Any] | None:
    if not value:
        return None
    if isinstance(value, dict):
        return {
            "line_branch": str(value.get("伏神所在爻", "")),
            "relation": str(value.get("伏神六親", "")),
            "line_index": value.get("伏神排爻數字"),
            "host_line": str(value.get("本卦伏神所在爻", "")),
            "hidden_line": str(value.get("伏神爻", "")),
        }
    return {"raw": str(value)}


def _build_line_items(board: dict[str, Any], line_code: str, line_texts: dict[str, str]) -> list[dict[str, Any]]:
    tiangan = _stringify_sequence(board.get("天干"))
    dizhi = _stringify_sequence(board.get("地支"))
    wuxing = _stringify_sequence(board.get("五行"))
    stars = _stringify_sequence(board.get("星宿"))
    relations = _stringify_sequence(board.get("六親用神"))
    beasts = _stringify_sequence(board.get("六獸"))
    najia = _stringify_sequence(board.get("納甲"))
    month_build = _stringify_sequence(board.get("建月"))
    roles = _stringify_sequence(board.get("世應爻"))

    lines: list[dict[str, Any]] = []
    for index, label in enumerate(LINE_LABELS, start=1):
        raw_value = _safe_int(line_code[index - 1]) if len(line_code) >= index else None
        role_marker = roles[index - 1] if len(roles) >= index else ""
        lines.append(
            {
                "index": index,
                "label": label,
                "display": _line_display(label, raw_value),
                "raw_value": raw_value,
                "yin_yang": YIN_YANG_BY_VALUE.get(raw_value, ""),
                "is_moving": raw_value in MOVEMENT_BY_VALUE,
                "movement": MOVEMENT_BY_VALUE.get(raw_value, ""),
                "role": role_marker if role_marker in {"世", "應"} else "",
                "relation": relations[index - 1] if len(relations) >= index else "",
                "gan": tiangan[index - 1] if len(tiangan) >= index else "",
                "zhi": dizhi[index - 1] if len(dizhi) >= index else "",
                "ganzhi": najia[index - 1] if len(najia) >= index else "",
                "element": wuxing[index - 1] if len(wuxing) >= index else "",
                "beast": beasts[index - 1] if len(beasts) >= index else "",
                "star_mansion": stars[index - 1] if len(stars) >= index else "",
                "month_build": month_build[index - 1] if len(month_build) >= index else "",
                "line_text": line_texts.get(str(index), ""),
            }
        )
    return lines


def _normalize_hexagram(board: dict[str, Any], line_code: str, line_texts: dict[str, str]) -> dict[str, Any]:
    return {
        "name": str(board.get("卦", "")),
        "line_code": line_code,
        "five_star": str(board.get("五星", "")),
        "shi_ying_pattern": str(board.get("世應卦", "")),
        "body_line": str(board.get("身爻", "")),
        "hidden_spirit": _normalize_hidden_spirit(board.get("伏神")),
        "lines": _build_line_items(board, line_code, line_texts),
    }


def _build_movement_payload(main_lines: list[dict[str, Any]], explanation_lines: list[str]) -> dict[str, Any]:
    moving_lines = [
        {
            "index": line["index"],
            "label": line["label"],
            "display": line["display"],
            "raw_value": line["raw_value"],
            "movement": line["movement"],
            "line_text": line["line_text"],
        }
        for line in main_lines
        if line.get("is_moving")
    ]
    focus_rule = next((line for line in explanation_lines if "主要看" in line), "")
    focus_text = explanation_lines[-1] if explanation_lines else ""
    return {
        "moving_line_count": len(moving_lines),
        "moving_lines": moving_lines,
        "focus_line": _parse_focus_line(explanation_lines),
        "focus_rule": focus_rule,
        "focus_text": focus_text,
        "pair_name": _extract_pair_name(explanation_lines),
    }


def _legacy_hexagram_details(board: dict[str, Any]) -> dict[str, Any]:
    return {
        "shi_ying": board.get("世應卦"),
        "body_line": board.get("身爻"),
        "six_relations": board.get("六親用神"),
    }


def build_liuyao_interpretation(
    main_hexagram: str,
    changed_hexagram: str,
    movement_payload: dict[str, Any],
    explanation_lines: list[str],
) -> dict[str, Any]:
    moving_count = movement_payload["moving_line_count"]
    focus_line = movement_payload["focus_line"] or "动爻"
    focus_text = movement_payload["focus_text"] or "盘面已落到动爻，可继续按世应和用神细化。"

    if moving_count == 0:
        conclusion = "此卦偏静，短期内不易快速翻盘，更适合看原局稳定面。"
        confidence = "medium"
    elif moving_count == 1:
        conclusion = f"当前关键变化集中在{focus_line}，主线较清晰，可围绕这一爻判断成败与应期。"
        confidence = "high"
    else:
        conclusion = "当前变化点不止一处，事情处在动态调整中，判断时要同时看多条影响线。"
        confidence = "medium"

    key_signals = [
        f"本卦为{main_hexagram}，之卦为{changed_hexagram}。",
        movement_payload["focus_rule"] or f"重点先看{focus_line}。",
        focus_text,
    ]
    risk_points = [
        "若只看卦名不结合动爻、世应与六亲，容易把结构化结果误读成一句死断。",
    ]
    action_advice = [
        f"先围绕{focus_line}对应的人、事、位置去核对现实映射。",
        "再结合世应、用神与结果定义，判断主导方、阻碍点和应期。",
        "若要进一步贴近所问，补充关键对象与观察时间窗口后再细化。",
    ]

    return {
        "core_dynamic": conclusion,
        "focus_line": focus_line,
        "pair_name": movement_payload["pair_name"],
        "dynamic_focus": explanation_lines,
        "confidence": confidence,
        "key_signals": key_signals,
        "risk_points": risk_points,
        "action_advice": action_advice,
    }


def build_answer_card(normalized_question: str, interpretation: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "liuyao",
        "question": normalized_question,
        "conclusion": interpretation["core_dynamic"],
        "confidence": interpretation["confidence"],
        "key_signals": interpretation["key_signals"],
        "risk_points": interpretation["risk_points"],
        "timing_hint": interpretation["focus_line"],
        "action_advice": interpretation["action_advice"],
        "follow_up_focus": [
            "继续补结果定义、关键对象与观察时间窗口，可进一步细化应期。",
        ],
    }


def compute_liuyao(event_time: str, normalized_question: str) -> dict[str, Any]:
    """Compute a time-based Liuyao reading through the internal adapter contract."""
    provider_result = load_native_reading(event_time)
    provider_meta = provider_result["provider"]
    reading = provider_result["reading"]
    native_core = provider_result.get("native_core")

    main_board = reading.get("本卦", {})
    changed_board = reading.get("之卦", {})
    main_hexagram = main_board.get("卦")
    changed_hexagram = changed_board.get("卦")
    dayan = reading.get("大衍筮法", [])
    line_code = str(dayan[0]) if len(dayan) > 0 else ""
    changed_line_code = _change_line_code(line_code)
    line_texts = _normalize_text_map(dayan[3]) if len(dayan) > 3 else {}
    explanation = dayan[4] if len(dayan) > 4 else ()
    explanation_lines = _stringify_sequence(explanation)
    main_hexagram_payload = _normalize_hexagram(main_board, line_code, line_texts)
    changed_hexagram_payload = _normalize_hexagram(changed_board, changed_line_code, {})
    movement_payload = _build_movement_payload(main_hexagram_payload["lines"], explanation_lines)
    interpretation = build_liuyao_interpretation(
        str(main_hexagram or ""),
        str(changed_hexagram or ""),
        movement_payload,
        explanation_lines,
    )
    answer_card = build_answer_card(normalized_question, interpretation)
    gua_text = line_texts.get("0", "")
    tuan_text = line_texts.get("7", "")

    return {
        "status": "computed",
        "basis": "event_time",
        "engine": "liuyao.time-adapter",
        "normalized_question": normalized_question,
        "event_time": event_time,
        "computed_payload": {
            "protocol_version": "liuyao.adapter.v1",
            "provider": {
                "requested": provider_meta.get("name", "native"),
                "selected": provider_meta.get("name", "native"),
                "implementation": provider_meta.get("implementation", ""),
                "library": provider_meta.get("library", ""),
                "entrypoint": provider_meta.get("entrypoint", ""),
                "ready": bool(provider_meta.get("ready")),
                "fallback_applied": False,
                "fallback_reason": "",
                "coverage": provider_meta.get("coverage", []),
                "notes": provider_meta.get("notes", []),
            },
            "time_anchor": {
                "event_time": event_time,
                "ganzhi": reading.get("日期"),
            },
            "native_core": native_core,
            "hexagrams": {
                "main": main_hexagram_payload,
                "changed": changed_hexagram_payload,
            },
            "movement": movement_payload,
            "interpretation": {
                "dynamic_focus": explanation_lines,
                "gua_text": gua_text,
                "tuan_text": tuan_text,
                "structured": interpretation,
            },
            "answer_card": answer_card,
            "auxiliary": {
                "flying_spirit": reading.get("飛神"),
            },
            "ganzhi": reading.get("日期"),
            "main_hexagram": main_hexagram,
            "changed_hexagram": changed_hexagram,
            "main_hexagram_details": _legacy_hexagram_details(main_board),
            "changed_hexagram_details": _legacy_hexagram_details(changed_board),
            "dynamic_focus": explanation_lines,
            "gua_text": gua_text,
            "tuan_text": tuan_text,
        },
        "summary": (
            f"已按 {event_time} 起六爻，得 {main_hexagram} 之 {changed_hexagram}。"
            f"{interpretation['core_dynamic']}"
        ),
        "detail": movement_payload["focus_text"] or "大衍筮法已生成本卦、之卦与动爻说明。",
        "next_step": interpretation["action_advice"][0],
    }
