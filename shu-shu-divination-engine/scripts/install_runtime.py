#!/usr/bin/env python3
"""Install runtime dependencies for shu-shu-divination-engine."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REQUIREMENTS_FILE = SKILL_DIR / "requirements.txt"


def run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False, text=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def verify_imports() -> None:
    checks = {
        "cn2an": "cn2an",
        "ephem": "ephem",
        "kinliuren": "kinliuren",
        "kinqimen": "kinqimen",
        "numpy": "numpy",
        "proces": "proces",
        "sxtwl": "sxtwl",
    }
    missing: list[str] = []
    for package, module_name in checks.items():
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing.append(package)
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"runtime dependencies installed incompletely, missing imports: {names}")


def main() -> int:
    if not REQUIREMENTS_FILE.exists():
        raise SystemExit(f"missing requirements file: {REQUIREMENTS_FILE}")

    run([sys.executable, "-m", "ensurepip", "--upgrade"])
    run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)])
    run([sys.executable, "-m", "pip", "install", "--no-deps", "kinqimen==0.0.6.6"])
    verify_imports()
    print("runtime dependencies installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
