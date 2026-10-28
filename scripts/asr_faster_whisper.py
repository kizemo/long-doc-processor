"""faster-whisper ASR 包装脚本 - 处理单段录音

参考 memory:
- reference_whisper_turbo_path.md: ComfyUI portable + ~/.cache/whisper/large-v3-turbo.pt
- feedback_hf_hub_offline_faster_whisper.md: 必加 HF_HUB_OFFLINE=1
- feedback_whisper_speed_compare.md: faster-whisper 7.8× realtime
"""
import argparse
import os
import sys
import time
from pathlib import Path

# 必须在 import faster_whisper 之前设置
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 必须放在 HF_HUB_OFFLINE 之后 —— 离线标志要先设好再 import
from faster_whisper import WhisperModel

sys.path.insert(0, str(Path(__file__).parent))
from memory_guard import (  # noqa: E402
    ASR_BUDGET_MB,
    DEFAULT_SELF_MEM_LIMIT_MB,
    ENV_MEM_LIMIT,
    estimate_asr_peak_mb,
    install_self_memory_ceiling,
)
from utils import get_base_dir, write_file_safely, log  # noqa: E402


def _install_ceiling() -> None:
    """给当前进程装 commit 硬上限。

    这一步是必须的: faster-whisper 会用 PyAV 把整条音轨一次性解码成
    16 kHz 单声道 float32 —— 64 KB/s,两小时的片子光这一项就 ~500 MB,
    而且它发生在**模型加载之前**。没有上限的话,峰值是"片长 × 64 KB/s"。

    若外层已经用 Job Object 包住本进程(transcribe_via_crv.py 会把上限
    通过 LDP_MEM_LIMIT_MB 传下来),就不在这里再套一层 —— 嵌套 job 在
    Windows 上有坑(见 memory_guard 顶部注释)。
    """
    inherited = os.environ.get(ENV_MEM_LIMIT)
    if inherited:
        log(f"  外层已有护栏({ENV_MEM_LIMIT}={inherited} MB),跳过进程内上限")
        return
    limit = int(os.environ.get("LDP_SELF_MEM_LIMIT_MB", DEFAULT_SELF_MEM_LIMIT_MB))
    note = install_self_memory_ceiling(limit)
    if note:
        log(f"  WARN 进程内内存上限未生效: {note}(仅估算保护)")
    else:
        log(f"  进程内 commit 硬上限: {limit} MB")


def transcribe_segment(mp3_path: Path, output_path: Path, model_size: str = 'large-v3',
                       split_seconds: int = 600) -> None:
    """转录单段录音,输出 md 格式(含时间戳)

    **为什么必须分段(2026-10-24 实测事故)**
    --------------------------------------
    faster-whisper 1.2.1 的 `transcribe()` 无论传不传 `chunk_length`,
    都会对**整条音轨**做一次 STFT:

        features = self.feature_extractor(audio, chunk_length=chunk_length)

    而 `FeatureExtractor.__call__` 里 `chunk_length` 只改 n_samples/nb_max_frames
    (补零窗口),**不改 STFT 的分段**。于是长音频的峰值是:

        stft complex64   (1, 799487, 400)  ≈ 2.56 GB
        + .astype() 副本                    ≈ 2.56 GB
        + magnitudes float32                ≈ 1.28 GB
        + mel_spec / log_spec               ≈ 0.30 GB
        ----------------------------------------------
        ≈ 6.5 GB,**一次性**分配

    实测:2 小时 16 分的素材直接
    `numpy._ArrayMemoryError: Unable to allocate 1.19 GiB for an array with shape
    (1, 799487, 400)` —— 整个进程被内存上限干掉。

    修法:**自己按窗口切片再逐段转写**。每段的 STFT 只占几 MB,
    峰值变成"整条音轨的 float32(64 KB/s)+ 模型权重 + 一小段频谱",
    与**片长无关**。段与段的时间戳按偏移量拼回去。
    """
    log(f"开始转录: {mp3_path.name} (model={model_size}, 窗口={split_seconds}s)")
    start = time.time()

    _install_ceiling()

    # ComfyUI portable Python with CUDA(参考 memory reference_whisper_turbo_path.md)
    # 如果在 ComfyUI 环境运行,自动使用其 python
    model = WhisperModel(model_size, device='cuda', compute_type='float16')

    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(mp3_path), sampling_rate=16000)
    total_s = len(audio) / 16000.0
    log(f"  音频时长: {total_s:.1f}s ({len(audio) * 4 / 1024 / 1024:.0f} MB float32)")

    md_lines = [
        f"# {mp3_path.stem} - ASR Raw",
        "",
        f"> 源文件: `{mp3_path.name}`",
        f"> 模型: faster-whisper {model_size}",
        f"> 时长: {total_s:.1f}s",
        "",
        "---",
        "",
    ]

    step = max(1, split_seconds) * 16000
    seg_count = 0
    lang_prob = 0.0
    for idx, offset_samples in enumerate(range(0, len(audio), step)):
        chunk = audio[offset_samples:offset_samples + step]
        offset_s = offset_samples / 16000.0
        segments, info = model.transcribe(
            chunk,
            language='zh',
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            # 逐段独立解码:防止上一段的上下文把这一段带进重复循环
            condition_on_previous_text=False,
        )
        lang_prob = info.language_probability or lang_prob
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            seg_count += 1
            abs_start = offset_s + seg.start
            h = int(abs_start // 3600)
            m = int((abs_start % 3600) // 60)
            s = abs_start % 60
            ts = f"{h:02d}:{m:02d}:{s:05.2f}"
            md_lines.append(f"## [{ts}] {text}")
            md_lines.append("")
        done = min(offset_samples + step, len(audio)) / 16000.0
        log(f"  窗口 {idx + 1}: {offset_s:.0f}s → {done:.0f}s,累计 {seg_count} segments")

    log(f"  语言置信度: {lang_prob:.2f}")

    elapsed = time.time() - start
    speed = total_s / elapsed if elapsed > 0 else 0
    log(f"  完成: {seg_count} segments, 用时 {elapsed:.1f}s ({speed:.2f}× realtime)")

    # 写文件
    content = '\n'.join(md_lines)
    write_file_safely(output_path, content)
    log(f"  写入: {output_path.name}")


def _probe_duration_seconds(path: Path, timeout: float = 120.0) -> float:
    """探测时长(秒)。ffmpeg 调用本身也在护栏里。"""
    import re
    from memory_guard import run_guarded
    rc, out, err, note = run_guarded(
        ["ffmpeg", "-hide_banner", "-i", str(path)],
        mem_limit_mb=1024, timeout=timeout)
    blob = (out or "") + (err or "")
    m = re.search(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", blob)
    if not m:
        return -1.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def main():
    parser = argparse.ArgumentParser(description='单段录音 ASR 转录')
    parser.add_argument('--input', required=True, help='输入 mp3 路径')
    parser.add_argument('--output', help='输出 md 路径(默认 .cache/raw/{filename}.md)')
    parser.add_argument('--model', default='large-v3', help='模型大小(large-v3/large-v3-turbo)')
    parser.add_argument('--max-duration-s', type=float, default=4 * 3600,
                        help='超过这个时长的输入直接拒绝(整轨解码的内存随片长线性增长)')
    parser.add_argument('--split-seconds', type=int, default=600,
                        help='转写窗口长度(秒)。分段转写让峰值内存与片长无关,'
                             '默认 600s;调小更省内存,调大上下文更连贯')
    args = parser.parse_args()

    mp3_path = Path(args.input).resolve()
    if not mp3_path.exists():
        print(f"ERROR: 输入文件不存在: {mp3_path}", file=sys.stderr)
        sys.exit(1)

    # 预算层:整轨解码 64 KB/s,先算峰值再决定要不要跑
    limit = int(os.environ.get("LDP_MEM_LIMIT_MB") or 0)
    if limit <= 0:
        limit = int(os.environ.get("LDP_SELF_MEM_LIMIT_MB", DEFAULT_SELF_MEM_LIMIT_MB))
    try:
        duration = _probe_duration_seconds(mp3_path)
    except Exception:
        duration = -1.0
    if duration > 0:
        # 窗口化转写 => 峰值与片长无关(windowed=True)
        peak = estimate_asr_peak_mb(duration, model=args.model, windowed=True)
        log(f"  预算: 时长 {duration:.1f}s,预估峰值 {peak} MB,"
            f"预算 {ASR_BUDGET_MB} MB,硬上限 {limit} MB")
        if duration > args.max_duration_s:
            print(f"ERROR: 输入时长 {duration:.1f}s 超过上限 {args.max_duration_s}s,请分段转写",
                  file=sys.stderr)
            sys.exit(4)
        if peak > ASR_BUDGET_MB:
            print(f"ERROR: 预估峰值 {peak} MB 超过 ASR 预算 {ASR_BUDGET_MB} MB,"
                  "请降档模型或分段转写",
                  file=sys.stderr)
            sys.exit(4)

    base = get_base_dir()
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        cache_dir = base / '.cache' / 'raw'
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_path = cache_dir / f"{mp3_path.stem}.md"

    transcribe_segment(mp3_path, output_path, args.model, split_seconds=args.split_seconds)


if __name__ == '__main__':
    main()
