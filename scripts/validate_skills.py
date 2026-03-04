#!/usr/bin/env python3
"""Validate skill-hub repository structure and core skill metadata."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


INFRA_DIRS = {".git", ".github", "scripts", "__pycache__"}
REQUIRED_FRONTMATTER_KEYS = {"name", "description"}
REQUIRED_OPENAI_KEYS = {
    "interface:",
    "display_name:",
    "short_description:",
    "default_prompt:",
}


@dataclass
class ValidationResult:
    errors: List[str]
    warnings: List[str]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def has_utf8_bom(path: Path) -> bool:
    raw = path.read_bytes()
    return raw.startswith(b"\xef\xbb\xbf")


def load_json(path: Path) -> dict:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} JSON 格式错误: {exc}") from exc


def parse_frontmatter(skill_md_path: Path) -> dict[str, str]:
    content = read_text(skill_md_path)
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, flags=re.DOTALL)
    if not match:
        raise ValueError("SKILL.md 缺少 YAML frontmatter")

    frontmatter: dict[str, str] = {}
    body = match.group(1)
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            continue
        frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    return frontmatter


def discover_skill_dirs(repo_root: Path) -> List[Path]:
    skill_dirs: List[Path] = []

    skills_dir = repo_root / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                skill_dirs.append(child)

    for child in sorted(repo_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name in INFRA_DIRS or child.name == "skills":
            continue
        if (child / "SKILL.md").exists():
            skill_dirs.append(child)
    return skill_dirs


def validate_openai_yaml(skill_dir: Path, skill_name: str, result: ValidationResult) -> None:
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        result.warnings.append(f"{skill_dir.name}: 未找到 agents/openai.yaml（可选）")
        return

    if has_utf8_bom(openai_yaml):
        result.errors.append(f"{skill_dir.name}: agents/openai.yaml 存在 UTF-8 BOM")

    content = read_text(openai_yaml)
    for key in REQUIRED_OPENAI_KEYS:
        if key not in content:
            result.errors.append(f"{skill_dir.name}: agents/openai.yaml 缺少字段 {key}")

    expected_token = f"${skill_name}"
    if expected_token not in content:
        result.warnings.append(
            f"{skill_dir.name}: agents/openai.yaml default_prompt 未包含 {expected_token}"
        )


def validate_version_file(skill_dir: Path, result: ValidationResult) -> str:
    version_file = skill_dir / "VERSION"
    routing_rules = skill_dir / "references" / "routing-rules.json"

    if not version_file.exists():
        result.errors.append(f"{skill_dir.name}: 缺少 VERSION 文件")
        return ""

    version = read_text(version_file).strip()
    if not version:
        result.errors.append(f"{skill_dir.name}: VERSION 文件为空")
        return ""

    if routing_rules.exists():
        try:
            data = load_json(routing_rules)
        except ValueError as exc:
            result.errors.append(f"{skill_dir.name}: {exc}")
            return version
        rules_version = str(data.get("meta", {}).get("version", "")).strip()
        if rules_version and rules_version != version:
            result.errors.append(
                f"{skill_dir.name}: VERSION({version}) 与 routing-rules.json({rules_version}) 不一致"
            )
    return version


def validate_skills_index(
    repo_root: Path,
    skill_dirs: List[Path],
    versions: dict[str, str],
    result: ValidationResult,
) -> None:
    index_file = repo_root / "skills-index.json"
    if not index_file.exists():
        result.errors.append("仓库根目录缺少 skills-index.json")
        return

    try:
        data = load_json(index_file)
    except ValueError as exc:
        result.errors.append(str(exc))
        return

    records = data.get("skills", [])
    if not isinstance(records, list):
        result.errors.append("skills-index.json 的 skills 字段必须是数组")
        return

    record_map = {str(item.get("id", "")).strip(): item for item in records}
    for skill_dir in skill_dirs:
        skill_id = skill_dir.name
        if skill_id not in record_map:
            result.errors.append(f"skills-index.json 缺少技能记录: {skill_id}")
            continue

        record = record_map[skill_id]
        record_version = str(record.get("version", "")).strip()
        current_version = versions.get(skill_id, "")
        if current_version and record_version != current_version:
            result.errors.append(
                f"skills-index.json 技能 {skill_id} 版本({record_version}) 与 VERSION({current_version}) 不一致"
            )

        path_value = str(record.get("path", "")).strip()
        if path_value != skill_id:
            result.errors.append(
                f"skills-index.json 技能 {skill_id} 的 path({path_value}) 应为 {skill_id}"
            )


def validate_skill_dir(skill_dir: Path, result: ValidationResult) -> str:
    skill_md = skill_dir / "SKILL.md"
    if has_utf8_bom(skill_md):
        result.errors.append(f"{skill_dir.name}: SKILL.md 存在 UTF-8 BOM")

    try:
        frontmatter = parse_frontmatter(skill_md)
    except ValueError as exc:
        result.errors.append(f"{skill_dir.name}: {exc}")
        return ""

    missing = REQUIRED_FRONTMATTER_KEYS - set(frontmatter)
    if missing:
        result.errors.append(f"{skill_dir.name}: SKILL.md frontmatter 缺少字段 {sorted(missing)}")

    skill_name = frontmatter.get("name", "").strip()
    if not skill_name:
        result.errors.append(f"{skill_dir.name}: SKILL.md frontmatter.name 为空")
        return ""

    if skill_name != skill_dir.name:
        result.errors.append(
            f"{skill_dir.name}: frontmatter.name({skill_name}) 与目录名不一致"
        )

    validate_openai_yaml(skill_dir, skill_name, result)
    return validate_version_file(skill_dir, result)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    result = ValidationResult(errors=[], warnings=[])
    versions: dict[str, str] = {}

    skill_dirs = discover_skill_dirs(repo_root)
    if not skill_dirs:
        result.errors.append("未发现任何技能目录（需要目录下存在 SKILL.md）")
    else:
        for skill_dir in skill_dirs:
            versions[skill_dir.name] = validate_skill_dir(skill_dir, result)
        validate_skills_index(repo_root, skill_dirs, versions, result)

    if result.errors:
        print("校验失败：")
        for item in result.errors:
            print(f"- {item}")
        if result.warnings:
            print("警告：")
            for item in result.warnings:
                print(f"- {item}")
        return 1

    print(f"校验通过，共检查技能 {len(skill_dirs)} 个。")
    if result.warnings:
        print("警告：")
        for item in result.warnings:
            print(f"- {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
