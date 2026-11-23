#!/usr/bin/env python3
"""Checks for filling out US college applications with the student's own text.

The agent never writes or rewrites application text. This script only measures
and compares what the student provided, so problems can be reported back to the
student instead of being "fixed" by the agent.

Subcommands
  count    TEXT | --file F            characters (as the browser counts them) and words
  essay    --file F [--max N --min N] word count, per-paragraph counts, characters that may paste badly
  validate PROFILE.json               check every field against the platform limits in assets/limits.json
  sheet    PROFILE.json [--out F]     fill sheet (Markdown): every value verbatim, with counts and issues
  compare  PROFILE.json PAGE.json     verify values read back from the web form match the profile exactly
  init     PATH                       create an empty application profile (never overwrites)
  limits   [--platform P]             print the limits in use and where they come from

Exit code 1 when validate/compare/essay finds a problem that must go back to the student.
Standard library only (Python 3.8+).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMITS_FILE = HERE.parent / "assets" / "limits.json"

CJK_RE = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]")
EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️]")
SMART_RE = re.compile(r"[‘’“”]")

GRADES = {"9", "10", "11", "12", "PG"}
TIMING = {"school year", "school break", "all year",
          "during school year", "during school break",          # the form's own wording
          "上学期间", "学期中", "在校期间", "假期", "寒暑假", "全年"}   # how students often answer
LEVELS = {"school", "state/regional", "national", "international"}


# ---------------------------------------------------------------- counting

def char_count(s: str) -> int:
    """Length as a browser counts it: UTF-16 code units, CRLF counted as one line break."""
    s = s.replace("\r\n", "\n")
    return len(s.encode("utf-16-le")) // 2


def word_count(s: str) -> int:
    """Whitespace-separated tokens. Hyphenated words count as one. The portal's own counter is final."""
    return len(s.split())


def paragraphs(s: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", s.replace("\r\n", "\n")) if p.strip()]


def text_flags(s: str, single_line: bool) -> list[str]:
    """Things to tell the student about. Never change the text because of them."""
    flags = []
    if s != s.strip():
        flags.append("leading or trailing spaces (trimming them is fine)")
    if "  " in s:
        flags.append("double spaces")
    if single_line and ("\n" in s or "\r" in s):
        flags.append("line break in a single-line field")
    if "\t" in s:
        flags.append("tab character")
    cjk = CJK_RE.findall(s)
    if cjk:
        flags.append(f"contains Chinese/full-width characters ({''.join(cjk[:12])}{'…' if len(cjk) > 12 else ''}): the form expects English, so ask the student for the English text")
    emo = EMOJI_RE.findall(s)
    if emo:
        flags.append("contains emoji or pictographs, which may not display correctly")
    odd = sorted({ch for ch in s if unicodedata.category(ch) in ("Co", "Cn", "Cs")})
    if odd:
        flags.append("contains unassigned/private-use characters")
    return flags


# ---------------------------------------------------------------- profile helpers

def load_json(path: str) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_limits() -> dict:
    return json.loads(LIMITS_FILE.read_text(encoding="utf-8"))


def blank(v: object) -> bool:
    return v is None or v == "" or v == [] or v == {}


def flatten(obj: object, prefix: str = "") -> dict[str, object]:
    """{"activities": [{"description": "x"}]} -> {"activities[0].description": "x"}; keys starting with _ are skipped."""
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_"):
                continue
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list) and obj and all(isinstance(x, (dict, list)) for x in obj):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []     # must go back to the student before filling
        self.warnings: list[str] = []   # tell the student; they decide
        self.missing: list[str] = []    # not provided yet

    def err(self, m: str) -> None:
        self.errors.append(m)

    def warn(self, m: str) -> None:
        self.warnings.append(m)


def check_text(rep: Report, where: str, s: object, max_chars: int | None = None, max_words: int | None = None,
               min_words: int | None = None, single_line: bool = True, required: bool = False) -> None:
    if blank(s):
        if required:
            rep.missing.append(where)
        return
    if not isinstance(s, str):
        rep.err(f"{where}: expected text, got {type(s).__name__}")
        return
    if max_chars is not None:
        n = char_count(s.strip())
        if n > max_chars:
            rep.err(f"{where}: {n} characters, limit {max_chars} ({n - max_chars} over); the form would cut it after: “{cut_preview(s.strip(), max_chars)}”")
    if max_words is not None or min_words is not None:
        w = word_count(s)
        if max_words is not None and w > max_words:
            rep.err(f"{where}: {w} words, limit {max_words} ({w - max_words} over)")
        if min_words is not None and w < min_words:
            rep.err(f"{where}: {w} words, minimum {min_words} ({min_words - w} short)")
    for f in text_flags(s, single_line):
        rep.warn(f"{where}: {f}")


def cut_preview(s: str, limit: int) -> str:
    """The last few words that would still fit, so the student can see where the cut falls."""
    kept, n = [], 0
    for ch in s:
        n += char_count(ch)
        if n > limit:
            break
        kept.append(ch)
    tail = "".join(kept)
    return ("…" + tail[-40:]) if len(tail) > 40 else tail


def norm_choice(v: object) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().lower()


def validate_profile(p: dict, platform: str = "commonapp") -> Report:
    lim = load_limits()[platform]
    rep = Report()

    if platform == "commonapp":
        a_lim = lim["activities"]
        acts = p.get("activities") or []
        acts = [a for a in acts if isinstance(a, dict) and not all(blank(v) for k, v in a.items() if not k.startswith("_"))]
        if len(acts) > a_lim["max_entries"]:
            rep.err(f"activities: {len(acts)} entries, the form allows {a_lim['max_entries']}; the student must choose which to keep")
        f = a_lim["fields"]
        for i, a in enumerate(acts, 1):
            w = f"activity {i}"
            for key in ("type", "grades", "timing", "hours_per_week", "weeks_per_year", "continue_in_college"):
                if blank(a.get(key)):
                    rep.missing.append(f"{w} {key}")
            check_text(rep, f"{w} position", a.get("position"), f["position"]["max_chars"])
            check_text(rep, f"{w} organization", a.get("organization"), f["organization"]["max_chars"], required=True)
            check_text(rep, f"{w} description", a.get("description"), f["description"]["max_chars"], required=True)
            _check_grades(rep, f"{w} grades", a.get("grades"))
            for t in a.get("timing") or []:
                if norm_choice(t) not in TIMING:
                    rep.warn(f"{w} timing: “{t}” is not one of school year / school break / all year; match it to the form's option with the student")
            _check_number(rep, f"{w} hours_per_week", a.get("hours_per_week"), 0, 168)
            _check_number(rep, f"{w} weeks_per_year", a.get("weeks_per_year"), 0, 52)

        h_lim = lim["honors"]
        hons = [h for h in ((p.get("education") or {}).get("honors") or []) if isinstance(h, dict) and not blank(h.get("title"))]
        if len(hons) > h_lim["max_entries"]:
            rep.err(f"education.honors: {len(hons)} entries, the form allows {h_lim['max_entries']}; the student must choose which to keep")
        for i, h in enumerate(hons, 1):
            w = f"honor {i}"
            check_text(rep, f"{w} title", h.get("title"), h_lim["fields"]["title"]["max_chars"], required=True)
            _check_grades(rep, f"{w} grades", h.get("grades"))
            if blank(h.get("grades")):
                rep.missing.append(f"{w} grades")
            levels = h.get("levels") or []
            if blank(levels):
                rep.missing.append(f"{w} levels")
            for lv in levels:
                if norm_choice(lv) not in LEVELS:
                    rep.warn(f"{w} levels: “{lv}” is not one of School / State/Regional / National / International")

        wr = p.get("writing") or {}
        wl = lim["writing"]
        prompt = wr.get("essay_prompt")
        if not blank(wr.get("personal_essay")) and blank(prompt):
            rep.missing.append("writing.essay_prompt (the student chooses 1–7)")
        if not blank(prompt) and str(prompt) not in {str(i) for i in range(1, 8)}:
            rep.err(f"writing.essay_prompt: “{prompt}” is not 1–7")
        pe = wl["personal_essay"]
        check_text(rep, "writing.personal_essay", wr.get("personal_essay"), max_words=pe["max_words"], min_words=pe["min_words"], single_line=False)
        check_text(rep, "writing.challenges_circumstances", wr.get("challenges_circumstances"), max_words=wl["challenges_circumstances"]["max_words"], single_line=False)
        check_text(rep, "writing.additional_information", wr.get("additional_information"), max_words=wl["additional_information"]["max_words"], single_line=False)

        cols = [c for c in (p.get("colleges") or []) if isinstance(c, dict) and not blank(c.get("name"))]
        if len(cols) > lim["colleges"]["max_entries"]:
            rep.err(f"colleges: {len(cols)} colleges, the Common App list holds {lim['colleges']['max_entries']}")
        for i, c in enumerate(cols, 1):
            if not blank(c.get("deadline")) and blank(c.get("deadline_source")):
                rep.warn(f"college {i} ({c.get('name')}): deadline “{c.get('deadline')}” has no source; check it on the college's official admissions page")

    uc = p.get("uc") or {}
    if uc and platform in ("commonapp", "uc"):
        ul = load_limits()["uc"]["piq"]
        piqs = [q for q in (uc.get("piq") or []) if isinstance(q, dict) and not blank(q.get("answer"))]
        if len(piqs) > ul["choose"]:
            rep.err(f"uc.piq: {len(piqs)} answers, UC asks for exactly {ul['choose']}")
        seen = set()
        for i, q in enumerate(piqs, 1):
            qn = q.get("question")
            if blank(qn):
                rep.missing.append(f"PIQ {i} question number (1–8, the student's choice)")
            elif str(qn) in seen:
                rep.err(f"PIQ {i}: question {qn} is answered twice")
            seen.add(str(qn))
            check_text(rep, f"PIQ {i} answer", q.get("answer"), max_words=ul["max_words"], single_line=False)

    for key, v in flatten(p).items():   # every other text value: flag Chinese text, emoji and so on
        if isinstance(v, str) and v and not key.startswith(("activities", "education.honors", "writing", "uc.piq")):
            for fl in text_flags(v, single_line=True):
                if "Chinese" in fl or "emoji" in fl:
                    rep.warn(f"{key}: {fl}")
    return rep


def _check_grades(rep: Report, where: str, grades: object) -> None:
    for g in grades or []:
        if str(g).strip().upper() not in GRADES:
            rep.err(f"{where}: “{g}” is not a grade level (9, 10, 11, 12, PG)")


def _check_number(rep: Report, where: str, v: object, lo: float, hi: float) -> None:
    if blank(v):
        return
    try:
        x = float(v)
    except (TypeError, ValueError):
        rep.err(f"{where}: “{v}” is not a number")
        return
    if not lo <= x <= hi:
        rep.err(f"{where}: {v} is outside {lo:g}–{hi:g}")


def print_report(rep: Report) -> int:
    if rep.errors:
        print(f"PROBLEMS — send these back to the student ({len(rep.errors)}):")
        for e in rep.errors:
            print(f"  ✗ {e}")
    if rep.warnings:
        print(f"CHECK WITH THE STUDENT ({len(rep.warnings)}):")
        for w in rep.warnings:
            print(f"  △ {w}")
    if rep.missing:
        print(f"NOT PROVIDED YET ({len(rep.missing)}): " + ", ".join(rep.missing))
    if not (rep.errors or rep.warnings or rep.missing):
        print("✓ everything provided is within the limits")
    print("\nThe agent does not edit the student's text: report these and wait for the student's own revision.")
    return 1 if rep.errors else 0


# ---------------------------------------------------------------- fill sheet

SECTION_ORDER = ["profile", "family", "education", "testing", "activities", "responsibilities_circumstances",
                 "writing", "colleges", "uc"]
SINGLE = {"position", "organization", "description", "title"}


def render_sheet(p: dict, platform: str = "commonapp") -> str:
    rep = validate_profile(p, platform)
    lim = load_limits()[platform] if platform in load_limits() else {}
    out = ["# Application fill sheet", "",
           "Every value below is exactly what the student provided. The agent enters these verbatim and does not edit them.", ""]
    if rep.errors or rep.warnings or rep.missing:
        out.append("## Before filling")
        out += [f"- ✗ {e}" for e in rep.errors]
        out += [f"- △ {w}" for w in rep.warnings]
        if rep.missing:
            out.append("- Not provided yet: " + ", ".join(rep.missing))
        out.append("")
    keys = [k for k in SECTION_ORDER if k in p] + [k for k in p if k not in SECTION_ORDER and not k.startswith("_")]
    for sec in keys:
        val = p[sec]
        if blank(val):
            continue
        out.append(f"## {sec}")
        if sec == "activities" and isinstance(val, list):
            for i, a in enumerate(val, 1):
                if not isinstance(a, dict) or all(blank(v) for v in a.values()):
                    continue
                out.append(f"### Activity {i}")
                out += _sheet_fields(a, lim.get("activities", {}).get("fields", {}))
        elif sec == "writing" and isinstance(val, dict):
            for k, v in val.items():
                if blank(v) or k.startswith("_"):
                    continue
                if isinstance(v, str) and len(v) > 80:
                    out.append(f"### {k} — {word_count(v)} words")
                    out += ["```text", v.strip(), "```"]
                else:
                    out.append(f"- **{k}**: {v}")
        else:
            for path, v in flatten(val).items():
                if blank(v):
                    continue
                shown = ", ".join(map(str, v)) if isinstance(v, list) else v
                extra = f"  ({char_count(v)} chars)" if isinstance(v, str) and path.rsplit(".", 1)[-1] in SINGLE else ""
                out.append(f"- **{path}**: {shown}{extra}")
        out.append("")
    return "\n".join(out)


def _sheet_fields(a: dict, flim: dict) -> list[str]:
    lines = []
    for k, v in a.items():
        if blank(v) or k.startswith("_"):
            continue
        if isinstance(v, str) and k in flim:
            lim = flim[k]["max_chars"]
            n = char_count(v.strip())
            mark = "✓" if n <= lim else "✗ over"
            lines.append(f"- **{k}** ({n}/{lim} {mark}):")
            lines += ["  ```text", f"  {v.strip()}", "  ```"]
        else:
            lines.append(f"- **{k}**: {', '.join(map(str, v)) if isinstance(v, list) else v}")
    return lines


# ---------------------------------------------------------------- compare

def norm_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "|".join(sorted(norm_value(x) for x in v))
    s = "" if v is None else str(v)
    return s.replace("\r\n", "\n").strip()


def compare(profile: dict, page: object) -> list[str]:
    """Return mismatches between the profile and values read back from the form.
    PAGE may be nested like the profile, or flat {"activities[0].description": "..."}."""
    exp = flatten(profile)
    got = flatten(page) if not (isinstance(page, dict) and any("[" in k or "." in k for k in page)) else dict(page)
    problems = []
    for path, gv in got.items():
        if path not in exp:
            problems.append(f"{path}: on the page but not in the profile — find out who entered it")
            continue
        ev = exp[path]
        if norm_value(gv) == norm_value(ev):
            continue
        e, g = norm_value(ev), norm_value(gv)
        if e.startswith(g) and len(g) < len(e):
            problems.append(f"{path}: TRUNCATED by the form — {char_count(g)} of {char_count(e)} characters kept; the student must shorten it")
        else:
            problems.append(f"{path}: differs from the student's text\n      profile: {e[:160]!r}\n      page:    {g[:160]!r}")
    return problems


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("count")
    c.add_argument("text", nargs="?")
    c.add_argument("--file")
    e = sub.add_parser("essay")
    e.add_argument("--file", required=True)
    e.add_argument("--max", type=int, default=None, help="word limit (default: Common App personal essay)")
    e.add_argument("--min", type=int, default=None)
    v = sub.add_parser("validate")
    v.add_argument("profile")
    v.add_argument("--platform", default="commonapp")
    sh = sub.add_parser("sheet")
    sh.add_argument("profile")
    sh.add_argument("--platform", default="commonapp")
    sh.add_argument("--out")
    cp = sub.add_parser("compare")
    cp.add_argument("profile")
    cp.add_argument("page")
    ini = sub.add_parser("init")
    ini.add_argument("path")
    li = sub.add_parser("limits")
    li.add_argument("--platform")
    a = ap.parse_args(argv)

    if a.cmd == "count":
        text = Path(a.file).read_text(encoding="utf-8-sig") if a.file else (a.text if a.text is not None else sys.stdin.read())
        print(f"characters: {char_count(text.strip())} (with spaces, as the browser counts them)")
        print(f"words: {word_count(text)}")
        for f in text_flags(text, single_line=False):
            print(f"△ {f}")
        return 0

    if a.cmd == "essay":
        text = Path(a.file).read_text(encoding="utf-8-sig")
        pe = load_limits()["commonapp"]["writing"]["personal_essay"]
        mx = a.max if a.max is not None else pe["max_words"]
        mn = a.min if a.min is not None else (pe["min_words"] if a.max is None else 0)
        w = word_count(text)
        print(f"words: {w} (allowed {mn}–{mx})")
        print(f"characters: {char_count(text.strip())}")
        print("paragraph word counts (for the student to decide what to change):")
        for i, para in enumerate(paragraphs(text), 1):
            print(f"  ¶{i}: {word_count(para)} words — starts “{para[:50]}{'…' if len(para) > 50 else ''}”")
        bad = False
        if w > mx:
            print(f"✗ {w - mx} words over the limit: ask the student to cut it themselves and send the new version")
            bad = True
        elif w < mn:
            print(f"✗ {mn - w} words short of the minimum")
            bad = True
        else:
            print("✓ within the word range")
        for f in text_flags(text, single_line=False):
            print(f"△ {f}")
        return 1 if bad else 0

    if a.cmd == "validate":
        return print_report(validate_profile(load_json(a.profile), a.platform))

    if a.cmd == "sheet":
        md = render_sheet(load_json(a.profile), a.platform)
        if a.out:
            Path(a.out).write_text(md, encoding="utf-8")
            print(f"fill sheet written to {a.out}")
        else:
            print(md)
        return 0

    if a.cmd == "compare":
        probs = compare(load_json(a.profile), load_json(a.page))
        if probs:
            print(f"✗ {len(probs)} value(s) on the page do not match the student's text:")
            for pr in probs:
                print(f"  - {pr}")
            return 1
        print("✓ every value read back from the page matches the student's text exactly")
        return 0

    if a.cmd == "init":
        dest = Path(a.path)
        if dest.exists():
            print(f"{dest} already exists — not overwriting it")
            return 2
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text((HERE.parent / "assets" / "profile_template.json").read_text(encoding="utf-8"), encoding="utf-8")
        print(f"created {dest} — record the student's answers verbatim; it stays on this computer")
        return 0

    if a.cmd == "limits":
        data = load_limits()
        print(json.dumps(data if not a.platform else data.get(a.platform, {}), ensure_ascii=False, indent=2))
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
