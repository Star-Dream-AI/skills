"""Shared helpers for ClearForAll validators.

Standard library only, so the scripts run offline on any machine with Python 3.8+
and never send document contents anywhere.

The core job here is *normalization*: the same fact can be written many ways
("$1,250", "1250 美元", "2027年3月31日", "March 31, 2027", "3万元"), and the
validators need to recognise that a simplified or translated text still carries
the exact value from the source.
"""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------- text loading


def read_text(path: str | Path) -> str:
    """Read a UTF-8 (optionally BOM-prefixed) text file."""
    return Path(path).read_text(encoding="utf-8-sig")


def load_json(path: str | Path):
    return json.loads(read_text(path))


def ensure_utf8_stdout() -> None:
    """Windows consoles default to a legacy code page; force UTF-8 output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in {"p", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "div", "section", "td", "th", "dt", "dd"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "dt", "dd"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    return html.unescape("".join(parser.parts))


def output_text(path: str | Path) -> str:
    """Visible text of an output file (HTML is stripped of tags)."""
    raw = read_text(path)
    if str(path).lower().endswith((".html", ".htm")):
        return html_to_text(raw)
    return raw


# --------------------------------------------------------------- normalization

CJK_RE = re.compile(r"[㐀-鿿]")


def nfkc(text: str) -> str:
    # A full-width comma is a list separator in Chinese ("100，200"), not a
    # thousands separator, so protect it before NFKC turns it into ",".
    return unicodedata.normalize("NFKC", text.replace("，", "、"))


def canon_number(raw: str) -> str:
    """'1,250.00' -> '1250', '0.50' -> '0.5'."""
    s = raw.replace(",", "").strip()
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    s = s.lstrip("0") or "0"
    if s.startswith("."):
        s = "0" + s
    return s


_ZH_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ZH_UNITS = {"十": 10, "百": 100, "千": 1000}
_ZH_BIG = {"万": 10_000, "亿": 100_000_000}
ZH_NUM_RE = re.compile(r"[零〇一二两三四五六七八九十百千万亿]{1,12}")


def zh_to_int(token: str) -> int | None:
    """Convert a Chinese numeral ('三千五百', '二〇二六', '十二') to int."""
    if not token or not any(c in _ZH_DIGITS or c in _ZH_UNITS or c in _ZH_BIG for c in token):
        return None
    if not any(c in _ZH_UNITS or c in _ZH_BIG for c in token):
        # Digit-by-digit form such as 二〇二六 (a year).
        return int("".join(str(_ZH_DIGITS[c]) for c in token))
    total = section = number = 0
    for ch in token:
        if ch in _ZH_DIGITS:
            number = _ZH_DIGITS[ch]
        elif ch in _ZH_UNITS:
            section += (number or 1) * _ZH_UNITS[ch]
            number = 0
        elif ch in _ZH_BIG:
            section += number
            total += (section or 1) * _ZH_BIG[ch]
            section = number = 0
    return total + section + number


# A letter right before the digits means an identifier such as "F13", not a value.
NUM_RE = re.compile(r"(?<![A-Za-z\d.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\d|,\d)|(?<![A-Za-z\d.,])\d+(?:\.\d+)?")
WAN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([万亿])")


def extract_numbers(text: str) -> set[str]:
    """All numeric values in canonical form, including Chinese numerals and 万/亿."""
    t = nfkc(text)
    values = {canon_number(m.group(0)) for m in NUM_RE.finditer(t)}
    for m in WAN_RE.finditer(t):
        mult = _ZH_BIG[m.group(2)]
        val = float(m.group(1)) * mult
        values.add(canon_number(f"{val:.4f}"))
    for m in ZH_NUM_RE.finditer(t):
        val = zh_to_int(m.group(0))
        if val is not None:
            values.add(str(val))
    return values


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_PAT = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"

DATE_PATTERNS = [
    # 2027-03-31, 2027/3/31, 2027.3.31
    ("ymd", re.compile(r"(?<!\d)(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})(?!\d)")),
    # 2027年3月31日 / 号
    ("ymd", re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")),
    # March 31, 2027 / Mar. 31st 2027
    ("mdy_name", re.compile(_MONTH_PAT + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,\s*|\s+)(\d{4})", re.I)),
    # 31 March 2027
    ("dmy_name", re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH_PAT + r",?\s+(\d{4})", re.I)),
    # 03/31/2027 (US order; ambiguous for non-US readers, see find_ambiguous_dates)
    ("mdy_num", re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")),
]
PARTIAL_PATTERNS = [
    ("md", re.compile(r"(?<![\d年])(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")),
    ("md_name", re.compile(_MONTH_PAT + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?![\d,]*\s*\d{4})", re.I)),
]


def _iso(y: int, m: int, d: int) -> str | None:
    if 1 <= m <= 12 and 1 <= d <= 31:
        return f"{y:04d}-{m:02d}-{d:02d}"
    return None


def extract_dates(text: str) -> tuple[set[str], set[str]]:
    """Return (full ISO dates, partial 'MM-DD' dates) found in text."""
    t = nfkc(text)
    full: set[str] = set()
    for kind, pat in DATE_PATTERNS:
        for m in pat.finditer(t):
            g = m.groups()
            if kind == "ymd":
                iso = _iso(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "mdy_name":
                iso = _iso(int(g[2]), _MONTHS[g[0][:3].lower()], int(g[1]))
            elif kind == "dmy_name":
                iso = _iso(int(g[2]), _MONTHS[g[1][:3].lower()], int(g[0]))
            else:  # mdy_num
                iso = _iso(int(g[2]), int(g[0]), int(g[1]))
            if iso:
                full.add(iso)
    partial: set[str] = set()
    for kind, pat in PARTIAL_PATTERNS:
        for m in pat.finditer(t):
            g = m.groups()
            if kind == "md":
                mo, d = int(g[0]), int(g[1])
            else:
                mo, d = _MONTHS[g[0][:3].lower()], int(g[1])
            if 1 <= mo <= 12 and 1 <= d <= 31:
                partial.add(f"{mo:02d}-{d:02d}")
    return full, partial


def find_ambiguous_dates(text: str) -> list[str]:
    """Numeric dates like 03/04/2027 where day/month order is ambiguous."""
    hits = []
    for m in re.finditer(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{2,4})(?!\d)", nfkc(text)):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= 12 and b <= 12 and a != b:
            hits.append(m.group(0))
    return hits


PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)\s*|\d{2,4}[\s.-])\d{3,4}[\s.-]?\d{3,4}(?!\d)|(?<!\d)1\d{10}(?!\d)|(?<![\d-])\d{5}(?![\d-])")


def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def extract_phones(text: str) -> set[str]:
    return {digits_only(m.group(0)) for m in PHONE_RE.finditer(nfkc(text))}


def phone_present(canonical_digits: str, text: str) -> bool:
    want = digits_only(canonical_digits)
    if not want:
        return False
    for got in extract_phones(text):
        if got == want or got.endswith(want) or (want.endswith(got) and len(got) >= 7):
            return True
    # Fall back to scanning digit runs for formats PHONE_RE does not know.
    # Each run is checked separately so unrelated numbers never join up.
    for run in re.findall(r"[\d\s().+-]{7,}", nfkc(text)):
        if digits_only(run).endswith(want):
            return True
    return False


def value_present(fact: dict, text: str) -> tuple[bool, str]:
    """Is the fact's canonical value carried by text?  Returns (found, note)."""
    vtype = fact.get("value_type", "text")
    value = str(fact.get("value", "")).strip()
    if vtype in {"text", "", None} or not value:
        return True, "not value-checked (text fact)"
    if vtype == "date":
        full, partial = extract_dates(text)
        if value in full:
            return True, ""
        if len(value) == 10 and value[5:] in partial:
            return True, "month/day found but the year is not written next to it"
        return False, f"date {value} not found"
    if vtype == "phone":
        return (phone_present(value, text), "" if phone_present(value, text) else f"phone {value} not found")
    if vtype == "range":
        lo, _, hi = value.partition("-")
        nums = extract_numbers(text)
        ok = canon_number(lo) in nums and canon_number(hi) in nums
        return ok, "" if ok else f"range {value} not fully found"
    # money / number / percent / duration
    ok = canon_number(value) in extract_numbers(text)
    return ok, "" if ok else f"{vtype} {value} not found"


def squash_ws(s: str) -> str:
    return re.sub(r"\s+", "", nfkc(s))


def quote_in_source(quote: str, source: str) -> bool:
    """Whitespace-insensitive verbatim match (PDF text extraction breaks lines)."""
    q = squash_ws(quote)
    return bool(q) and q in squash_ws(source)


def line_of(needle: str, source: str) -> int | None:
    sq = squash_ws(needle)
    for i, line in enumerate(source.splitlines(), 1):
        if sq and sq[: min(len(sq), 20)] in squash_ws(line):
            return i
    return None


# --------------------------------------------------------------------- report


class Report:
    """Collects PASS / WARN / FAIL lines and decides the exit code."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.items: list[tuple[str, str]] = []

    def ok(self, msg: str) -> None:
        self.items.append(("PASS", msg))

    def warn(self, msg: str) -> None:
        self.items.append(("WARN", msg))

    def fail(self, msg: str) -> None:
        self.items.append(("FAIL", msg))

    @property
    def failed(self) -> bool:
        return any(level == "FAIL" for level, _ in self.items)

    def counts(self) -> dict[str, int]:
        out = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for level, _ in self.items:
            out[level] += 1
        return out

    def render(self, quiet: bool = False) -> str:
        lines = [f"== {self.title} =="]
        for level, msg in self.items:
            if quiet and level == "PASS":
                continue
            lines.append(f"[{level}] {msg}")
        c = self.counts()
        lines.append(f"-- {c['PASS']} pass, {c['WARN']} warn, {c['FAIL']} fail")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"title": self.title, "items": [{"level": l, "message": m} for l, m in self.items], "counts": self.counts()}
