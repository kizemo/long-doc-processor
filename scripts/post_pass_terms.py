"""post-pass 术语纠错: 基于配套文件驱动的规则级替换

参考 memory:
- feedback_term_context_safe_replace.md: 上下文安全替换
- feedback_lecture_term_correction_workflow.md: 双轨同步范式
- feedback_term_context_safe_replace.md: 规则存 safe_replacements_2.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, write_file_safely, get_base_dir, log


def load_safe_replacements() -> list:
    """加载 safe_replacements_2.json"""
    base = get_base_dir()
    path = base / 'scripts' / 'safe_replacements_2.json'
    data = json.loads(read_file_safely(path))
    return data.get('rules', [])


def apply_context_safe_replace(content: str, rules: list) -> tuple:
    """应用上下文安全替换,返回 (新内容, 替换计数)"""
    new_content = content
    counts = {}

    for rule in rules:
        from_word = rule['from']
        to_word = rule['to']
        context = rule.get('context', '')

        # 上下文检查:替换前必须确保 context 关键词在 ±50 字符内
        pattern = re.compile(re.escape(from_word))

        def repl(match):
            # 上下文窗口
            start = max(0, match.start() - 50)
            end = min(len(new_content), match.end() + 50)
            window = new_content[start:end]
            # 如果 context 关键词在窗口内,替换;否则跳过
            if context and context in window:
                return to_word
            elif not context:
                return to_word
            return match.group(0)

        new_content = pattern.sub(repl, new_content)
        counts[f"{from_word}→{to_word}"] = len(re.findall(re.escape(to_word), new_content)) - len(re.findall(re.escape(to_word), content))

    return new_content, counts


def post_pass_file(input_path: Path, output_path: Path) -> dict:
    """对单个文件做 post-pass"""
    content = read_file_safely(input_path)
    rules = load_safe_replacements()

    new_content, counts = apply_context_safe_replace(content, rules)

    write_file_safely(output_path, new_content)

    log(f"Post-pass: {input_path.name}")
    for k, v in counts.items():
        if v > 0:
            log(f"  {k}: {v} 次替换")

    return counts


def main():
    parser = argparse.ArgumentParser(description='post-pass 术语纠错')
    parser.add_argument('--day', type=int, choices=[1, 2, 3],
                        help='处理技能自带 day{N} 目录下的项目笔记(历史用法)')
    parser.add_argument('--file', type=Path,
                        help='直接处理指定的 md 文件(--day 的通用替代)')
    parser.add_argument('--dry-run', action='store_true',
                        help='只报告将要发生的替换,不写文件')
    args = parser.parse_args()

    base = get_base_dir()

    # ---- 通用模式: 处理任意 md 文件 ----
    if args.file:
        src = Path(args.file)
        if not src.exists():
            log(f"ERROR: 文件不存在: {src}")
            sys.exit(1)
        rules = load_safe_replacements()
        content = read_file_safely(src)
        new_content, counts = apply_context_safe_replace(content, rules)
        changed = content != new_content
        log(f"Post-pass: {src.name}  (rules={len(rules)})")
        for k, v in counts.items():
            if v > 0:
                log(f"  {k}: {v} 次替换")
        if not changed:
            log("  无替换发生")
        if args.dry_run:
            log("  [dry-run] 未写文件")
        else:
            write_file_safely(src, new_content)
            log(f"  已写回 {src}")
        return

    days = [args.day] if args.day else [1, 2, 3]
    all_counts = {}

    for d in days:
        # 匹配 day{N}/2026-08-XX_天{N}_*.md
        date_str = f"2026-08-{22 + d - 1:02d}"
        pattern = f"{date_str}_天{d}_*.md"
        files = list((base / f'day{d}').glob(pattern))
        if not files:
            log(f"WARNING: day{d} 无笔记文件,跳过")
            continue
        # 取第一个匹配
        f = files[0]
        # 原地更新(写回原文件)
        counts = post_pass_file(f, f)
        all_counts[d] = counts

    log("\n=== Post-pass 总览 ===")
    for d, counts in all_counts.items():
        log(f"Day {d}: {sum(c for c in counts.values() if c > 0)} 处替换")


if __name__ == '__main__':
    main()
