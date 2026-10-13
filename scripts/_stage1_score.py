#!/usr/bin/env python3
"""_stage1_score.py — Stage 1: LLM 评分筛选(OCR-only)

输入 frames.json (N 帧) + cleaned.md (H3 列表),
输出 top8.json (Top-8 候选帧 + h3_hint)。

Usage:
    python _stage1_score.py \\
        --frames-json output/test-crv2/frames.json \\
        --cleaned-md output/<stem>_cleaned.md \\
        --output-json output/test-crv2/top8.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts._llm_vision import call_vision  # absolute import — pytest 把 rootdir 加进 sys.path, scripts 作为 namespace package


PROMPT_TEMPLATE = """你是电商培训视频内容匹配专家。下面是视频中 {n_frames} 个候选关键帧(每帧:时间戳 + OCR文本)
和讲座净化后的 {n_h3} 个 H3 子节标题。请为每帧评估"对讲座哪个 H3 子节有视觉辅助价值"。

排除规则(必须遵守):
- 讲师头像 / 半身像 / 头像特写
- 片头片尾 / 空白过渡帧
- 仅含 PPT chrome / logo / 水印
- OCR 文本与所有 H3 主题均不相关

评分规则:
- 1.0: 完美匹配,帧内容是该 H3 主题的核心视觉(公式图/案例截图/操作步骤)
- 0.8: 强相关,帧内容是 H3 的辅助视觉(对比图/数据图/示例)
- 0.6: 弱相关,可有可无
- 0.0-0.5: 不相关或装饰帧

输出 JSON 数组(按 score 降序,只返回 score ≥ 0.65 的帧):
[{{"frame_id": "...", "score": 0.85, "h3_hint": "1.2", "rationale": "..."}}]

若所有帧 score < 0.65,返回 []。

--- 帧数据 ---
{frames_block}

--- H3 子节 ---
{h3_block}
"""


def build_stage1_prompt(frames_meta: list[dict], h3_titles: list[str]) -> str:
    """构造 Stage 1 prompt。frames_meta 含 {id, timestamp, ocr_text}。"""
    frames_block = "\n".join(
        f"frame_id={f['id']}, timestamp={f.get('timestamp', 0)}s, ocr={f.get('ocr_text', '') or '(OCR 缺失)'}"
        for f in frames_meta
    )
    h3_block = "\n".join(f"{i+1}. {h}" for i, h in enumerate(h3_titles))
    return PROMPT_TEMPLATE.format(
        n_frames=len(frames_meta),
        n_h3=len(h3_titles),
        frames_block=frames_block,
        h3_block=h3_block,
    )


def parse_stage1_response(llm_response: str) -> list[dict]:
    """从 LLM 响应解析 JSON 数组。

    容错:
    - 响应包在 ```json ... ``` 内 → 提取 JSON 块
    - 非法 JSON → 返回 []
    - frame_id 缺失 / score 非数字 → 跳过该条
    """
    text = llm_response.strip()

    # 提取 ```json ... ``` 块
    code_block_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1)

    # 直接尝试 JSON 解析
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if "frame_id" not in item or "score" not in item:
            continue
        try:
            score = float(item["score"])
        except (TypeError, ValueError):
            continue
        cleaned.append({
            "frame_id": str(item["frame_id"]),
            "score": score,
            "h3_hint": str(item.get("h3_hint", "")),
            "rationale": str(item.get("rationale", "")),
        })
    return cleaned


def run_stage1(frames_json: Path, cleaned_md: Path, output_json: Path,
               max_count: int = 8, score_threshold: float = 0.65) -> list[dict]:
    """读 frames.json + cleaned.md,调 LLM,filter score,写 top8.json。

    Returns:
        Top-N 候选帧 list,按 score 降序
    """
    frames = json.loads(frames_json.read_text(encoding="utf-8"))
    md_text = cleaned_md.read_text(encoding="utf-8")

    # 提取 H3 标题列表
    h3_titles = re.findall(r"^###\s+(\d+\.\d+\s+.*?)$", md_text, re.MULTILINE)
    if not h3_titles:
        print("WARN: no H3 found in cleaned.md", file=sys.stderr)
        return []

    prompt = build_stage1_prompt(frames, h3_titles)
    response = call_vision(prompt, [])  # Stage 1 不附图,只看 OCR 文本
    candidates = parse_stage1_response(response)

    # filter + sort + truncate
    candidates = [c for c in candidates if c["score"] >= score_threshold]
    candidates.sort(key=lambda x: x["score"], reverse=True)
    candidates = candidates[:max_count]

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"OK Stage 1: {len(candidates)} candidates → {output_json}")
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-json", required=True, type=Path)
    parser.add_argument("--cleaned-md", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--max-count", type=int, default=8)
    args = parser.parse_args()
    run_stage1(args.frames_json, args.cleaned_md, args.output_json, max_count=args.max_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())