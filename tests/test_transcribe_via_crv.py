"""test_transcribe_via_crv.py — 单元测试 transcribe_via_crv.py 的解析逻辑

不调真实 claude-real-video(昂贵 + 慢),只覆盖:
1. 输入类型检测(audio/video/unknown)
2. crv 产物目录发现
3. audio.json 解析
4. audio.srt 解析
5. audio.txt 解析
6. transcript.md 渲染(含时间戳格式)
7. 选优顺序(json > srt > txt)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.transcribe_via_crv as crv
from scripts.transcribe_via_crv import (
    detect_input_kind,
    find_crv_transcript_dir,
    format_timestamp,
    parse_audio_json,
    parse_audio_srt,
    parse_audio_txt,
    render_transcript_md,
    load_segments_from_crv,
    CRV_OUT_SUBDIR_PATTERN,
)


class TestInputDetection(unittest.TestCase):
    """输入类型检测"""

    def test_audio_extensions(self):
        for ext in ('.mp3', '.m4a', '.wav', '.flac', '.aac'):
            with self.subTest(ext=ext):
                self.assertEqual(detect_input_kind(Path(f'audio{ext}')), 'audio')

    def test_video_extensions(self):
        for ext in ('.mp4', '.mkv', '.mov', '.avi', '.webm'):
            with self.subTest(ext=ext):
                self.assertEqual(detect_input_kind(Path(f'video{ext}')), 'video')

    def test_unknown_extension(self):
        self.assertEqual(detect_input_kind(Path('foo.xyz')), 'unknown')

    def test_case_insensitive(self):
        """大小写不敏感(常见 .MP4 vs .mp4)"""
        self.assertEqual(detect_input_kind(Path('audio.MP3')), 'audio')
        self.assertEqual(detect_input_kind(Path('video.MP4')), 'video')


class TestFormatTimestamp(unittest.TestCase):
    """时间戳格式化"""

    def test_zero(self):
        self.assertEqual(format_timestamp(0), "00:00:00.00")

    def test_seconds_only(self):
        self.assertEqual(format_timestamp(45.5), "00:00:45.50")

    def test_minutes(self):
        self.assertEqual(format_timestamp(125.0), "00:02:05.00")

    def test_hours(self):
        self.assertEqual(format_timestamp(3661.25), "01:01:01.25")

    def test_large_duration(self):
        """3 小时(超过 10000 秒,常见长讲座)"""
        self.assertEqual(format_timestamp(10800.0), "03:00:00.00")


class TestParseJson(unittest.TestCase):
    """audio.json 解析"""

    def test_basic_segments(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump({
                'language': 'zh',
                'duration': 30.5,
                'segments': [
                    {'start': 0.0, 'end': 5.0, 'text': ' 第一段'},
                    {'start': 5.5, 'end': 12.3, 'text': ' 第二段'},
                ],
            }, f, ensure_ascii=False)
            tmp_path = Path(f.name)
        try:
            duration, segs = parse_audio_json(tmp_path)
            self.assertEqual(duration, 30.5)
            self.assertEqual(len(segs), 2)
            self.assertEqual(segs[0], (0.0, 5.0, ' 第一段'))
            self.assertEqual(segs[1], (5.5, 12.3, ' 第二段'))
        finally:
            tmp_path.unlink()

    def test_empty_segments(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump({'language': 'zh', 'duration': 0, 'segments': []}, f)
            tmp_path = Path(f.name)
        try:
            duration, segs = parse_audio_json(tmp_path)
            self.assertEqual(duration, 0)
            self.assertEqual(segs, [])
        finally:
            tmp_path.unlink()

    def test_missing_fields_tolerated(self):
        """字段缺失容错(空字段兜底为 0 / '')"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump({'segments': [{'start': 1.0, 'text': 'x'}]}, f)
            tmp_path = Path(f.name)
        try:
            duration, segs = parse_audio_json(tmp_path)
            # 缺 end: 兜底 0.0
            self.assertEqual(segs[0], (1.0, 0.0, 'x'))
        finally:
            tmp_path.unlink()


class TestParseSrt(unittest.TestCase):
    """audio.srt 解析"""

    def test_basic_srt(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
            f.write("""1
00:00:01,000 --> 00:00:05,500
第一段文字

2
00:00:06,000 --> 00:00:10,000
第二段文字
多行内容
""")
            tmp_path = Path(f.name)
        try:
            segs = parse_audio_srt(tmp_path)
            self.assertEqual(len(segs), 2)
            self.assertEqual(segs[0], (1.0, 5.5, '第一段文字'))
            self.assertEqual(segs[1], (6.0, 10.0, '第二段文字 多行内容'))
        finally:
            tmp_path.unlink()

    def test_invalid_srt_skipped(self):
        """格式错误的 block 跳过"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
            f.write("""NOT VALID BLOCK

1
00:00:01,000 --> 00:00:05,000
正确段
""")
            tmp_path = Path(f.name)
        try:
            segs = parse_audio_srt(tmp_path)
            self.assertEqual(len(segs), 1)
            self.assertEqual(segs[0][2], '正确段')
        finally:
            tmp_path.unlink()


class TestParseTxt(unittest.TestCase):
    """audio.txt 兜底解析"""

    def test_basic_txt(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("纯文本内容\n没有时间戳\n")
            tmp_path = Path(f.name)
        try:
            segs = parse_audio_txt(tmp_path)
            self.assertEqual(len(segs), 1)
            self.assertEqual(segs[0][:2], (0.0, 0.0))
            self.assertIn('纯文本', segs[0][2])
        finally:
            tmp_path.unlink()


class TestLoadSegmentsPriority(unittest.TestCase):
    """audio.json > audio.srt > audio.txt 优先级"""

    def test_json_priority(self):
        """三个文件都存在时优先用 json"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / 'audio.json').write_text(
                json.dumps({'segments': [{'start': 0, 'end': 1, 'text': 'JSON'}]}, ensure_ascii=False),
                encoding='utf-8'
            )
            (tmp / 'audio.srt').write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nSRT\n", encoding='utf-8'
            )
            (tmp / 'audio.txt').write_text("TXT", encoding='utf-8')

            duration, segs = load_segments_from_crv(tmp)
            self.assertEqual(segs[0][2], 'JSON')

    def test_fallback_to_srt(self):
        """无 json 时降级 srt"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / 'audio.srt').write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nSRT段\n", encoding='utf-8'
            )
            (tmp / 'audio.txt').write_text("TXT", encoding='utf-8')

            duration, segs = load_segments_from_crv(tmp)
            self.assertEqual(segs[0][2], 'SRT段')

    def test_fallback_to_txt(self):
        """无 json/srt 时降级 txt"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / 'audio.txt').write_text("TXT纯文本", encoding='utf-8')

            duration, segs = load_segments_from_crv(tmp)
            self.assertEqual(segs[0][2], 'TXT纯文本')

    def test_missing_all_raises(self):
        """三个文件都缺失时抛 FileNotFoundError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            with self.assertRaises(FileNotFoundError):
                load_segments_from_crv(tmp)


class TestFindCrvDir(unittest.TestCase):
    """crv 产物目录发现"""

    def test_find_latest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # 多个产物目录,应找最新的(字典序倒序)
            (tmp / 'crv-out-2026-10-01-test').mkdir()
            (tmp / 'crv-out-2026-10-12-test').mkdir()
            (tmp / 'not-crv-dir').mkdir()

            found = find_crv_transcript_dir(tmp)
            self.assertIsNotNone(found)
            self.assertEqual(found.name, 'crv-out-2026-10-12-test')

    def test_no_crv_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / 'random-dir').mkdir()
            self.assertIsNone(find_crv_transcript_dir(tmp))

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(find_crv_transcript_dir(Path(tmpdir)))

    def test_pattern_matches(self):
        """CRV_OUT_SUBDIR_PATTERN 正确匹配"""
        self.assertIsNotNone(CRV_OUT_SUBDIR_PATTERN.match('crv-out-2026-10-12-foo'))
        self.assertIsNotNone(CRV_OUT_SUBDIR_PATTERN.match('crv-out-2026-10-12-foo bar'))
        self.assertIsNone(CRV_OUT_SUBDIR_PATTERN.match('not-crv-out'))
        self.assertIsNone(CRV_OUT_SUBDIR_PATTERN.match('crv-out-not-a-date'))


class TestRenderTranscriptMd(unittest.TestCase):
    """transcript.md 渲染"""

    def test_basic_render(self):
        segs = [
            (0.0, 5.0, '第一段'),
            (5.5, 10.2, '第二段'),
        ]
        md = render_transcript_md(
            'lecture_2026', 'lecture.mp4', 'turbo', 30.0, '0.5.0', segs
        )
        # 关键内容检查
        self.assertIn('# lecture_2026 - ASR Transcript', md)
        self.assertIn('> 模型: claude-real-video (whisper-turbo)', md)
        self.assertIn('> 时长: 30.0s', md)
        self.assertIn('## [00:00:00.00] 第一段', md)
        self.assertIn('## [00:00:05.50] 第二段', md)

    def test_empty_segments_with_note(self):
        """空 segments + note 渲染"""
        md = render_transcript_md(
            'fail', 'fail.mp4', 'turbo', 0.0, '0.5.0', [],
            note='ERROR: crv 产物解析失败'
        )
        self.assertIn('> ERROR: crv 产物解析失败', md)

    def test_segments_blank_text_skipped(self):
        """空 text 的 segment 跳过(避免空 H2 标题)"""
        segs = [
            (0.0, 5.0, '   '),  # 全空白
            (5.0, 10.0, '正常段'),
        ]
        md = render_transcript_md('test', 'test.mp3', 'turbo', 10.0, '0.5.0', segs)
        self.assertNotIn('## [00:00:00.00]', md)
        self.assertIn('## [00:00:05.00] 正常段', md)


class TestBinaryDetection(unittest.TestCase):
    """claude-real-video 二进制检测"""

    def test_crv_in_path(self):
        """crv 在 PATH 中时能找到"""
        binary = crv.find_crv_binary()
        if binary:
            self.assertTrue(binary.endswith('crv') or 'claude-real-video' in binary)
        else:
            self.skipTest("crv not in PATH (test environment)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
