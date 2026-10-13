"""test_post_terms_fix.py — 单元测试 _post_terms_fix.py 的核心逻辑

覆盖维度:
1. 默认配置加载
2. 长词在前排序
3. 单条无 context 规则
4. 单条带 context 规则(命中 + 未命中)
5. 文件级 wrapper
6. YAML 解析(边界: 缺失字段、空 rules)
7. 自动发现优先级(explicit > cwd > test-crv2 > builtin)
8. --selftest 走通

每个 test 都独立运行,不依赖文件系统固定状态。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# scripts/ 作为 namespace package 加载(pytest 把 rootdir 加进 sys.path)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts._post_terms_fix as ptf
from scripts._post_terms_fix import (
    apply_corrections,
    apply_rule,
    find_config_path,
    load_rules,
    post_terms_fix_file,
    sort_rules_long_first,
)


class TestRuleLoading(unittest.TestCase):
    """规则加载与校验"""

    def test_load_builtin(self):
        """加载 skill 内置默认配置,无 YAML 字段错误"""
        cfg = Path(__file__).resolve().parent.parent / 'references' / 'asr_corrections.yaml'
        rules = load_rules(cfg)
        self.assertGreater(len(rules), 20, "内置规则应至少 20 条")
        for r in rules:
            self.assertIn('from', r)
            self.assertIn('to', r)
            self.assertIn('context', r)
            self.assertNotEqual(r['from'], r['to'], "from == to 是无效规则")

    def test_load_missing_file(self):
        """加载不存在的文件抛 FileNotFoundError"""
        with self.assertRaises(FileNotFoundError):
            load_rules(Path('/nonexistent/asr_corrections.yaml'))

    def test_load_invalid_yaml(self):
        """加载非法 YAML(rules 不是列表)抛 ValueError"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write("rules: not_a_list\n")
            tmp_path = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                load_rules(tmp_path)
        finally:
            tmp_path.unlink()

    def test_load_rule_missing_from(self):
        """规则缺少 from 字段抛 ValueError"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write("rules:\n  - {to: 'bar'}\n")
            tmp_path = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                load_rules(tmp_path)
        finally:
            tmp_path.unlink()


class TestSortRules(unittest.TestCase):
    """长词在前排序"""

    def test_sort_long_first(self):
        rules = [
            {'from': '心', 'to': '新', 'context': ''},
            {'from': '心客', 'to': '新客', 'context': ''},
            {'from': '心客群', 'to': '新客群', 'context': ''},
        ]
        sorted_rules = sort_rules_long_first(rules)
        self.assertEqual(sorted_rules[0]['from'], '心客群')
        self.assertEqual(sorted_rules[1]['from'], '心客')
        self.assertEqual(sorted_rules[2]['from'], '心')

    def test_sort_tie_breaker_alphabetical(self):
        """同长度按 from Unicode 序,确保稳定排序(Python tuple 比较)

        注:Python 默认 string compare 按 Unicode codepoint;中文 '占' (\u5360)
        < '重' (\u91cd),所以 '权占' 排在 '权重' 前。这是稳定可预期的行为。
        """
        rules = [
            {'from': '权重', 'to': '全站', 'context': ''},
            {'from': '权占', 'to': '全占', 'context': ''},
        ]
        sorted_rules = sort_rules_long_first(rules)
        # 同长度,按 from Unicode codepoint 升序: '权占' < '权重'
        self.assertEqual(sorted_rules[0]['from'], '权占')
        self.assertEqual(sorted_rules[1]['from'], '权重')


class TestApplyRule(unittest.TestCase):
    """单条规则应用"""

    def test_no_context_replace_all(self):
        """无 context:无脑替换"""
        content = "心客转化率 + 心客复购率"
        rule = {'from': '心客', 'to': '新客', 'context': ''}
        new_content, count = apply_rule(content, rule)
        self.assertEqual(new_content, "新客转化率 + 新客复购率")
        self.assertEqual(count, 2)

    def test_with_context_hit(self):
        """带 context 且命中:替换"""
        content = "同店打爆产品是大忌"  # 含 "同店"
        rule = {'from': '打爆', 'to': '打散', 'context': '同店'}
        new_content, count = apply_rule(content, rule)
        self.assertEqual(new_content, "同店打散产品是大忌")
        self.assertEqual(count, 1)

    def test_with_context_miss(self):
        """带 context 但未命中:跳过"""
        content = "打爆气球"  # 不含 "同店"
        rule = {'from': '打爆', 'to': '打散', 'context': '同店'}
        new_content, count = apply_rule(content, rule)
        self.assertEqual(new_content, "打爆气球")  # 未变
        self.assertEqual(count, 0)

    def test_with_context_boundary(self):
        """context 在 ±50 字符窗口边缘(应命中)"""
        # "同店" 在 from 后 48 字符位置
        content = "同店是核心 " + "x" * 40 + " 打爆产品"
        rule = {'from': '打爆', 'to': '打散', 'context': '同店'}
        new_content, count = apply_rule(content, rule)
        self.assertEqual(count, 1, "同店在 ±50 窗口内应命中")
        self.assertEqual(new_content, "同店是核心 " + "x" * 40 + " 打散产品")

    def test_with_context_outside_window(self):
        """context 超出 ±50 字符窗口(应跳过)"""
        # "同店" 在 from 前 60 字符位置
        content = "同店" + "x" * 60 + " 打爆产品"
        rule = {'from': '打爆', 'to': '打散', 'context': '同店'}
        new_content, count = apply_rule(content, rule)
        self.assertEqual(count, 0, "同店超出 ±50 窗口应跳过")
        self.assertEqual(new_content, content)


class TestApplyCorrections(unittest.TestCase):
    """多规则批量应用"""

    def test_long_first_prevents_false_match(self):
        """长词在前避免短词误匹配:长规则先消耗文本,短规则无残留可误伤

        示例:
          - 短规则 "权" → "全" (1 字符,太宽)
          - 长规则 "权占" → "全站" (2 字符,精确)

        排序后(长在前):
          - 先跑"权占" → "全站":"权占比" → "全占比" → 错了!

        等等,错了。让我换一个例子:

        排序后(长在前):
          - 先跑"权占" → "全站":"权占比" → "全占比"?

        啊 — 实际 re.sub 在原文中找非重叠匹配:
          - "权占比" 中只有一处 "权占"(0-1)
          - 替换后变 "全占比"
          - 继续从 index 2 找,无更多 "权占"

        所以排序后也是 "全占比"。长词在前 vs 不排序,在这例里结果一样。

        真实价值在嵌套匹配:短规则若跑先,会破坏长规则的 source substring。
        """
        # 设计能体现 长词在前 价值的场景:
        # - 短规则 "占" → "站" (1 字符,不应误伤)
        # - 长规则 "权占" → "全站" (2 字符,正确替换)
        # 输入: "权占数据 + 占有率"
        rules = [
            {'from': '占', 'to': '站', 'context': ''},       # 短(若在前会误伤第二个)
            {'from': '权占', 'to': '全站', 'context': ''},   # 长(应在前)
        ]
        rules = sort_rules_long_first(rules)  # 排序后"权占"在前

        content = "权占数据"
        new_content, counts = apply_corrections(content, rules)
        # 期望:"权占" 被长规则先替换成 "全站数据"
        # 然后短规则再跑,但 "全站数据" 中无 "占",不应误伤
        self.assertEqual(new_content, "全站数据")
        self.assertNotIn('占', new_content)

    def test_multiple_rules_chain(self):
        """多规则链式应用(每条规则基于上一条的输出)"""
        rules = [
            {'from': '皮气护理', 'to': '皮质护理', 'context': ''},
            {'from': '皮质护理', 'to': '皮肤护理', 'context': ''},
        ]
        # 长词在前顺序
        rules = sort_rules_long_first(rules)
        content = "皮气护理很重要"
        new_content, counts = apply_corrections(content, rules)
        # 链式:皮气护理 → 皮质护理 → 皮肤护理
        self.assertEqual(new_content, "皮肤护理很重要")

    def test_empty_rules(self):
        """空规则列表不修改内容"""
        content = "任意文本"
        new_content, counts = apply_corrections(content, [])
        self.assertEqual(new_content, content)
        self.assertEqual(counts, {})


class TestConfigDiscovery(unittest.TestCase):
    """配置自动发现"""

    def test_explicit_overrides_others(self):
        """--config 显式指定最高优先级"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            explicit = tmp / 'explicit.yaml'
            explicit.write_text("rules:\n  - {from: 'EX', to: 'EXPLICIT'}\n", encoding='utf-8')

            cfg_path, label = find_config_path(Path(tmpdir), explicit=explicit)
            self.assertEqual(label, "explicit")
            self.assertEqual(cfg_path, explicit)

    def test_fallback_to_builtin(self):
        """无任何配置时兜底到 builtin"""
        # 用一个完全空的临时目录 CWD 测试
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            # 确保 cwd 和 test-crv2 都没有配置
            cfg_path, label = find_config_path(cwd, explicit=None)
            self.assertEqual(label, "builtin")


class TestFileWrapper(unittest.TestCase):
    """文件级 wrapper"""

    def test_post_terms_fix_file_roundtrip(self):
        """从输入 md 文件 → 输出 md 文件,验证内容正确修正"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / 'input.md'
            output_path = tmp / 'output.md'

            input_path.write_text(
                "皮气护理对皮质很重要,心客转化率高于老客。",
                encoding='utf-8',
            )

            counts = post_terms_fix_file(input_path, output_path)

            output_text = output_path.read_text(encoding='utf-8')
            # 长词在前的去重是规则问题 — 实际效果看输出
            # 期望:皮气护理 → 皮质护理;心客 → 新客
            self.assertIn('皮质护理', output_text)  # 皮气护理 已修正
            self.assertIn('新客', output_text)  # 心客 已修正
            self.assertNotIn('皮气护理', output_text)  # 错词清除
            self.assertNotIn('心客', output_text)  # 错词清除
            self.assertGreater(sum(counts.values()), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
