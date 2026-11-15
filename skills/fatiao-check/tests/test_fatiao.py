"""Offline regression tests (bundled library only).

Run:  python -m unittest discover -s tests     (from the skill folder)
"""

import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fatiao as f  # noqa: E402


def check(text, as_of=None):
    return f.check_text(text, online=False, as_of=as_of)["results"]


class Numbers(unittest.TestCase):
    def test_roundtrip(self):
        for n in (1, 10, 11, 20, 47, 100, 105, 120, 1001, 1079, 1260):
            self.assertEqual(f.cn2int(f.int2cn(n)), n)
        self.assertEqual(f.cn2int("两百"), 200)
        self.assertEqual(f.art_label("133-1"), "第一百三十三条之一")


class Extraction(unittest.TestCase):
    def labels(self, text):
        return [(c.law_name, c.article, c.para, c.item) for c in f.extract_citations(text)]

    def test_forms(self):
        t = ("根据《中华人民共和国劳动合同法》第三十九条第一款第（二）项；劳动合同法第82条；"
             "《刑法》第一百三十三条之一；《劳动合同法》第三十八条、第三十九条和第四十条；"
             "《民法典》第五百八十五条至第五百八十七条；《劳动法》第三十六、三十八条。本法第四十一条。")
        got = self.labels(t)
        self.assertIn(("中华人民共和国劳动合同法", "39", 1, 2), got)
        self.assertIn(("劳动合同法", "82", None, None), got)
        self.assertIn(("刑法", "133-1", None, None), got)
        for k in ("38", "39", "40"):
            self.assertIn(("劳动合同法", k, None, None), got)
        for k in ("585", "586", "587"):
            self.assertIn(("民法典", k, None, None), got)
        self.assertIn(("劳动法", "36", None, None), got)
        self.assertIn(("劳动法", "38", None, None), got)
        self.assertIn(("劳动法", "41", None, None), got)        # 本法 → last named law

    def test_quote_captured(self):
        c = f.extract_citations("《民法典》第一千零七十九条规定：“夫妻一方要求离婚的，可以由有关组织进行调解。”")[0]
        self.assertTrue(c.quote.startswith("夫妻一方要求离婚的"))


class Verification(unittest.TestCase):
    def one(self, text, **kw):
        res = check(text, **kw)
        self.assertEqual(len(res), 1, res)
        return res[0]

    def test_quote_from_another_article(self):
        r = self.one("根据《劳动合同法》第四十六条规定：“经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资的标准向劳动者支付。”")
        self.assertEqual(r["status"], "quote_mismatch")
        self.assertIn("第四十七条", r["suggestion"])

    def test_article_does_not_exist(self):
        r = self.one("根据《劳动合同法》第一百零二条，用人单位自用工之日起超过一个月不满一年未与劳动者订立书面劳动合同的，应当向劳动者每月支付二倍的工资。")
        self.assertEqual(r["status"], "no_article")
        self.assertIn("第八十二条", r["suggestion"])

    def test_abolished_law_maps_to_civil_code(self):
        r = self.one("依照《合同法》第一百一十四条，约定的违约金过分高于造成的损失的，可以请求适当减少。")
        self.assertEqual(r["status"], "abolished")
        self.assertIn("第五百八十五条", r["suggestion"])

    def test_abolished_but_document_predates(self):
        r = self.one("依照《合同法》第一百一十四条，约定的违约金过分高于造成的损失的，可以请求适当减少。", as_of=date(2019, 6, 1))
        self.assertNotEqual(r["status"], "abolished")

    def test_item_does_not_exist(self):
        r = self.one("属于《劳动合同法》第三十九条第七项规定的情形。")
        self.assertEqual(r["status"], "no_item")

    def test_wrong_article_for_claim(self):
        r = self.one("根据《劳动合同法》第二十条，劳动合同期限三个月以上不满一年的，试用期不得超过一个月。")
        self.assertEqual(r["status"], "suspect")
        self.assertIn("第十九条", r["suggestion"])

    def test_old_version_numbering(self):
        r = self.one("依据《公司法》第三十七条，股东会行使下列职权：决定公司的经营方针和投资计划。")
        self.assertEqual(r["status"], "old_version")
        self.assertIn("第五十九条", r["suggestion"])

    def test_correct_quote_and_paraphrase(self):
        r = self.one("《民法典》第五百八十五条第二款规定：“约定的违约金低于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以增加；约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。”")
        self.assertEqual(r["status"], "ok")
        r = self.one("根据《劳动合同法》第十条，建立劳动关系，应当订立书面劳动合同。")
        self.assertEqual(r["status"], "ok")

    def test_old_version_by_distinctive_term(self):
        r = self.one("申请人不构成《治安管理处罚法》第二十六条规定的寻衅滋事，被申请人引用该条缺乏依据。")
        self.assertEqual(r["status"], "old_version")
        self.assertIn("第三十条", r["suggestion"])

    def test_old_version_when_paragraph_missing_in_current(self):
        # 反不正当竞争法 2025 修订：商业秘密 第九条 → 第十条；新第九条只有两款
        r = self.one("被告明知原告前员工违反保密协议，仍获取并使用原告的客户名单，"
                     "依照《反不正当竞争法》第九条第三款，应视为侵犯商业秘密。")
        self.assertEqual(r["status"], "old_version")
        self.assertIn("第十条第三款", r["suggestion"])
        self.assertIn("2019年版", r["old_article"]["label"])
        self.assertIn("2025年版第十条", r["current_article"]["label"])
        # the "missing paragraph" note must say it is the current version that lacks it
        self.assertIn("2025年版第九条只有 2 款", " ".join(r["messages"]))

    def test_old_version_when_item_missing_in_current(self):
        # 混淆行为 第六条 → 第七条；新第六条不分项
        r = self.one("被告擅自使用与原告有一定影响的商品名称、包装、装潢近似的标识，"
                     "构成《反不正当竞争法》第六条第（一）项规定的混淆行为。")
        self.assertEqual(r["status"], "old_version")
        self.assertIn("第七条第（一）项", r["suggestion"])

    def test_missing_item_message_for_article_without_items(self):
        r = self.one("属于《劳动合同法》第十条第二项规定的情形。")
        self.assertEqual(r["status"], "no_item")
        self.assertIn("不分项", " ".join(r["messages"]))

    def test_implicit_reference_in_other_citation_sentence_not_flagged(self):
        res = check("贵司违法解除劳动合同，依照《劳动合同法》第八十七条，应当依照本法第四十七条规定的经济补偿标准的二倍向劳动者支付赔偿金。")
        self.assertEqual({r["status"] for r in res} & {"suspect", "old_version", "no_article"}, set())

    def test_version_not_yet_in_force(self):
        law, _ = f.get_law("商标法", online=False)
        cur, note = f.in_force(law, date(2026, 11, 15), online=False)
        self.assertEqual(cur.version, "2019年")
        self.assertIn("2027年1月1日", note)
        later, note2 = f.in_force(law, date(2027, 2, 1), online=False)
        self.assertEqual(later.version, "2026年")
        self.assertEqual(note2, "")

    def test_unknown_law_offline(self):
        r = self.one("依据《某某省物业管理条例》第十条。")
        self.assertEqual(r["status"], "unresolved")


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = f.main(list(args))
        return code, buf.getvalue()

    def test_offline_flag_before_or_after_subcommand(self):
        for args in (["--offline", "show", "律师法", "41"], ["show", "律师法", "41", "--offline"]):
            code, out = self.run_cli(*args)
            self.assertEqual(code, 0, args)
            self.assertIn("第四十一条", out)
        code, _ = self.run_cli("list", "--offline")
        self.assertEqual(code, 0)

    def test_fetch_refuses_offline(self):
        code, out = self.run_cli("--offline", "fetch", "中华人民共和国反垄断法")
        self.assertEqual(code, 2)
        self.assertIn("import", out)


class Parsing(unittest.TestCase):
    def test_items_and_chapters(self):
        lines = ["第一章　总则", "第一条　为了测试，制定本法。", "第二条　有下列情形之一的：",
                 "（一）甲；", "（二）乙。", "前款规定不适用于丙。", "第三条之一　补充。", "附件一", "1. 杂项"]
        arts = f.parse_articles(lines)
        self.assertEqual(list(arts), ["1", "2", "3-1"])
        self.assertEqual(len(arts["2"].paras), 2)
        self.assertEqual(len(arts["2"].paras[0]["items"]), 2)
        self.assertEqual(arts["1"].chapter, "第一章 总则")
        self.assertNotIn("杂项", arts["3-1"].text)

    def test_import_docx(self):
        body = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in
                       ["中华人民共和国测试法", "第一条　测试第一条。", "第二条　测试第二条。"])
        xml = f'<?xml version="1.0"?><w:document xmlns:w="w"><w:body>{body}</w:body></w:document>'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.docx"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("word/document.xml", xml)
            law = f.import_official(p)
        self.assertEqual(law.title, "中华人民共和国测试法")
        self.assertEqual(len(law.articles), 2)


class Library(unittest.TestCase):
    def test_bundled_counts(self):
        for title, n in (("中华人民共和国民法典", 1260), ("中华人民共和国劳动合同法", 98), ("中华人民共和国宪法", 143)):
            law = f.load_law_file(f.BUNDLED, title)
            self.assertEqual(law.max_article(), n)
            self.assertEqual(len([k for k in law.articles if "-" not in k]), n)

    def test_aliases(self):
        self.assertEqual(f.resolve_title("民诉法"), "中华人民共和国民事诉讼法")
        self.assertEqual(f.resolve_title("《个保法》"), "中华人民共和国个人信息保护法")
        self.assertEqual(f.resolve_title("公司法（2023年修订）"), "中华人民共和国公司法")


if __name__ == "__main__":
    unittest.main()
