#!/usr/bin/env python3
"""memory_guard.py — 内核级内存硬上限，给长音视频处理子进程用。

为什么存在（2026-10-24 事故教训的移植）
---------------------------------------
本机在 ad-cut 那条线上被 ffmpeg 打死过 4 次：单个进程提交 99~107 GB 虚拟内存，
把系统 commit limit 打到 99.9%，于是 dwm.exe / TextInputHost.exe / ImeService.exe /
ToDesk.exe 连锁分配失败 —— 桌面假死、输入法弹窗、远程控制服务再也拉不起来。

复盘结论有两条，**和技能无关、与工具无关**，所以必须在这里重做一遍：

1. **根因不是 ffmpeg，是「子进程没有任何上限」。**
   危险的命令形态（多分支 trim+concat、双输入 ssim）历史上出现过，但也出现过
   「同一条命令连跑 8 次炸 1 次」的间歇性行为 —— 靠"这条命令看着安全"是不成立的，
   安全性必须由内核强制。
2. **采样监控不是护栏。**
   20 ms 轮询 + 6 GB 就杀，实测拦不住分配风暴（分配速度远超采样间隔）。
   必须用内核在分配点强制：Windows = Job Object，POSIX = RLIMIT_AS。

护栏必须装在**子进程启动之前**，否则存在启动竞态：
    CREATE_SUSPENDED → AssignProcessToJobObject → NtResumeProcess
先 Popen 再 Assign 的写法有窗口期，窗口期内进程可以已经吃掉几十 GB。

Windows 实现说明
-----------------
- 只用 ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` (0x100)：它给 job 内**每个进程**的
  commit 设硬顶，正是单次音视频处理想要的语义。
- 不用 ``JOB_OBJECT_LIMIT_JOB_MEMORY`` (0x10)：嵌套 job 下它返回 ERROR_INVALID_PARAMETER
  (87)。agent 运行时会把子进程放进 job，嵌套是常态，job 级标志在两个宿主里
  表现不一致；进程级标志两个宿主都能用。
- 子进程会被**继承**进同一个 job，所以 crv 派生的 ffmpeg 子进程同样受同一个上限约束。

用法
----
    from memory_guard import run_guarded
    rc, out, err, note = run_guarded(
        ["crv", str(video), "--out", outdir],
        mem_limit_mb=8192, timeout=7200, log_path=logfile)

给**当前进程**装上限（重活在进程内做时用，比如 faster-whisper 的 PyAV 解码）：

    from memory_guard import install_self_memory_ceiling
    note = install_self_memory_ceiling(6144)

降级策略：Job Object 装不上时**仍然执行**，但在 note 里明确写"没有硬上限"，
让调用方能把它当成"仅估算保护"而不是"已保护"。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

# 子进程的 commit 硬上限（内核强制）。
#
# 这个值**不是**"预期用量",而是"超过就自杀"的最后一道闸。两个量级要分清：
#   预算层（ASR_BUDGET_MB）：按片长估算的峰值，用来在**启动前**拒绝不划算的任务；
#   上限层（本常量）：内核强制的硬顶，超过就死，但机器不动。
#
# 为什么给到 16 GB：跑 crv 的那条路径(faster-whisper 整轨 STFT)对一条
# 2 小时的片子实测要 ~9~10 GB 峰值 —— 6 GB 的上限会让**正常的长片任务**
# 直接失败，那不是保护，那是把功能改没了。
DEFAULT_MEM_LIMIT_MB = 16384

# 独立跑 faster-whisper 时给当前进程装的硬上限。
# 窗口化转写后的真实峰值约 3~4 GB，其中 ~2 GB 是 CUDA context 计入的 commit
# —— 6 GB 太紧（实测会在模型刚加载完就 bad allocation），12 GB 才是安全值。
DEFAULT_SELF_MEM_LIMIT_MB = 12288

# ASR 预算层：预估峰值超过这个值就不值得跑（降档模型或分段）。
ASR_BUDGET_MB = 6144

# 传给子进程的环境变量名。子脚本据此判断"外面已经有护栏了"，
# 避免在已被 job 约束的进程里再套一层 job（嵌套 job 的坑）。
ENV_MEM_LIMIT = "LDP_MEM_LIMIT_MB"


# --------------------------------------------------------------------------
# Windows Job Object
# --------------------------------------------------------------------------

_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_STATUS_NO_MEMORY = 0xC0000017
_CREATE_SUSPENDED = 0x00000004


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _load_kernel32():
    if not sys.platform.startswith("win"):
        return None
    try:
        return ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return None


_kernel32 = _load_kernel32()

if _kernel32 is not None:
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    _kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    _kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.SetInformationJobObject.restype = ctypes.c_int
    _kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    _kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.TerminateJobObject.restype = ctypes.c_int
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_int
    _kernel32.GetCurrentProcess.argtypes = []
    _kernel32.GetCurrentProcess.restype = ctypes.c_void_p


def _load_ntdll():
    if not sys.platform.startswith("win"):
        return None
    try:
        dll = ctypes.WinDLL("ntdll", use_last_error=True)
    except OSError:
        return None
    dll.NtResumeProcess.argtypes = [ctypes.c_void_p]
    dll.NtResumeProcess.restype = ctypes.c_long
    return dll


_ntdll = _load_ntdll()


def _make_job(mem_limit_bytes: int):
    """Create a Job Object whose per-process commit is capped.

    Returns (handle, error_text). handle is None when the ceiling could not be
    installed; the caller then degrades to "no hard ceiling" and says so.
    """
    if _kernel32 is None:
        return None, "kernel32 not available"
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return None, "CreateJobObjectW failed (%d)" % ctypes.get_last_error()
    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = mem_limit_bytes
    ok = _kernel32.SetInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
        ctypes.sizeof(info))
    if not ok:
        err = ctypes.get_last_error()
        _kernel32.CloseHandle(job)
        return None, "SetInformationJobObject failed (%d)" % err
    return job, ""


def _assign(job, proc) -> str:
    handle = getattr(proc, "_handle", None)
    if handle is None:
        return "no process handle"
    if not _kernel32.AssignProcessToJobObject(job, handle):
        return "AssignProcessToJobObject failed (%d)" % ctypes.get_last_error()
    return ""


def _terminate(job) -> None:
    if _kernel32 is not None and job:
        try:
            _kernel32.TerminateJobObject(job, 1)
        except OSError:
            pass


def _close(job) -> None:
    if _kernel32 is not None and job:
        try:
            _kernel32.CloseHandle(job)
        except OSError:
            pass


def _resume(proc) -> str:
    """Resume a process started with CREATE_SUSPENDED. "" on success."""
    handle = getattr(proc, "_handle", None)
    if handle is None:
        return "no process handle"
    if _ntdll is None:
        return "ntdll not available"
    status = _ntdll.NtResumeProcess(handle)
    if status != 0:
        return "NtResumeProcess failed (0x%08x)" % (status & 0xFFFFFFFF)
    return ""


# --------------------------------------------------------------------------
# POSIX fallback
# --------------------------------------------------------------------------

def _posix_preexec(mem_limit_bytes: int):
    """Build a preexec_fn that caps address space for the child (POSIX only)."""
    try:
        import resource
    except ImportError:
        return None

    def _apply():
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_limit_bytes, mem_limit_bytes))
        except (ValueError, OSError):
            pass
    return _apply


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def run_guarded(cmd, mem_limit_mb: int = DEFAULT_MEM_LIMIT_MB,
                timeout: float | None = None, log_path=None,
                cwd=None, env=None, stdin_bytes: bytes | None = None):
    """Run a child process under a kernel-enforced memory ceiling.

    Args:
        cmd: command list (str elements).
        mem_limit_mb: per-process commit ceiling in MB. 0 disables the ceiling.
        timeout: seconds; None means no limit.
        log_path: when given, the child's stdout/stderr are written straight to
            this file instead of being buffered in RAM. A long ASR run can
            print a lot; buffering it in the parent is a needless memory cost.
        stdin_bytes: bytes fed to the child's stdin.
        env: environment for the child (the memory ceiling is exported in it
            so the child knows it is already guarded).

    Returns:
        (returncode, stdout_text, stderr_text, note)
    """
    cmd = [str(c) for c in cmd]
    note = ""
    job = None
    mem_limit_bytes = int(mem_limit_mb) * 1024 * 1024

    child_env = dict(os.environ if env is None else env)
    if mem_limit_mb > 0:
        child_env[ENV_MEM_LIMIT] = str(int(mem_limit_mb))

    popen_kwargs = dict(cwd=cwd, env=child_env)
    if stdin_bytes is not None:
        popen_kwargs["stdin"] = subprocess.PIPE
    else:
        popen_kwargs["stdin"] = subprocess.DEVNULL

    out_handle = None
    err_handle = None
    log_file = None
    try:
        if log_path:
            log_file = open(log_path, "wb")
            popen_kwargs["stdout"] = log_file
            popen_kwargs["stderr"] = log_file
        else:
            popen_kwargs["stdout"] = subprocess.PIPE
            popen_kwargs["stderr"] = subprocess.PIPE

        if mem_limit_mb > 0:
            if sys.platform.startswith("win"):
                job, err = _make_job(mem_limit_bytes)
                if job is None:
                    note = "job object unavailable (%s), no hard memory ceiling" % err
            else:
                pre = _posix_preexec(mem_limit_bytes)
                if pre is None:
                    note = "resource.setrlimit unavailable, no hard memory ceiling"
                else:
                    popen_kwargs["preexec_fn"] = pre

        suspended = False
        if job is not None:
            # Start suspended: the child cannot allocate before the ceiling is
            # installed, which removes the start-up race entirely.
            popen_kwargs["creationflags"] = _CREATE_SUSPENDED
            suspended = True

        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
        except OSError:
            if not suspended:
                raise
            popen_kwargs.pop("creationflags", None)
            suspended = False
            proc = subprocess.Popen(cmd, **popen_kwargs)

        if job is not None:
            err = _assign(job, proc)
            if err:
                note = "job assignment failed (%s), no hard memory ceiling" % err
                _close(job)
                job = None
        if suspended:
            rerr = _resume(proc)
            if rerr:
                proc.kill()
                try:
                    proc.communicate(timeout=10)
                except Exception:
                    pass
                return 125, "", "", \
                    (note + "; " if note else "") + \
                    "could not resume suspended child (%s)" % rerr

        try:
            out, errout = proc.communicate(input=stdin_bytes, timeout=timeout)
        except subprocess.TimeoutExpired:
            if job is not None:
                _terminate(job)
            proc.kill()
            try:
                proc.communicate(timeout=10)
            except Exception:
                pass
            return 124, "", "", (note + "; " if note else "") + \
                "timeout after %ss" % timeout

        rc = proc.returncode
        if rc is not None and rc < 0:
            rc = -rc
            note = (note + "; " if note else "") + \
                "killed by the memory ceiling (exit %d)" % rc
        elif rc is not None and (rc & 0xFFFFFFFF) == _STATUS_NO_MEMORY:
            note = (note + "; " if note else "") + \
                "killed by the memory ceiling (STATUS_NO_MEMORY)"

        if log_file is not None:
            log_file.flush()
            log_file.close()
            log_file = None
            stdout_text, stderr_text = _read_log_tail(log_path)
        else:
            stdout_text = _decode(out)
            stderr_text = _decode(errout)
        return rc, stdout_text, stderr_text, note
    finally:
        if log_file is not None:
            try:
                log_file.close()
            except OSError:
                pass
        if job is not None:
            _close(job)


def _decode(raw) -> str:
    """Decode child output.

    Windows children write in the console code page (cp936 here), not UTF-8.
    Decoding with errors="replace" is mandatory: one stray byte must not kill
    the reader thread and take the whole step down with it.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("mbcs")
        except (UnicodeDecodeError, LookupError):
            return raw.decode("utf-8", "replace")


def _read_log_tail(log_path, max_bytes: int = 65536) -> tuple[str, str]:
    """Read back the tail of a log file written by the child."""
    try:
        size = Path(log_path).stat().st_size
        with open(log_path, "rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            data = fh.read()
    except OSError:
        return "", ""
    return _decode(data), ""


def install_self_memory_ceiling(mem_limit_mb: int = DEFAULT_SELF_MEM_LIMIT_MB) -> str:
    """Install a per-process commit ceiling on the CURRENT process.

    Used when the heavy work happens in-process (faster-whisper's PyAV audio
    decode + ctranslate2 inference) and there is no child process to wrap.

    Returns "" on success; otherwise a description of why the ceiling is NOT
    in force, so the caller can degrade to estimate-only protection.
    """
    global _SELF_JOB
    if _kernel32 is None:
        return "kernel32 not available"
    if mem_limit_mb <= 0:
        return "ceiling disabled"
    if _SELF_JOB is not None:
        return ""
    job, err = _make_job(int(mem_limit_mb) * 1024 * 1024)
    if job is None:
        return "job object unavailable (%s)" % err
    proc = _kernel32.GetCurrentProcess()
    if not _kernel32.AssignProcessToJobObject(job, proc):
        code = ctypes.get_last_error()
        _close(job)
        return "job assignment failed (%d)" % code
    _SELF_JOB = job  # must stay alive for the lifetime of the process
    return ""


_SELF_JOB = None


def current_commit_gb() -> float:
    """System commit usage in GB (how close the machine is to the ceiling)."""
    try:
        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        st = _MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(st)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return (st.ullTotalPageFile - st.ullAvailPageFile) / (1024.0 ** 3)
    except Exception:
        pass
    return -1.0


def estimate_asr_peak_mb(duration_s: float, model: str = "large-v3-turbo",
                         compute_type: str = "float16", windowed: bool = True) -> int:
    """Estimate peak RSS of an in-process faster-whisper run, in MB.

    Three terms, and the order of importance is the opposite of what people assume:

    1. model weights: ctranslate2 int8/float16 weights, ~0.5 GB per 300M params
    2. decoded audio: faster-whisper decodes the whole track into 16 kHz mono
       float32 through PyAV -> 64 KB/s. A 2h16m lecture is ~500 MB on its own,
       and it is allocated *before* inference starts.
    3. CUDA context: on Windows the device memory mapping counts toward the
       process commit, so a CUDA run carries ~2 GB that never shows up in RSS.

    And the term that actually killed a 2h16m run (2026-10-24):
    the **full-length STFT**. faster-whisper 1.2.1 always runs the STFT over
    the whole waveform in one go (`chunk_length` does NOT chunk it), which costs

        98 frames/s x 400 bins x 8 B x ~4 live copies ~= 810 KB per second of audio

    i.e. ~6.6 GB for a 2h16m lecture, allocated in one shot.

    windowed=True  -> the caller slices the audio into windows (as
                      scripts/asr_faster_whisper.py now does) => no STFT term,
                      peak is independent of duration.
    windowed=False -> the caller hands the whole file to faster-whisper
                      (crv does this) => the STFT term applies.
    """
    weights = {
        "tiny": 150, "base": 250, "small": 550, "medium": 900,
        "large": 1600, "large-v3": 1600, "large-v3-turbo": 1100, "turbo": 1100,
    }.get(model, 1600)
    audio_mb = max(0.0, float(duration_s)) * 64.0 / 1024.0  # 64 KB/s -> MB
    peak = weights + audio_mb * 1.15 + 2048 + 512
    if not windowed:
        peak += max(0.0, float(duration_s)) * 810.0 / 1024.0  # full-length STFT
    return int(peak)


if __name__ == "__main__":
    # Self test: prove the ceiling stops a greedy child instead of the machine.
    print("commit now: %.1f GB" % current_commit_gb())
    rc, out, err, note = run_guarded(
        [sys.executable, "-c",
         "x = bytearray(400 * 1024 * 1024); print('allocated', len(x))"],
        mem_limit_mb=int(os.environ.get("MEM_LIMIT_MB", "256")),
        timeout=60)
    print("exit=%s note=%s" % (rc, note))
    print("stdout=%s" % out.strip()[:200])
    print("commit after: %.1f GB" % current_commit_gb())
