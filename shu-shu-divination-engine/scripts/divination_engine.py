#!/usr/bin/env python3
"""Deterministic router and execution engine for four shu-shu methods."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from engine_common import (  # noqa: E402
    RuntimeDependencyError,
    extract_explicit_datetimes,
    normalize_candidate_times,
    normalize_datetime_text,
)
from engine_liuren import compute_liuren  # noqa: E402
from engine_liuyao import compute_liuyao  # noqa: E402
from engine_qimen import compute_qimen  # noqa: E402


TRIGRAMS = {
    1: {"name": "乾", "element": "金", "direction": "西北", "lines": [1, 1, 1]},
    2: {"name": "兑", "element": "金", "direction": "正西", "lines": [1, 1, 0]},
    3: {"name": "离", "element": "火", "direction": "正南", "lines": [1, 0, 1]},
    4: {"name": "震", "element": "木", "direction": "正东", "lines": [1, 0, 0]},
    5: {"name": "巽", "element": "木", "direction": "东南", "lines": [0, 1, 1]},
    6: {"name": "坎", "element": "水", "direction": "正北", "lines": [0, 1, 0]},
    7: {"name": "艮", "element": "土", "direction": "东北", "lines": [0, 0, 1]},
    8: {"name": "坤", "element": "土", "direction": "西南", "lines": [0, 0, 0]},
}

TRIGRAM_BY_LINES = {tuple(value["lines"]): key for key, value in TRIGRAMS.items()}
HEXAGRAM_NAMES = {
    ("坎", "艮"): "蒙",
    ("乾", "离"): "同人",
    ("巽", "坎"): "渙",
}
ELEMENT_FLOW = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
ELEMENT_CONTROL = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
METHOD_ORDER = ["qimen", "liuren", "liuyao", "meihua"]
FRAMEWORKS = {
    "meihua": "短期应事 / 寻物 / 快速方向判断",
    "liuyao": "一事一问 / 成败阻碍 / 应期判断",
    "qimen": "择时择方 / 策略推进 / 候选时间比较",
    "liuren": "隐藏动机 / 多方关系 / 事态演变",
}
METHOD_LABELS = {
    "meihua": "梅花易数",
    "liuyao": "六爻",
    "qimen": "奇门遁甲",
    "liuren": "大六壬",
}


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def split_prompt(prompt: str) -> list[str]:
    normalized = normalize_whitespace(prompt)
    if not normalized:
        return []
    parts = re.split(r"[。！？!?；;\n]+", normalized)
    return [part.strip(" ，,") for part in parts if part.strip(" ，,")]


def detect_destiny_style_question(text: str) -> bool:
    generic_markers = [
        "财运",
        "总运",
        "命里",
        "一生",
        "大运",
        "流年",
        "身强",
        "身弱",
        "喜神",
        "忌神",
        "命格",
        "十神",
    ]
    if any(marker in text for marker in generic_markers):
        return True
    if "适合" in text and any(marker in text for marker in ["打工", "创业"]) and "年" not in text:
        return True
    return False


def detect_adjacent_system(text: str) -> str | None:
    mapping = {
        "bazi": ["八字", "四柱", "大运", "流年", "身强", "身弱", "喜神", "忌神", "命盘"],
        "ziwei": ["紫微", "斗数"],
        "astrology": ["星盘", "上升", "月亮星座", "太阳星座", "第七宫", "第十宫"],
        "tarot": ["塔罗"],
        "fengshui": ["风水", "飞星", "户型", "缺角", "床头", "动土", "阳宅"],
    }
    for system, keywords in mapping.items():
        if any(keyword in text for keyword in keywords):
            return system
    return None


def detect_high_risk_flags(text: str) -> list[str]:
    rules = {
        "self_harm": ["自杀", "轻生", "不想活", "结束生命"],
        "medical": ["癌症", "绝症", "寿元", "还能活多久", "猝死"],
        "violence": ["报复", "杀", "血光之灾"],
    }
    return [flag for flag, keywords in rules.items() if any(keyword in text for keyword in keywords)]


def is_method_only_request(text: str) -> bool:
    markers = [
        "先别算",
        "先不要算",
        "只告诉我用什么术数",
        "只告诉我该用哪种术数",
        "该用六爻还是奇门",
        "更适合六爻还是奇门",
        "先判断该用哪门术数",
    ]
    return any(marker in text for marker in markers)


def is_short_term_question(text: str) -> bool:
    return any(token in text for token in ["今天", "今晚", "明天", "这周", "下周", "马上", "最近", "下午", "上午"])


def infer_primary_question(text: str) -> str:
    return normalize_whitespace(text)


def extract_numbers(text: str) -> list[int]:
    if not text:
        return []
    if "数字" not in text and "数是" not in text and "号码" not in text:
        return []
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    return numbers[:6]


def extract_candidate_slots(text: str) -> list[str]:
    slots: list[str] = []
    weekday_pattern = re.compile(r"(?:这周|下周|本周)?周[一二三四五六日天](?:上午|中午|下午|晚上)?")
    for match in weekday_pattern.finditer(text):
        value = match.group(0)
        if value not in slots:
            slots.append(value)
    for match in re.finditer(r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}", text):
        value = match.group(0)
        if value not in slots:
            slots.append(value)
    return slots


def extract_roles(text: str) -> list[str]:
    roles: list[str] = []
    for role in ["客户", "合伙人", "前任", "对象", "领导", "同事", "朋友", "父母", "家人", "第三者"]:
        if role in text:
            roles.append(role)
    return roles


def required_inputs(method: str | None) -> list[str]:
    mapping = {
        "meihua": ["三个随机数字，或明确的起测时间"],
        "liuyao": ["明确的起测时间"],
        "qimen": ["一个明确时间，或两个以上候选时间"],
        "liuren": ["明确的起课时间"],
    }
    return mapping.get(method or "", [])


def missing_inputs(method: str | None, recognized_inputs: dict[str, Any]) -> list[str]:
    if method == "meihua":
        if recognized_inputs.get("numbers") and len(recognized_inputs["numbers"]) >= 3:
            return []
        if recognized_inputs.get("event_time"):
            return []
        return ["梅花易数当前还缺起测锚点：请补足 3 个随机数字，或给出明确起测时间。"]
    if method == "liuyao" and not recognized_inputs.get("event_time"):
        return ["六爻需要明确起测时间，例如 2026-03-18T15:00:00。"]
    if method == "qimen":
        if len(recognized_inputs.get("candidate_times", [])) >= 2 or recognized_inputs.get("event_time"):
            return []
        return ["奇门需要一个明确时间，或两个以上候选时间点。"]
    if method == "liuren" and not recognized_inputs.get("event_time"):
        return ["大六壬需要明确起课时间，例如 2026-03-18T15:00:00。"]
    return []


def choose_numbers(numbers: list[int], event_time: str | None) -> tuple[list[int], str | None]:
    if len(numbers) >= 3:
        return numbers[:3], "numbers"
    if event_time:
        dt = datetime.fromisoformat(event_time)
        derived = [dt.year + dt.month + dt.day, dt.hour + 1, dt.minute + dt.day]
        return derived, "event_time"
    return [], None


def is_supporting_fragment(text: str) -> bool:
    return ("数字" in text or "数是" in text or "号码" in text) and not any(
        marker in text for marker in ["能不能", "会不会", "什么时候", "哪个", "如何", "怎么", "适合", "结果"]
    )


def score_methods(text: str, recognized_inputs: dict[str, Any]) -> dict[str, int]:
    scores = {method: 0 for method in METHOD_LABELS}
    if any(token in text for token in ["梅花", "梅花易数"]):
        scores["meihua"] += 5
    if "六爻" in text:
        scores["liuyao"] += 5
    if any(token in text for token in ["奇门", "遁甲"]):
        scores["qimen"] += 5
    if any(token in text for token in ["六壬", "大六壬"]):
        scores["liuren"] += 5

    if any(token in text for token in ["钥匙", "丢", "不见", "寻物", "找不到"]):
        scores["meihua"] += 6
    if is_short_term_question(text):
        scores["meihua"] += 2
    if recognized_inputs.get("numbers"):
        scores["meihua"] += 3

    if any(token in text for token in ["能不能成", "会不会", "何时", "什么时候", "结果", "复合", "行不行", "值不值得"]):
        scores["liuyao"] += 4
    if any(token in text for token in ["合作", "感情", "复合", "考试", "项目", "主业", "写作"]):
        scores["liuyao"] += 2

    if any(token in text for token in ["哪个时间", "哪天", "见客户", "谈合作", "方向", "方位", "择时", "择方", "更适合去"]):
        scores["qimen"] += 5
    if len(recognized_inputs.get("candidate_times", [])) >= 2 or len(recognized_inputs.get("candidate_slots", [])) >= 2:
        scores["qimen"] += 6

    if any(token in text for token in ["怎么想", "真实想法", "背后", "暗线", "盘算", "第三者", "演变", "幕后", "谁在推动"]):
        scores["liuren"] += 6
    if recognized_inputs.get("roles"):
        scores["liuren"] += 1

    if detect_destiny_style_question(text):
        for method in scores:
            scores[method] -= 1

    if recognized_inputs.get("event_time"):
        scores["liuyao"] += 1
        scores["liuren"] += 1
        scores["qimen"] += 1
    return scores


def choose_method(scores: dict[str, int]) -> str | None:
    positive = [(method, score) for method, score in scores.items() if score > 0]
    if not positive:
        return None
    positive.sort(key=lambda item: (-item[1], METHOD_ORDER.index(item[0])))
    return positive[0][0]


def classify_sub_question(text: str, reference_dt: datetime | None) -> dict[str, Any]:
    normalized = infer_primary_question(text)
    explicit_times = extract_explicit_datetimes(normalized, reference_dt=reference_dt)
    recognized_inputs = {
        "event_time": explicit_times[0] if explicit_times else None,
        "candidate_times": explicit_times if len(explicit_times) >= 2 else [],
        "candidate_slots": extract_candidate_slots(normalized),
        "numbers": extract_numbers(normalized),
        "roles": extract_roles(normalized),
    }
    adjacent_system = detect_adjacent_system(normalized)
    risk_flags = detect_high_risk_flags(normalized)
    scores = score_methods(normalized, recognized_inputs)
    selected_method = choose_method(scores)
    bucket = "executable"
    if is_supporting_fragment(normalized):
        bucket = "supporting"
    elif risk_flags:
        bucket = "high-risk"
    elif adjacent_system and not selected_method:
        bucket = "adjacent"
    elif detect_destiny_style_question(normalized) and not any(
        token in normalized for token in ["行不行", "能不能", "是否", "哪个更适合", "合作", "写作", "见客户"]
    ):
        bucket = "adjacent"
    priority = (
        1 if selected_method else 0,
        1 if not missing_inputs(selected_method, recognized_inputs) else 0,
        1 if recognized_inputs["candidate_times"] or recognized_inputs["event_time"] or len(recognized_inputs["numbers"]) >= 3 else 0,
        1 if is_short_term_question(normalized) else 0,
        1 if "年" in normalized and any(token in normalized for token in ["行不行", "能不能", "适不适合"]) else 0,
        max(scores.values()) if scores else 0,
        len(normalized),
    )
    return {
        "question": normalized,
        "bucket": bucket,
        "selected_method": selected_method,
        "scores": scores,
        "adjacent_system": adjacent_system,
        "risk_flags": risk_flags,
        "required_inputs": required_inputs(selected_method),
        "missing_inputs": missing_inputs(selected_method, recognized_inputs),
        "recognized_inputs": recognized_inputs,
        "priority": priority,
    }


def choose_primary_sub_question(items: list[dict[str, Any]]) -> tuple[int | None, dict[str, Any] | None]:
    executable = [(index, item) for index, item in enumerate(items) if item["bucket"] == "executable" and item["selected_method"]]
    if executable:
        executable.sort(key=lambda pair: pair[1]["priority"], reverse=True)
        return executable[0]
    adjacent = [(index, item) for index, item in enumerate(items) if item["bucket"] == "adjacent"]
    if adjacent:
        return adjacent[0]
    high_risk = [(index, item) for index, item in enumerate(items) if item["bucket"] == "high-risk"]
    if high_risk:
        return high_risk[0]
    return None, None


def build_compound_summary(
    breakdown: list[dict[str, Any]],
    primary_index: int | None,
    supporting_fragments: list[str],
) -> dict[str, str]:
    if primary_index is None:
        return {
            "this_round": "这轮还没有选出可直接进入起测的主问题。",
            "selection_logic": "系统先做拆分，再按可执行性、起测锚点和短期判断价值排序。",
        }
    executable_count = sum(1 for item in breakdown if item["bucket"] == "executable")
    adjacent_count = sum(1 for item in breakdown if item["bucket"] == "adjacent")
    risk_count = sum(1 for item in breakdown if item["bucket"] == "high-risk")
    return {
        "this_round": f"本轮先处理第 {primary_index + 1} 个子问题：{breakdown[primary_index]['question']}。",
        "selection_logic": (
            "主问题按可执行性、起测锚点和短期判断价值选择，不按提问顺序机械取第一句。"
            f"其余问题中，可后续继续进入四术数的有 {max(executable_count - 1, 0)} 题，"
            f"属于相邻体系的有 {adjacent_count} 题，需要先降风险的有 {risk_count} 题。"
            + (f"另识别到 {len(supporting_fragments)} 条补充片段。" if supporting_fragments else "没有额外的补充信息片段。")
        ),
    }


def is_adjacent_dominant_prompt(
    prompt: str,
    breakdown: list[dict[str, Any]],
    merged_inputs: dict[str, Any],
    overall_adjacent_system: str | None,
) -> bool:
    if not overall_adjacent_system:
        return False
    if merged_inputs.get("event_time") or merged_inputs.get("candidate_times") or len(merged_inputs.get("numbers", [])) >= 3:
        return False
    adjacent_markers = [
        "分析这个八字",
        "八字命盘",
        "四柱命理",
        "大运流年",
        "结合过去",
        "过去二十年",
        "校验",
        "校准",
        "推演",
    ]
    if not any(marker in prompt for marker in adjacent_markers):
        return False
    adjacent_count = sum(1 for item in breakdown if item["bucket"] == "adjacent")
    executable_count = sum(1 for item in breakdown if item["bucket"] == "executable")
    return adjacent_count >= executable_count


def element_relation(base: str, other: str) -> str:
    if base == other:
        return "同气相应"
    if ELEMENT_FLOW.get(base) == other:
        return "体生用"
    if ELEMENT_FLOW.get(other) == base:
        return "用生体"
    if ELEMENT_CONTROL.get(base) == other:
        return "体克用"
    if ELEMENT_CONTROL.get(other) == base:
        return "用克体"
    return "关系平平"


def flip_line(value: int) -> int:
    return 0 if value else 1


def lines_to_trigram_number(lines: list[int]) -> int:
    return TRIGRAM_BY_LINES[tuple(lines)]


def derive_meihua_trigrams(numbers: list[int]) -> dict[str, Any]:
    upper_num = numbers[0] % 8 or 8
    lower_num = numbers[1] % 8 or 8
    moving_line = numbers[2] % 6 or 6
    full_lines = TRIGRAMS[lower_num]["lines"][:] + TRIGRAMS[upper_num]["lines"][:]
    changed_lines = full_lines[:]
    changed_lines[moving_line - 1] = flip_line(changed_lines[moving_line - 1])
    changed_lower_num = lines_to_trigram_number(changed_lines[:3])
    changed_upper_num = lines_to_trigram_number(changed_lines[3:])
    main_upper = TRIGRAMS[upper_num]
    main_lower = TRIGRAMS[lower_num]
    changed_upper = TRIGRAMS[changed_upper_num]
    changed_lower = TRIGRAMS[changed_lower_num]
    return {
        "numbers": numbers,
        "moving_line": moving_line,
        "main_upper": main_upper,
        "main_lower": main_lower,
        "changed_upper": changed_upper,
        "changed_lower": changed_lower,
        "main_hexagram": HEXAGRAM_NAMES.get((main_upper["name"], main_lower["name"]), f"{main_upper['name']}上{main_lower['name']}下"),
        "changed_hexagram": HEXAGRAM_NAMES.get((changed_upper["name"], changed_lower["name"]), f"{changed_upper['name']}上{changed_lower['name']}下"),
    }


def build_meihua_reading(normalized_question: str, numbers: list[int], basis: str, event_time: str | None) -> dict[str, Any]:
    trigrams = derive_meihua_trigrams(numbers)
    relation = element_relation(trigrams["main_lower"]["element"], trigrams["main_upper"]["element"])
    direction = trigrams["changed_lower"]["direction"]
    lost_item = any(token in normalized_question for token in ["钥匙", "丢", "不见", "找不到", "寻物"])

    if lost_item:
        conclusion = f"这件失物仍有回找机会，优先朝{direction}一侧、静置收纳区和你最后确认的近身位置回搜。"
        key_signals = [
            f"主卦 {trigrams['main_hexagram']}，变卦 {trigrams['changed_hexagram']}。",
            f"动爻在第 {trigrams['moving_line']} 爻，事情已进入“可回溯、可复盘”的阶段。",
            f"体用关系为“{relation}”，先查最近一次拿起后没有完全放回原位的动作链。",
        ]
        action_advice = [
            "先回到最后一次确认地点，按“桌面 -> 抽屉 -> 包内夹层 -> 床边/椅边缝隙”顺序复查。",
            f"重点留意{direction}方位、靠墙角落、收纳盒、布料遮挡物下方。",
            "不要一边找一边换区域，先把最后一段行动路径完整走一遍。",
        ]
    else:
        conclusion = f"从梅花盘势看，当前更像短期可判断的问题，主线先看第 {trigrams['moving_line']} 爻带出的变化。"
        key_signals = [
            f"主卦 {trigrams['main_hexagram']}，变卦 {trigrams['changed_hexagram']}。",
            f"上卦为{trigrams['main_upper']['name']}，下卦为{trigrams['main_lower']['name']}。",
            f"体用关系为“{relation}”。",
        ]
        action_advice = [
            "先把问题收缩到一件事、一个时间窗、一个结果定义。",
            "优先验证最先出现的外部变化，而不是一次性展开所有分支判断。",
            "如果要继续细化，应补充起心动念时刻或更稳定的数字锚点。",
        ]

    answer_card = {
        "method": "meihua",
        "question": normalized_question,
        "conclusion": conclusion,
        "confidence": "medium",
        "key_signals": key_signals,
        "risk_points": ["梅花更适合短期应事和方向判断，不宜硬拉成长周期命盘总论。"],
        "timing_hint": f"第 {trigrams['moving_line']} 爻先动",
        "action_advice": action_advice,
        "follow_up_focus": ["若结果仍不清楚，可补充更精确的时间锚点后转入六爻或奇门细化。"],
    }
    return {
        "status": "computed",
        "basis": basis,
        "engine": "meihua.native",
        "normalized_question": normalized_question,
        "event_time": event_time,
        "moving_line": trigrams["moving_line"],
        "computed_payload": {
            "numbers": numbers,
            "main_hexagram": trigrams["main_hexagram"],
            "changed_hexagram": trigrams["changed_hexagram"],
            "main_upper": trigrams["main_upper"],
            "main_lower": trigrams["main_lower"],
            "changed_upper": trigrams["changed_upper"],
            "changed_lower": trigrams["changed_lower"],
            "relation": relation,
        },
        "summary": conclusion,
        "detail": "已根据当前可用锚点完成梅花易数起测。",
        "next_step": action_advice[0],
        "answer_card": answer_card,
    }


def build_high_risk_response(flags: list[str]) -> dict[str, Any]:
    return {
        "status": "high-risk",
        "headline": "这类问题不适合直接当作数术测算题处理。",
        "sections": [
            {"title": "风险提醒", "lines": ["当前内容涉及高风险主题，先处理现实安全与专业支持。"]},
            {"title": "建议处理", "lines": [f"识别到风险标记：{', '.join(flags)}。", "如果存在现实紧急风险，请优先联系身边可信任的人或专业机构。"]},
        ],
    }


def build_adjacent_response(adjacent_system: str, question: str) -> dict[str, Any]:
    rewrites = {
        "bazi": [
            "把问题改写成一个具体决策，例如：2026 年是否适合把写作当主业？",
            "或给出两个候选时间，让我用奇门做择时比较。",
        ],
        "astrology": ["先把问题缩成一个短期判断，例如：这段关系接下来三个月有没有明确推进机会？"],
        "fengshui": ["如果你真正要问的是某次谈判、搬家或入住时机，可以改写成奇门可处理的问题。"],
    }
    lines = rewrites.get(adjacent_system, ["先把问题收缩成一个可执行、可验证的具体预测问题。"])
    return {
        "status": "adjacent-rewrite",
        "headline": "这更像相邻体系的问题，不建议直接硬套四术数。",
        "sections": [
            {"title": "更适合的体系", "lines": [f"当前更接近：{adjacent_system}。"]},
            {"title": "为什么不直接硬套四术数", "lines": [f"原问题“{question}”更偏命盘 / 总运 / 相邻体系分析。"]},
            {"title": "可改写的问题", "lines": lines},
        ],
    }


def summarize_recognized_inputs(recognized_inputs: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if recognized_inputs.get("event_time"):
        lines.append(f"时间锚点：{recognized_inputs['event_time']}")
    if recognized_inputs.get("candidate_times"):
        lines.append(f"候选时间：{', '.join(recognized_inputs['candidate_times'])}")
    if recognized_inputs.get("numbers"):
        lines.append(f"数字锚点：{', '.join(str(item) for item in recognized_inputs['numbers'])}")
    if recognized_inputs.get("roles"):
        lines.append(f"关键人物：{', '.join(recognized_inputs['roles'])}")
    return lines


def build_final_response_sections(result: dict[str, Any]) -> list[dict[str, Any]]:
    routing = result["routing"]
    execution = result["execution"]
    summary = result["compound_analysis"]["summary"]
    sections: list[dict[str, Any]] = []
    method = routing["selected_method"]

    if execution["status"] == "computed":
        answer_card = execution["answer_card"]
        sections.append(
            {
                "title": "适用术数",
                "lines": [
                    f"本轮术数：{method}",
                    f"更适合用{METHOD_LABELS[method]}处理这一轮问题。",
                    f"归一问题：{routing['normalized_question']}",
                ],
            }
        )
        sections.append({"title": "本轮处理", "lines": [summary["this_round"], summary["selection_logic"]]})
        sections.append({"title": "起测依据", "lines": summarize_recognized_inputs(execution["recognized_inputs"]) or ["本轮未识别到可用锚点。"]})
        sections.append(
            {
                "title": "测算结论",
                "lines": [
                    answer_card["conclusion"],
                    f"置信度：{answer_card['confidence']}",
                    f"时间提示：{answer_card['timing_hint']}",
                    *answer_card["key_signals"][:3],
                ],
            }
        )
        sections.append({"title": "风险提示", "lines": answer_card["risk_points"]})
        sections.append({"title": "下一步建议", "lines": answer_card["action_advice"] + answer_card["follow_up_focus"]})
        if execution["deferred_questions"]:
            sections.append({"title": "暂缓问题", "lines": execution["deferred_questions"]})
    elif execution["status"] == "needs_input":
        sections.append({"title": "适用术数", "lines": [f"建议术数：{method}", f"对应框架：{execution['framework']}"]})
        sections.append({"title": "本轮处理", "lines": [summary["this_round"], summary["selection_logic"]]})
        sections.append({"title": "当前状态", "lines": [execution["summary"]]})
        sections.append({"title": "还需补充", "lines": execution["missing_inputs"]})
        if execution["deferred_questions"]:
            sections.append({"title": "暂缓问题", "lines": execution["deferred_questions"]})
    elif execution["status"] == "method-only":
        sections.append({"title": "适用术数", "lines": [f"建议术数：{method}", routing["reason"]]})
        sections.append({"title": "为什么选它", "lines": [execution["summary"]]})
        sections.append({"title": "若继续起测", "lines": execution["missing_inputs"] or ["当前信息已足够进入下一步。"]})
    elif execution["status"] == "adjacent-rewrite":
        sections = build_adjacent_response(routing["adjacent_system"], routing["primary_question"])["sections"]
    elif execution["status"] == "high-risk":
        sections = build_high_risk_response(result["risk_flags"])["sections"]
    return sections


def render_final_response_text(headline: str, sections: list[dict[str, Any]]) -> str:
    parts = [headline]
    for section in sections:
        parts.append("")
        parts.append(f"{section['title']}:")
        for line in section["lines"]:
            parts.append(f"- {line}")
    return "\n".join(parts).strip()


def build_final_response(result: dict[str, Any]) -> dict[str, Any]:
    execution = result["execution"]
    routing = result["routing"]
    if execution["status"] == "computed":
        answer_card = execution["answer_card"]
        reply = (
            f"这轮更适合用{METHOD_LABELS[routing['selected_method']]}来处理。"
            f"就当前结果看，{answer_card['conclusion']} "
            f"你可以先按“{answer_card['action_advice'][0]}”落地，后续如果要继续细化，我会围绕 {answer_card['timing_hint']} 再追问。"
        )
        headline = answer_card["conclusion"]
    elif execution["status"] == "needs_input":
        reply = f"这轮已经分流到{METHOD_LABELS[routing['selected_method']]}，但还不能直接起测。先补齐关键信息后，我就继续往下算。"
        headline = execution["summary"]
    elif execution["status"] == "method-only":
        reply = f"如果只做分流，这题优先走{METHOD_LABELS[routing['selected_method']]}。原因是它最贴近你这一轮的核心目标。"
        headline = f"当前更适合用{METHOD_LABELS[routing['selected_method']]}。"
    elif execution["status"] == "adjacent-rewrite":
        reply = "这题本质上更像相邻体系问题，不建议硬套四术数。我已经给出可执行的改写方向。"
        headline = "这更像相邻体系的问题，不建议直接硬套四术数。"
    else:
        reply = "当前问题先不进入数术测算，应该先处理现实风险。"
        headline = "这类问题不适合直接当作数术测算题处理。"

    sections = build_final_response_sections(result)
    return {
        "status": execution["status"],
        "headline": headline,
        "reply": reply,
        "sections": sections,
        "text": render_final_response_text(headline, sections),
    }


def finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    result["final_response"] = build_final_response(result)
    return result


def render_text_report(result: dict[str, Any]) -> str:
    return result["final_response"]["text"]


def analyze_prompt(
    prompt: str,
    *,
    event_time: str | None = None,
    candidate_times: list[str] | None = None,
    numbers: list[int] | None = None,
    reference_time: str | None = None,
) -> dict[str, Any]:
    reference_dt = datetime.fromisoformat(reference_time) if reference_time else None
    normalized_prompt = normalize_whitespace(prompt)
    raw_parts = split_prompt(normalized_prompt) or [normalized_prompt]
    breakdown = [classify_sub_question(part, reference_dt) for part in raw_parts]
    supporting_fragments = [item["question"] for item in breakdown if item["bucket"] == "supporting"]
    primary_index, primary_item = choose_primary_sub_question(breakdown)
    if primary_item is None:
        primary_index, primary_item = 0, breakdown[0]

    explicit_event_time = normalize_datetime_text(event_time, reference_dt=reference_dt) if event_time else None
    explicit_candidate_times = normalize_candidate_times(candidate_times, reference_dt=reference_dt)
    explicit_numbers = list(numbers or [])
    overall_adjacent_system = detect_adjacent_system(normalized_prompt)

    merged_inputs = {
        "event_time": explicit_event_time or primary_item["recognized_inputs"].get("event_time"),
        "candidate_times": explicit_candidate_times or primary_item["recognized_inputs"].get("candidate_times", []),
        "candidate_slots": primary_item["recognized_inputs"].get("candidate_slots", []),
        "numbers": explicit_numbers or primary_item["recognized_inputs"].get("numbers", []),
        "roles": primary_item["recognized_inputs"].get("roles", []),
    }
    for item in breakdown:
        if item["bucket"] != "supporting":
            continue
        merged_inputs["numbers"] = (merged_inputs["numbers"] + item["recognized_inputs"].get("numbers", []))[:6]
        for key in ["candidate_slots", "roles"]:
            for value in item["recognized_inputs"].get(key, []):
                if value not in merged_inputs[key]:
                    merged_inputs[key].append(value)

    selected_method = primary_item["selected_method"]
    adjacent_system = primary_item["adjacent_system"]
    risks = list({flag for item in breakdown for flag in item["risk_flags"]})
    missing = missing_inputs(selected_method, merged_inputs)
    method_only = is_method_only_request(normalized_prompt)
    compound_summary = build_compound_summary(breakdown, primary_index, supporting_fragments)
    deferred_questions = [
        item["question"]
        for index, item in enumerate(breakdown)
        if index != primary_index and item["bucket"] == "executable"
    ]

    result: dict[str, Any] = {
        "input_prompt": normalized_prompt,
        "compound": len(raw_parts) > 1,
        "sub_questions": [item["question"] for item in breakdown],
        "risk_flags": risks,
        "method_only_request": method_only,
        "compound_analysis": {
            "primary_index": primary_index,
            "primary_question": primary_item["question"],
            "primary_bucket": primary_item["bucket"],
            "selection_reason": compound_summary["selection_logic"],
            "summary": compound_summary,
            "breakdown": [{key: value for key, value in item.items() if key != "priority"} for item in breakdown],
            "supporting_fragments": supporting_fragments,
            "deferred_questions": deferred_questions,
        },
        "routing": {
            "selected_method": selected_method,
            "adjacent_system": adjacent_system,
            "reason": f"问题目标与输入结构更贴近{METHOD_LABELS[selected_method]}。" if selected_method else "",
            "scores": primary_item["scores"],
            "normalized_question": primary_item["question"],
            "required_inputs": required_inputs(selected_method),
            "primary_question": primary_item["question"],
        },
        "execution": {
            "status": "pending",
            "normalized_question": primary_item["question"],
            "recognized_inputs": merged_inputs,
            "missing_inputs": missing,
            "framework": FRAMEWORKS.get(selected_method or "", "待判定"),
            "summary": "",
            "next_step": "",
            "deferred_questions": deferred_questions,
        },
    }

    if risks:
        result["execution"]["status"] = "high-risk"
        result["execution"]["summary"] = "当前问题涉及高风险主题，先不进入数术测算。"
        result["execution"]["next_step"] = "先处理现实安全与专业支持。"
        return finalize_result(result)

    if is_adjacent_dominant_prompt(normalized_prompt, breakdown, merged_inputs, overall_adjacent_system):
        result["routing"]["selected_method"] = None
        result["routing"]["adjacent_system"] = overall_adjacent_system
        result["routing"]["reason"] = f"原问题整体更接近{overall_adjacent_system}体系，本轮先不强行落到四术数执行。"
        result["execution"]["status"] = "adjacent-rewrite"
        result["execution"]["summary"] = "原问题整体仍以相邻体系为主，建议先改写后再进入四术数。"
        result["execution"]["next_step"] = "先抽出一个短期、单一、可验证的预测问题。"
        return finalize_result(result)

    if not selected_method and adjacent_system:
        result["execution"]["status"] = "adjacent-rewrite"
        result["execution"]["summary"] = "原问题更像相邻体系，建议先改写。"
        result["execution"]["next_step"] = "把问题缩成一个可执行的具体预测问题。"
        return finalize_result(result)

    if method_only and selected_method:
        result["execution"]["status"] = "method-only"
        result["execution"]["summary"] = f"当前更适合走{METHOD_LABELS[selected_method]}。"
        result["execution"]["next_step"] = "如果你愿意继续，我就按这个术数进入起测。"
        return finalize_result(result)

    try:
        if selected_method == "meihua":
            chosen_numbers, basis = choose_numbers(merged_inputs["numbers"], merged_inputs["event_time"])
            if not chosen_numbers or basis is None:
                result["execution"]["status"] = "needs_input"
                result["execution"]["summary"] = "梅花易数还不能直接起测。"
                result["execution"]["next_step"] = missing[0]
                return finalize_result(result)
            execution = build_meihua_reading(primary_item["question"], chosen_numbers, basis, merged_inputs["event_time"])
        elif selected_method == "liuyao":
            if missing:
                result["execution"]["status"] = "needs_input"
                result["execution"]["summary"] = "六爻还不能直接起卦。"
                result["execution"]["next_step"] = missing[0]
                return finalize_result(result)
            execution = compute_liuyao(merged_inputs["event_time"], primary_item["question"])
            execution["answer_card"] = execution["computed_payload"]["answer_card"]
            execution["computed_payload"]["interpretation"]["core"] = execution["computed_payload"]["interpretation"]["structured"]
        elif selected_method == "qimen":
            if missing:
                result["execution"]["status"] = "needs_input"
                result["execution"]["summary"] = "奇门还不能直接起盘。"
                result["execution"]["next_step"] = missing[0]
                return finalize_result(result)
            qimen_times = merged_inputs["candidate_times"] or ([merged_inputs["event_time"]] if merged_inputs["event_time"] else [])
            execution = compute_qimen(qimen_times, primary_item["question"])
            execution["answer_card"] = execution["computed_payload"]["answer_card"]
        elif selected_method == "liuren":
            if missing:
                result["execution"]["status"] = "needs_input"
                result["execution"]["summary"] = "大六壬还不能直接起课。"
                result["execution"]["next_step"] = missing[0]
                return finalize_result(result)
            execution = compute_liuren(merged_inputs["event_time"], primary_item["question"])
            execution["answer_card"] = execution["computed_payload"]["answer_card"]
        else:
            result["execution"]["status"] = "adjacent-rewrite"
            result["execution"]["summary"] = "这题暂时没有落到四术数可执行入口。"
            result["execution"]["next_step"] = "先把问题收缩成一个短期、单一、可验证的预测问题。"
            return finalize_result(result)
    except RuntimeDependencyError as exc:
        result["execution"]["status"] = "missing-runtime"
        result["execution"]["summary"] = f"当前环境缺少 {exc.dependency} 运行依赖，暂时不能继续起测。"
        result["execution"]["next_step"] = exc.install_hint
        result["execution"]["missing_dependency"] = {
            "name": exc.dependency,
            "detail": exc.detail,
            "install_hint": exc.install_hint,
        }
        return finalize_result(result)

    result["execution"].update(execution)
    result["execution"]["recognized_inputs"] = merged_inputs
    result["execution"]["missing_inputs"] = []
    result["execution"]["framework"] = FRAMEWORKS[selected_method]
    result["execution"]["deferred_questions"] = deferred_questions
    return finalize_result(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Shu-shu divination engine")
    parser.add_argument("--prompt", required=True, help="User prompt")
    parser.add_argument("--event-time", help="Explicit event time")
    parser.add_argument("--candidate-times", help="Comma-separated candidate times")
    parser.add_argument("--numbers", help="Comma-separated numbers for meihua")
    parser.add_argument("--reference-time", help="Reference time for resolving relative datetimes")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    candidate_times = [item.strip() for item in args.candidate_times.split(",")] if args.candidate_times else None
    numbers = [int(item.strip()) for item in args.numbers.split(",") if item.strip()] if args.numbers else None
    result = analyze_prompt(
        args.prompt,
        event_time=args.event_time,
        candidate_times=candidate_times,
        numbers=numbers,
        reference_time=args.reference_time,
    )
    if args.output == "text":
        sys.stdout.write(render_text_report(result))
    else:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
