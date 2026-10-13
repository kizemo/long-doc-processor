#!/usr/bin/env python3
"""validate_skill.py — 静态校验 skill 内部一致性。

Usage:
    python validate_skill.py <skill_root>

校验项（对应 qa-gates.md 第 10.4 节）：
1. frontmatter 可解析
2. name 与目录名一致（小写、连字符）
3. description 以 'Load when' 开头
4. 根 SKILL.md 长度 < 5000 tokens（粗略估算：bytes/3.2）
5. 所有 references/ 中的 markdown 内部链接在文件树中存在
6. evals/*.json 可解析
7. scripts/*.py 可编译
8. 报告 Codex 与 Claude 部署副本是否一致（若两者均存在）
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def parse_frontmatter(text: str) -> dict[str, str] | None:
    m = re.match(r"^---\n(.+?)\n---\n", text, re.S)
    if not m:
        return None
    block = m.group(1)
    result: dict[str, str] = {}
    current_key: str | None = None
    current_list: list[str] | None = None
    for line in block.splitlines():
        if line.startswith("  - ") and current_key is not None:
            if current_list is None:
                current_list = []
            current_list.append(line[4:].strip())
            result[current_key] = "\n".join(current_list)
            continue
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            current_key = key.strip()
            current_list = None
            result[current_key] = value.strip()
    return result


def check_skill(root: Path) -> list[str]:
    issues: list[str] = []
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        return [f"SKILL.md not found in {root}"]
    text = skill_md.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    if not fm:
        issues.append("frontmatter not parseable")
        return issues
    name = fm.get("name", "")
    desc = fm.get("description", "")
    dir_name = root.name

    # 2
    if name != dir_name:
        issues.append(f"name '{name}' != directory '{dir_name}'")
    if not re.match(r"^[a-z][a-z0-9\-]*$", name):
        issues.append(f"name '{name}' not lowercase-hyphen")

    # 3
    if not desc.lower().startswith("load when"):
        issues.append("description does not start with 'Load when'")

    # 4
    body = text.split("---", 2)[-1] if text.count("---") >= 2 else text
    approx_tokens = round(len(body) / 3.2)
    if approx_tokens > 5000:
        issues.append(f"SKILL.md body ~{approx_tokens} tokens exceeds 5000")

    # 5
    refs_dir = root / "references"
    md_files = list(refs_dir.rglob("*.md"))
    for md in md_files:
        body = md.read_text(encoding="utf-8", errors="ignore")
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", body):
            if link.startswith(("http://", "https://", "#", "data:")):
                continue
            target = (md.parent / link).resolve()
            if not target.exists():
                issues.append(f"{md.relative_to(root)}: broken link {link}")

    # 6
    evals_dir = root / "evals"
    for json_file in evals_dir.glob("*.json"):
        try:
            json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append(f"{json_file.relative_to(root)}: invalid JSON: {exc}")

    # 7
    scripts_dir = root / "scripts"
    for py in scripts_dir.glob("*.py"):
        try:
            # 用 utf-8-sig 剥离 BOM，与 Python 运行时行为一致
            src_text = py.read_text(encoding="utf-8-sig")
            compile(src_text, str(py), "exec")
        except SyntaxError as exc:
            issues.append(f"{py.relative_to(root)}: SyntaxError: {exc}")

    return issues


def check_deployment_consistency(codex: Path, claude: Path) -> list[str]:
    issues: list[str] = []
    if not codex.exists():
        return [f"Codex deployment missing: {codex}"]
    if not claude.exists():
        return [f"Claude deployment missing: {claude}"]
    rel_files = [p.relative_to(codex) for p in codex.rglob("*") if p.is_file()]
    rel_files = [p for p in rel_files if "__pycache__" not in p.parts]
    for rel in rel_files:
        cp = codex / rel
        lp = claude / rel
        if not lp.exists():
            issues.append(f"Claude missing: {rel}")
            continue
        if cp.read_bytes() != lp.read_bytes():
            issues.append(f"content differs: {rel}")
    return issues


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python validate_skill.py <skill_root> [--compare <other_root>]", file=sys.stderr)
        return 2
    root = Path(argv[1])
    issues = check_skill(root)
    if "--compare" in argv:
        idx = argv.index("--compare")
        if idx + 1 < len(argv):
            other = Path(argv[idx + 1])
            issues.extend(check_deployment_consistency(root, other))
    if issues:
        for i in issues:
            print(f"FAIL: {i}")
        return 1
    print(f"OK: {root} passed all checks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))