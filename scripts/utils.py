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
