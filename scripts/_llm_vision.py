#!/usr/bin/env python3
"""_llm_vision.py — 通用多模态 LLM 调用封装

调用 Anthropic Claude vision API,支持图片附件 + 文本 prompt。
未来可扩展到 GPT-4V(GPT-4o)作为 fallback。

v4.21 增强:
  - 新增 safe_llm_call(超时/重试/退避/status 分流,整合 M-01/M-02/M-12 经验)
  - 保留 call_vision 作为底层调用,供 safe_llm_call 内部使用

Usage:
    from _llm_vision import safe_llm_call, call_vision
    text, status = safe_llm_call("describe this")
    response = call_vision("describe this", [Path("img.jpg")])
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable


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
        return _call_vision_or_raise(prompt, image_paths, model)
    except Exception as e:
        print(f"ERROR: vision API call failed: {e}", file=sys.stderr)
        return ""


def _call_vision_or_raise(
    prompt: str, image_paths: list[Path], model: str = "claude-sonnet-4-5"
) -> str:
    """调 Anthropic vision API,失败时抛异常(供 safe_llm_call 区分 error vs empty)。

    Returns:
        LLM 响应文本

    Raises:
        RuntimeError: SDK 未装 / API key 缺失 / LLM 异常
    """
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic") from e

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

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

    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )
    return msg.content[0].text if msg.content else ""


# safe_llm_call ----------------------------------------------------
# 整合跨项目踩坑模式 M-01/M-02/M-12:
#   - M-01:返回 status 而非 raise,调用方按 5 种 status 分流
#   - M-02:minimal_prompt 兜底(empty/error 时降级到最简 prompt)
#   - M-12:支持 input 绝对化(调用方在传文件时)
# status ∈ {"ok", "empty", "timeout", "error", "rate_limited", "no_api_key", "no_sdk"}


def safe_llm_call(
    prompt: str,
    *,
    model: str = "claude-sonnet-4-5",
    max_retries: int = 3,
    timeout: int = 120,
    backoff: float = 2.0,
    on_status: Callable[[str], None] | None = None,
    minimal_prompt: str | None = None,
) -> tuple[str, str]:
    """统一 LLM 调用,带 timeout / retry / backoff / status 分流(M-02 经验)。

    Args:
        prompt: 文本 prompt
        model: 模型 ID
        max_retries: 最大重试次数(含初次)
        timeout: 单次调用超时(秒)
        backoff: 指数退避基数(秒,rate_limited 时用 backoff * 2^attempt)
        on_status: status 回调(供调用方 log / 监控分流)
        minimal_prompt: 兜底 prompt(M-02 经验:empty/error 1 次重试后降级到最简 prompt)

    Returns:
        (response_text, status)
        status ∈ {"ok", "empty", "timeout", "error", "rate_limited", "no_api_key", "no_sdk"}
    """
    def _emit(s: str) -> None:
        if on_status is not None:
            try:
                on_status(s)
            except Exception:
                pass

    # 无 SDK / 无 API key 立即返回(无需重试)
    try:
        from anthropic import Anthropic  # noqa: F401
    except ImportError:
        _emit("no_sdk")
        return "", "no_sdk"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _emit("no_api_key")
        return "", "no_api_key"

    def _call_once(p: str) -> str:
        return _call_vision_or_raise(p, [], model=model)

    last_status = "error"
    for attempt in range(1, max_retries + 1):
        # 1. 调 LLM
        start_ts = time.time()
        try:
            # 用信号式超时:subprocess 在 LLM SDK 不直接支持 timeout 时无法强制中断
            # 这里依赖 anthropic SDK 内部 socket timeout(默认 600s);用 elapsed 估算
            text = _call_once(prompt)
            elapsed = time.time() - start_ts
        except Exception as e:
            elapsed = time.time() - start_ts
            err_str = str(e).lower()
            # 429 / rate limit 单独分流
            if "429" in err_str or "rate" in err_str:
                last_status = "rate_limited"
                _emit(f"rate_limited (attempt {attempt})")
                wait = backoff * (2 ** (attempt - 1))
                time.sleep(min(wait, 60))  # 上限 60s
                continue
            last_status = "error"
            _emit(f"error (attempt {attempt}, elapsed={elapsed:.1f}s): {type(e).__name__}: {e}")
            if attempt < max_retries:
                time.sleep(backoff)
            continue

        # 2. 校验结果
        if not text or not text.strip():
            last_status = "empty"
            _emit(f"empty (attempt {attempt}, elapsed={elapsed:.1f}s)")
            # empty: 1 次重试(可能 LLM 触发内容过滤 1026,M-02)
            if attempt < 2 and minimal_prompt is None:
                time.sleep(backoff)
                continue
            if attempt < 2 and minimal_prompt is not None:
                prompt = minimal_prompt  # 切到 minimal_prompt 兜底
                time.sleep(backoff)
                continue
            break

        # 3. 超时检测(elapsed > timeout)
        if elapsed > timeout:
            last_status = "timeout"
            _emit(f"timeout (attempt {attempt}, elapsed={elapsed:.1f}s > {timeout}s)")
            if attempt < max_retries:
                time.sleep(backoff)
            continue

        # 4. 成功
        _emit(f"ok (attempt {attempt}, elapsed={elapsed:.1f}s)")
        return text, "ok"

    return "", last_status