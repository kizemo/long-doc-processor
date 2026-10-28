#!/usr/bin/env python3
"""_stage2_decide.py — Stage 2: 逐帧 LLM 决策

输入 top8.json (Stage 1 输出) + audio_paragraphs.md + cleaned.md,
对每个候选帧调一次 LLM,返回 {h3_target, crop_box, caption, score}。
LLM 看实际帧 + ASR 上下文,确认/修改 Stage 1 的 h3_hint。

Usage:
    python _stage2_decide.py \\
        --frames-dir output/test-crv2/frames \\
        --frames-json output/test-crv2/frames.json \\
        --top8-json output/test-crv2/top8.json \\
        --asr-md output/test-crv2/audio_paragraphs.md \\
        --cleaned-md output/<stem>_cleaned.md \\
        --output-json output/test-crv2/crop_decisions.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts._llm_vision import call_vision  # absolute import per R2
from scripts.frames_meta import load_frames_meta  # noqa: E402


PROMPT_TEMPLATE = """你是视觉内容分析专家。请分析这张视频关键帧,并决定它对应讲座哪个 H3 子节。

注意:已从 OCR 文本初步判断 h3_hint = "{h3_hint}",你可以确认或改选其它 H3。

裁剪规则:
- 必须排除讲师人像/头像/半身像
- 必须排除 PPT chrome/logo/水印/页眉页脚
- 必须保留主题内容(公式/表格/案例图/操作界面/数据图)
- 若整图无清晰主题,score=0,不裁剪不插入

帧 ID: {frame_id}
时间戳: {timestamp}s
ASR 上下文(±30s):
{asr_context}

cleaned.md 全文:
---
{full_md}
---

输出 JSON(单选):
{{"frame_id": "{frame_id}", "h3_target": "1.2", "crop_box": {{"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.7}}, "caption": "...", "score": 0.85}}
"""


def build_stage2_prompt(frame_meta: dict, h3_hint: str, asr_context: str, full_md: str) -> str:
    return PROMPT_TEMPLATE.format(
        frame_id=frame_meta["id"],
        timestamp=frame_meta.get("timestamp", 0),
        h3_hint=h3_hint or "(无 hint)",
        asr_context=asr_context or "(ASR 上下文不可用)",
        full_md=full_md[:8000],  # 防 prompt 过长,截断到 8K
    )


def parse_stage2_response(llm_response: str) -> dict | None:
    """从 LLM 响应解析 JSON 对象。缺字段返回 None。"""
    text = llm_response.strip()

    # 提取 ```json ... ``` 块
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    # 必填字段
    required = ["frame_id", "h3_target", "crop_box", "caption", "score"]
    if not all(k in data for k in required):
        return None

    # crop_box 必须含 x, y, w, h
    cb = data["crop_box"]
    if not all(k in cb for k in ("x", "y", "w", "h")):
        return None

    # score 转 float
    try:
        data["score"] = float(data["score"])
    except (TypeError, ValueError):
        return None

    # crop_box 值转 float
    try:
        data["crop_box"] = {k: float(v) for k, v in cb.items()}
    except (TypeError, ValueError):
        return None

    return data


def get_asr_context(asr_path: Path, timestamp: int, window: int = 30) -> str:
    """从 audio_paragraphs.md 抽取 timestamp ±window 秒的段落。"""
    if not asr_path.exists():
        return ""
    text = asr_path.read_text(encoding="utf-8")
    # 段落化(以空行分隔),每段可能含时间戳 [mm:ss] 或 [hh:mm:ss]
    paragraphs = re.split(r"\n\s*\n", text)
    matched = []
    for p in paragraphs:
        # 找段落中第一个时间戳
        m = re.search(r"\[?(\d+):(\d+)(?::(\d+))?\]?", p)
        if m:
            parts = [int(x) for x in m.groups() if x]
            if len(parts) == 3:
                ts = parts[0] * 3600 + parts[1] * 60 + parts[2]
            elif len(parts) == 2:
                ts = parts[0] * 60 + parts[1]
            else:
                continue
            if abs(ts - timestamp) <= window:
                matched.append(p.strip())
    return "\n\n".join(matched[:3])  # 最多 3 段


def run_stage2(frames_dir: Path, frames_json: Path, top8_json: Path,
               asr_path: Path, full_md_path: Path, output_json: Path,
               score_threshold: float = 0.65,
               ocr_dir: Path | None = None) -> list[dict]:
    """对 top8 中每帧调 LLM,写 crop_decisions.json。

    Returns:
        决策 list,过滤 score < threshold
    """
    frames = {f["id"]: f for f in load_frames_meta(frames_json, ocr_dir=ocr_dir)}
    top8 = json.loads(top8_json.read_text(encoding="utf-8"))
    full_md = full_md_path.read_text(encoding="utf-8")

    decisions = []
    for cand in top8:
        fid = cand["frame_id"]
        h3_hint = cand.get("h3_hint", "")
        if fid not in frames:
            print(f"SKIP {fid}: not in frames.json")
            continue

        frame_meta = frames[fid]
        ts = frame_meta.get("timestamp", 0)
        asr_ctx = get_asr_context(asr_path, ts)

        # 找图片路径(.jpg 或 .png)
        img_path = frames_dir / f"{fid}.jpg"
        if not img_path.exists():
            img_path = frames_dir / f"{fid}.png"
        if not img_path.exists():
            print(f"SKIP {fid}: image file not found")
            continue

        prompt = build_stage2_prompt(frame_meta, h3_hint, asr_ctx, full_md)
        response = call_vision(prompt, [img_path])

        decision = parse_stage2_response(response)
        if decision is None:
            print(f"SKIP {fid}: invalid LLM response")
            continue

        if decision["score"] < score_threshold:
            print(f"SKIP {fid}: score {decision['score']} < {score_threshold}")
            continue

        decisions.append(decision)
        print(f"OK {fid} → H3 {decision['h3_target']} (score {decision['score']})")

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\nDONE Stage 2: {len(decisions)} decisions → {output_json}")
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-dir", required=True, type=Path)
    parser.add_argument("--frames-json", required=True, type=Path)
    parser.add_argument("--top8-json", required=True, type=Path)
    parser.add_argument("--asr-md", required=True, type=Path)
    parser.add_argument("--cleaned-md", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--ocr-dir", type=Path, help="关键帧 OCR 文本目录(<id>.ocr.txt)")
    args = parser.parse_args()
    run_stage2(
        args.frames_dir, args.frames_json, args.top8_json,
        args.asr_md, args.cleaned_md, args.output_json,
        ocr_dir=args.ocr_dir
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())