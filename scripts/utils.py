"""long-doc-processor 通用工具模块

提供:
- read_file_safely / write_file_safely (UTF-8 安全读写, 跨平台 BOM 处理)
- parse_frontmatter (YAML frontmatter 解析)
- check_links (相对链接检查)
- get_base_dir (返回 skill 安装根目录)
- log (统一日志输出, 线程安全)
- configure_stdout_utf8 (Windows 兼容 UTF-8, M-04 经验)
"""
from __future__ import annotations

import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Tuple


def get_base_dir() -> Path:
    """返回 long-doc-processor skill 的安装根目录

    解析规则: __file__ -> ../  (scripts/utils.py -> skill 根)
    """
    return Path(__file__).resolve().parent.parent


def read_file_safely(path) -> str:
    """UTF-8 安全读文件, 自动跳过 BOM"""
    p = Path(path)
    # 优先尝试 utf-8-sig (自动去 BOM)
    try:
        return p.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        return p.read_text(encoding='utf-8', errors='replace')


def write_file_safely(path, content: str) -> None:
    """UTF-8 写文件, 不带 BOM"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')


# 线程安全 log (M-04 经验, A2 实现) ---------------------------------

_log_lock = threading.Lock()


def log(msg: str) -> None:
    """统一日志: stderr 输出, 不污染 stdout, 线程安全(加锁)。

    v4.21 起加 lock 防 3 worker 并发时日志行交错(原 print 在 Windows 下
    多线程并发会撕裂单行输出);输出前缀时间戳便于排序。
    """
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with _log_lock:
        print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


def configure_stdout_utf8() -> None:
    """M-04:Windows terminal 默认 GBK,reconfigure 避免 UnicodeEncodeError。

    在脚本入口 __main__ 调一次即可:
        if __name__ == "__main__":
            from utils import configure_stdout_utf8
            configure_stdout_utf8()
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


# safe_llm_call verbose status callback (v4.21 C4 沉淀) ----------

def make_verbose_status_callback(prefix: str = "llm"):
    """生成 safe_llm_call 的 on_status 回调(C4 阶段沉淀)。

    用法:在 5 个 LLM 脚本的 --verbose flag 启用时,传给 safe_llm_call:
        if args.verbose:
            on_status = make_verbose_status_callback("[smooth]")
        else:
            on_status = None
        response, status = safe_llm_call(prompt, on_status=on_status)

    行为:把 safe_llm_call 的 status(ok / empty / error / timeout / rate_limited /
    no_api_key / no_sdk) 写到 stderr,便于 debug 5 worker 并发时的状态分流。
    """
    def _on_status(s: str) -> None:
        log(f"[{prefix}] {s}")
    return _on_status


# D7 时间预算埋点(v4.21 D 阶段)----------------------------------

import time
from contextlib import contextmanager


@contextmanager
def time_budget(phase: str, budget: dict | None = None):
    """D7 时间预算埋点 context manager。

    用法:
        budget = {}
        with time_budget("phase_0", budget):
            run_asr(...)
        # budget = {"phase_0": 12.3}  # 秒

    退出时自动 log 耗时到 stderr(用 log 函数,线程安全)。
    可选 budget dict 累积所有 phase 耗时(供 D1 run_pipeline 输出总览)。
    """
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        if budget is not None:
            budget[phase] = elapsed
        log(f"[time] {phase}: {elapsed:.1f}s")


def format_budget_summary(budget: dict[str, float]) -> str:
    """格式化时间预算总览(D7 + D1 配合)。

    Args:
        budget: {phase_name: elapsed_seconds}

    Returns:
        多行字符串,每行一个 phase(按耗时降序)
    """
    if not budget:
        return "(无 phase 记录)"
    total = sum(budget.values())
    lines = [f"[budget] 总耗时 {total:.1f}s"]
    sorted_phases = sorted(budget.items(), key=lambda x: -x[1])
    for phase, elapsed in sorted_phases:
        pct = elapsed / total * 100 if total > 0 else 0
        lines.append(f"  {phase:30s} {elapsed:7.1f}s ({pct:5.1f}%)")
    return "\n".join(lines)


# E1 utils 扩充(v4.21 E 阶段)-----------------------------------

def find_files_by_ext(root: Path, ext: str) -> list[Path]:
    """递归找 root 下所有指定后缀的文件。

    Args:
        root: 搜索根目录
        ext: 后缀名,含 `.`(如 `.md` / `.json` / `.py`)

    Returns:
        Path 列表(按字母序)
    """
    if not ext.startswith('.'):
        ext = '.' + ext
    return sorted(root.rglob(f'*{ext}'))


def safe_rename(src: Path, dst: Path) -> bool:
    """Windows 安全的 rename(处理 WinError 5 文件锁)。

    策略:os.replace → 失败时 sleep 0.1s 重试 → 最终用 os.remove + os.rename(M-12 衍生)。

    Args:
        src: 源路径(必须存在)
        dst: 目标路径(可存在或不存在)

    Returns:
        True 成功, False 失败
    """
    import os
    import time as _t
    if not src.exists():
        return False
    try:
        os.replace(src, dst)
        return True
    except OSError:
        _t.sleep(0.1)
        try:
            if dst.exists():
                os.remove(dst)
            os.rename(src, dst)
            return True
        except OSError:
            return False


def compute_md5(path: Path) -> str:
    """计算文件 MD5 哈希(回归测试对比用)。"""
    import hashlib
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, content: str) -> None:
    """原子写:写临时文件 → rename,防中途崩溃损坏原文件。

    Args:
        path: 目标文件路径
        content: 内容
    """
    import os
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + '.',
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        # 失败时清理临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def parse_table_row(line: str) -> list[str]:
    """解析 markdown 表格行 `| a | b | c |` → ['a', 'b', 'c']。

    算法:line.count('|') - 1(去除两侧边界 v4.21 B2 沉淀)+ strip + 过滤空字符串。
    """
    stripped = line.strip()
    if not stripped.startswith('|') or not stripped.endswith('|'):
        return []
    # 去两侧边界 `|`
    inner = stripped[1:-1]
    # 按 | 切
    cells = [c.strip() for c in inner.split('|')]
    return cells


def is_cjk(char: str) -> bool:
    """判断单字符是否是 CJK 字符(基本汉字 + 扩展)。

    Args:
        char: 单字符字符串(长度必须为 1)

    Returns:
        True = CJK, False = 非 CJK
    """
    if len(char) != 1:
        return False
    cp = ord(char)
    return (
        '\u4e00' <= char <= '\u9fff'  # CJK 统一汉字
        or '\u3400' <= char <= '\u4dbf'  # CJK 扩展 A
        or '\uF900' <= char <= '\uFAFF'  # CJK 兼容
    )


def extract_first_h1(text: str) -> str | None:
    """提取 markdown 第一个 H1 标题(verify_html 用)。

    Args:
        text: markdown 内容

    Returns:
        H1 文字(去 `# ` 前缀并 strip),无 H1 返回 None
    """
    for line in text.splitlines():
        m = re.match(r'^#\s+(.+)$', line)
        if m:
            return m.group(1).strip()
    return None


def normalize_whitespace(text: str) -> str:
    """规范化空白(连续空格/tab 折叠为单空格,行尾空格去除,空行折叠为单行)。

    用于回归测试字段比对(避免空格差异导致误判)。
    """
    lines = text.splitlines()
    out_lines: list[str] = []
    prev_blank = False
    for line in lines:
        # 折叠连续空格/tab 为单空格,strip 行尾
        normalized = re.sub(r'[ \t]+', ' ', line).rstrip()
        is_blank = (normalized == '')
        if is_blank and prev_blank:
            continue  # 跳过连续空行
        out_lines.append(normalized)
        prev_blank = is_blank
    # 去掉末尾空行
    while out_lines and out_lines[-1] == '':
        out_lines.pop()
    return '\n'.join(out_lines)


# E2 argparse boilerplate 统一(v4.21 E 阶段)---------------------

def make_standard_parser(
    description: str,
    *,
    add_verbose: bool = True,
    add_dry_run: bool = False,
    add_workers: bool = False,
) -> "argparse.ArgumentParser":
    """生成统一的 argparse parser(E2 boilerplate 统一)。

    自动注册:
      - description
      - --verbose flag(若 add_verbose=True,默认 True)
      - --dry-run flag(若 add_dry_run=True,默认 False)
      - --workers flag(若 add_workers=True,默认 3)

    设计:
      - 各脚本仍可自行添加其他 args
      - 一致的 flag 命名减少学习成本
      - C4 verbose status 通过 --verbose 启用

    Usage:
        parser = make_standard_parser("我的脚本", add_dry_run=True, add_workers=True)
        parser.add_argument("input", help="...")
        args = parser.parse_args()
    """
    import argparse
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    if add_verbose:
        parser.add_argument(
            '--verbose', action='store_true',
            help='verbose 模式:LLM status 写到 stderr(v4.21 C4)',
        )
    if add_dry_run:
        parser.add_argument(
            '--dry-run', action='store_true',
            help='dry-run 模式:不调 LLM/外部命令,只 mock',
        )
    if add_workers:
        parser.add_argument(
            '--workers', type=int, default=3,
            help='并发 LLM 数(默认 3)',
        )
    return parser


def safe_main(main_fn) -> int:
    """统一 CLI 入口(E2 boilerplate 统一)。

    替代 `if __name__ == "__main__": sys.exit(main())`,自动:
      1. 调 configure_stdout_utf8(Windows UTF-8 兼容)
      2. 调 main_fn()
      3. 捕获 KeyboardInterrupt → exit 130
      4. 异常未捕获 → exit 1 + log 异常

    Usage:
        def main() -> int: ...
        if __name__ == "__main__":
            sys.exit(safe_main(main))
    """
    configure_stdout_utf8()
    try:
        return main_fn()
    except KeyboardInterrupt:
        log("[main] 用户中断")
        return 130
    except SystemExit:
        raise  # argparse 正常 exit 不捕获
    except Exception as e:
        log(f"[main] 未捕获异常:{type(e).__name__}: {e}")
        return 1


def parse_frontmatter(content: str) -> Tuple[dict, str]:
    """解析 YAML frontmatter, 返回 (frontmatter_dict, 正文)

    不抛异常, 解析失败返回 ({}, 原内容)
    """
    if not content.startswith('---'):
        return {}, content
    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1]
    body = parts[2].lstrip('\n')
    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        fm = {}
    return fm, body


_LINK_PATTERN = re.compile(r'(?<!\!)\[([^\]]+)\]\(([^)]+)\)')


def check_links(md_path, content: str) -> list:
    """检查 markdown 中的相对链接

    返回 broken 列表 [(text, target, reason), ...]
    """
    base = Path(md_path).parent
    broken = []
    for text, target in _LINK_PATTERN.findall(content):
        # 跳过 http(s):// / mailto: / #anchor
        if target.startswith(('http://', 'https://', 'mailto:', '#')):
            continue
        # 跳过纯 anchor (#xxx)
        if target.startswith('#'):
            continue
        # 去掉 anchor 部分
        target_path = target.split('#', 1)[0]
        if not target_path:
            continue
        candidate = (base / target_path).resolve()
        if not candidate.exists():
            broken.append((text, target, 'not found'))
    return broken
