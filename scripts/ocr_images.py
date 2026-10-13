#!/usr/bin/env python3
"""ocr_images.py — 从 .docx/XMind/Markdown 目录抽取图片并 OCR。

Usage:
    python ocr_images.py <input> <output_dir>

实现策略：
- .docx：解压 word/media/ 下的图片；
- XMind：解压 attachments/ 与 content.json 中引用的图片；
- Markdown 目录：递归复制所有被引用的本地图片；
- OCR：默认调用 RapidOCR（若不可用，回退到占位实现并打印警告）。

OCR 文本输出到 <output_dir>/<image_name>.ocr.txt。
"""
from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path


IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def extract_from_docx(src: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    with zipfile.ZipFile(src) as zf:
        for name in zf.namelist():
            if name.startswith("word/media/") and Path(name).suffix.lower() in IMG_EXTS:
                target = out_dir / Path(name).name
                with zf.open(name) as src_f, target.open("wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)
                results.append(target)
    return results


def extract_from_xmind(src: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    with zipfile.ZipFile(src) as zf:
        for name in zf.namelist():
            if (name.startswith("attachments/") or "/image" in name) and Path(name).suffix.lower() in IMG_EXTS:
                target = out_dir / Path(name).name
                with zf.open(name) as src_f, target.open("wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)
                results.append(target)
    return results


def extract_from_markdown_dir(src: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    pattern = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
    for md in src.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="ignore")
        for m in pattern.finditer(text):
            ref = m.group(1)
            if ref.startswith(("http://", "https://", "data:")):
                continue
            img_path = (md.parent / ref).resolve()
            if img_path.exists() and img_path.suffix.lower() in IMG_EXTS:
                target = out_dir / img_path.name
                shutil.copy(img_path, target)
                results.append(target)
    return results


def ocr_image(path: Path) -> str:
    """调用 RapidOCR 或占位回退。"""
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        engine = RapidOCR()
        result, _ = engine(str(path))
        if not result:
            return ""
        return "\n".join(line[1] for line in result if line and len(line) > 1)
    except Exception as exc:  # pragma: no cover
        print(f"WARN: OCR unavailable for {path.name}: {exc}", file=sys.stderr)
        return f"[OCR unavailable: {path.name}]"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python ocr_images.py <input> <output_dir>", file=sys.stderr)
        return 2
    src = Path(argv[1])
    out = Path(argv[2])
    if not src.exists():
        print(f"ERROR: input not found: {src}", file=sys.stderr)
        return 1
    if src.suffix.lower() == ".docx":
        images = extract_from_docx(src, out)
    elif src.suffix.lower() == ".xmind":
        images = extract_from_xmind(src, out)
    elif src.is_dir():
        images = extract_from_markdown_dir(src, out)
    else:
        print(f"ERROR: unsupported input: {src}", file=sys.stderr)
        return 1
    for img in images:
        text = ocr_image(img)
        (out / f"{img.stem}.ocr.txt").write_text(text, encoding="utf-8")
        print(f"OCR: {img.name} -> {len(text)} chars")
    print(f"OK: extracted {len(images)} images to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))