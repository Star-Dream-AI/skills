"""Offline tests for appcheck.py.  Run from the skill folder:  python -m unittest discover -s tests"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import appcheck as ac  # noqa: E402


def run(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = ac.main(list(args))
    return code, buf.getvalue()


def activity(**kw):
    a = {"type": "Work (Paid)", "position": "Cashier", "organization": "Green Tea House",
         "description": "Took orders and handled cash on weekends.", "grades": ["11", "12"],
         "timing": ["school year"], "hours_per_week": 12, "weeks_per_year": 40, "continue_in_college": False}
    a.update(kw)
    return a


class Counting(unittest.TestCase):
    def test_chars_include_spaces_and_count_like_a_browser(self):
        self.assertEqual(ac.char_count("ab c"), 4)
        self.assertEqual(ac.char_count("a\r\nb"), 3)          # CRLF is one line break
        self.assertEqual(ac.char_count("😀"), 2)              # emoji = 2 UTF-16 units, as JS counts
        self.assertEqual(ac.char_count("中文"), 2)

    def test_words(self):
        self.assertEqual(ac.word_count("A well-known  fact.\nNew line"), 5)

    def test_flags_chinese_and_emoji(self):
        f = " ".join(ac.text_flags("Volunteer 图书馆 😀", single_line=True))
        self.assertIn("Chinese", f)
        self.assertIn("emoji", f)


class Validation(unittest.TestCase):
    def check(self, profile):
        return ac.validate_profile(profile)

    def test_valid_profile_has_no_errors(self):
        rep = self.check({"activities": [activity()]})
        self.assertEqual(rep.errors, [])

    def test_description_over_150_is_an_error_with_exact_count(self):
        desc = "x" * 171
        rep = self.check({"activities": [activity(description=desc)]})
        self.assertTrue(any("171 characters, limit 150 (21 over)" in e for e in rep.errors), rep.errors)

    def test_position_over_50_and_optional(self):
        rep = self.check({"activities": [activity(position="P" * 58)]})
        self.assertTrue(any("activity 1 position: 58 characters, limit 50" in e for e in rep.errors))
        rep = self.check({"activities": [activity(position="")]})
        self.assertFalse(any("position" in m for m in rep.missing))   # optional since 2026–27

    def test_too_many_activities_and_honors(self):
        rep = self.check({"activities": [activity() for _ in range(11)],
                          "education": {"honors": [{"title": f"Award {i}", "grades": ["10"], "levels": ["School"]} for i in range(6)]}})
        self.assertTrue(any("11 entries, the form allows 10" in e for e in rep.errors))
        self.assertTrue(any("6 entries, the form allows 5" in e for e in rep.errors))

    def test_bad_grade_hours_weeks(self):
        rep = self.check({"activities": [activity(grades=["8"], hours_per_week=200, weeks_per_year=60)]})
        joined = " ".join(rep.errors)
        self.assertIn("“8” is not a grade level", joined)
        self.assertIn("200 is outside 0–168", joined)
        self.assertIn("60 is outside 0–52", joined)

    def test_chinese_description_is_flagged_not_changed(self):
        p = {"activities": [activity(description="在社区图书馆给小学生读绘本")]}
        rep = self.check(p)
        self.assertTrue(any("Chinese" in w for w in rep.warnings))
        self.assertEqual(p["activities"][0]["description"], "在社区图书馆给小学生读绘本")

    def test_writing_limits(self):
        rep = self.check({"writing": {"essay_prompt": 2, "personal_essay": "word " * 688,
                                      "additional_information": "word " * 320,
                                      "challenges_circumstances": "word " * 100}})
        joined = " ".join(rep.errors)
        self.assertIn("688 words, limit 650 (38 over)", joined)
        self.assertIn("additional_information: 320 words, limit 300", joined)
        self.assertNotIn("challenges", joined)

    def test_essay_needs_prompt_choice(self):
        rep = self.check({"writing": {"personal_essay": "word " * 300}})
        self.assertTrue(any("essay_prompt" in m for m in rep.missing))

    def test_uc_piq(self):
        rep = self.check({"uc": {"piq": [{"question": 1, "answer": "w " * 351}, {"question": 1, "answer": "w " * 10}]}})
        joined = " ".join(rep.errors)
        self.assertIn("351 words, limit 350", joined)
        self.assertIn("answered twice", joined)

    def test_deadline_without_source_is_flagged(self):
        rep = self.check({"colleges": [{"name": "Example U", "plan": "ED", "deadline": "Nov 1", "deadline_source": ""}]})
        self.assertTrue(any("no source" in w for w in rep.warnings))


class SheetAndCompare(unittest.TestCase):
    def test_sheet_keeps_text_verbatim(self):
        desc = "Tutored 3 kids in math — weekly; raised scores."
        md = ac.render_sheet({"activities": [activity(description=desc)]})
        self.assertIn(desc, md)
        self.assertIn(f"({ac.char_count(desc)}/150 ✓)", md)

    def test_compare_detects_truncation_and_edits(self):
        prof = {"activities": [activity(description="A" * 120 + " end")]}
        page = {"activities[0].description": "A" * 120, "activities[0].organization": "Green Tea House "}
        probs = ac.compare(prof, page)
        self.assertTrue(any("TRUNCATED" in p for p in probs))
        self.assertEqual(len(probs), 1)       # trailing space alone is not a difference
        probs = ac.compare(prof, {"activities[0].organization": "Green Tea Shop"})
        self.assertTrue(any("differs" in p for p in probs))

    def test_compare_nested_page_json(self):
        prof = {"activities": [activity()]}
        self.assertEqual(ac.compare(prof, {"activities": [{"organization": "Green Tea House"}]}), [])


class Cli(unittest.TestCase):
    def test_essay_command(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "essay.txt"
            p.write_text(("word " * 340).strip() + "\n\n" + ("word " * 348).strip(), encoding="utf-8")
            code, out = run("essay", "--file", str(p))
        self.assertEqual(code, 1)
        self.assertIn("words: 688", out)
        self.assertIn("¶1: 340 words", out)
        self.assertIn("38 words over", out)

    def test_validate_and_sheet_commands(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "profile.json"
            p.write_text(json.dumps({"activities": [activity()]}), encoding="utf-8")
            code, out = run("validate", str(p))
            self.assertEqual(code, 0)
            code, out = run("sheet", str(p), "--out", str(Path(d) / "sheet.md"))
            self.assertTrue((Path(d) / "sheet.md").exists())

    def test_init_creates_profile_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "application_profile.json"
            code, _ = run("init", str(p))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["activities"], [])
            code, out = run("init", str(p))
            self.assertEqual(code, 2)
            self.assertIn("not overwriting", out)

    def test_messages_use_human_numbering(self):
        rep = ac.validate_profile({"activities": [activity(), activity(description="y" * 160)]})
        self.assertTrue(any(e.startswith("activity 2 description: 160 characters") for e in rep.errors), rep.errors)

    def test_template_is_valid_json_and_passes(self):
        tpl = json.loads((Path(ac.HERE).parent / "assets" / "profile_template.json").read_text(encoding="utf-8"))
        rep = ac.validate_profile(tpl)
        self.assertEqual(rep.errors, [])


if __name__ == "__main__":
    unittest.main()
