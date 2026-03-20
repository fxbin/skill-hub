#!/usr/bin/env python3
"""Shared helpers for the deterministic divination adapters."""

from __future__ import annotations

import importlib.util
import importlib
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
KINQIMEN_INSTALL_HINT = "请先在虚拟环境中运行 `python scripts/install_runtime.py` 安装 kinqimen 运行依赖。"
KINLIUREN_INSTALL_HINT = "请先在虚拟环境中运行 `python scripts/install_runtime.py` 安装 kinliuren 与 kinqimen 运行依赖。"

PALACE_DIRECTIONS = {
    "乾": "西北",
    "兑": "正西",
    "兌": "正西",
    "離": "正南",
    "离": "正南",
    "震": "正东",
    "巽": "东南",
    "坎": "正北",
    "艮": "东北",
    "坤": "西南",
    "中": "中宫",
}

RELATIVE_DAY_OFFSETS = {
    "今天": 0,
    "今日": 0,
    "明天": 1,
    "明日": 1,
    "后天": 2,
    "昨天": -1,
    "昨日": -1,
    "今晚": 0,
    "今早": 0,
    "今晨": 0,
    "明晚": 1,
    "明早": 1,
}

RELATIVE_DEFAULT_MERIDIEM = {
    "今晚": "晚上",
    "今早": "早上",
    "今晨": "早上",
    "明晚": "晚上",
    "明早": "早上",
}


class RuntimeDependencyError(RuntimeError):
    """Raised when a deterministic adapter is missing a required runtime dependency."""

    def __init__(self, dependency: str, install_hint: str, detail: str | None = None) -> None:
        message = detail or f"missing runtime dependency: {dependency}"
        super().__init__(message)
        self.dependency = dependency
        self.install_hint = install_hint
        self.detail = detail or ""

def _alias_kinqimen_config() -> None:
    if "config" in sys.modules:
        return
    try:
        spec = importlib.util.find_spec("kinqimen.config")
    except ModuleNotFoundError:
        return
    if spec is None:
        return
    module = importlib.import_module("kinqimen.config")
    sys.modules["config"] = module


def ensure_runtime_paths() -> None:
    """Prepare installed-package runtime aliases."""
    # kinqimen upstream uses bare `import config`; map it explicitly to the
    # installed package submodule so we do not need ad-hoc sys.path hacks.
    _alias_kinqimen_config()


def _load_module(module_name: str, *, dependency: str, install_hint: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name not in {module_name, dependency, "config"} and not str(exc.name).startswith(f"{dependency}."):
            raise
        raise RuntimeDependencyError(
            dependency,
            install_hint,
            f"缺少运行依赖 {dependency}，当前无法加载 {module_name}。",
        ) from exc


def load_kinqimen_config():
    """Load kinqimen config lazily so the whole engine does not fail at import time."""
    ensure_runtime_paths()
    return _load_module("kinqimen.config", dependency="kinqimen", install_hint=KINQIMEN_INSTALL_HINT)


def load_qimen_class():
    """Load the kinqimen Qimen class lazily."""
    ensure_runtime_paths()
    module = _load_module("kinqimen.kinqimen", dependency="kinqimen", install_hint=KINQIMEN_INSTALL_HINT)
    return module.Qimen


def load_liuren_class():
    """Load the kinliuren Liuren class lazily."""
    module = _load_module("kinliuren.kinliuren", dependency="kinliuren", install_hint=KINLIUREN_INSTALL_HINT)
    return module.Liuren


def apply_meridiem(hour: int, meridiem: str | None) -> int:
    """Convert a Chinese meridiem phrase into a 24-hour clock value."""
    if not meridiem:
        return hour
    if meridiem in {"下午", "晚上"} and hour < 12:
        return hour + 12
    if meridiem == "中午":
        if hour == 0:
            return 12
        if 1 <= hour < 11:
            return hour + 12
    if meridiem == "凌晨" and hour == 12:
        return 0
    return hour


def normalize_datetime_text(value: str, reference_dt: datetime | None = None) -> str | None:
    """Normalize common absolute and relative datetime formats into ISO text."""
    cleaned = value.strip()
    if not cleaned:
        return None
    anchor = reference_dt or datetime.now()

    try:
        direct = cleaned.replace("Z", "")
        if len(direct) == 16:
            return datetime.fromisoformat(direct).strftime("%Y-%m-%dT%H:%M:%S")
        return datetime.fromisoformat(direct).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass

    iso_like = re.search(
        r"(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})[ T]"
        r"(?P<hour>\d{1,2}):(?P<minute>\d{1,2})(?::(?P<second>\d{1,2}))?",
        cleaned,
    )
    if iso_like:
        dt = datetime(
            int(iso_like.group("year")),
            int(iso_like.group("month")),
            int(iso_like.group("day")),
            int(iso_like.group("hour")),
            int(iso_like.group("minute")),
            int(iso_like.group("second") or 0),
        )
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    chinese = re.search(
        r"(?P<year>\d{4})年\s*(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日?"
        r"\s*(?:(?P<ampm>凌晨|上午|早上|中午|下午|晚上))?"
        r"\s*(?P<hour>\d{1,2})(?:[:点时](?P<minute>\d{1,2}))?(?:分)?",
        cleaned,
    )
    if chinese:
        hour = apply_meridiem(int(chinese.group("hour")), chinese.group("ampm"))
        minute = int(chinese.group("minute") or 0)
        dt = datetime(
            int(chinese.group("year")),
            int(chinese.group("month")),
            int(chinese.group("day")),
            hour,
            minute,
            0,
        )
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    relative = re.search(
        r"(?P<relative>今天|今日|明天|明日|后天|昨天|昨日|今晚|今早|今晨|明晚|明早)"
        r"\s*(?:(?P<ampm>凌晨|上午|早上|中午|下午|晚上))?"
        r"\s*(?P<hour>\d{1,2})(?:[:点时](?P<minute>\d{1,2}))?(?:分)?",
        cleaned,
    )
    if relative:
        day_token = relative.group("relative")
        base = anchor + timedelta(days=RELATIVE_DAY_OFFSETS[day_token])
        meridiem = relative.group("ampm") or RELATIVE_DEFAULT_MERIDIEM.get(day_token)
        hour = apply_meridiem(int(relative.group("hour")), meridiem)
        minute = int(relative.group("minute") or 0)
        dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    return None


def extract_explicit_datetimes(text: str, reference_dt: datetime | None = None) -> list[str]:
    """Extract unique absolute and relative datetimes from prompt text."""
    patterns = [
        re.compile(
            r"(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})[ T]"
            r"(?P<hour>\d{1,2}):(?P<minute>\d{1,2})(?::(?P<second>\d{1,2}))?"
        ),
        re.compile(
            r"(?P<year>\d{4})年\s*(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日?"
            r"\s*(?:(?P<ampm>凌晨|上午|早上|中午|下午|晚上))?"
            r"\s*(?P<hour>\d{1,2})(?:[:点时](?P<minute>\d{1,2}))?(?:分)?"
        ),
        re.compile(
            r"(?P<relative>今天|今日|明天|明日|后天|昨天|昨日|今晚|今早|今晨|明晚|明早)"
            r"\s*(?:(?P<ampm>凌晨|上午|早上|中午|下午|晚上))?"
            r"\s*(?P<hour>\d{1,2})(?:[:点时](?P<minute>\d{1,2}))?(?:分)?"
        ),
    ]

    seen: set[str] = set()
    results: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = normalize_datetime_text(match.group(0), reference_dt=reference_dt)
            if value and value not in seen:
                seen.add(value)
                results.append(value)
    return results


def normalize_candidate_times(values: list[str] | None, reference_dt: datetime | None = None) -> list[str]:
    """Normalize explicit candidate timestamps while keeping valid entries only."""
    normalized: list[str] = []
    for item in values or []:
        value = normalize_datetime_text(item, reference_dt=reference_dt)
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def split_iso_datetime(value: str) -> tuple[int, int, int, int, int]:
    """Convert a normalized ISO string into integer datetime parts."""
    dt = datetime.fromisoformat(value)
    return dt.year, dt.month, dt.day, dt.hour, dt.minute
