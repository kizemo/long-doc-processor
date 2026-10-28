#!/usr/bin/env python3
"""transcribe_via_crv.py — v4.4 主路径:claude-real-video 包装

调用 claude-real-video(crv)统一处理 .mp3/.mp4 等音视频,
输出兼容 `<stem>_transcript.md` 格式(下游 asr_faster_whisper.py 等同款)。

设计要点(SKILL.md v4.4 changelog):
  - v4.4 起音视频主路径改为 claude-real-video,whisper 路径降为兜底
  - 输出格式兼容 asr_faster_whisper.py(同一 Phase 1 净化输入契约)
  - crv 不可用时自动 fallback 到 asr_faster_whisper.py(同 SKILL.md "fail-soft")

用法:
  python scripts/transcribe_via_crv.py --input <audio_or_video> --output <transcript.md>
  python scripts/transcribe_via_crv.py --input <audio.mp3> --output <out.md> --model turbo --lang zh
  python scripts/transcribe_via_crv.py --input <audio.mp3> --output <out.md> --no-fallback

输出格式(<stem>_transcript.md):
  # {stem} - ASR Transcript

  > 源文件: `{filename}`
  > 模型: claude-real-video (whisper-{model})
  > 时长: {duration}s
  > 转录方式: crv v{version}

  ---

  ## [HH:MM:SS] {segment_text}
  ## [HH:MM:SS] {segment_text}

退出码:
  0 = 成功(crv 或 fallback 都跑通)
  1 = crv + fallback 都失败
  2 = 参数错误
  3 = crv 调用成功但产物解析失败(仍生成兜底 transcript.md 标注 ERROR)
  4 = 超出资源预算(时长超限 / 预估峰值超硬上限)—— 护栏在启动前拦下,不是故障

内存护栏(2026-10-24 加):
  全部子进程都在 Job Object 的 commit 硬上限内运行(内核在分配点强制),
  并且跑之前先做预算检查 —— 见 scripts/memory_guard.py。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))
from utils import read_file_safely, write_file_safely, log  # noqa: E402
from memory_guard import (  # noqa: E402
    ASR_BUDGET_MB,
    DEFAULT_MEM_LIMIT_MB,
    estimate_asr_peak_mb,
    run_guarded,
)


# CRV 输出约定 ------------------------------------------------------

AUDIO_EXTS = {'.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac'}
VIDEO_EXTS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv'}

# 单条音视频的时长上限（秒）。超过就不该一口气跑完 ——
# 内存不是唯一的约束，时间也是：2 小时以上的讲座请分段跑。
MAX_INPUT_DURATION_S = 4 * 3600

# 退出码：4 = 超出预算（护栏拦下，不是故障）
EXIT_OVER_BUDGET = 4

CRV_OUT_SUBDIR_PATTERN = re.compile(r'^crv-out-[\d-]+-(.+)$')


def detect_input_kind(path: Path) -> str:
    """根据扩展名判断 input 类型:audio / video / unknown"""
    ext = path.suffix.lower()
    if ext in AUDIO_EXTS:
        return 'audio'
    if ext in VIDEO_EXTS:
        return 'video'
    return 'unknown'


def find_crv_binary() -> str | None:
    """查找 claude-real-video 可执行文件路径。"""
    return shutil.which('claude-real-video') or shutil.which('crv')


def get_crv_version(binary: str) -> str:
    """crv --version 输出格式不稳定,容错解析。"""
    try:
        result = subprocess.run(
            [binary, '--version'], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10
        )
        # 取 stdout/stderr 第一行非空内容
        for line in ((result.stdout or "") + (result.stderr or "")).splitlines():
            line = line.strip()
            if line:
                return line
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "unknown"


# 时长探测 ---------------------------------------------------------

def probe_duration_seconds(video: Path, timeout: float = 120.0) -> float:
    """探测时长(秒)。

    不用 ffprobe: 本机 PATH 上的 ffprobe 是坏壳子(STATUS_DLL_NOT_FOUND)。
    走 ffmpeg -i 读 Duration 行,并且这个 ffmpeg 调用本身也必须在护栏里 ——
    "只是探测一下"照样是跑 ffmpeg,危险的分配不因为用途轻就变安全。
    """
    rc, out, err, note = run_guarded(
        ["ffmpeg", "-hide_banner", "-i", str(video)],
        mem_limit_mb=1024, timeout=timeout)
    blob = (out or "") + (err or "")
    m = re.search(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", blob)
    if not m:
        return -1.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def budget_check(video: Path, model: str, mem_limit_mb: int,
                 windowed: bool = True) -> tuple[bool, str]:
    """跑之前先算账:时长超限 / 预估峰值超预算 ⇒ 拒绝启动。

    顺序很重要 —— 错误必须发生在任何大额分配之前。

    windowed=True  表示调用方会按窗口切片转写(本技能的 asr_faster_whisper.py)，
                   峰值与片长无关;
    windowed=False 表示整轨丢给 faster-whisper(crv 的做法),要算上整轨 STFT。
    """
    duration = probe_duration_seconds(video)
    if duration < 0:
        # 探测失败不阻断(ffmpeg 版本差异可能导致解析不到),但要说明。
        return True, "时长探测失败,跳过预算检查(仍受 %d MB 硬上限保护)" % mem_limit_mb
    if duration > MAX_INPUT_DURATION_S:
        return False, ("输入时长 %.1f s 超过上限 %d s,请分段处理"
                       % (duration, MAX_INPUT_DURATION_S))
    peak = estimate_asr_peak_mb(duration, model=model, windowed=windowed)
    if peak > ASR_BUDGET_MB:
        return False, ("预估峰值 %d MB 超过 ASR 预算 %d MB。"
                       "换更小的模型(medium/small)或用窗口化转写"
                       % (peak, ASR_BUDGET_MB))
    return True, ("时长 %.1f s,预估峰值 %d MB(预算 %d MB,硬上限 %d MB)"
                  % (duration, peak, ASR_BUDGET_MB, mem_limit_mb))


# CRV 调用 ---------------------------------------------------------

def run_crv(input_path: Path, output_dir: Path, model: str, lang: str,
            keep_audio: bool = True,
            mem_limit_mb: int = DEFAULT_MEM_LIMIT_MB,
            timeout: float | None = 7200) -> tuple[int, str, str]:
    """调 claude-real-video 处理 input,产物落到 output_dir。

    Returns: (exit_code, stdout, stderr)
    """
    binary = find_crv_binary()
    if not binary:
        raise FileNotFoundError("claude-real-video 未安装;请 pip install 或检查 PATH")

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary, str(input_path),
        '--out', str(output_dir),
        '--whisper-model', model,
        '--lang', lang,
    ]
    if keep_audio:
        cmd.append('--keep-audio')

    log(f"[crv] cmd: {' '.join(cmd)}")
    log(f"[crv] 内存硬上限: {mem_limit_mb} MB(Job Object,内核在分配点强制)")

    # 输出直接落盘,不在父进程内存里攒 —— 一场两小时的 ASR 会打印很多。
    log_path = output_dir / "crv-run.log"

    start = time.time()
    rc, stdout, stderr, note = run_guarded(
        cmd, mem_limit_mb=mem_limit_mb, timeout=timeout, log_path=str(log_path))
    elapsed = time.time() - start
    log(f"[crv] exit={rc} elapsed={elapsed:.1f}s")
    if note:
        log(f"[crv] guard: {note}")
    if rc == 124:
        raise TimeoutError("crv 超时(%ss)被终止" % timeout)
    return rc, stdout, stderr


# 产物解析 ---------------------------------------------------------

def find_crv_transcript_dir(output_dir: Path) -> Path | None:
    """找 crv 产物目录。

    版本漂移(2026-10-24 实测):旧版 crv 会在 --out 下建 `crv-out-<日期>-<stem>/`
    子目录;crv 0.10.x 改成**直接把产物写进 --out 本身**。
    两种布局都要认，否则会报"产物目录未找到"而丢掉一次已经跑完的转写。
    """
    if not output_dir.exists():
        return None
    for child in sorted(output_dir.iterdir(), reverse=True):  # 最新优先
        if child.is_dir() and CRV_OUT_SUBDIR_PATTERN.match(child.name):
            return child
    # 新版布局：--out 本身就是产物目录
    markers = ("MANIFEST.txt", "frames.json", "transcript.json", "transcript.txt")
    if any((output_dir / m).exists() for m in markers):
        return output_dir
    return None


def parse_audio_json(json_path: Path) -> tuple[float, list[tuple[float, float, str]]]:
    """解析 crv 的 json 产物,返回 (总时长秒, [(start, end, text), ...])。

    crv 0.10.x 写的是 `transcript.json` = {"segments": [{start, end, text}]}(没有 duration 字段);
    旧版是 `audio.json` = {"language", "duration", "segments"}。两种都认。

    没有 duration 时用最后一段的 end 兜底 —— 时长只用于写进 md 的元信息,
    错了不影响切分,但总比写 0 强。
    """
    data = json.loads(read_file_safely(json_path))
    duration = float(data.get('duration') or 0)
    segs = []
    for s in data.get('segments', []):
        segs.append((float(s.get('start', 0)), float(s.get('end', 0)), str(s.get('text', ''))))
    if not duration and segs:
        duration = max(e for _, e, _ in segs)
    return duration, segs


def parse_audio_txt(txt_path: Path) -> list[tuple[float, float, str]]:
    """解析兜底 audio.txt(纯文本,无时间戳)。

    Returns: [(0.0, 0.0, "full_text")]
    """
    text = read_file_safely(txt_path).strip()
    return [(0.0, 0.0, text)]


def parse_audio_srt(srt_path: Path) -> list[tuple[float, float, str]]:
    """解析 SRT 字幕,返回 [(start, end, text), ...]。

    SRT block 结构(以空行分隔):
        1                                           ← 序号(可忽略)
        00:00:01,000 --> 00:00:05,500               ← 时间码
        第一段文字                                   ← 文本(可多行)

    鲁棒处理:每个 block 内**遍历找时间码行**,而非假设在 lines[0]
    """
    content = read_file_safely(srt_path)
    blocks = re.split(r'\n\s*\n', content.strip())
    segs: list[tuple[float, float, str]] = []
    timecode_re = re.compile(
        r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})'
    )
    for block in blocks:
        block_lines = block.strip().splitlines()
        if len(block_lines) < 2:
            continue
        # 遍历找时间码行(可能是 lines[1],非 lines[0])
        tc_idx = None
        m = None
        for i, line in enumerate(block_lines):
            m = timecode_re.match(line.strip())
            if m:
                tc_idx = i
                break
        if m is None or tc_idx is None:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
        text = ' '.join(block_lines[tc_idx + 1:]).strip()
        if text:
            segs.append((start, end, text))
    return segs


def load_segments_from_crv(crv_dir: Path) -> tuple[float, list[tuple[float, float, str]]]:
    """从 crv 产物目录读 segments。

    文件名有版本漂移:crv 0.10.x 写 `transcript.json` / `transcript.txt`;
    旧版写 `audio.json` / `audio.srt` / `audio.txt`。按"新→旧"的顺序都试一遍。
    """
    for name in ('transcript.json', 'audio.json'):
        json_path = crv_dir / name
        if json_path.exists():
            log(f"[crv] 解析 {name}: {json_path}")
            return parse_audio_json(json_path)

    srt_path = crv_dir / 'audio.srt'
    if srt_path.exists():
        log(f"[crv] 解析 audio.srt: {srt_path}")
        segs = parse_audio_srt(srt_path)
        duration = segs[-1][1] if segs else 0.0
        return duration, segs

    for name in ('transcript.txt', 'audio.txt'):
        txt_path = crv_dir / name
        if txt_path.exists():
            log(f"[crv] 兜底 {name}: {txt_path}")
            segs = parse_audio_txt(txt_path)
            return 0.0, segs

    raise FileNotFoundError(
        f"crv 产物目录 {crv_dir} 缺 transcript.json / audio.json / audio.srt / transcript.txt")


def crv_has_transcript(crv_dir: Path) -> bool:
    """crv 到底有没有产出转写。

    "跑完了"和"转写了"是两件事:crv 用 ffprobe 判断音轨,ffprobe 坏掉时它
    会跳过转写但照样 exit 0。这里显式验产物,把静默失效变成显式降级。
    """
    return any((crv_dir / n).exists() for n in
               ('transcript.json', 'audio.json', 'audio.srt', 'transcript.txt', 'audio.txt'))


def ffprobe_usable() -> bool:
    """ffprobe 能不能用。

    crv 用 ffprobe 判断"这个视频有没有音轨"。本机 PATH 上的 ffprobe 是**坏壳子**
    (STATUS_DLL_NOT_FOUND),于是 crv 会认为"没有音轨" → **静默跳过转写** → exit 0 →
    产物里根本没有 transcript。"跑完了但没转写"是典型的静默失效,
    所以这里先探活,跑完还要验产物。
    """
    import shutil
    import subprocess as sp
    exe = shutil.which("ffprobe")
    if not exe:
        return False
    try:
        r = sp.run([exe, "-version"], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=20)
        return r.returncode == 0
    except Exception:
        return False


# transcript.md 渲染 ----------------------------------------------

def format_timestamp(seconds: float) -> str:
    """秒 → HH:MM:SS.ss 格式"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def render_transcript_md(stem: str, input_name: str, model: str,
                          duration: float, crv_version: str,
                          segments: list[tuple[float, float, str]],
                          note: str = "") -> str:
    """渲染 <stem>_transcript.md(兼容 asr_faster_whisper.py 输出格式)。"""
    lines = [
        f"# {stem} - ASR Transcript",
        "",
        f"> 源文件: `{input_name}`",
        f"> 模型: claude-real-video (whisper-{model})",
        f"> 时长: {duration:.1f}s",
        f"> 转录方式: crv v{crv_version}",
        "",
        "---",
        "",
    ]
    if note:
        lines.extend([f"> {note}", "", ""])

    for start, end, text in segments:
        text = text.strip()
        if not text:
            continue
        ts = format_timestamp(start)
        lines.append(f"## [{ts}] {text}")
        lines.append("")

    return '\n'.join(lines)


# 主流程 -----------------------------------------------------------

def transcribe(input_path: Path, output_path: Path,
               model: str = 'turbo', lang: str = 'zh',
               crv_out_dir: Path | None = None,
               fallback: bool = True,
               mem_limit_mb: int = DEFAULT_MEM_LIMIT_MB,
               engine: str = 'auto') -> int:
    """主入口:crv → 解析 → 写 transcript.md。

    engine:
      auto   (默认) 先跑 crv,**验产物**;没转写出来就降级到 faster-whisper
      crv    只跑 crv;没转写出来直接算失败
      whisper 跳过 crv,直接走 faster-whisper

      什么时候用 whisper:crv 依赖 ffprobe 判断音轨。本机 PATH 上的 ffprobe 是
      坏壳子(STATUS_DLL_NOT_FOUND),crv 会认为"没有音轨"而**静默跳过转写**
      却照样 exit 0。这种机器上直接用 whisper 引擎,省掉一次白跑的抽帧。
    """
    binary = find_crv_binary()
    if binary is None and not fallback:
        log("ERROR: claude-real-video 未安装且 --no-fallback")
        return 1

    if crv_out_dir is None:
        crv_out_dir = output_path.parent / '.crv-out'

    crv_version = get_crv_version(binary) if binary else "n/a"

    # 预算层:先算账再分配。超预算直接拒绝启动,连模型都不加载。
    # crv 走的是整轨 STFT(峰值随片长线性增长),whisper 引擎走的是窗口化转写。
    windowed = (engine == 'whisper')
    ok, msg = budget_check(input_path, model, mem_limit_mb, windowed=windowed)
    log(f"[budget] {msg}")
    if not ok:
        log(f"[budget] 拒绝启动:{msg}")
        return EXIT_OVER_BUDGET

    if engine == 'whisper':
        log("[engine] 直接走 faster-whisper(跳过 crv)")
        return _fallback_to_faster_whisper(input_path, output_path, model, lang)

    if binary:
        if not ffprobe_usable():
            log("[crv] WARN ffprobe 不可用(坏壳子?)—— crv 用它判断音轨,"
                "很可能认为'没有音轨'从而跳过转写;跑完会验产物,没有转写就降级")
        try:
            rc, stdout, stderr = run_crv(input_path, crv_out_dir, model, lang,
                                         mem_limit_mb=mem_limit_mb)
        except FileNotFoundError as e:
            log(f"[crv] {e}")
            rc = 127  # command not found
        except TimeoutError as e:
            log(f"[crv] {e}")
            rc = 124
    else:
        rc = 127

    if rc != 0:
        log(f"[crv] 退出码 {rc};crv 失败")
        if not fallback:
            return 1
        log("[crv] 降级到 asr_faster_whisper.py")
        return _fallback_to_faster_whisper(input_path, output_path, model, lang)

    # 找 crv 产物
    crv_dir = find_crv_transcript_dir(crv_out_dir)
    if crv_dir is None:
        log(f"[crv] 产物目录未找到:{crv_out_dir}")
        if not fallback:
            return 3
        return _fallback_to_faster_whisper(input_path, output_path, model, lang)

    # 关键:crv exit 0 **不等于**转写成功。
    # 本机 ffprobe 是坏壳子,crv 会认为"没有音轨"→ 跳过转写 → 照样 exit 0,
    # 产物里只有 frames.json 没有 transcript.json。
    # 必须验产物,否则会拿着一份空的 transcript 继续往下跑。
    if not crv_has_transcript(crv_dir):
        log(f"[crv] 产物目录里没有转写文件:{crv_dir}"
            "(crv 很可能因为 ffprobe 不可用而误判'无音轨')")
        if not fallback:
            return 3
        log("[crv] 降级到 asr_faster_whisper.py")
        return _fallback_to_faster_whisper(input_path, output_path, model, lang)

    # 解析 segments
    try:
        duration, segs = load_segments_from_crv(crv_dir)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as e:
        log(f"[crv] 产物解析失败:{e}")
        if not fallback:
            # 仍写一个 ERROR transcript.md 让用户看到失败状态
            md = render_transcript_md(
                output_path.stem, input_path.name, model, 0.0, crv_version, [],
                note=f"ERROR: crv 产物解析失败:{e}"
            )
            write_file_safely(output_path, md)
            return 3
        return _fallback_to_faster_whisper(input_path, output_path, model, lang)

    # 写 transcript.md
    md = render_transcript_md(
        output_path.stem, input_path.name, model, duration, crv_version, segs
    )
    write_file_safely(output_path, md)
    log(f"[crv] DONE: {output_path} ({len(segs)} segments, {duration:.1f}s)")
    return 0


def _fallback_to_faster_whisper(input_path: Path, output_path: Path,
                                 model: str, lang: str) -> int:
    """兜底:调 asr_faster_whisper.py 跑 whisper large-v3 路径"""
    fw_script = Path(__file__).parent / 'asr_faster_whisper.py'
    if not fw_script.exists():
        log("ERROR: 兜底脚本 asr_faster_whisper.py 不存在")
        return 1

    # 转换 whisper model 名(turbo → large-v3-turbo)
    fw_model = 'large-v3' if model == 'turbo' else model

    cmd = [
        sys.executable, str(fw_script),
        '--input', str(input_path),
        '--output', str(output_path),
        '--model', fw_model,
    ]
    log(f"[fallback] cmd: {' '.join(cmd)}")
    # 兜底路径同样必须在护栏里:whisper 的 PyAV 解码 + ctranslate2 推理
    # 全在子进程内发生,峰值随片长线性增长(64 KB/s 的整轨解码)。
    rc, out, err, note = run_guarded(
        cmd, mem_limit_mb=DEFAULT_MEM_LIMIT_MB, timeout=7200)
    log(f"[fallback] exit={rc}")
    if note:
        log(f"[fallback] guard: {note}")
    if err:
        log(f"[fallback] stderr: {err[-2000:]}")
    return rc


# CLI --------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='v4.4 主路径:claude-real-video 音视频转录包装',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--input', required=True, type=Path, help='输入音视频文件')
    parser.add_argument('--output', required=True, type=Path, help='输出 transcript.md')
    parser.add_argument('--model', default='turbo', help='whisper 模型(turbo/large-v3/...)')
    parser.add_argument('--lang', default='zh', help='语言代码(zh/en/...)')
    parser.add_argument('--crv-out-dir', type=Path, help='crv 产物目录(默认 .crv-out)')
    parser.add_argument('--no-fallback', action='store_true', help='crv 失败时不降级')
    parser.add_argument('--mem-limit-mb', type=int, default=DEFAULT_MEM_LIMIT_MB,
                        help='子进程 commit 硬上限(Job Object 内核强制);0=不限制')
    parser.add_argument('--engine', choices=['auto', 'crv', 'whisper'], default='auto',
                        help='auto=先 crv 后验产物再降级(默认);crv=只用 crv;'
                             'whisper=跳过 crv 直接走 faster-whisper'
                             '(ffprobe 坏掉的机器上用这个)')
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = args.output.resolve()

    if not input_path.exists():
        log(f"ERROR: 输入文件不存在:{input_path}")
        return 2

    kind = detect_input_kind(input_path)
    if kind == 'unknown':
        log(f"WARN: 输入扩展名 {input_path.suffix} 不在已知列表;按 video 路径尝试")

    return transcribe(
        input_path, output_path,
        model=args.model, lang=args.lang,
        crv_out_dir=args.crv_out_dir,
        fallback=not args.no_fallback,
        mem_limit_mb=args.mem_limit_mb,
        engine=args.engine,
    )


if __name__ == '__main__':
    sys.exit(main())
