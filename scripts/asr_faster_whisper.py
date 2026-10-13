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

from faster_whisper import WhisperModel

# 添加 scripts/ 到 sys.path
sys.path.insert(0, str(Path(__file__).parent))
from utils import get_base_dir, write_file_safely, log


def transcribe_segment(mp3_path: Path, output_path: Path, model_size: str = 'large-v3') -> None:
    """转录单段录音,输出 md 格式(含时间戳)"""
    log(f"开始转录: {mp3_path.name} (model={model_size})")
    start = time.time()

    # ComfyUI portable Python with CUDA(参考 memory reference_whisper_turbo_path.md)
    # 如果在 ComfyUI 环境运行,自动使用其 python
    model = WhisperModel(model_size, device='cuda', compute_type='float16')

    segments, info = model.transcribe(
        str(mp3_path),
        language='zh',
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    log(f"  检测语言: {info.language} (prob={info.language_probability:.2f})")
    log(f"  音频时长: {info.duration:.1f}s")

    # 流式输出 segments
    md_lines = [
        f"# {mp3_path.stem} - ASR Raw",
        "",
        f"> 源文件: `{mp3_path.name}`",
        f"> 模型: faster-whisper {model_size}",
        f"> 时长: {info.duration:.1f}s",
        "",
        "---",
        "",
    ]

    seg_count = 0
    for seg in segments:
        seg_count += 1
        # 时间戳格式: HH:MM:SS
        h = int(seg.start // 3600)
        m = int((seg.start % 3600) // 60)
        s = seg.start % 60
        ts = f"{h:02d}:{m:02d}:{s:05.2f}"
        md_lines.append(f"## [{ts}] {seg.text.strip()}")
        md_lines.append("")

    elapsed = time.time() - start
    speed = info.duration / elapsed if elapsed > 0 else 0
    log(f"  完成: {seg_count} segments, 用时 {elapsed:.1f}s ({speed:.2f}× realtime)")

    # 写文件
    content = '\n'.join(md_lines)
    write_file_safely(output_path, content)
    log(f"  写入: {output_path.name}")


def main():
    parser = argparse.ArgumentParser(description='单段录音 ASR 转录')
    parser.add_argument('--input', required=True, help='输入 mp3 路径')
    parser.add_argument('--output', help='输出 md 路径(默认 .cache/raw/{filename}.md)')
    parser.add_argument('--model', default='large-v3', help='模型大小(large-v3/large-v3-turbo)')
    args = parser.parse_args()

    mp3_path = Path(args.input).resolve()
    if not mp3_path.exists():
        print(f"ERROR: 输入文件不存在: {mp3_path}", file=sys.stderr)
        sys.exit(1)

    base = get_base_dir()
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        cache_dir = base / '.cache' / 'raw'
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_path = cache_dir / f"{mp3_path.stem}.md"

    transcribe_segment(mp3_path, output_path, args.model)


if __name__ == '__main__':
    main()
