#!/usr/bin/env python3
"""Validate skill-hub repository structure and core skill metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


INFRA_DIRS = {".git", ".github", "scripts", "__pycache__"}
NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
RELATIVE_REF_PATTERN = re.compile(r"`((?:references|scripts|assets|agents)/[^`\n]+|VERSION)`")
README_SKILL_ROW_PATTERN = re.compile(
    r"^\|\s*`(?P<id>[^`]+)`\s*\|\s*(?P<name>[^|]+?)\s*\|\s*`(?P<version>[^`]+)`\s*\|\s*`(?P<path>[^`]+)`\s*\|",
    flags=re.MULTILINE,
)
DEFAULT_CONFIG = {
    "required_frontmatter_keys": ["name", "description"],
    "allowed_frontmatter_keys": ["name", "description", "metadata", "allowed-tools", "license"],
    "required_openai_fields": ["display_name", "short_description", "default_prompt"],
    "require_openai_yaml": False,
    "require_version_file": True,
    "require_skills_index": True,
    "short_description_min": 25,
    "short_description_max": 64,
    "max_name_length": 64,
    "max_description_length": 1024,
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


def load_config(config_path: str | None) -> dict:
    config = dict(DEFAULT_CONFIG)
    if not config_path:
        return config
    path = Path(config_path).resolve()
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a JSON object")
    config.update(data)
    return config


def parse_frontmatter(skill_md_path: Path) -> dict[str, str]:
    content = read_text(skill_md_path)
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, flags=re.DOTALL)
    if not match:
        raise ValueError("SKILL.md 缺少 YAML frontmatter")

    frontmatter: dict[str, str] = {}
    body = match.group(1)
    for line in body.splitlines():
        # 只解析顶层 key，忽略缩进的嵌套字段（如 metadata.short-description）
        if line.startswith(" ") or line.startswith("\t"):
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            continue
        frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    return frontmatter


def extract_yaml_scalar(content: str, key: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*:\s*(.*?)\s*$", content)
    if not match:
        return ""
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def find_relative_refs(content: str) -> list[str]:
    return [match.group(1).strip() for match in RELATIVE_REF_PATTERN.finditer(content)]


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


def validate_openai_yaml(skill_dir: Path, skill_name: str, config: dict, result: ValidationResult) -> None:
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        if config.get("require_openai_yaml"):
            result.errors.append(f"{skill_dir.name}: 缺少 agents/openai.yaml")
        else:
            result.warnings.append(f"{skill_dir.name}: 未找到 agents/openai.yaml（可选）")
        return

    if has_utf8_bom(openai_yaml):
        result.errors.append(f"{skill_dir.name}: agents/openai.yaml 存在 UTF-8 BOM")

    content = read_text(openai_yaml)
    if "interface:" not in content:
        result.errors.append(f"{skill_dir.name}: agents/openai.yaml 缺少 interface 节点")
        return

    values = {
        field: extract_yaml_scalar(content, field) for field in set(config["required_openai_fields"])
    }
    for field, value in values.items():
        if not value:
            result.errors.append(f"{skill_dir.name}: agents/openai.yaml 缺少字段 {field}")

    short_description = values.get("short_description", "")
    min_len = int(config["short_description_min"])
    max_len = int(config["short_description_max"])
    if short_description and not (min_len <= len(short_description) <= max_len):
        result.warnings.append(
            f"{skill_dir.name}: short_description 长度为 {len(short_description)}，建议 {min_len}-{max_len} 字符"
        )

    expected_token = f"${skill_name}"
    default_prompt = values.get("default_prompt", "")
    if default_prompt and expected_token not in default_prompt:
        result.warnings.append(
            f"{skill_dir.name}: agents/openai.yaml default_prompt 未包含 {expected_token}"
        )


def read_openai_interface(skill_dir: Path) -> dict[str, str]:
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        return {}
    content = read_text(openai_yaml)
    if "interface:" not in content:
        return {}
    return {
        "display_name": extract_yaml_scalar(content, "display_name"),
        "short_description": extract_yaml_scalar(content, "short_description"),
        "default_prompt": extract_yaml_scalar(content, "default_prompt"),
    }


def validate_skill_references(skill_dir: Path, result: ValidationResult) -> None:
    skill_md = skill_dir / "SKILL.md"
    content = read_text(skill_md)
    refs = find_relative_refs(content)
    for rel in refs:
        target = skill_dir / rel
        if not target.exists():
            result.errors.append(f"{skill_dir.name}: SKILL.md 引用了不存在的路径 {rel}")


def validate_script_test_coverage(skill_dir: Path, result: ValidationResult) -> None:
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return

    scripts = [path for path in scripts_dir.rglob("*") if path.is_file()]
    executable_scripts = [path for path in scripts if path.suffix in {".py", ".sh", ".js"}]
    if len(executable_scripts) == 0:
        return

    tests_dir = skill_dir / "tests"
    if not tests_dir.is_dir():
        result.warnings.append(f"{skill_dir.name}: 存在 scripts/ 但未提供 tests/ 覆盖")
        return

    test_files = [path for path in tests_dir.rglob("test_*.py") if path.is_file()]
    if len(test_files) == 0:
        result.warnings.append(f"{skill_dir.name}: 存在 scripts/ 但 tests/ 下未发现 test_*.py")


def read_readme_skill_rows(repo_root: Path) -> dict[str, dict[str, str]]:
    readme = repo_root / "README.md"
    if not readme.exists():
        return {}
    content = read_text(readme)
    rows: dict[str, dict[str, str]] = {}
    for match in README_SKILL_ROW_PATTERN.finditer(content):
        skill_id = match.group("id").strip()
        rows[skill_id] = {
            "display_name": match.group("name").strip(),
            "version": match.group("version").strip(),
            "path": match.group("path").strip(),
        }
    return rows


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
    config: dict,
    result: ValidationResult,
) -> None:
    index_file = repo_root / "skills-index.json"
    if not index_file.exists():
        if config.get("require_skills_index"):
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
        if config.get("require_version_file") and current_version and record_version != current_version:
            result.errors.append(
                f"skills-index.json 技能 {skill_id} 版本({record_version}) 与 VERSION({current_version}) 不一致"
            )

        path_value = str(record.get("path", "")).strip()
        if path_value != skill_id:
            result.errors.append(
                f"skills-index.json 技能 {skill_id} 的 path({path_value}) 应为 {skill_id}"
            )

        interface = read_openai_interface(skill_dir)
        record_display_name = str(record.get("display_name", "")).strip()
        if interface.get("display_name") and record_display_name != interface["display_name"]:
            result.errors.append(
                f"skills-index.json 技能 {skill_id} 的 display_name({record_display_name})"
                f" 与 agents/openai.yaml({interface['display_name']}) 不一致"
            )

        record_prompt = str(record.get("default_prompt", "")).strip()
        if interface.get("default_prompt") and record_prompt != interface["default_prompt"]:
            result.errors.append(
                f"skills-index.json 技能 {skill_id} 的 default_prompt 与 agents/openai.yaml 不一致"
            )


def validate_readme_index(
    repo_root: Path,
    skill_dirs: List[Path],
    versions: dict[str, str],
    result: ValidationResult,
) -> None:
    readme = repo_root / "README.md"
    if not readme.exists():
        result.errors.append("仓库根目录缺少 README.md")
        return

    rows = read_readme_skill_rows(repo_root)
    for skill_dir in skill_dirs:
        skill_id = skill_dir.name
        if skill_id not in rows:
            result.errors.append(f"README.md 缺少技能表格记录: {skill_id}")
            continue

        row = rows[skill_id]
        expected_version = versions.get(skill_id, "")
        if expected_version and row["version"] != expected_version:
            result.errors.append(
                f"README.md 技能 {skill_id} 版本({row['version']}) 与 VERSION({expected_version}) 不一致"
            )
        if row["path"] != f"{skill_id}/":
            result.errors.append(
                f"README.md 技能 {skill_id} 的路径({row['path']}) 应为 {skill_id}/"
            )
        interface = read_openai_interface(skill_dir)
        display_name = interface.get("display_name", "").strip()
        if display_name and row["display_name"] != display_name:
            result.errors.append(
                f"README.md 技能 {skill_id} 的名称({row['display_name']})"
                f" 与 agents/openai.yaml({display_name}) 不一致"
            )


def validate_skill_dir(skill_dir: Path, config: dict, result: ValidationResult) -> str:
    skill_md = skill_dir / "SKILL.md"
    if has_utf8_bom(skill_md):
        result.errors.append(f"{skill_dir.name}: SKILL.md 存在 UTF-8 BOM")

    try:
        frontmatter = parse_frontmatter(skill_md)
    except ValueError as exc:
        result.errors.append(f"{skill_dir.name}: {exc}")
        return ""

    required_frontmatter = set(config["required_frontmatter_keys"])
    missing = required_frontmatter - set(frontmatter)
    if missing:
        result.errors.append(f"{skill_dir.name}: SKILL.md frontmatter 缺少字段 {sorted(missing)}")

    allowed_frontmatter = set(config["allowed_frontmatter_keys"])
    unexpected = set(frontmatter) - allowed_frontmatter
    if unexpected:
        result.errors.append(
            f"{skill_dir.name}: SKILL.md frontmatter 包含未允许字段 {sorted(unexpected)}"
        )

    skill_name = frontmatter.get("name", "").strip()
    if not skill_name:
        result.errors.append(f"{skill_dir.name}: SKILL.md frontmatter.name 为空")
        return ""

    max_name_length = int(config["max_name_length"])
    if len(skill_name) > max_name_length:
        result.errors.append(
            f"{skill_dir.name}: frontmatter.name 长度超过 {max_name_length} 字符"
        )
    if not NAME_PATTERN.fullmatch(skill_name):
        result.errors.append(
            f"{skill_dir.name}: frontmatter.name 需为小写字母/数字/中划线"
        )
    if skill_name.startswith("-") or skill_name.endswith("-") or "--" in skill_name:
        result.errors.append(
            f"{skill_dir.name}: frontmatter.name 不能前后为中划线且不能包含连续中划线"
        )

    if skill_name != skill_dir.name:
        result.errors.append(
            f"{skill_dir.name}: frontmatter.name({skill_name}) 与目录名不一致"
        )

    description = frontmatter.get("description", "").strip()
    if not description:
        result.errors.append(f"{skill_dir.name}: frontmatter.description 为空")
    else:
        max_description_length = int(config["max_description_length"])
        if len(description) > max_description_length:
            result.errors.append(
                f"{skill_dir.name}: frontmatter.description 超过 {max_description_length} 字符"
            )

    validate_skill_references(skill_dir, result)
    validate_openai_yaml(skill_dir, skill_name, config, result)
    validate_script_test_coverage(skill_dir, result)
    if config.get("require_version_file"):
        return validate_version_file(skill_dir, result)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a skill repository.")
    parser.add_argument("--repo-root", help="Repository root to validate")
    parser.add_argument("--config", help="Optional JSON config file")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parent.parent
    config = load_config(args.config)
    result = ValidationResult(errors=[], warnings=[])
    versions: dict[str, str] = {}

    skill_dirs = discover_skill_dirs(repo_root)
    if not skill_dirs:
        result.errors.append("未发现任何技能目录（需要目录下存在 SKILL.md）")
    else:
        for skill_dir in skill_dirs:
            versions[skill_dir.name] = validate_skill_dir(skill_dir, config, result)
        validate_skills_index(repo_root, skill_dirs, versions, config, result)
        validate_readme_index(repo_root, skill_dirs, versions, result)

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
