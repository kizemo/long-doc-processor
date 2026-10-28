#!/usr/bin/env python3
"""llm_env.py — 把本机运行时配置里的 LLM provider 导出成 Anthropic SDK 认的环境变量。

为什么需要它（2026-10-24 实测发现的静默失效）
----------------------------------------------
本技能的 LLM 步骤全部走 `_llm_vision.call_vision` → Anthropic SDK。
SDK 只认两个环境变量：`ANTHROPIC_BASE_URL` 和 `ANTHROPIC_API_KEY`。

但本机**没有导出**这两个变量 —— 凭据在运行时自己的 `config.yaml` 里：

    provider:
      minimax:
        npm: '@ai-sdk/anthropic'      # 协议就是 Anthropic messages
        options:
          apiKey: <...>
          baseURL: https://.../llm/v1

后果不是报错，而是**静默无操作**：

    call_vision()  → 没有 ANTHROPIC_API_KEY → print + return ""
    purify_v4_4_hierarchical.py  → 「LLM 返回空」→ continue → 3 次重试全空
                                → fail-soft 保留原文 → cleaned.md 其实没净化过

一份「没净化过的 cleaned.md」会被当成合格产物交付，这是比报错更糟的失败模式。

本脚本把 config.yaml 里的 provider 映射成 SDK 认的环境变量，并**显式检查**
映射结果，避免下一个「静默无操作」。

用法
----
    import sys; sys.path.insert(0, "<skill>/scripts")
    import llm_env
    info = llm_env.apply()          # 导出环境变量
    model = llm_env.default_model()  # -> "MiniMax-M3"
    if not info["ok"]:
        raise SystemExit(info["error"])

命令行：
    python scripts/llm_env.py --check     # 只打印状态（不打印 key）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 候选配置文件路径，按优先级排列。
# 1) 显式指定：环境变量 LDP_LLM_CONFIG
# 2) 运行时数据目录（MiniMax Code / MiniMax Agent）：<dataDir>/config.yaml
# 3) 用户主目录下的 .minimax/.minimax/config.yaml
def _candidate_paths() -> list[Path]:
    out: list[Path] = []
    explicit = os.environ.get("LDP_LLM_CONFIG")
    if explicit:
        out.append(Path(explicit))
    home = Path.home()
    for base in (
        home / ".minimax" / ".minimax",
        home / ".minimax",
        Path("E:/Users/Duanyi/.minimax/.minimax"),
        Path("C:/Users/Duanyi/.minimax/.minimax"),
    ):
        out.append(base / "config.yaml")
    # 去重且保序
    seen = set()
    uniq = []
    for p in out:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def _load_config() -> tuple[dict | None, str]:
    """Load the first readable config.yaml. Returns (config, path)."""
    for path in _candidate_paths():
        try:
            if not path.exists():
                continue
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data, str(path)
        except Exception as exc:  # pragma: no cover - environment dependent
            return None, "%s (%s)" % (path, exc)
    return None, ""


def _pick_provider(config: dict) -> tuple[str, dict] | tuple[None, str]:
    """Pick the provider to use.

    Preference order:
      1. the provider named by LDP_LLM_PROVIDER
      2. the provider of defaultModel ("<provider>/<model>")
      3. the single provider in the file
    """
    providers = config.get("provider") or {}
    if not isinstance(providers, dict) or not providers:
        return None, "config.yaml 里没有 provider 段"

    wanted = os.environ.get("LDP_LLM_PROVIDER")
    if wanted and wanted in providers:
        return wanted, providers[wanted]

    default_model = str(config.get("defaultModel") or "")
    if "/" in default_model:
        pname = default_model.split("/", 1)[0]
        if pname in providers:
            return pname, providers[pname]

    if len(providers) == 1:
        name = next(iter(providers))
        return name, providers[name]

    # Several providers and no default: prefer an anthropic-protocol one,
    # because the skill's scripts speak the Anthropic messages API.
    for name, prov in providers.items():
        if isinstance(prov, dict) and "anthropic" in str(prov.get("npm", "")).lower():
            return name, prov
    return None, "无法确定 provider（请设 LDP_LLM_PROVIDER）"


def default_model(config: dict | None = None, provider_name: str | None = None) -> str:
    """Return the model id to pass to the Anthropic SDK."""
    if config is None:
        config, _ = _load_config()
    if not config:
        return os.environ.get("LDP_LLM_MODEL", "MiniMax-M3")
    providers = config.get("provider") or {}
    name = provider_name
    if not name:
        picked = _pick_provider(config)
        name = picked[0] if picked[0] else None
    if not name or name not in providers:
        return os.environ.get("LDP_LLM_MODEL", "MiniMax-M3")
    prov = providers[name] or {}
    models = prov.get("models") or {}
    order = prov.get("model_order") or []
    for candidate in order:
        if candidate in models:
            return candidate
    if models:
        return next(iter(models))
    return os.environ.get("LDP_LLM_MODEL", "MiniMax-M3")


def apply(model: str | None = None) -> dict:
    """Export ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY from the local config.

    Returns a status dict. It never contains the key itself.
    """
    config, path = _load_config()
    if not config:
        return {
            "ok": False,
            "error": "找不到可读的 config.yaml（尝试过: %s）" %
                     ", ".join(str(p) for p in _candidate_paths()),
            "config_path": path,
        }

    picked = _pick_provider(config)
    if picked[0] is None:
        return {"ok": False, "error": picked[1], "config_path": path}

    provider_name, provider = picked
    options = provider.get("options") or {}
    api_key = options.get("apiKey")
    base_url = options.get("baseURL")
    if not api_key:
        return {"ok": False, "error": "provider %s 没有 apiKey" % provider_name,
                "config_path": path}
    if not base_url:
        return {"ok": False, "error": "provider %s 没有 baseURL" % provider_name,
                "config_path": path}

    npm = str(provider.get("npm") or "")
    if "anthropic" not in npm.lower():
        return {
            "ok": False,
            "error": "provider %s 的协议是 %s，本技能的脚本走 Anthropic messages API，"
                     "协议不匹配" % (provider_name, npm or "(未声明)"),
            "config_path": path,
        }

    # 占位符密钥检测：运行时配置里常常留的是 "null"/"none"/空串这种占位，
    # 真跑起来会拿到 401 "token is required"。在这里就说清楚，
    # 不要等到流水线跑到一半才发现。
    if len(str(api_key)) < 20:
        return {
            "ok": False,
            "error": "provider %s 的 apiKey 是占位符(长度 %d),不是真实凭据 —— "
                     "用这个配置调 API 会拿到 401 'token is required'。"
                     "请手工导出真实的 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL。"
                     % (provider_name, len(str(api_key))),
            "config_path": path,
        }

    os.environ["ANTHROPIC_API_KEY"] = str(api_key)
    os.environ["ANTHROPIC_BASE_URL"] = str(base_url)
    chosen = model or default_model(config, provider_name)
    os.environ.setdefault("LDP_LLM_MODEL", chosen)

    return {
        "ok": True,
        "provider": provider_name,
        "base_url": str(base_url),
        "model": chosen,
        "config_path": path,
    }


def main() -> int:
    if "--check" in sys.argv:
        info = apply()
        if info.get("ok"):
            print("OK  provider=%s  model=%s" % (info["provider"], info["model"]))
            print("    base_url = %s" % info["base_url"])
            print("    config   = %s" % info["config_path"])
            print("    ANTHROPIC_API_KEY 已导出（%d 字符，不显示内容）"
                  % len(os.environ.get("ANTHROPIC_API_KEY", "")))
            return 0
        print("FAIL: %s" % info.get("error"))
        return 1

    info = apply()
    print(info.get("error") or
          "provider=%s model=%s base_url=%s" %
          (info["provider"], info["model"], info["base_url"]))
    return 0 if info.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
