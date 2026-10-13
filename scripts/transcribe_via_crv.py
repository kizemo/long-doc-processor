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


# CRV 输出约定 ------------------------------------------------------

AUDIO_EXTS = {'.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac'}
VIDEO_EXTS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv'}

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
            [binary, '--version'], capture_output=True, text=True, timeout=10
        )
        # 取 stdout/stderr 第一行非空内容
        for line in (result.stdout + result.stderr).splitlines():
            line = line.strip()
            if line:
                return line
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return "unknown"


# CRV 调用 ---------------------------------------------------------

def run_crv(input_path: Path, output_dir: Path, model: str, lang: str,
            keep_audio: bool = True) -> tuple[int, str, str]:
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
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    elapsed = time.time() - start
    log(f"[crv] exit={result.returncode} elapsed={elapsed:.1f}s")
    return result.returncode, result.stdout, result.stderr


# 产物解析 ---------------------------------------------------------

def find_crv_transcript_dir(output_dir: Path) -> Path | None:
    """找 crv 产物目录:output_dir/crv-out-*-{source_stem}/"""
    if not output_dir.exists():
        return None
    for child in sorted(output_dir.iterdir(), reverse=True):  # 最新优先
        if child.is_dir() and CRV_OUT_SUBDIR_PATTERN.match(child.name):
            return child
    return None


def parse_audio_json(json_path: Path) -> tuple[float, list[tuple[float, float, str]]]:
    """解析 crv audio.json,返回 (总时长秒, [(start, end, text), ...])

    crv audio.json 格式(基于 claude-real-video 0.x 推测,实测需校验):
      {
        "language": "zh",
        "duration": 1234.5,
        "segments": [
          {"start": 0.0, "end": 5.2, "text": "..."},
          ...
        ]
      }
    """
    data = json.loads(read_file_safely(json_path))
    duration = float(data.get('duration', 0))
    segs = []
    for s in data.get('segments', []):
        segs.append((float(s.get('start', 0)), float(s.get('end', 0)), str(s.get('text', ''))))
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
    """从 crv 产物目录读 segments,优先 audio.json,降级 audio.srt,再降级 audio.txt。"""
    json_path = crv_dir / 'audio.json'
    if json_path.exists():
        log(f"[crv] 解析 audio.json: {json_path}")
        return parse_audio_json(json_path)

    srt_path = crv_dir / 'audio.srt'
    if srt_path.exists():
        log(f"[crv] 解析 audio.srt: {srt_path}")
        segs = parse_audio_srt(srt_path)
        duration = segs[-1][1] if segs else 0.0
        return duration, segs

    txt_path = crv_dir / 'audio.txt'
    if txt_path.exists():
        log(f"[crv] 兜底 audio.txt: {txt_path}")
        segs = parse_audio_txt(txt_path)
        return 0.0, segs

    raise FileNotFoundError(f"crv 产物目录 {crv_dir} 缺 audio.json/srt/txt")


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
               fallback: bool = True) -> int:
    """主入口:crv → 解析 → 写 transcript.md。

    失败兜底:crv 失败 → 调 asr_faster_whisper.py(若 fallback=True)
    """
    binary = find_crv_binary()
    if binary is None and not fallback:
        log("ERROR: claude-real-video 未安装且 --no-fallback")
        return 1

    if crv_out_dir is None:
        crv_out_dir = output_path.parent / '.crv-out'

    crv_version = get_crv_version(binary) if binary else "n/a"

    if binary:
        try:
            rc, stdout, stderr = run_crv(input_path, crv_out_dir, model, lang)
        except FileNotFoundError as e:
            log(f"[crv] {e}")
            rc = 127  # command not found
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
    rc = subprocess.run(cmd, capture_output=True, text=True).returncode
    log(f"[fallback] exit={rc}")
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
    )


if __name__ == '__main__':
    sys.exit(main())
