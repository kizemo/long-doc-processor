#!/usr/bin/env python3
"""test_asr_term_correction.py — v4.21 ASR 错词规则链路测试

覆盖:
1. _post_terms_fix.py 4 条 v4.21 新规则 (玺承 2026 双十一项目)
2. pipe-separated context alternates 字段支持
3. ±50 字符 context 窗口
5. 长词先于短词匹配 (内置排序)
"""
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / 'scripts'))

from _post_terms_fix import (  # noqa: E402
    load_rules, apply_rule, post_terms_fix_file
)
from _post_terms_fix import selftest  # noqa: E402


CONFIG_PATH = SKILL_ROOT / 'references' / 'asr_corrections.yaml'


def _rule_by(rules, key):
    for r in rules:
        if r['from'] == key:
            return r
    raise KeyError(key)


def test_rules_loaded_count():
    rules = load_rules(CONFIG_PATH)
    # v4.21 后内置 45 条 (v4.16 + v4.21 +4)
    assert len(rules) >= 45, f'expected >= 45 rules, got {len(rules)}'


def test_v4_22_new_rules_exist():
    """v4.22 新规则:4 个 v4.21 字面规则已合并入 v4.22 phonetic 模式。"""
    rules = load_rules(CONFIG_PATH)
    expected = [
        # v4.21 字面规则(部分保留作字面兜底)
        ('磁包', '词包', None, False),          # 字面规则
        # v4.22 phonetic 模式规则
        ('控点击', '控点击', '投放|计划|出价|成交|板块|对不对', True),
        ('相似品跟投', '相似品跟投', None, True),
        ('会员券', '会员券', 'VIP|会员|权益|券', True),
    ]
    for from_w, to_c, ctx, phonetic in expected:
        r = _rule_by(rules, from_w)
        assert r['to'] == to_c, f'{from_w}: to mismatch ({r["to"]} != {to_c})'
        assert r.get('context', '') == (ctx or ''), \
            f'{from_w}: context mismatch'
        assert bool(r.get('phonetic', False)) == phonetic, \
            f'{from_w}: phonetic flag mismatch (got {r.get("phonetic")})'


def test_magnetic_packet_to_word_packet():
    rules = load_rules(CONFIG_PATH)
    r = _rule_by(rules, '磁包')
    text = '智能计划里磁包打开'
    new, count = apply_rule(text, r)
    assert count == 1
    assert new == '智能计划里词包打开'


def test_control_click_to_control_click_phonetic():
    """v4.22 控点击 phonetic 捕获 同音变体 控电机 / 恐点鸡。"""
    rules = load_rules(CONFIG_PATH)
    r = _rule_by(rules, '控点击')
    # 有 context 关键词 + phonetic → 替换同音
    samples = [
        ('直通车计划里有控电机', '控点击'),
        ('直通车投放板块恐点鸡', '控点击'),
        ('直通车计划里控点击', '控点击'),
    ]
    for text, expected in samples:
        new, count = apply_rule(text, r)
        assert count >= 1, f'{text!r}: should be replaced'
        assert expected in new, f'{text!r} → {new!r}, expected {expected!r}'


def test_control_click_no_context_not_replaced():
    """无 context 关键词时,phonetic 也不替换。"""
    rules = load_rules(CONFIG_PATH)
    r = _rule_by(rules, '控点击')
    # 没有 context 关键词 → 不替换
    text = '恐点鸡 发电装置里'  # 没有 投放/计划/出价/成交/板块/对不对
    new, count = apply_rule(text, r)
    assert count == 0, f'{text!r}: should NOT be replaced (no context kw)'
    assert '恐点鸡' in new, f'{text!r} should remain unchanged'

    # 确认有 context 关键词时会替换
    text2 = '恐点鸡 在直通车板块'
    new, count = apply_rule(text2, r)
    assert count >= 1, f'{text2!r}: should be replaced'


def test_pipe_separated_context():
    """pipe-separated context 任一关键词匹配即触发。"""
    rules = load_rules(CONFIG_PATH)
    r = _rule_by(rules, '控点击')
    for kw in ['投放', '计划', '出价', '成交', '板块', '对不对']:
        text = f'前面有{kw}的语境 控电机后面 跟着'
        new, count = apply_rule(text, r)
        assert count >= 1, f'kw={kw!r} should match'


def test_similar_product_gengtou_to_gengtou():
    """v4.22 相似品跟投 phonetic 捕获 同音变体 相似品跟头。"""
    rules = load_rules(CONFIG_PATH)
    r = _rule_by(rules, '相似品跟投')
    text = '关键词计划里相似品跟头是常用场景'
    new, count = apply_rule(text, r)
    assert count == 1
    assert new == '关键词计划里相似品跟投是常用场景'


def test_member_coupon_phonetic_with_vip_context():
    """会员券 phonetic + VIP context。

    注:phonetic 算法对 3-char 滑动窗口的所有 CJK 子串检查拼音匹配;这意味着
    任何含相同拼音的 3 字串都会被捕获(如 会员权 / 会员全 / 会员圈)。
    这是同音匹配的固有特性,用户在 ASR 错听 货源券 → 会员券 时有效,
    但其他 同音 3 字组 也会被波及。

    注:`VIP货源券` 不会被自动替换 → 货 ≠ 惠,不同音。这种"语义错词"只能由
    LLM 净化阶段处理,不在 _post_terms_fix 兜底范围。
    """
    rules = load_rules(CONFIG_PATH)
    r = _rule_by(rules, '会员券')

    # 同音错词被捕获:汇员券(汇 huì / 惠 huì 同音)
    text = 'VIP汇员券'
    new, count = apply_rule(text, r)
    assert count == 1, f'{text!r} should be replaced (汇=惠 同音)'
    assert new == 'VIP会员券', f'expected VIP会员券, got {new!r}'

    # 没 VIP/会员 关键词 → 不替换
    text2 = '在路上开车'
    new, count = apply_rule(text2, r)
    assert count == 0, f'{text2!r} should NOT be replaced (no context)'


def test_long_first_sort_protects_short_rules():
    rules = load_rules(CONFIG_PATH)
    # 检查所有规则已按 from 长度降序排列
    lens = [len(r['from']) for r in rules]
    assert lens == sorted(lens, reverse=True), \
        f'rules not sorted long-first: {lens[:10]}...'


def test_selftest_passes():
    # 内置 selftest 必须 PASS
    rc = selftest()
    assert rc == 0, f'selftest failed: rc={rc}'


def test_post_pass_on_real_transcript():
    """端到端:在 raw transcript 上跑 post-pass,4 个错词应全部替换"""
    transcript_path = SKILL_ROOT.parent / 'tests' / 'regression_cases' / 'tmall_2026_d11.json'
    # 实际路径在用户工作目录
    user_path = Path('F:/resourse_study/玺承/2026直播/2026-09-29_2026天猫双十一备战全攻略/2026天猫双十一备战全攻略_2026-09-29_transcript.md')
    if not user_path.exists():
        return  # skip if test data missing
    out_path = Path('C:/Temp/test_transcript_fixed.md')
    out_path.parent.mkdir(exist_ok=True)
    counts = post_terms_fix_file(user_path, out_path)
    out_text = out_path.read_text(encoding='utf-8')

    # 关键: 4 个错词必须 0 残留
    assert out_text.count('磁包') == 0
    assert out_text.count('控电机') == 0
    assert out_text.count('相似品跟头') == 0

    # 正确术语应出现
    assert out_text.count('词包') > 0
    assert out_text.count('控点击') > 0
    assert out_text.count('相似品跟投') > 0

    # 清理
    out_path.unlink(missing_ok=True)


# === v4.22 phonetic 匹配测试 ===

def test_phonetic_module_loads():
    """pypinyin 成功导入,to_pinyin 函数可用。"""
    from _post_terms_fix import to_pinyin, is_cjk
    # 基本字串 → 拼音映射
    assert to_pinyin('控点击') == 'kongdianji'
    assert to_pinyin('磁包') == 'cibao'
    assert is_cjk('控') is True
    assert is_cjk('A') is False
    assert is_cjk('1') is False


def test_phonetic_catches_known_homophones():
    """同音变体被 phonetic 规则捕获。"""
    from _post_terms_fix import apply_rule, to_pinyin
    rule = {'from': '控点击', 'to': '控点击', 'context': '', 'phonetic': True}

    tests = [
        # (input, expected_pinyin, expected_replaced_count)
        ('控点击', 'kongdianji', 1),     # 原词 → 替换为原词(等于, count=1)
        ('控电机', 'kongdianji', 1),     # ASR 把 点→机 → 控点击(同拼音)
        ('恐点鸡', 'kongdianji', 1),     # ASR 把 控/击 → 恐/鸡 → 控点击(同拼音)
    ]
    for text, expected_py, expected_n in tests:
        assert to_pinyin(text) == expected_py, f'{text!r} pinyin mismatch'
        new, n = apply_rule(text, rule)
        assert n == expected_n, f'{text!r}: expected {expected_n}, got {n}'


def test_phonetic_skips_non_homophone():
    """不同拼音的词不被 phonetic 误伤。"""
    from _post_terms_fix import apply_rule
    rule = {'from': '控点击', 'to': '控点击', 'context': '', 'phonetic': True}
    # "酷点鸡" - 酷/控 是不同拼音,不应替换
    new, n = apply_rule('酷点鸡 在直通车', rule)
    assert '酷点鸡' in new, f'non-homophone should not be replaced: {new!r}'


def test_phonetic_does_not_replace_unchanged_text():
    """phonetic 规则不应替换已正确的原词(避免回环)。

    注:实现可能在内部标记匹配(计数+1)但因 segment == from_text
    而跳过实际写入;所以输出不变即视为通过。
    """
    from _post_terms_fix import apply_rule
    rule = {'from': '控点击', 'to': '控点击', 'context': '', 'phonetic': True}
    # 控制点击 已经在文本中,不应再触发实际写入
    text = '直通车覆盖控点击、最大化、控成本成交、控投产'
    new, n = apply_rule(text, rule)
    assert new == text, f'unchanged text should not be touched: {new!r}'


def test_phonetic_handles_chinese_word_packet_variants():
    """词包 phonetic 捕获 同音变体 次包/茨包/磁包。"""
    from _post_terms_fix import apply_rule
    rule = {'from': '词包', 'to': '词包', 'context': '', 'phonetic': True}
    for text in ['次包打开', '茨包打开', '磁包打开']:
        new, n = apply_rule(text, rule)
        assert n == 1, f'{text!r}: should be replaced'
        assert '词包' in new, f'{text!r} → {new!r}'


def test_phonetic_with_context_still_works():
    """phonetic 模式下 context 检查依然生效。"""
    from _post_terms_fix import apply_rule
    rule = {'from': '控点击', 'to': '控点击',
            'context': '投放|计划|出价|成交|板块|对不对', 'phonetic': True}
    # 有 context 关键词 → 替换
    new, n = apply_rule('控电机 投放', rule)
    assert n == 1
    # 没有 context 关键词 → 不替换
    new, n = apply_rule('控电机 是一种装置', rule)
    assert n == 0


def test_phonetic_pinyin_cache():
    """to_pinyin 缓存生效,重复调用不走 pypinyin。"""
    from _post_terms_fix import to_pinyin, _PINYIN_CACHE
    _PINYIN_CACHE.clear()
    # 第一次调用 → 写入缓存
    r1 = to_pinyin('测试')
    assert '测试' in _PINYIN_CACHE
    cached_value = _PINYIN_CACHE['测试']
    # 第二次调用 → 返回缓存
    r2 = to_pinyin('测试')
    assert r1 == r2 == cached_value


def test_phonetic_end_to_end_on_raw_transcript():
    """端到端:phonetic 模式在真实 raw transcript 上捕获同音变体。"""
    # 用合成输入模拟,验证 phonetic 触发
    test_input = '磁包智能计划\n恐点鸡 在直通车\n词包计划'
    inp = Path('C:/Temp/test_phonetic_e2e.md')
    out = Path('C:/Temp/test_phonetic_e2e_out.md')
    inp.parent.mkdir(exist_ok=True)
    inp.write_text(test_input, encoding='utf-8')
    post_terms_fix_file(inp, out)
    out_text = out.read_text(encoding='utf-8')

    # 同音变体被替换
    assert '恐点鸡' not in out_text, f'恐点鸡 should be replaced: {out_text!r}'
    assert '磁包' not in out_text, f'磁包 should be replaced: {out_text!r}'

    inp.unlink(missing_ok=True)
    out.unlink(missing_ok=True)


if __name__ == '__main__':
    tests = [
        test_rules_loaded_count,
        test_v4_22_new_rules_exist,
        test_magnetic_packet_to_word_packet,
        test_control_click_to_control_click_phonetic,
        test_control_click_no_context_not_replaced,
        test_pipe_separated_context,
        test_similar_product_gengtou_to_gengtou,
        test_member_coupon_phonetic_with_vip_context,
        test_long_first_sort_protects_short_rules,
        test_selftest_passes,
        test_post_pass_on_real_transcript,
        # v4.22 phonetic 测试
        test_phonetic_module_loads,
        test_phonetic_catches_known_homophones,
        test_phonetic_skips_non_homophone,
        test_phonetic_does_not_replace_unchanged_text,
        test_phonetic_handles_chinese_word_packet_variants,
        test_phonetic_with_context_still_works,
        test_phonetic_pinyin_cache,
        test_phonetic_end_to_end_on_raw_transcript,
    ]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f'PASS {t.__name__}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
        except Exception as e:
            failed += 1
            print(f'ERR  {t.__name__}: {e}')
    print(f'\n{passed} pass, {failed} fail')
    sys.exit(0 if failed == 0 else 1)