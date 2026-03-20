#!/usr/bin/env python3
"""Native Liuyao provider based on local qigua and paipan logic."""

from __future__ import annotations

import itertools
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any

from engine_common import ensure_runtime_paths, split_iso_datetime


ensure_runtime_paths()

from kinqimen import config  # type: ignore  # noqa: E402


TRIGRAM_LINE_CODES = {
    1: "777",
    2: "778",
    3: "787",
    4: "788",
    5: "877",
    6: "878",
    7: "887",
    8: "888",
}

BRANCH_INDEX = dict(zip("子丑寅卯辰巳午未申酉戌亥", range(1, 13)))
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
LOCAL_DATA_FILE = SKILL_DIR / "assets" / "liuyao" / "data.pkl"


def _multi_key_dict_get(mapping: dict[Any, Any], key: Any) -> Any:
    for keys, value in mapping.items():
        if key in keys:
            return value
    return None


def _new_list(values: list[str], start: str) -> list[str]:
    index = values.index(start)
    return values[index:] + values[:index]


def _rotated_reverse_window(values: list[str], start: str, position: int) -> list[str]:
    full_reversed = list(reversed(_new_list(values, start)))
    if position == 5:
        return full_reversed[-6:]
    if position == 4:
        return full_reversed[-6:][1:] + [full_reversed[0]]
    if position == 3:
        return full_reversed[-6:][2:] + full_reversed[0:2]
    if position == 2:
        return full_reversed[-6:][3:] + full_reversed[0:3]
    if position == 1:
        return full_reversed[-6:][4:] + full_reversed[0:4]
    return _new_list(values, start)[0:6]


def _jiazi(tiangan: list[str], dizhi: list[str]) -> list[str]:
    return [tiangan[index % len(tiangan)] + dizhi[index % len(dizhi)] for index in range(60)]


def _chunked(values: list[str], chunk_size: int) -> list[list[str]]:
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


@lru_cache(maxsize=1)
def _assets() -> dict[str, Any]:
    with LOCAL_DATA_FILE.open("rb") as handle:
        data = pickle.load(handle)

    gua_names = data["八卦"]
    return {
        "data": data,
        "tiangan": data["干"],
        "dizhi": data["支"],
        "wuxing": data["五行"],
        "gua_names": gua_names,
        "gua_down_code": dict(zip(gua_names, data["下卦數"])),
        "gua_up_code": dict(zip(gua_names, data["上卦數"])),
        "findshiying": dict(zip(list(data["八宮卦"].values()), data["世應排法"])),
    }


def _stringify_line(line_parts: list[str]) -> str:
    return "".join(str(part) for part in line_parts)


def _find_six_mons(day_ganzhi: str) -> list[str]:
    mons = [item[1] for item in _assets()["data"]["六獸"]]
    start = _multi_key_dict_get(
        dict(zip([tuple(item) for item in "甲乙,丙丁,戊,己,庚辛,壬癸".split(",")], mons)),
        day_ganzhi[0],
    )
    return _new_list(mons, start)


def _compute_native_core(event_time: str) -> dict[str, Any]:
    year, month, day, hour, minute = split_iso_datetime(event_time)
    ganzhi = config.gangzhi(year, month, day, hour, minute)
    lunar = config.lunar_date_d(year, month, day)

    year_branch_code = BRANCH_INDEX[ganzhi[0][1]]
    hour_branch_code = BRANCH_INDEX[ganzhi[3][1]]
    lunar_month = int(lunar["月"])
    lunar_day = int(lunar["日"])

    upper_remainder = (year_branch_code + lunar_month + lunar_day + hour_branch_code) % 8 or 8
    lower_remainder = (year_branch_code + lunar_month + lunar_day) % 8 or 8
    upper_gua = TRIGRAM_LINE_CODES[upper_remainder]
    lower_gua = TRIGRAM_LINE_CODES[lower_remainder]

    line_chars = list(lower_gua + upper_gua)
    moving_line_index = (year_branch_code + lunar_month + lunar_day + hour_branch_code) % 6 or 6
    line_chars[moving_line_index - 1] = line_chars[moving_line_index - 1].replace("7", "9").replace("8", "6")
    line_code = "".join(line_chars)
    changed_code = line_code.replace("6", "7").replace("9", "8")

    return {
        "event_time": event_time,
        "ganzhi": f"{ganzhi[0]}年{ganzhi[1]}月{ganzhi[2]}日{ganzhi[3]}時",
        "day_ganzhi": ganzhi[2],
        "lunar_month": lunar_month,
        "lunar_day": lunar_day,
        "year_branch_code": year_branch_code,
        "hour_branch_code": hour_branch_code,
        "line_code": line_code,
        "changed_code": changed_code,
        "moving_line_index": moving_line_index,
    }


def _decode_gua(gua_code: str, day_ganzhi: str) -> dict[str, Any]:
    assets = _assets()
    data = assets["data"]
    tiangan = assets["tiangan"]
    dizhi = assets["dizhi"]
    wuxing = assets["wuxing"]

    fivestars = data["五星"]
    eightgua = data["數字排八卦"]
    sixtyfourgua = data["數字排六十四卦"]
    su_yao = data["二十八宿配干支"]
    shiying = _multi_key_dict_get(data["八宮卦"], _multi_key_dict_get(sixtyfourgua, gua_code))
    shiying_marks = list(assets["findshiying"][shiying])

    down_gua = assets["gua_down_code"][_multi_key_dict_get(eightgua, gua_code[0:3])]
    up_gua = assets["gua_up_code"][_multi_key_dict_get(eightgua, gua_code[3:6])]

    dt = [tiangan[int(item[0])] for item in [line.split(",") for line in down_gua[0:3]]]
    dd = [dizhi[int(item[1])] for item in [line.split(",") for line in down_gua[0:3]]]
    dw = [wuxing[int(item[2])] for item in [line.split(",") for line in down_gua[0:3]]]
    ut = [tiangan[int(item[0])] for item in [line.split(",") for line in up_gua[0:3]]]
    ud = [dizhi[int(item[1])] for item in [line.split(",") for line in up_gua[0:3]]]
    uw = [wuxing[int(item[2])] for item in [line.split(",") for line in up_gua[0:3]]]

    t = dt + ut
    d = dd + ud
    w = dw + uw

    gua_name = _multi_key_dict_get(sixtyfourgua, gua_code)
    find_gua_wuxing = _multi_key_dict_get(data["八宮卦五行"], gua_name)
    liuqin = [item[0] for item in data["六親"]]
    lq = [_multi_key_dict_get(data["六親五行"], item + find_gua_wuxing) for item in w]

    sixtyfour_gua_index = data["六十四卦"]
    find_su = dict(zip(sixtyfour_gua_index, itertools.cycle(_new_list(data["二十八宿"], "參"))))[gua_name]
    sy = dict(zip(sixtyfour_gua_index, su_yao))[gua_name]
    ng = [t[index] + d[index] for index in range(6)]
    sy2 = [candidate == sy for candidate in ng]
    sy3 = [str(item).replace("False", "").replace("True", find_su) for item in sy2]
    ss = dict(zip(sixtyfour_gua_index, itertools.cycle(_new_list(fivestars, "鎮星"))))[gua_name]
    position = sy3.index(find_su)
    g = _rotated_reverse_window(data["二十八宿"], find_su, position)

    build_month_code = dict(zip(data["六十四卦"], data["月建"]))[gua_name]
    build_month = _new_list(_jiazi(tiangan, dizhi), build_month_code)[0:6]
    accumulate_code = dict(zip(data["六十四卦"], data["積算"]))[gua_name]
    accumulate = _new_list(_jiazi(tiangan, dizhi), accumulate_code)

    fu = str(str([value for value in liuqin if value not in list(set(lq))]).replace("['", "").replace("']", ""))
    fu_gua = _dc_gua(_multi_key_dict_get(data["八宮卦純卦"], gua_name))
    fu_gua_lq = fu_gua["六親用神"]
    shen = _multi_key_dict_get(data["世身"], d[shiying_marks.index("世")])

    try:
        fu_num = fu_gua_lq.index(fu)
        fuyao = [str(item == fu) for item in fu_gua_lq].index("True")
        fuyao1 = (
            fu_gua_lq[fu_num]
            + fu_gua["天干"][fu_num]
            + fu_gua["地支"][fu_num]
            + fu_gua["五行"][fu_num]
        )
        fu_yao = {
            "伏神所在爻": lq[fuyao],
            "伏神六親": fu,
            "伏神排爻數字": fu_num,
            "本卦伏神所在爻": lq[fu_num] + t[fu_num] + d[fu_num] + w[fu_num],
            "伏神爻": fuyao1,
        }
    except (ValueError, IndexError, AttributeError):
        fu_yao = ""

    return {
        "卦": gua_name,
        "五星": ss,
        "世應卦": f"{shiying}卦",
        "星宿": g,
        "天干": t,
        "地支": d,
        "五行": w,
        "世應爻": shiying_marks,
        "身爻": lq[shen] + t[shen] + d[shen] + w[shen],
        "六親用神": lq,
        "伏神": fu_yao,
        "六獸": _find_six_mons(day_ganzhi),
        "納甲": ng,
        "建月": build_month,
        "積算": _chunked(accumulate, 6),
    }


def _dc_gua(gua_code: str) -> dict[str, Any]:
    assets = _assets()
    data = assets["data"]
    tiangan = assets["tiangan"]
    dizhi = assets["dizhi"]
    wuxing = assets["wuxing"]

    fivestars = data["五星"]
    eightgua = data["數字排八卦"]
    sixtyfourgua = data["數字排六十四卦"]
    su_yao = data["二十八宿配干支"]
    shiying = _multi_key_dict_get(data["八宮卦"], _multi_key_dict_get(sixtyfourgua, gua_code))
    shiying_marks = list(assets["findshiying"][shiying])

    down_gua = assets["gua_down_code"][_multi_key_dict_get(eightgua, gua_code[0:3])]
    up_gua = assets["gua_up_code"][_multi_key_dict_get(eightgua, gua_code[3:6])]

    dt = [tiangan[int(item[0])] for item in [line.split(",") for line in down_gua[0:3]]]
    dd = [dizhi[int(item[1])] for item in [line.split(",") for line in down_gua[0:3]]]
    dw = [wuxing[int(item[2])] for item in [line.split(",") for line in down_gua[0:3]]]
    ut = [tiangan[int(item[0])] for item in [line.split(",") for line in up_gua[0:3]]]
    ud = [dizhi[int(item[1])] for item in [line.split(",") for line in up_gua[0:3]]]
    uw = [wuxing[int(item[2])] for item in [line.split(",") for line in up_gua[0:3]]]

    t = dt + ut
    d = dd + ud
    w = dw + uw

    gua_name = _multi_key_dict_get(sixtyfourgua, gua_code)
    find_gua_wuxing = _multi_key_dict_get(data["八宮卦五行"], gua_name)
    lq = [_multi_key_dict_get(data["六親五行"], item + find_gua_wuxing) for item in w]

    sixtyfour_gua_index = data["六十四卦"]
    find_su = dict(zip(sixtyfour_gua_index, itertools.cycle(_new_list(data["二十八宿"], "參"))))[gua_name]
    sy = dict(zip(sixtyfour_gua_index, su_yao))[gua_name]
    ng = [t[index] + d[index] for index in range(6)]
    sy2 = [candidate == sy for candidate in ng]
    sy3 = [str(item).replace("False", "").replace("True", find_su) for item in sy2]
    ss = dict(zip(sixtyfour_gua_index, itertools.cycle(_new_list(fivestars, "鎮星"))))[gua_name]
    position = sy3.index(find_su)
    g = _rotated_reverse_window(data["二十八宿"], find_su, position)

    build_month_code = dict(zip(data["六十四卦"], data["月建"]))[gua_name]
    build_month = _new_list(_jiazi(tiangan, dizhi), build_month_code)[0:6]
    accumulate_code = dict(zip(data["六十四卦"], data["積算"]))[gua_name]
    accumulate = _new_list(_jiazi(tiangan, dizhi), accumulate_code)

    return {
        "卦": gua_name,
        "五星": ss,
        "世應卦": f"{shiying}卦",
        "星宿": g,
        "天干": t,
        "地支": d,
        "五行": w,
        "世應": shiying_marks,
        "六親用神": lq,
        "納甲": ng,
        "建月": build_month,
        "積算": _chunked(accumulate, 6),
    }


def _decode_two_gua(main_code: str, changed_code: str, day_ganzhi: str) -> dict[str, Any]:
    main = _decode_gua(main_code, day_ganzhi)
    changed = _decode_gua(changed_code, day_ganzhi)
    return {
        "本卦": main,
        "之卦": changed,
        "飛神": "",
    }


def _mget_bookgua_details(line_code: str) -> list[Any]:
    data = _assets()["data"]
    sixtyfourgua = data["數字排六十四卦"]
    gua_name = _multi_key_dict_get(sixtyfourgua, line_code)
    yao_results = data["易經卦爻詳解"][gua_name]
    moving_mask = line_code.replace("6", "1").replace("9", "1").replace("7", "0").replace("8", "0")
    moving_count = moving_mask.count("1")
    explanation = f"動爻有【{moving_count}】根。"
    changed_code = line_code.replace("6", "7").replace("9", "8")
    changed_name = _multi_key_dict_get(sixtyfourgua, changed_code)
    changed_results = data["易經卦爻詳解"][changed_name]
    pair_name = f"【{gua_name}之{changed_name}】"
    top_bian = moving_mask.rfind("1") + 1
    second_bian = moving_mask.rfind("1", 0, moving_mask.rfind("1")) + 1
    top_static = moving_mask.rfind("0") + 1
    second_static = moving_mask.rfind("0", 0, moving_mask.rfind("0")) + 1
    top = yao_results.get(top_bian)
    second = yao_results.get(second_bian)

    explanation2 = None
    try:
        if moving_count == 0:
            explanation2 = (explanation, f"主要看【{gua_name}】卦彖辭。", yao_results[7][2:])
        elif moving_count == 1:
            explanation2 = (explanation, pair_name, f"主要看【{top[:2]}】", top)
        elif moving_count == 2:
            explanation2 = (pair_name, explanation, f"主要看【{top[:2]}】，其次看【{second[:2]}】。", top, second)
        elif moving_count == 3:
            if moving_mask.find("1") == 0:
                explanation2 = (
                    pair_name,
                    explanation,
                    f"【{gua_name}】卦為貞(我方)，【{changed_name}】卦為悔(他方)。前十卦，主貞【{gua_name}】卦，請參考兩卦彖辭",
                    yao_results[7][2:],
                    changed_results[7][2:],
                )
            else:
                explanation2 = (
                    pair_name,
                    explanation,
                    f"【{gua_name}】卦為貞(我方)，【{changed_name}】卦為悔(他方)。後十卦，主悔【{changed_name}】卦，請參考兩卦彖辭",
                    changed_results[7][2:],
                    yao_results[7][2:],
                )
        elif moving_count == 4:
            explanation2 = (
                pair_name,
                explanation,
                f"主要看【{changed_name}】的{changed_results.get(second_static)[:2]}，其次看{changed_results.get(top_static)[:2]}。",
                changed_results.get(second_static),
                changed_results.get(top_static),
            )
        elif moving_count == 5:
            explanation2 = (
                pair_name,
                explanation,
                f"主要看【{changed_name}】的{changed_results.get(top_static)[:2]}。",
                changed_results.get(top_static),
            )
        elif moving_count == 6:
            explanation2 = (pair_name, explanation, f"主要看【{changed_name}】卦的彖辭。", changed_results[7][2:])
    except (TypeError, UnboundLocalError):
        explanation2 = None

    return [line_code, gua_name, changed_name, yao_results, explanation2]


def describe_provider() -> dict[str, Any]:
    return {
        "name": "native",
        "ready": True,
        "implementation": "internal-native",
        "library": "shu-shu-divination-engine",
        "entrypoint": "native_time_qigua",
        "coverage": [
            "native time-based qigua",
            "native board details",
            "native text and focus selection",
            "native main and changed hexagrams",
        ],
        "notes": [
            "当前 native provider 已自行完成起卦、排本卦之卦、动爻说明与基础盘面结构。",
            "六爻静态数据已内置到仓库，默认运行只依赖仓库内资产与当前运行时依赖。",
        ],
    }


def load_reading(event_time: str) -> dict[str, Any]:
    native_core = _compute_native_core(event_time)
    details = _decode_two_gua(native_core["line_code"], native_core["changed_code"], native_core["day_ganzhi"])
    return {
        "provider": describe_provider(),
        "reading": {
            "日期": native_core["ganzhi"],
            "大衍筮法": _mget_bookgua_details(native_core["line_code"]),
            **details,
        },
        "native_core": {
            **native_core,
            "data_source": str(LOCAL_DATA_FILE.relative_to(SKILL_DIR)).replace("\\", "/"),
            "legacy_enrichment": [],
        },
    }
