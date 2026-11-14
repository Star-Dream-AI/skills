"""Regression tests built on well-known poems with settled 格律 analyses.

Run:  python -m unittest discover -s tests   (from the skill folder)
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gelv  # noqa: E402


def msgs(res, level=None):
    return [x["msg"] for x in res["issues"] if level is None or x["level"] == level]


class ClassicPoems(unittest.TestCase):
    def test_dengguanquelou(self):
        r = gelv.check_text("白日依山尽，黄河入海流。欲穷千里目，更上一层楼。")
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["form"], "五言绝句")
        self.assertEqual(r["rhyme_group"], "下平十一尤")
        self.assertIn("白", r["ru_sheng_read_ping_in_mandarin"])

    def test_chunwang_two_readings(self):
        r = gelv.check_text("国破山河在，城春草木深。感时花溅泪，恨别鸟惊心。烽火连三月，家书抵万金。白头搔更短，浑欲不胜簪。")
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["rhyme_group"], "下平十二侵")
        sheng = [t for t in r["two_reading_chars"] if t["ch"] == "胜"]
        self.assertTrue(sheng and sheng[0]["need"] == "平")
        self.assertFalse([t for t in r["two_reading_chars"] if t["ch"] == "浑"], "flexible position should not be listed")

    def test_denggao_qilv(self):
        r = gelv.check_text("风急天高猿啸哀，渚清沙白鸟飞回。无边落木萧萧下，不尽长江滚滚来。万里悲秋常作客，百年多病独登台。艰难苦恨繁霜鬓，潦倒新停浊酒杯。")
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(r["form"], "七言律诗")
        self.assertEqual(r["rhyme_group"], "上平十灰")
        self.assertTrue(r["first_line_rhymes"])

    def test_teao_special_form(self):
        r = gelv.check_text("白也诗无敌，飘然思不群。清新庾开府，俊逸鲍参军。渭北春天树，江东日暮云。何时一樽酒，重与细论文。")
        self.assertTrue(r["ok"], r["issues"])
        self.assertEqual(sum("特拗" in m for m in msgs(r, "info")), 2)

    def test_duijujiu_rescue(self):
        r = gelv.check_text("向晚意不适，驱车登古原。夕阳无限好，只是近黄昏。")
        self.assertTrue(r["ok"], r["issues"])
        self.assertTrue(any("对句救" in m for m in msgs(r, "info")))

    def test_jingyesi_is_not_regulated(self):
        r = gelv.check_text("床前明月光，疑是地上霜。举头望明月，低头思故乡。")
        self.assertFalse(r["ok"])
        self.assertTrue(any("失粘" in m for m in msgs(r, "error")))
        self.assertTrue(any("重字" in m for m in msgs(r, "warn")))

    def test_chunxiao_ze_rhyme_is_gu_ti(self):
        r = gelv.check_text("春眠不觉晓，处处闻啼鸟。夜来风雨声，花落知多少。")
        self.assertFalse(r["ok"])
        self.assertTrue(any("仄声字" in m for m in msgs(r, "error")))
        self.assertTrue(any("古体诗" in m for m in msgs(r, "info")))


class Faults(unittest.TestCase):
    def test_constructed_faults(self):
        r = gelv.check_text("秋风吹落叶，月明照我来。江上孤舟远，山中客梦长。")
        e = " | ".join(msgs(r, "error"))
        for word in ("犯孤平", "失对", "失粘"):
            self.assertIn(word, e)
        # 两个韵脚各属一韵、无从判断谁对时，报告“不同韵”而不是武断地判某字出韵
        self.assertIn("不同韵", e)

    def test_out_of_rhyme_with_majority(self):
        r = gelv.check_text("江南三月柳如烟，燕子归来绕画檐。独倚栏杆思往事，满庭黄菊映窗前。")
        e = msgs(r, "error")
        self.assertEqual(len(e), 1, e)
        self.assertIn("出韵", e[0])
        self.assertIn("檐", e[0])
        self.assertEqual(r["rhyme_group"], "下平一先")
        self.assertIn("菊", r["ru_sheng_read_ping_in_mandarin"])

    def test_three_level_tail(self):
        line = [gelv.char_tone(c, "pingshui") for c in "我欲登山归"]  # 仄仄平平平
        issues, _ = gelv.check_line(line, "b", None)
        self.assertTrue(any("三平尾" in x.msg for x in issues))

    def test_gu_ping_rescue_in_line(self):
        line = [gelv.char_tone(c, "pingshui") for c in "月明归故乡"]  # 仄平平仄平
        issues, _ = gelv.check_line(line, "B", None)
        self.assertTrue(any("孤平拗救" in x.msg for x in issues))
        self.assertFalse([x for x in issues if x.level == "error"])

    def test_wrong_line_count(self):
        r = gelv.check_text("白日依山尽，黄河入海流。欲穷千里目。")
        self.assertFalse(r["ok"])
        self.assertEqual(r["verdict"], "体裁不符")


class Couplets(unittest.TestCase):
    def test_good_couplet(self):
        r = gelv.check_text("海阔凭鱼跃，天高任鸟飞。")
        self.assertEqual(r["form"], "对联")
        self.assertTrue(r["ok"], r["issues"])

    def test_reversed_couplet(self):
        r = gelv.check_text("天高任鸟飞，海阔凭鱼跃。")
        self.assertFalse(r["ok"])
        self.assertEqual(len(msgs(r, "error")), 1)
        self.assertIn("颠倒", msgs(r, "error")[0])

    def test_long_couplet(self):
        r = gelv.check_text("风声雨声读书声声声入耳，家事国事天下事事事关心。")
        self.assertTrue(r["ok"], r["issues"])


class Lexicon(unittest.TestCase):
    def test_ru_sheng_vs_mandarin(self):
        self.assertEqual(gelv.char_tone("国", "pingshui").pz, "仄")
        self.assertEqual(gelv.char_tone("国", "xin").pz, "平")
        self.assertEqual(gelv.char_tone("白", "pingshui").pz, "仄")

    def test_two_readings(self):
        self.assertEqual(gelv.char_tone("看", "pingshui").pz, "中")
        self.assertEqual(gelv.char_tone("不", "pingshui").pz, "仄")
        self.assertEqual(gelv.char_tone("不", "xin").pz, "仄")

    def test_variant_bridge(self):
        t = gelv.char_tone("为", "pingshui")
        self.assertIn("上平四支", t.groups)
        self.assertIn("異體", t.note.replace("异体", "異體"))

    def test_xinyun_groups(self):
        self.assertIn("九文", gelv.char_tone("心", "xin").ping_groups)
        self.assertIn("二波", gelv.char_tone("歌", "xin").ping_groups)
        self.assertIn("十三支", gelv.char_tone("诗", "xin").ping_groups)
        self.assertIn("十一庚", gelv.char_tone("东", "xin").ping_groups)

    def test_rhymes_and_patterns(self):
        out = gelv.cmd_rhymes("侵", None, "pingshui", False, "平")
        self.assertIn("心", out)
        pat = gelv.cmd_patterns("五绝", "仄起", False)
        self.assertIn("1. 仄仄平平仄", pat)
        self.assertIn("2. 平平仄仄平（韵）", pat)
        self.assertIn("3. 平平平仄仄", pat)
        self.assertIn("4. 仄仄仄平平（韵）", pat)


if __name__ == "__main__":
    unittest.main()
