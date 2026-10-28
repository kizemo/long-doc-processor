"""tests/test_memory_guard.py — 内核级内存护栏的回归测试。

这些用例盯的是「护栏本身必须真的生效」，不是「护栏函数返回了正确的字符串」。
判别性测试的写法：对照组（无上限）必须成功，实验组（有上限）必须失败 ——
只有两边都符合预期，才说明拦住分配的是内核上限，而不是别的什么偶然因素。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from memory_guard import (  # noqa: E402
    _decode,
    current_commit_gb,
    estimate_asr_peak_mb,
    install_self_memory_ceiling,
    run_guarded,
)

IS_WINDOWS = sys.platform.startswith("win")


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


# ----------------------------------------------------------------------
# 1) 无上限的对照组：必须成功（否则下面的"被拦住"就没有说服力）
# ----------------------------------------------------------------------

def test_unbounded_child_succeeds():
    rc, out, err, note = run_guarded(
        _py("print('hello-guard')"), mem_limit_mb=0, timeout=60)
    assert rc == 0, note
    assert "hello-guard" in out


# ----------------------------------------------------------------------
# 2) 有上限的实验组：贪心分配必须被内核拒绝，且机器状态不变
# ----------------------------------------------------------------------

@pytest.mark.skipif(not IS_WINDOWS, reason="Job Object 硬上限是 Windows 专有机制")
def test_greedy_child_is_stopped_by_ceiling():
    before = current_commit_gb()
    rc, out, err, note = run_guarded(
        _py("x = bytearray(600 * 1024 * 1024); print('allocated')"),
        mem_limit_mb=256, timeout=120)
    after = current_commit_gb()
    assert rc != 0, "有上限时贪心子进程必须失败，而不是分配成功"
    assert "allocated" not in out
    # 机器的提交量不应出现尖峰（这是整个护栏存在的意义）
    assert after - before < 1.0, "提交量出现尖峰: %s -> %s" % (before, after)


@pytest.mark.skipif(not IS_WINDOWS, reason="Job Object 硬上限是 Windows 专有机制")
def test_ceiling_is_installed_before_child_starts():
    """零竞态验证：子进程启动前上限必须已经装好。

    做法：让子进程一启动就分配超过上限的内存。装上限在前 ⇒ 分配失败；
    若上限是"事后补装"的，分配会先成功。
    """
    rc, out, err, note = run_guarded(
        _py("x = bytearray(600 * 1024 * 1024); print('allocated')"),
        mem_limit_mb=128, timeout=120)
    assert rc != 0
    assert "allocated" not in out


# ----------------------------------------------------------------------
# 3) 超时行为
# ----------------------------------------------------------------------

def test_timeout_is_reported_not_hung():
    rc, out, err, note = run_guarded(
        _py("import time; time.sleep(30)"), mem_limit_mb=0, timeout=3)
    assert rc == 124
    assert "timeout" in note.lower()


# ----------------------------------------------------------------------
# 4) 输出解码：Windows 控制台代码页(cp936)下不能炸
# ----------------------------------------------------------------------

def test_decode_never_raises_on_invalid_utf8():
    raw = b"ok \xff\xfe broken \x92 tail"
    text = _decode(raw)
    assert isinstance(text, str)
    assert "ok" in text


def test_decode_passes_through_str():
    assert _decode("already str") == "already str"


def test_decode_handles_none():
    assert _decode(None) == ""


# ----------------------------------------------------------------------
# 5) 日志落盘：长任务不该把 stdout 全塞进父进程内存
# ----------------------------------------------------------------------

def test_child_output_is_written_to_log_file(tmp_path):
    log = tmp_path / "child.log"
    rc, out, err, note = run_guarded(
        _py("print('logged-line')"), mem_limit_mb=0, timeout=60, log_path=str(log))
    assert rc == 0, note
    assert log.exists()
    assert "logged-line" in log.read_text(encoding="utf-8", errors="replace")
    assert "logged-line" in out


# ----------------------------------------------------------------------
# 6) 内存估算：必须含"整条音轨解码"这一主项
# ----------------------------------------------------------------------

def test_estimate_scales_with_duration():
    short = estimate_asr_peak_mb(600)
    long = estimate_asr_peak_mb(8152)
    assert long > short
    # 8152s @ 64KB/s ≈ 510MB 的解码项，加上权重与安全系数应显著超过 1GB
    assert long > 1024


def test_estimate_is_deterministic():
    assert estimate_asr_peak_mb(1000) == estimate_asr_peak_mb(1000)


def test_windowed_estimate_is_independent_of_stft_term():
    """窗口化转写 ⇒ 峰值不随片长线性暴涨。

    判别依据:整轨 STFT 的代价 ≈ 810 KB/s 音频。两条 2 小时的片子,
    整轨路径要多花 >10 GB;窗口化路径只多花音频本身的 64 KB/s。
    """
    win = estimate_asr_peak_mb(8152, windowed=True)
    whole = estimate_asr_peak_mb(8152, windowed=False)
    assert whole - win > 5000, "整轨路径的 STFT 项没有被计入"
    # 窗口化路径仍然要随片长增长(音频解码那 64 KB/s),但增长得很慢
    assert win - estimate_asr_peak_mb(1000, windowed=True) < 1200


def test_budget_gate_rejects_a_whole_file_stft_on_a_long_video():
    """整轨路径 + 长视频 ⇒ 预估峰值超 ASR 预算(应当被预算层拦下)。"""
    from memory_guard import ASR_BUDGET_MB
    peak = estimate_asr_peak_mb(4 * 3600, windowed=False)
    assert peak > ASR_BUDGET_MB
    # 而窗口化路径在同样的 4 小时上仍然在预算内
    assert estimate_asr_peak_mb(4 * 3600, windowed=True) < ASR_BUDGET_MB


# ----------------------------------------------------------------------
# 7) 进程内上限（当前进程）
# ----------------------------------------------------------------------

@pytest.mark.skipif(not IS_WINDOWS, reason="Job Object 是 Windows 专有机制")
def test_self_ceiling_reports_status():
    note = install_self_memory_ceiling(8192)
    assert isinstance(note, str)
    # 要么装上了（空串），要么明确说了为什么没装上 —— 不能静默失败
    if note:
        assert any(k in note for k in
                   ("kernel32", "job", "unavailable", "failed", "disabled"))


# ----------------------------------------------------------------------
# 8) 诊断
# ----------------------------------------------------------------------

def test_current_commit_gb_is_a_number():
    v = current_commit_gb()
    assert isinstance(v, float)
    assert v > 0
