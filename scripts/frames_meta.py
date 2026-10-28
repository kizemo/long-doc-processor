#!/usr/bin/env python3
"""frames_meta.py — 把各种来源的关键帧清单统一成一种结构。

为什么需要它（2026-10-24 实测）
--------------------------------
Phase 1.8 的三个脚本（`_stage1_score.py` / `_stage2_decide.py` /
`_crop_insert_frames.py`）都直接 `json.loads(frames.json)` 然后当**列表**用：

    frames = {f["id"]: f for f in json.loads(frames_json.read_text(...))}

但本技能自己的上游（claude-real-video）写出来的是**另一种形状**：

    {"frames": [{"file": "frame_001.jpg",
                 "timestamp_sec": 0.021,
                 "timestamp": "00:00:00.021",
                 "selection_reason": "first"}]}

——是 dict、字段叫 `file`/`timestamp_sec`、没有 `id`、也没有 `ocr_text`。

于是 Phase 1.8 一跑就 `KeyError: 'id'`，而这个错误在脚本的 try 之外，
直接把整条 Stage 1 打断。**生产者与消费者对同一个文件的格式认知不一致**，
是这类流水线最典型的病。

本模块提供唯一的读取入口，把两种形状都归一化成：

    [{"id": "frame_001", "timestamp": 0.021, "timestamp_str": "00:00:00.021",
      "file": "frame_001.jpg", "ocr_text": "..."}]

ocr_text 从 OCR 目录里按 `<id>.ocr.txt` 取（`scripts/ocr_images.py` 的产物）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _parse_timestamp_str(value) -> float:
    """'HH:MM:SS.mmm' -> 秒。"""
    if not value:
        return 0.0
    m = re.match(r"^(\d+):(\d{2}):(\d{2}(?:\.\d+)?)$", str(value).strip())
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def load_frames_meta(frames_json: Path, frames_dir: Path | None = None,
                     ocr_dir: Path | None = None) -> list[dict]:
    """Load and normalize frame metadata.

    Args:
        frames_json: frames.json (either a list, or {"frames": [...]}).
        frames_dir: optional dir holding the actual images (for ocr lookup).
        ocr_dir: optional dir holding `<id>.ocr.txt` produced by ocr_images.py.

    Returns:
        list of dicts with keys: id, timestamp, timestamp_str, file, ocr_text.
    """
    raw = json.loads(Path(frames_json).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("frames") or raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file_name = item.get("file") or item.get("name") or ""
        fid = item.get("id")
        if not fid:
            fid = Path(str(file_name)).stem or f"frame_{len(out) + 1:05d}"
        ts = item.get("timestamp_sec")
        if ts is None:
            ts = item.get("timestamp")
            if isinstance(ts, str):
                ts = _parse_timestamp_str(ts)
            elif ts is None:
                ts = 0.0
        ts = float(ts or 0.0)
        ts_str = item.get("timestamp")
        if not isinstance(ts_str, str):
            ts_str = ""
        ocr_text = item.get("ocr_text") or ""
        if not ocr_text and ocr_dir:
            p = Path(ocr_dir) / f"{fid}.ocr.txt"
            if p.exists():
                try:
                    ocr_text = p.read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    ocr_text = ""
        out.append({
            "id": str(fid),
            "timestamp": ts,
            "timestamp_str": ts_str,
            "file": file_name or f"{fid}.jpg",
            "ocr_text": ocr_text,
        })
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="归一化 frames.json")
    ap.add_argument("frames_json", type=Path)
    ap.add_argument("--ocr-dir", type=Path)
    args = ap.parse_args()
    metas = load_frames_meta(args.frames_json, ocr_dir=args.ocr_dir)
    print(f"{len(metas)} frames")
    for m in metas[:5]:
        print(f"  {m['id']}  t={m['timestamp']:.1f}s  ocr={len(m['ocr_text'])} chars")
