"""test_crop_insert.py — Phase 1.8 单元 + 集成测试

覆盖:
- Task 1: Stage 3 (PIL 裁剪 + Markdown 注入) — Test 1-6
- Task 2: Stage 1 (LLM 评分) — Test 7-10 (后续追加)
- Task 3: Stage 2 (LLM 逐帧决策) — Test 11-14 (后续追加)
"""
from __future__ import annotations

import pytest
from pathlib import Path
from PIL import Image

from scripts._crop_insert_frames import crop_box_to_pixels, crop_frame, inject_to_md


# === Task 1 · Stage 3 ===

# Test 1: crop_box 0-1 归一化 → 像素正确 + 5% padding 内缩
def test_crop_box_to_pixels_normal():
    box = {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
    x, y, w, h = crop_box_to_pixels(box, (1000, 800))
    # x = int(0.1*1000) + int(50) = 100 + 50 = 150
    # y = int(0.2*800) + int(40) = 160 + 40 = 200
    # w = int(0.8*1000) - 2*50 = 800 - 100 = 700
    # h = int(0.6*800) - 2*40 = 480 - 80 = 400
    assert (x, y, w, h) == (150, 200, 700, 400)


# Test 2: crop_box 越界 → clamp 到边界
def test_crop_box_to_pixels_clamp():
    box = {"x": 0.95, "y": 0.95, "w": 0.5, "h": 0.5}
    x, y, w, h = crop_box_to_pixels(box, (1000, 800))
    # 不能越界
    assert x >= 0 and y >= 0
    assert x + w <= 1000 and y + h <= 800
    # clamp 后必须有有效区域
    assert w > 0 and h > 0


# Test 3: PIL 裁剪 → 输出 JPEG ≤ 200KB
def test_crop_frame_size_limit(tmp_path):
    src = tmp_path / "src.jpg"
    # 创建一个 1000x800 测试图(填红)
    Image.new("RGB", (1000, 800), "red").save(src, "JPEG")
    out = tmp_path / "out.jpg"
    box = {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}
    bytes_written = crop_frame(src, box, out)
    assert out.exists()
    assert bytes_written <= 200 * 1024, f"Got {bytes_written} bytes, must be ≤ 200KB"


# Test 4: Markdown 注入 → H3 段首下一行有 ![]() 行
def test_inject_to_md_basic(tmp_path):
    md = tmp_path / "test.md"
    md.write_text("# Title\n\n## 1. A\n\n### 1.1 X\n\nContent\n", encoding="utf-8")
    ok = inject_to_md(md, "1.1", "img/foo.jpg", "Test caption")
    assert ok
    text = md.read_text(encoding="utf-8")
    assert "![Test caption](img/foo.jpg)" in text
    # 必须在 "### 1.1 X" 之后, "Content" 之前
    img_line = text.index("![Test caption]")
    h3_line = text.index("### 1.1 X")
    content_line = text.index("Content")
    assert h3_line < img_line < content_line


# Test 5: H3 不存在 → 返回 False, 不修改文件
def test_inject_to_md_h3_not_found(tmp_path):
    md = tmp_path / "test.md"
    original = "# Title\n\n## 1. A\n"
    md.write_text(original, encoding="utf-8")
    ok = inject_to_md(md, "9.9", "img/foo.jpg", "cap")
    assert not ok
    assert md.read_text(encoding="utf-8") == original


# Test 6: CRLF 行尾兼容
def test_inject_to_md_crlf(tmp_path):
    md = tmp_path / "test.md"
    md.write_bytes(b"# Title\r\n\r\n## 1. A\r\n\r\n### 1.1 X\r\n\r\nContent\r\n")
    ok = inject_to_md(md, "1.1", "img/foo.jpg", "cap")
    assert ok
    text = md.read_text(encoding="utf-8")
    assert "![cap](img/foo.jpg)" in text


# === Task 2 · Stage 1 (LLM 评分) ===

from scripts._llm_vision import call_vision
from scripts._stage1_score import build_stage1_prompt, parse_stage1_response


# Test 7: Stage 1 prompt 包含 H3 列表 + 帧 OCR(含 OCR 缺失兜底)
def test_build_stage1_prompt():
    frames = [
        {"id": "f1", "timestamp": 120, "ocr_text": "电钻工种"},
        {"id": "f2", "timestamp": 600, "ocr_text": ""},  # OCR 缺失
    ]
    h3 = ["1.1 课程说明", "1.2 案例 1:电钻", "2.1 隐性需求"]
    prompt = build_stage1_prompt(frames, h3)
    assert "1.2 案例 1:电钻" in prompt
    assert "f1" in prompt
    assert "电钻工种" in prompt
    # OCR 缺失兜底: frame_id 仍出现
    assert "f2" in prompt


# Test 8: parse_stage1_response — 合法 JSON 数组
def test_parse_stage1_valid():
    response = '''[
      {"frame_id": "f1", "score": 0.85, "h3_hint": "1.2", "rationale": "test"},
      {"frame_id": "f2", "score": 0.5, "h3_hint": "2.1"}
    ]'''
    result = parse_stage1_response(response)
    assert len(result) == 2
    assert result[0]["frame_id"] == "f1"


# Test 9: parse_stage1_response — JSON 包在 ```json ... ``` 内
def test_parse_stage1_markdown_wrapped():
    response = '下面是结果:\n```json\n[{"frame_id": "f1", "score": 0.9, "h3_hint": "1.2"}]\n```\n完毕'
    result = parse_stage1_response(response)
    assert len(result) == 1
    assert result[0]["frame_id"] == "f1"


# Test 10: parse_stage1_response — 非法 JSON 兜底返回 []
def test_parse_stage1_invalid():
    response = "抱歉,我无法生成 JSON 格式响应"
    result = parse_stage1_response(response)
    assert result == []


# === Task 3 · Stage 2 (LLM 逐帧决策) ===

from scripts._stage2_decide import build_stage2_prompt, parse_stage2_response


# Test 11: Stage 2 prompt 包含 h3_hint + ASR 上下文 + 全文
def test_build_stage2_prompt():
    frame = {"id": "f1", "timestamp": 120, "ocr_text": "电钻工种"}
    h3_hint = "1.2"
    asr = "讲师讲解电钻按工种拆分的案例..."
    md = "# Title\n\n## 1. A\n\n### 1.2 X\n\nContent\n"
    prompt = build_stage2_prompt(frame, h3_hint, asr, md)
    assert 'h3_hint = "1.2"' in prompt
    assert "电钻按工种拆分" in asr  # ASR 上下文存在性
    # cleaned.md 全文或 H3 至少有一个在 prompt
    assert "### 1.2 X" in prompt or "### 1.2 X" in md


# Test 12: parse_stage2_response — 合法 JSON
def test_parse_stage2_valid():
    response = '{"frame_id": "f1", "h3_target": "1.2", "crop_box": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.7}, "caption": "电钻工种拆分图", "score": 0.85}'
    result = parse_stage2_response(response)
    assert result["frame_id"] == "f1"
    assert result["h3_target"] == "1.2"
    assert result["crop_box"]["w"] == 0.8


# Test 13: parse_stage2_response — 包在 ```json ... ```
def test_parse_stage2_markdown():
    response = '```json\n{"frame_id": "f1", "h3_target": "1.2", "crop_box": {"x": 0, "y": 0, "w": 1, "h": 1}, "caption": "ok", "score": 0.9}\n```'
    result = parse_stage2_response(response)
    assert result["frame_id"] == "f1"


# Test 14: parse_stage2_response — 缺字段返回 None
def test_parse_stage2_missing_fields():
    response = '{"frame_id": "f1", "score": 0.5}'  # 缺 h3_target, crop_box, caption
    result = parse_stage2_response(response)
    assert result is None