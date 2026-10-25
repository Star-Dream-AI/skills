#!/usr/bin/env python3
"""Static accessibility and privacy lint for ClearForAll HTML outputs.

Covers the WCAG 2.2 AA points that can be checked from markup alone.  It does
not replace testing with a screen reader or a person with low literacy, but
it catches the failures that make a page unusable for them.

Checks: document language (and lang on passages in another language), title,
charset and viewport, one h1 and no skipped heading levels, a <main>
landmark, alt text on images, header cells on data tables, meaningful link
text, a minimum base font size, and no third-party resources (fonts, scripts,
trackers) that would leak who opened the page.

Usage:
    python check_html.py page.html [more.html ...]
"""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cfa_common import CJK_RE, Report, ensure_utf8_stdout, read_text  # noqa: E402

VAGUE_LINKS = {
    "click here", "here", "more", "read more", "link", "this", "this link", "learn more",
    "点击这里", "点击此处", "这里", "此处", "更多", "详情", "链接", "点此",
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


class Lint(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang = None
        self.title = ""
        self.in_title = False
        self.charset = False
        self.viewport = False
        self.headings: list[tuple[int, str]] = []
        self._heading: list[str] | None = None
        self._heading_level = 0
        self.main = 0
        self.imgs_no_alt = 0
        self.tables = 0
        self.tables_without_th = 0
        self._table_stack: list[dict] = []
        self.links: list[str] = []
        self._link: list[str] | None = None
        self.external: list[str] = []
        self.lang_stack: list[tuple[str, str]] = []
        self.cjk_under_en = 0
        self.latin_words_under_zh: list[str] = []
        self.style_text: list[str] = []
        self._in_style = False
        self.skip_link = False
        self.first_link_seen = False

    # ----- helpers
    def cur_lang(self) -> str:
        for _, lang in reversed(self.lang_stack):
            if lang:
                return lang
        return self.html_lang or ""

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "html":
            self.html_lang = a.get("lang")
        if tag not in VOID:
            self.lang_stack.append((tag, a.get("lang", "")))
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            if "charset" in a or a.get("http-equiv", "").lower() == "content-type":
                self.charset = True
            if a.get("name", "").lower() == "viewport":
                self.viewport = True
        elif re.fullmatch(r"h[1-6]", tag):
            self._heading = []
            self._heading_level = int(tag[1])
        elif tag == "main" or a.get("role") == "main":
            self.main += 1
        elif tag == "img":
            if "alt" not in a:
                self.imgs_no_alt += 1
            self._external(a.get("src", ""), "img")
        elif tag == "table":
            self.tables += 1
            self._table_stack.append({"th": False, "presentation": a.get("role") in {"presentation", "none"}})
        elif tag == "th" and self._table_stack:
            self._table_stack[-1]["th"] = True
        elif tag == "a":
            self._link = []
            href = a.get("href", "")
            if not self.first_link_seen:
                self.first_link_seen = True
                self.skip_link = href.startswith("#")
            if a.get("aria-label"):
                self._link.append(a["aria-label"])
        elif tag in {"script", "iframe", "embed", "object", "audio", "video", "source"}:
            self._external(a.get("src", "") or a.get("data", ""), tag)
        elif tag == "link":
            self._external(a.get("href", ""), f"link rel={a.get('rel', '')}")
        elif tag == "style":
            self._in_style = True
        if a.get("style"):
            self.style_text.append(a["style"])

    def _external(self, url: str, what: str) -> None:
        if re.match(r"^(https?:)?//", url.strip(), re.I):
            self.external.append(f"<{what}> {url}")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif re.fullmatch(r"h[1-6]", tag) and self._heading is not None:
            self.headings.append((self._heading_level, "".join(self._heading).strip()))
            self._heading = None
        elif tag == "table" and self._table_stack:
            t = self._table_stack.pop()
            if not t["th"] and not t["presentation"]:
                self.tables_without_th += 1
        elif tag == "a" and self._link is not None:
            self.links.append("".join(self._link).strip())
            self._link = None
        elif tag == "style":
            self._in_style = False
        if tag not in VOID:
            for i in range(len(self.lang_stack) - 1, -1, -1):
                if self.lang_stack[i][0] == tag:
                    del self.lang_stack[i:]
                    break

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self._heading is not None:
            self._heading.append(data)
        if self._link is not None:
            self._link.append(data)
        if self._in_style:
            self.style_text.append(data)
            return
        lang = self.cur_lang().lower()
        if lang.startswith("en"):
            self.cjk_under_en += len(CJK_RE.findall(data))
        elif lang.startswith("zh"):
            # Whole English sentences inside a zh page should carry lang="en".
            for m in re.finditer(r"(?:[A-Za-z]{2,}[ ,']+){5,}[A-Za-z]{2,}", data):
                self.latin_words_under_zh.append(m.group(0)[:60])


def lint(path: str) -> Report:
    rep = Report(f"html: {Path(path).name}")
    p = Lint()
    p.feed(read_text(path))

    if not p.html_lang:
        rep.fail("<html> has no lang attribute (screen readers pick the wrong voice)")
    elif not LANG_RE.match(p.html_lang):
        rep.fail(f"<html lang=\"{p.html_lang}\"> is not a valid language tag (use en, zh-Hans, zh-Hant, zh-CN ...)")
    else:
        rep.ok(f"lang=\"{p.html_lang}\"")
    if p.cjk_under_en > 3:
        rep.fail(f"{p.cjk_under_en} Chinese characters inside English-language markup: wrap them in an element with lang=\"zh-Hans\"")
    if p.latin_words_under_zh:
        rep.warn(f"English passages inside Chinese-language markup without lang=\"en\": {p.latin_words_under_zh[0]!r}")
    if not p.title.strip():
        rep.fail("missing or empty <title>")
    if not p.charset:
        rep.fail("missing <meta charset=\"utf-8\">")
    if not p.viewport:
        rep.fail("missing <meta name=\"viewport\"> (page will not reflow on phones)")

    h1 = [h for h in p.headings if h[0] == 1]
    if len(h1) != 1:
        rep.fail(f"expected exactly one <h1>, found {len(h1)}")
    prev = 0
    for level, text in p.headings:
        if prev and level > prev + 1:
            rep.fail(f"heading level skips from h{prev} to h{level} at '{text[:40]}'")
        if not text:
            rep.fail(f"empty <h{level}>")
        prev = level
    if len(p.headings) < 3:
        rep.warn("fewer than 3 headings: long pages need headings so screen-reader users can jump between sections")
    if p.main != 1:
        rep.fail(f"expected exactly one <main> landmark, found {p.main}")
    if not p.skip_link:
        rep.warn("first link is not a skip link (e.g. <a href=\"#main\">Skip to content</a>)")
    if p.imgs_no_alt:
        rep.fail(f"{p.imgs_no_alt} <img> without alt (use alt=\"\" for decorative images)")
    if p.tables_without_th:
        rep.fail(f"{p.tables_without_th} data table(s) without <th> header cells")
    elif p.tables:
        rep.ok(f"{p.tables} table(s) have header cells")
    vague = [t for t in p.links if t.lower().strip(" .。:：") in VAGUE_LINKS or not t]
    if vague:
        rep.fail(f"vague or empty link text: {vague[:5]} (say where the link goes)")
    if p.external:
        rep.fail("loads third-party resources (privacy + offline use): " + "; ".join(p.external[:5]))
    else:
        rep.ok("no third-party resources")

    css = " ".join(p.style_text)
    small = [m.group(0) for m in re.finditer(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", css) if float(m.group(1)) < 16]
    if re.search(r"(?:html|body)\s*\{[^}]*font-size\s*:\s*(\d+(?:\.\d+)?)px", css):
        m = re.search(r"(?:html|body)\s*\{[^}]*font-size\s*:\s*(\d+(?:\.\d+)?)px", css)
        if m and float(m.group(1)) < 16:
            rep.fail(f"base font size {m.group(1)}px is below 16px")
    if small:
        rep.warn(f"text sizes below 16px: {', '.join(small[:4])}")
    if re.search(r"user-scalable\s*=\s*no|maximum-scale\s*=\s*1(?:\.0)?\b", read_text(path)):
        rep.fail("viewport disables zoom (user-scalable=no / maximum-scale=1)")
    if re.search(r"outline\s*:\s*(?:none|0)\b", css) and ":focus" not in css:
        rep.warn("outline removed without a :focus style - keyboard users lose their place")
    return rep


def main() -> int:
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", nargs="+")
    args = ap.parse_args()
    failed = False
    for page in args.pages:
        rep = lint(page)
        print(rep.render())
        failed |= rep.failed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
