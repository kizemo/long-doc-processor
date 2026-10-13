#!/usr/bin/env python3
"""_llm_vision.py — 通用多模态 LLM 调用封装

调用 Anthropic Claude vision API,支持图片附件 + 文本 prompt。
未来可扩展到 GPT-4V(GPT-4o)作为 fallback。

Usage:
    from _llm_vision import call_vision
    response = call_vision("describe this", [Path("img.jpg")])
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def call_vision(prompt: str, image_paths: list[Path], model: str = "claude-sonnet-4-5") -> str:
    """调 Anthropic vision API,返回 LLM 文本响应。

    Args:
        prompt: 文本 prompt
        image_paths: 图片绝对路径列表(可为空,纯文本 LLM 调用)
        model: 模型 ID,默认 claude-sonnet-4-5

    Returns:
        LLM 响应文本;失败/无 key 时返回空字符串
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
        return ""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return ""

    import base64

    client = Anthropic(api_key=api_key)

    # 构造消息
    content = [{"type": "text", "text": prompt}]
    for img_path in image_paths:
        if not img_path.exists():
            print(f"WARN: image not found: {img_path}", file=sys.stderr)
            continue
        # 推断 mime
        ext = img_path.suffix.lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        img_bytes = img_path.read_bytes()
        img_b64 = base64.standard_b64encode(img_bytes).decode("ascii")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": img_b64,
            }
        })

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        return msg.content[0].text if msg.content else ""
    except Exception as e:
        print(f"ERROR: vision API call failed: {e}", file=sys.stderr)
        return ""