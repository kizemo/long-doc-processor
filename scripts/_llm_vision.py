#!/usr/bin/env python3
"""_llm_vision.py — 通用多模态 LLM 调用封装

调用 Anthropic Claude vision API,支持图片附件 + 文本 prompt。
未来可扩展到 GPT-4V(GPT-4o)作为 fallback。

Usage:
    from _llm_vision import call_vision
    response = call_vision("describe this", [Path("img.jpg")])

**2026-10-24 行为变更（重要）**
--------------------------------
以前：后端不可用时返回空字符串。

    call_vision(...) -> "" (打印一行 ERROR,继续跑)

后果是**静默无操作**：净化步骤把空串当成"LLM 说了但没内容"，
fail-soft 保留原文，于是流水线"成功"结束，产出一份其实**根本没净化过**的
cleaned.md，而且没有任何报错。调用方（purify / smooth / strip_*）全都
`except Exception: 保留原文`，所以从外面看不出发生过任何事。

一份没净化过的文档被当成合格产物交付，比直接报错更糟。

现在：后端不可用时抛 `LLMBackendError`，并且带上**可执行的修复指引**。
调用方现有的 `except Exception` 依然会 fail-soft 保留原文（行为不变），
但日志里会出现真正的原因（"没设 ANTHROPIC_API_KEY"/"端点 401"），
而不是一句没头没脑的"返回空"。

另外新增：
- `LDP_LLM_MODEL` 环境变量可覆盖默认模型（默认 `claude-sonnet-4-5`）
- `backend_status()` 探活，给流水线一个"后端到底通不通"的明确答案
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_MODEL = os.environ.get("LDP_LLM_MODEL", "claude-sonnet-4-5")

# 本次进程内累计的调用失败次数。流水线结束时可以据此判断
# "LLM 步骤是不是根本没跑"。
LLM_CALL_FAILURES = 0
LLM_CALL_OK = 0


class LLMBackendError(RuntimeError):
    """LLM 后端不可用 —— 必须让调用方知道,不能静默返回空串。"""


def _resolve_model(model: str | None) -> str:
    if model:
        return model
    return os.environ.get("LDP_LLM_MODEL") or DEFAULT_MODEL


def _require_credentials() -> str:
    """取 API key;取不到就抛 LLMBackendError(带修复指引)。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMBackendError(
            "LLM 后端不可用:未设置 ANTHROPIC_API_KEY。"
            "两种修法:(1) 导出 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL;"
            "(2) 用 `python scripts/llm_env.py --check` 检查本机运行时配置里的 provider。"
            "注意:缺 key 时本脚本会抛错而不是静默返回空串 —— "
            "否则净化步骤会 fail-soft 保留原文,产出一份没净化过的 cleaned.md。")
    return api_key


def backend_status() -> dict:
    """探活:后端到底通不通。返回 {'ok': bool, 'reason': str, 'model': str}。"""
    model = _resolve_model(None)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"ok": False, "reason": "未设置 ANTHROPIC_API_KEY", "model": model}
    try:
        out = call_vision("只回复一个字：好", [])
        return {"ok": bool(out and out.strip()),
                "reason": "" if out and out.strip() else "后端返回空",
                "model": model}
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "model": model}


def call_vision(prompt: str, image_paths: list[Path],
                model: str | None = None) -> str:
    """调 Anthropic vision API,返回 LLM 文本响应。

    Args:
        prompt: 文本 prompt
        image_paths: 图片绝对路径列表(可为空,纯文本 LLM 调用)
        model: 模型 ID;None 时用 LDP_LLM_MODEL / 默认 claude-sonnet-4-5

    Returns:
        LLM 响应文本。

    Raises:
        LLMBackendError: 后端不可用(没有 key / SDK 没装 / 请求失败)。
            调用方可以选择 fail-soft,但**必须把异常打出来**。
    """
    global LLM_CALL_FAILURES, LLM_CALL_OK

    model = _resolve_model(model)

    try:
        from anthropic import Anthropic
    except ImportError as exc:
        LLM_CALL_FAILURES += 1
        raise LLMBackendError(
            "LLM 后端不可用:anthropic SDK 没装(%s)。装它:pip install anthropic" % exc)

    api_key = _require_credentials()

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
        text = msg.content[0].text if msg.content else ""
        if not text.strip():
            LLM_CALL_FAILURES += 1
            raise LLMBackendError(
                "LLM 后端返回了空内容(model=%s)。可能是 max_tokens 不够或模型拒答。"
                % model)
        LLM_CALL_OK += 1
        return text
    except LLMBackendError:
        raise
    except Exception as e:
        LLM_CALL_FAILURES += 1
        raise LLMBackendError("LLM 调用失败(model=%s): %s" % (model, e)) from e


if __name__ == "__main__":
    st = backend_status()
    print("backend ok=%s model=%s %s" % (st["ok"], st["model"], st["reason"]))
    sys.exit(0 if st["ok"] else 1)
