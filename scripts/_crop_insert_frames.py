#!/usr/bin/env python3
"""_crop_insert_frames.py — Stage 3: PIL 裁剪 + Markdown 注入

本脚本实现 long-doc-processor Phase 1.8 的 Stage 3 (脚本裁剪与插入)。
由 Stage 1 (LLM 评分) 和 Stage 2 (LLM 决策) 的 JSON 输出驱动。

Usage:
    python _crop_insert_frames.py \\
        --frames-dir output/test-crv2/frames \\
        --frames-json output/test-crv2/frames.json \\
        --decisions-json output/test-crv2/crop_decisions.json \\
        --cleaned-md output/<stem>_cleaned.md \\
        --output-dir output/

Outputs:
    output/img/fig-crop-NN-{semantic}.jpg   (≤8 张,每张 ≤ 200KB)
    output/<stem>_cleaned.md                 (注入 ![]() 行)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image


def crop_box_to_pixels(crop_box: dict, frame_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """把 LLM 返回的 0-1 归一化 crop_box 转为像素坐标,带 5% padding 内缩 + 边界 clamp。

    Args:
        crop_box: {"x": float, "y": float, "w": float, "h": float},每个值 ∈ [0, 1]
        frame_size: (W, H) 原帧尺寸

    Returns:
        (x, y, w, h) 像素坐标,已 clamp 到 [0, W] / [0, H],5% padding 内缩
    """
    W, H = frame_size
    # clamp 归一化值到 [0, 1]
    x_norm = max(0.0, min(1.0, crop_box.get("x", 0)))
    y_norm = max(0.0, min(1.0, crop_box.get("y", 0)))
    w_norm = max(0.0, min(1.0, crop_box.get("w", 1)))
    h_norm = max(0.0, min(1.0, crop_box.get("h", 1)))

    # 转像素 + 5% padding 内缩 (各边各缩 5% 帧宽/高)
    pad_w = int(0.05 * W)
    pad_h = int(0.05 * H)
    x = int(x_norm * W) + pad_w
    y = int(y_norm * H) + pad_h
    w = int(w_norm * W) - 2 * pad_w
    h = int(h_norm * H) - 2 * pad_h

    # 边界 clamp — 保证 w/h ≥ 1 (即使 crop_box 严重越界也保留最小有效区域)
    if x < 0:
        x = 0
    if y < 0:
        y = 0
    if x + w > W:
        w = W - x
        if w < 1:
            x = max(0, W - 1)
            w = 1
    if y + h > H:
        h = H - y
        if h < 1:
            y = max(0, H - 1)
            h = 1

    return (x, y, w, h)


def crop_frame(frame_path: Path, crop_box: dict, output_path: Path,
               max_size: tuple[int, int] = (800, 600),
               max_bytes: int = 200 * 1024) -> int:
    """PIL 读帧 → 裁剪 → resize → JPEG 压缩到 ≤ max_bytes。

    Args:
        frame_path: 原帧路径
        crop_box: LLM 返回的 0-1 归一化 crop_box
        output_path: 输出 JPEG 路径
        max_size: thumbnail 上限 (W, H),保持 aspect ratio
        max_bytes: 输出文件大小硬上限,默认 200KB

    Returns:
        写入字节数
    """
    img = Image.open(frame_path).convert("RGB")
    W, H = img.size
    x, y, w, h = crop_box_to_pixels(crop_box, (W, H))
    cropped = img.crop((x, y, x + w, y + h))
    cropped.thumbnail(max_size, Image.LANCZOS)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 循环降 quality 直到 ≤ max_bytes (起点 85)
    quality = 85
    while quality >= 50:
        cropped.save(output_path, "JPEG", quality=quality, optimize=True)
        size = output_path.stat().st_size
        if size <= max_bytes:
            return size
        quality -= 10
    return output_path.stat().st_size


def inject_to_md(md_path: Path, h3_target: str, image_rel_path: str, caption: str) -> bool:
    """把 ![]() 行注入到 cleaned.md 中 `### {h3_target}` 段首的下一行。

    Args:
        md_path: cleaned.md 路径
        h3_target: H3 编号,例如 "1.2"
        image_rel_path: 相对 md 的图片路径,例如 "img/foo.jpg"
        caption: alt 文本

    Returns:
        True 注入成功,False H3 不存在或注入失败
    """
    text = md_path.read_text(encoding="utf-8")
    # 兼容 \n 和 \r\n
    lines = text.splitlines(keepends=True)
    new_lines = []
    injected = False

    pattern = re.compile(rf"^###\s+{re.escape(h3_target)}\b")

    for i, line in enumerate(lines):
        new_lines.append(line)
        if not injected and pattern.match(line.lstrip()):
            # 段首: 紧跟 H3 行后插入
            insert_line = f"![{caption}]({image_rel_path})\n"
            # 行尾兼容: 若 H3 行是 \r\n, 新行也用 \r\n
            if line.endswith("\r\n"):
                insert_line = insert_line.rstrip("\n") + "\r\n"
            new_lines.append(insert_line)
            injected = True

    if not injected:
        return False

    md_path.write_text("".join(new_lines), encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3: PIL 裁剪 + Markdown 注入")
    parser.add_argument("--frames-dir", required=True, type=Path)
    parser.add_argument("--frames-json", required=True, type=Path)
    parser.add_argument("--decisions-json", required=True, type=Path)
    parser.add_argument("--cleaned-md", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    if not args.frames_json.exists():
        print(f"ERROR: frames.json not found: {args.frames_json}", file=sys.stderr)
        return 1
    if not args.decisions_json.exists():
        print(f"ERROR: crop_decisions.json not found: {args.decisions_json}", file=sys.stderr)
        return 1

    frames = {f["id"]: f for f in json.loads(args.frames_json.read_text(encoding="utf-8"))}
    decisions = json.loads(args.decisions_json.read_text(encoding="utf-8"))

    img_dir = args.output_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    inserted_count = 0
    for i, dec in enumerate(decisions, 1):
        if dec.get("score", 0) < 0.65:
            print(f"SKIP frame {dec.get('frame_id')}: score {dec.get('score')} < 0.65")
            continue

        frame_id = dec["frame_id"]
        if frame_id not in frames:
            print(f"SKIP frame {frame_id}: not in frames.json")
            continue

        frame_path = args.frames_dir / f"{frame_id}.jpg"
        if not frame_path.exists():
            # 尝试 .png 后缀
            frame_path = args.frames_dir / f"{frame_id}.png"
            if not frame_path.exists():
                print(f"SKIP frame {frame_id}: file not found")
                continue

        semantic = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", dec.get("caption", "frame"))[:30].strip("-") or "frame"
        out_name = f"fig-crop-{i:02d}-{semantic}.jpg"
        out_path = img_dir / out_name
        rel_path = f"img/{out_name}"

        try:
            size = crop_frame(frame_path, dec["crop_box"], out_path)
            print(f"OK frame {frame_id} → {out_name} ({size} bytes)")
        except Exception as e:
            print(f"SKIP frame {frame_id}: PIL error {e}")
            continue

        ok = inject_to_md(args.cleaned_md, dec["h3_target"], rel_path, dec.get("caption", ""))
        if ok:
            inserted_count += 1
            print(f"OK inject into H3 {dec['h3_target']}")
        else:
            print(f"WARN: H3 {dec['h3_target']} not found in cleaned.md, image kept in img/")

    print(f"\nDONE: inserted {inserted_count} images into {args.cleaned_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())