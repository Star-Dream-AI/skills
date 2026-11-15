#!/usr/bin/env python3
"""法条引用核验：把文稿里引用的中国法律条文，逐条对照原文核对。

Standard library only. Law texts come from, in order of priority:
  1. official files the user downloaded from 国家法律法规数据库 (flk.npc.gov.cn)
     and imported with `import` (docx / txt);
  2. the bundled library in assets/laws/ (works offline);
  3. 维基文库 zh.wikisource.org through its public MediaWiki API, cached locally.

Subcommands
  check   核验一段文字（或文件）里的全部法条引用
  show    显示某部法律的某一条（含款、项）
  search  在某部法律里按关键词找条文（找“正确的条号”时用）
  fetch   从维基文库获取 / 更新一部法律到本地缓存
  import  导入从国家法律法规数据库下载的官方文本（docx/txt）
  list    列出本地已有的法律及版本

Examples
  python fatiao.py check --file 律师函.txt
  python fatiao.py check "根据《劳动合同法》第四十七条规定，经济补偿按工作年限计算。"
  python fatiao.py show 劳动合同法 47
  python fatiao.py search 民法典 违约金 过分高于
  python fatiao.py fetch 中华人民共和国反垄断法
  python fatiao.py import ~/Downloads/中华人民共和国劳动合同法.docx
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLED = ROOT / "assets" / "laws"
CACHE = Path(os.environ.get("FATIAO_CACHE", Path.home() / ".cache" / "fatiao-check"))
UA = os.environ.get("FATIAO_UA", "fatiao-check/0.1 (Agent Skill; https://github.com/Star-Dream-AI/skills)")
WS_API = "https://zh.wikisource.org/w/api.php"
PRC = "中华人民共和国"

# ---------------------------------------------------------------- numbers

CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}
NUM = r"[零〇一二两三四五六七八九十百千\d]+"


def cn2int(s: str) -> int | None:
    s = unicodedata.normalize("NFKC", s.strip())
    if not s:
        return None
    if s.isdigit():
        return int(s)
    total = sec = num = 0
    seen = False
    for ch in s:
        if ch in CN_DIGIT:
            num = CN_DIGIT[ch]
            seen = True
        elif ch in CN_UNIT:
            sec += (num or 1) * CN_UNIT[ch]
            num = 0
            seen = True
        else:
            return None
    return total + sec + num if seen else None


def int2cn(n: int) -> str:
    if n <= 0:
        return str(n)
    digits = "零一二三四五六七八九"
    units = [(1000, "千"), (100, "百"), (10, "十")]
    out, zero = "", False
    rest = n
    for val, name in units:
        d, rest = divmod(rest, val)
        if d:
            if zero:
                out += "零"
                zero = False
            out += ("" if (val == 10 and d == 1 and not out) else digits[d]) + name
        elif out:
            zero = True
    if rest:
        if zero:
            out += "零"
        out += digits[rest]
    return out


def art_key(num: int, sub: int | None = None) -> str:
    return f"{num}" if not sub else f"{num}-{sub}"


def art_label(key: str) -> str:
    if "-" in key:
        a, b = key.split("-")
        return f"第{int2cn(int(a))}条之{int2cn(int(b))}"
    return f"第{int2cn(int(key))}条"


# ---------------------------------------------------------------- text utils

def norm(s: str) -> str:
    """Normalize for comparison: NFKC, drop whitespace and punctuation."""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s，。、；：？！“”‘’「」『』《》（）()\[\]【】,.;:?!\"'—…·\-]", "", s)


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a in b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def best_window(quote: str, text: str) -> tuple[float, str]:
    """Best similarity of quote against any same-length window of text (quotes are often partial)."""
    q, t = norm(quote), norm(text)
    if not q or not t:
        return 0.0, ""
    if q in t:
        return 1.0, quote
    if len(t) <= len(q):
        return difflib.SequenceMatcher(None, q, t, autojunk=False).ratio(), text
    best, best_span = 0.0, ""
    step = max(1, len(q) // 4)
    starts = list(range(0, len(t) - len(q) + 1, step)) + [len(t) - len(q)]
    for start in starts:
        win = t[start:start + len(q)]
        r = difflib.SequenceMatcher(None, q, win, autojunk=False).ratio()
        if r > best:
            best, best_span = r, win
    return best, best_span


def bigrams(s: str) -> set[str]:
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


# ---------------------------------------------------------------- law model

@dataclass
class Article:
    key: str
    label: str
    chapter: str
    paras: list[dict]          # [{"text": str, "items": [str, ...]}]

    @property
    def text(self) -> str:
        out = []
        for p in self.paras:
            out.append(p["text"])
            out.extend(p.get("items", []))
        return "\n".join(out)


@dataclass
class Law:
    title: str
    version: str = ""
    effective: str = ""
    status: str = "有效"                  # 有效 / 已废止 / 未知
    abolished: dict | None = None         # {"date": "2021-01-01", "by": "中华人民共和国民法典"}
    source: dict = field(default_factory=dict)
    notes: str = ""
    articles: dict[str, Article] = field(default_factory=dict)
    versions: list[dict] = field(default_factory=list)   # [{"page": "…公司法 (2018年)", "year": 2018}, …] oldest first

    def to_json(self) -> dict:
        return {
            "title": self.title, "version": self.version, "effective": self.effective,
            "status": self.status, "abolished": self.abolished, "source": self.source, "notes": self.notes,
            "versions": self.versions,
            "articles": [{"key": a.key, "label": a.label, "chapter": a.chapter, "paras": a.paras} for a in self.articles.values()],
        }

    @classmethod
    def from_json(cls, d: dict) -> "Law":
        law = cls(d["title"], d.get("version", ""), d.get("effective", ""), d.get("status", "有效"),
                  d.get("abolished"), d.get("source", {}), d.get("notes", ""), versions=d.get("versions", []))
        for a in d.get("articles", []):
            law.articles[a["key"]] = Article(a["key"], a["label"], a.get("chapter", ""), a["paras"])
        return law

    def max_article(self) -> int:
        nums = [int(k.split("-")[0]) for k in self.articles]
        return max(nums) if nums else 0


# ---------------------------------------------------------------- parsing law text

ART_RE = re.compile(r"^\s*第(" + NUM + r")条(?:之(" + NUM + r"))?[\s　]*(.*)$")
# Page furniture that must never be glued onto the last article (navboxes, licence notices, footers).
STOP_RE = re.compile(r"^(附件[一二三四五六七八九十\d]*[:：]?|附[:：].*|查|论|编|查论编|v\s*t\s*e|.{0,6}全文完.{0,6}|本作品|这部作品|此作品|本作品在|Public domain|公有领域|上一[篇章节]|下一[篇章节]|返回|分类[:：]|"
                     r"本法规|本条例|.*依据《中华人民共和国著作权法》.*不(适用|受)|.*不受著作权法保护|.*Wikisource|中华人民共和国(法律|基本法律|行政法规|主席令))")
ITEM_RE = re.compile(r"^\s*[（(][一二三四五六七八九十百]+[）)]")
ZW_RE = re.compile(r"[​‌‍⁠﻿­]")   # zero-width characters that strip() keeps
HEAD_RE = re.compile(r"^\s*(第[零〇一二三四五六七八九十百千]+[编分章节]\s*.*|附\s*则)\s*$")


def parse_articles(lines: list[str]) -> dict[str, Article]:
    arts: dict[str, Article] = {}
    chapter = ""
    cur: Article | None = None
    for raw in lines:
        line = ZW_RE.sub("", raw).strip().replace("　", " ").strip()
        if not line:
            continue
        m = ART_RE.match(line)
        if m:
            num = cn2int(m.group(1))
            sub = cn2int(m.group(2)) if m.group(2) else None
            if num is None:
                continue
            key = art_key(num, sub)
            body = m.group(3).strip()
            cur = Article(key, art_label(key), chapter, [{"text": body, "items": []}] if body else [])
            if key not in arts:          # keep the first occurrence (later ones are usually quotes)
                arts[key] = cur
            continue
        if HEAD_RE.match(line) and len(line) < 40:
            chapter = re.sub(r"\s+", " ", line)
            cur = None
            continue
        if STOP_RE.match(line):
            cur = None
            continue
        if cur is None:
            continue
        if ITEM_RE.match(line) and cur.paras:
            cur.paras[-1]["items"].append(line)
        else:
            cur.paras.append({"text": line, "items": []})
    return arts


def wikitext_to_lines(wt: str) -> list[str]:
    s = re.sub(r"<!--.*?-->", "", wt, flags=re.S)
    s = re.sub(r"</?(onlyinclude|noinclude|includeonly)[^>]*>", "", s)
    s = re.sub(r"<templatestyles[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", s, flags=re.S)
    s = re.sub(r"\{\{gap\}\}", "", s, flags=re.I)
    s = re.sub(r"==+\s*(.*?)\s*==+", r"\n\1\n", s)                  # headings
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)          # links
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)                              # remaining simple templates
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.splitlines()


def html_to_lines(h: str) -> list[str]:
    import html as _h
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h, flags=re.S | re.I)
    s = re.sub(r'<span class="mw-editsection".*?</span></span>', "", s, flags=re.S)
    s = re.sub(r"<sup[^>]*class=\"reference\".*?</sup>", "", s, flags=re.S)
    s = re.sub(r"</(p|div|h\d|li|dd|dt|tr|table)>|<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return _h.unescape(s).splitlines()


def ws_parse(title: str) -> tuple[str, int]:
    """Rendered HTML of a page with every transclusion expanded (sub-pages, scanned-page sections…)."""
    d = _ws_get({"action": "parse", "page": title, "prop": "text|revid", "disableeditsection": "1", "redirects": "1"})
    p = d.get("parse", {})
    return p.get("text", ""), p.get("revid", 0)


CN_DATE = re.compile(r"((?:19|20)\d{2})年(\d{1,2})月(\d{1,2})日")


def parse_cn_date(s: str) -> date | None:
    m = CN_DATE.search(s or "")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def find_effective(raw: str, articles: dict[str, "Article"], online: bool = True) -> str:
    """Effective date of a version: header 生效日期 → amendment decision → last article."""
    eff = header_field(raw, "生效日期")
    if parse_cn_date(eff):
        return eff
    notes_raw = re.search(r"\|\s*notes\s*=\s*(.*?)(?:\n\s*\||\n\}\})", raw, flags=re.S)
    notes_raw = notes_raw.group(1) if notes_raw else ""
    events = re.findall(r"((?:19|20)\d{2})年\d{1,2}月\d{1,2}日[^（）()]{0,160}?(通过|修订|修正)", re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", notes_raw))
    if events and events[-1][1] == "修正" and online:
        links = re.findall(r"\[\[([^\]|]*决定[^\]|]*)(?:\|[^\]]*)?\]\]", notes_raw)
        if links:
            try:
                dec = ws_pages([links[-1]]).get(links[-1], {}).get("content", "")
                m = re.search(r"本决定自\s*(" + CN_DATE.pattern + r")\s*起施行", dec)
                if m:
                    return m.group(1)
            except Exception:
                pass
    if articles and (not events or events[-1][1] in ("通过", "修订")):
        last = articles.get(str(max(int(k.split("-")[0]) for k in articles)))
        m = re.search(r"(?:本法|本条例|本规定|本办法)自\s*(" + CN_DATE.pattern + r")\s*起施行", last.text if last else "")
        if m:
            return m.group(1)
    # Most amendment decisions take effect on promulgation (“自公布之日起施行”): use the last event date.
    plain = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", notes_raw)
    dated = re.findall(r"(" + CN_DATE.pattern + r")[^（）()]{0,160}?(?:通过|修订|修正)", plain)
    if dated:
        return dated[-1][0]
    return eff


def header_field(wt: str, name: str) -> str:
    m = re.search(r"\|\s*" + re.escape(name) + r"\s*=\s*([^\n|]*)", wt)
    return re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", m.group(1)).strip() if m else ""


# ---------------------------------------------------------------- wikisource

def _ws_get(params: dict) -> dict:
    params = {**params, "format": "json", "formatversion": "2", "maxlag": "5"}
    url = WS_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("error", {}).get("code") == "maxlag":
                time.sleep(5)
                continue
            return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
    return {}


def ws_pages(titles: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(titles), 40):
        d = _ws_get({"action": "query", "prop": "revisions", "rvprop": "content|ids|timestamp",
                     "rvslots": "main", "titles": "|".join(titles[i:i + 40]), "redirects": "1"})
        q = d.get("query", {})
        redirect = {r["from"]: r["to"] for r in q.get("redirects", []) + q.get("normalized", [])}
        for p in q.get("pages", []):
            if p.get("missing"):
                continue
            rev = p["revisions"][0]
            out[p["title"]] = {"content": rev["slots"]["main"]["content"], "revid": rev["revid"], "timestamp": rev["timestamp"]}
        for src, dst in redirect.items():
            if dst in out:
                out[src] = out[dst]
    return out


def ws_search(query: str, limit: int = 8) -> list[str]:
    d = _ws_get({"action": "query", "list": "search", "srsearch": query, "srlimit": str(limit), "srnamespace": "0"})
    return [x["title"] for x in d.get("query", {}).get("search", [])]


ABOLISH_RE = re.compile(r"\{\{\s*中华人民共和国废止法律\s*\|([^}]*)\}\}")


def fetch_wikisource(title: str) -> Law:
    pages = ws_pages([title])
    if title not in pages:
        hits = [t for t in ws_search(title) if "/" not in t]
        exact = [t for t in hits if t == title or t.replace(PRC, "") == title.replace(PRC, "")]
        if not exact:
            raise LookupError(f"维基文库没有找到《{title}》（相近页面：{'、'.join(hits[:5]) or '无'}）")
        title = exact[0]
        pages = ws_pages([title])
    main = pages[title]
    wt = main["content"]
    law = Law(title)
    m = ABOLISH_RE.search(wt)
    if m:
        args = dict(re.findall(r"(\w+)\s*=\s*([^|]*)", m.group(1)))
        if args.get("y"):
            law.status = "已废止"
            law.abolished = {"date": f"{int(args['y']):04d}-{int(args.get('m', 1)):02d}-{int(args.get('d', 1)):02d}",
                             "by": args.get("law", "").strip()}
    # The main page usually transcludes the current version, e.g. {{:中华人民共和国劳动合同法 (2012年)}}
    content_title = title
    wt_version = wt
    inc = re.findall(r"\{\{:([^}|]+)\}\}", wt)
    if inc:
        content_title = inc[0].strip()
        vpages = ws_pages([content_title])
        wt_version = vpages.get(content_title, {}).get("content", "") or wt
        vm = re.search(r"\((\d{4})年\)", content_title)
        law.version = f"{vm.group(1)}年" if vm else ""
        law.notes = header_field(wt_version, "notes")
    if not law.notes:
        law.notes = header_field(wt, "notes")
    if not law.version:
        # latest year the text was passed / amended, e.g. （1995年6月30日…通过 … 1998年11月4日…修正）
        years = [int(y) for y in re.findall(r"((?:19|20)\d{2})年\d{1,2}月\d{1,2}日[^（）()]{0,80}?(?:通过|修正|修订)", law.notes)]
        y = str(max(years)) if years else (header_field(wt, "year") or header_field(wt, "y"))
        law.version = f"{y}年" if y.isdigit() else ""
    # Rendered HTML expands every kind of transclusion (sub-pages, scanned-page sections).
    html, revid = ws_parse(content_title)
    law.articles = parse_articles(html_to_lines(html)) if html else parse_articles(wikitext_to_lines(wt))
    law.effective = find_effective(wt_version, law.articles) or find_effective(wt, law.articles)
    law.source = {"site": "zh.wikisource.org", "page": content_title, "revid": revid or main["revid"],
                  "url": "https://zh.wikisource.org/wiki/" + urllib.parse.quote(content_title),
                  "fetched": date.today().isoformat()}
    # every historical version linked from the 沿革 notes, e.g. [[中华人民共和国公司法 (2018年)|…]]
    seen = {}
    for page, y in re.findall(r"\[\[(" + re.escape(title) + r"\s*\((\d{4})年\))", wt):
        seen[page.strip()] = int(y)
    law.versions = [{"page": p, "year": y} for p, y in sorted(seen.items(), key=lambda x: x[1])]
    return law


def fetch_version(page: str, title: str, online: bool = True) -> Law:
    """A specific historical version page such as 中华人民共和国公司法 (2018年)."""
    for base in (BUNDLED / "versions", CACHE / "versions"):
        cached = load_law_file(base, page)
        if cached:
            cached.title = title
            return cached
    if not online:
        raise LookupError(f"本地没有 {page}")
    raw = ws_pages([page]).get(page, {}).get("content", "")
    html, revid = ws_parse(page)
    vm = re.search(r"\((\d{4})年\)", page)
    law = Law(title, version=f"{vm.group(1)}年" if vm else "", status="历史版本", notes=header_field(raw, "notes"))
    law.articles = parse_articles(html_to_lines(html))
    law.effective = find_effective(raw, law.articles)
    law.source = {"site": "zh.wikisource.org", "page": page, "revid": revid,
                  "url": "https://zh.wikisource.org/wiki/" + urllib.parse.quote(page), "fetched": date.today().isoformat()}
    law.title = page                       # cache key = version page
    save_law(CACHE / "versions", law)
    law.title = title
    return law


# ---------------------------------------------------------------- library (bundled + cache + imported)

def _index_path(base: Path) -> Path:
    return base / "index.json"


def _load_index(base: Path) -> dict:
    p = _index_path(base)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"laws": {}, "aliases": {}}


def _law_file(base: Path, title: str) -> Path:
    safe = re.sub(r"[\\/:*?\"<>|\s]", "_", title)
    return base / f"{safe}.json.gz"


def save_law(base: Path, law: Law, aliases: list[str] | None = None) -> None:
    base.mkdir(parents=True, exist_ok=True)
    with gzip.open(_law_file(base, law.title), "wt", encoding="utf-8") as f:
        json.dump(law.to_json(), f, ensure_ascii=False, separators=(",", ":"))
    idx = _load_index(base)
    idx["laws"][law.title] = {"version": law.version, "effective": law.effective, "status": law.status,
                              "abolished": law.abolished, "articles": len(law.articles),
                              "source": {k: v for k, v in law.source.items() if k != "revids"}}
    for a in aliases or []:
        idx["aliases"][a] = law.title
    _index_path(base).write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def load_law_file(base: Path, title: str) -> Law | None:
    p = _law_file(base, title)
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return Law.from_json(json.load(f))


_memo: dict = {}   # (title, online, refresh) -> (law, where), see get_law


def all_aliases() -> dict[str, str]:
    out: dict[str, str] = {}
    for base in (BUNDLED, CACHE / "wikisource", CACHE / "official"):
        idx = _load_index(base)
        out.update(idx.get("aliases", {}))
        for t in idx.get("laws", {}):
            out.setdefault(t, t)
            short = t.replace(PRC, "")
            if short != t:
                out.setdefault(short, t)
    extra = ROOT / "assets" / "aliases.json"
    if extra.exists():
        for k, v in json.loads(extra.read_text(encoding="utf-8")).items():
            out.setdefault(k, v)
    return out


def resolve_title(name: str) -> str:
    name = name.strip().strip("《》").strip()
    name = re.sub(r"[（(][^）)]*(修正|修订|年)[^）)]*[）)]$", "", name).strip()   # 《公司法》（2023年修订）
    al = all_aliases()
    if name in al:
        return al[name]
    if not name.startswith(PRC) and (PRC + name) in al:
        return al[PRC + name]
    if re.search(r"(法|法典)$", name) and not name.startswith(PRC) and not re.search(r"(条例|规定|解释|办法|决定)$", name):
        return PRC + name
    return name


def get_law(name: str, online: bool = True, refresh: bool = False) -> tuple[Law | None, str]:
    """Return (law, where) — where is 'official' / 'bundled' / 'cache' / 'wikisource' / error message."""
    title = resolve_title(name)
    key = (title, online, refresh)
    if key in _memo:
        return _memo[key]
    for base, where in ((CACHE / "official", "official"), (BUNDLED, "bundled"), (CACHE / "wikisource", "cache")):
        if refresh and where == "cache":
            continue
        law = load_law_file(base, title)
        if law:
            _memo[key] = (law, where)
            return law, where
    if not online:
        res = (None, f"本地没有《{title}》，且未联网获取（去掉 --offline 或先运行 fetch / import）")
        _memo[key] = res
        return res
    try:
        law = fetch_wikisource(title)
    except LookupError as e:
        res = (None, str(e))
    except Exception as e:  # network problems
        res = (None, f"无法访问维基文库（{type(e).__name__}）。可从国家法律法规数据库下载该法官方文本后用 import 导入")
    else:
        if not law.articles and law.status != "已废止":
            res = (None, f"维基文库的《{title}》页面没有解析出条文")
        else:
            save_law(CACHE / "wikisource", law, [title.replace(PRC, "")] if title.startswith(PRC) else [])
            res = (law, "wikisource")
    _memo[key] = res
    return res


# ---------------------------------------------------------------- official file import

def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", " ", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    import html as _h
    return _h.unescape(text)


def import_official(path: Path, title: str | None = None, version: str = "", effective: str = "") -> Law:
    if path.suffix.lower() == ".docx":
        text = docx_text(path)
    else:
        text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not title:
        first = next((l.strip() for l in lines if l.strip()), "")
        title = first if len(first) < 60 else path.stem
    title = re.sub(r"\s+", "", title)
    law = Law(title, version=version, effective=effective)
    law.articles = parse_articles(lines)
    m = re.search(r"((?:19|20)\d{2})年\d{1,2}月\d{1,2}日[^）)]{0,60}(修正|修订|通过)[）)]?\s*$", text[:600], flags=re.M)
    if not version and m:
        law.version = f"{m.group(1)}年"
    law.source = {"site": "国家法律法规数据库（用户导入）", "file": str(path), "fetched": date.today().isoformat()}
    return law


# ---------------------------------------------------------------- citation extraction

@dataclass
class Citation:
    raw: str
    law_name: str
    article: str                 # key like "47" or "120-1"
    para: int | None = None
    item: int | None = None
    quote: str = ""
    sentence: str = ""
    start: int = 0
    implicit_law: bool = False   # 本法 / 该法 resolved from context
    siblings: list = field(default_factory=list)   # other articles of the same law cited in the same sentence

    def label(self) -> str:
        s = art_label(self.article)
        if self.para:
            s += f"第{int2cn(self.para)}款"
        if self.item:
            s += f"第{int2cn(self.item)}项"
        return s


LAW_NAME = r"《([^》]{2,60})》"
ART_TOKEN = re.compile(
    r"第\s*(" + NUM + r")\s*条(?:\s*之\s*(" + NUM + r"))?"
    r"(?:\s*第\s*(" + NUM + r")\s*款)?"
    r"(?:\s*第?\s*[（(]?\s*(" + NUM + r")\s*[）)]?\s*项)?"
)
SHARED_TOKEN = re.compile(r"第\s*(" + NUM + r")((?:\s*[、，,和及]\s*" + NUM + r")+)\s*条")   # 第三十八、三十九条
RANGE_TOKEN = re.compile(r"\s*(?:至|到|—|-|～|~)\s*第?\s*(" + NUM + r")\s*条")
QUOTE_RE = re.compile(r"^[^“”\"「」\n。]{0,24}?(?:规定|明确|指出|载明|写道|表述为)?\s*[:：，,]?\s*[“\"「]([^”\"」]{4,600})[”\"」]")
SENT_END = re.compile(r"[。！？!?\n]")


def _sentence(text: str, pos: int) -> str:
    """The sentence around pos; a 。 inside “quoted statute text” does not end it."""
    a = max(text.rfind(c, 0, pos) for c in "。！？!?\n")
    depth, i = 0, pos
    while i < len(text):
        ch = text[i]
        if ch in "“「":
            depth += 1
        elif ch in "”」":
            depth = max(0, depth - 1)
        elif ch == "\n" or (ch in "。！？!?" and depth == 0):
            i += 1
            break
        i += 1
    return text[a + 1:i].strip()


def extract_citations(text: str) -> list[Citation]:
    al = all_aliases()
    # bare law names (no 《》) that we know, longest first: 劳动合同法 before 劳动法
    bare_names = sorted({k for k in al if len(k) >= 3 and re.search(r"(法|法典|条例|解释)$", k)}, key=len, reverse=True)
    bare_re = re.compile("(" + "|".join(map(re.escape, bare_names)) + r")(?=\s*第)") if bare_names else None
    names: list[tuple[int, int, str]] = [(m.start(), m.end(), m.group(1)) for m in re.finditer(LAW_NAME, text)]
    if bare_re:
        taken = [(a, b) for a, b, _ in names]
        for m in bare_re.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            if text[max(0, m.start() - 1):m.start()] in ("《",):
                continue
            names.append((m.start(), m.end(), m.group(1)))
    for m in re.finditer(r"(本法|该法|同法|此法|上述法律|前述法律)(?=\s*第)", text):
        names.append((m.start(), m.end(), "@ctx"))
    names.sort()
    cites: list[Citation] = []
    last_law = ""
    for idx, (s, e, name) in enumerate(names):
        implicit = name == "@ctx"
        if implicit:
            if not last_law:
                continue
            name = last_law
        else:
            last_law = name
        nxt = names[idx + 1][0] if idx + 1 < len(names) else len(text)
        seg_end = min(nxt, e + 160)
        pos = e
        # the article reference must follow the law name closely (allow a version note or 编 name)
        gap = re.match(r"[\s　]*(?:[（(][^）)]{0,20}[）)])?[\s　]*(?:[^\s第。；;，,]{0,8}编)?[\s　]*", text[pos:seg_end])
        pos += gap.end() if gap else 0
        group_start = len(cites)
        sh = SHARED_TOKEN.match(text, pos)
        if sh:                                   # 第三十八、三十九条
            for tok in [sh.group(1)] + re.findall(NUM, sh.group(2)):
                n = cn2int(tok)
                if n:
                    cites.append(Citation(text[s:sh.end()], name, art_key(n), start=sh.start(), implicit_law=implicit))
            pos = sh.end()
            m = None
        else:
            m = ART_TOKEN.match(text, pos)
            if not m:
                continue
        while m and m.start() < seg_end:
            num = cn2int(m.group(1))
            sub = cn2int(m.group(2)) if m.group(2) else None
            para = cn2int(m.group(3)) if m.group(3) else None
            item = cn2int(m.group(4)) if m.group(4) else None
            if num:
                cites.append(Citation(text[s:m.end()], name, art_key(num, sub), para, item, start=m.start(), implicit_law=implicit))
            pos = m.end()
            r = RANGE_TOKEN.match(text, pos)         # 第三十八条至第四十条
            if r and num:
                hi = cn2int(r.group(1))
                if hi and num < hi <= num + 30:
                    for k in range(num + 1, hi + 1):
                        cites.append(Citation(text[s:r.end()], name, art_key(k), start=m.start(), implicit_law=implicit))
                pos = r.end()
            nm = re.match(r"[\s　]*(?:[、，,]|和|及|以及|或者?|与)[\s　]*(?=第)", text[pos:])
            if nm:                                    # 第三十八条、第三十九条
                m = ART_TOKEN.match(text, pos + nm.end())
                continue
            break
        # quoted text right after the last citation of this group
        if len(cites) > group_start:
            q = QUOTE_RE.match(text[pos:pos + 640])
            if q:
                cites[-1].quote = q.group(1)
    for c in cites:
        c.sentence = _sentence(text, c.start)
    for c in cites:
        law = resolve_title(c.law_name)
        c.siblings = [o.article for o in cites if o is not c and o.sentence == c.sentence and resolve_title(o.law_name) == law]
    return cites


# ---------------------------------------------------------------- verification

@dataclass
class Result:
    cite: Citation
    status: str                 # ok / quote_diff / quote_mismatch / no_article / no_para / no_item / abolished / suspect / unresolved / check_meaning
    law_title: str = ""
    law_where: str = ""
    law_version: str = ""
    article_text: str = ""
    messages: list[str] = field(default_factory=list)
    suggestion: str = ""
    score: float | None = None
    old_article: dict | None = None       # old_version: {"label": "2019年版第九条", "text": ...}
    current_article: dict | None = None   # old_version: the matching article of the version in force

    def to_dict(self) -> dict:
        c = self.cite
        return {
            "citation": f"《{self.law_title or c.law_name}》{c.label()}", "raw": c.raw, "status": self.status,
            "law": self.law_title, "version": self.law_version, "source": self.law_where,
            "quote": c.quote, "sentence": c.sentence, "article_text": self.article_text,
            "messages": self.messages, "suggestion": self.suggestion, "score": self.score,
            "old_article": self.old_article, "current_article": self.current_article,
        }


STATUS_LABEL = {
    "ok": "✓ 核对一致",
    "check_meaning": "○ 条文存在，请核对文意",
    "quote_diff": "△ 引文与原文有出入",
    "quote_mismatch": "✗ 引文与该条原文不符",
    "suspect": "✗ 疑似引错条号",
    "old_version": "✗ 引用的是修订前的旧版条号",
    "no_article": "✗ 条文不存在",
    "no_para": "✗ 款不存在",
    "no_item": "✗ 项不存在",
    "abolished": "✗ 法律已废止",
    "unresolved": "? 未能核验",
}
SEVERITY = {"ok": 0, "check_meaning": 1, "quote_diff": 2, "unresolved": 3, "suspect": 4, "old_version": 5, "quote_mismatch": 5,
            "no_item": 5, "no_para": 5, "no_article": 6, "abolished": 6}


def find_best_article(law: Law, probe: str, exclude: str | None = None) -> tuple[str, float]:
    best_k, best = "", 0.0
    for k, a in law.articles.items():
        if k == exclude:
            continue
        s, _ = best_window(probe, a.text)
        if s > best:
            best_k, best = k, s
    return best_k, best


PARTICLES = set("的之了和与及或在对向把被将其该本此等以为于由从而且并但")


def rare_terms(claim: str, law: Law, max_articles: int = 3) -> list[tuple[str, list[str]]]:
    """Distinctive legal terms in the claim: substrings (3–8 chars) that occur in only a few
    articles of the law, e.g. 寻衅滋事 / 回避 / 申请撤销裁决.  Longest first, no overlaps."""
    c = norm(claim)
    texts = {k: norm(a.text) for k, a in law.articles.items()}
    found: list[tuple[str, list[str]]] = []
    for length in range(8, 1, -1):
        for i in range(len(c) - length + 1):
            term = c[i:i + length]
            if term[0] in PARTICLES or term[-1] in PARTICLES:
                continue
            if any(term in t for t, _ in found):
                continue
            hits = [k for k, t in texts.items() if term in t]
            if 1 <= len(hits) <= max_articles:
                found.append((term, hits))
    return found


def topic_overlap(claim: str, art_text: str) -> float:
    a, b = bigrams(claim), bigrams(art_text)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), 40))


def claim_text(c: Citation) -> str:
    """What the sentence says about the article, with the citation itself and filler removed."""
    s = re.sub(r"^[\s（(]*[一二三四五六七八九十\d]+[、.．)）]\s*", "", c.sentence)
    s = re.sub(r"《[^》]*》|[^\s，。；]{0,12}(法|法典|条例)(?=第)|本法|该法|第[^条款项]{1,8}条(之[^款项]{1,4})?(第[^款]{1,4}款)?(第?[（(]?[^项]{1,4}[）)]?项)?", "", s)
    s = re.sub(r"根据|依据|按照|依照|规定|明确|载明|属于|情形|的规定|之规定|[:：“”\"]", "", s)
    return s


def _year(law: Law) -> int:
    m = re.match(r"(\d{4})", law.version or "")
    return int(m.group(1)) if m else 9999


def in_force(law: Law, ref: date, online: bool) -> tuple[Law, str]:
    """The version in force on `ref`.  The newest text may not be in force yet
    (e.g. an amendment passed in 2026 that takes effect on 2027-01-01), and an old
    document should be checked against the law as it stood at the time."""
    eff = parse_cn_date(law.effective)
    if not eff or eff <= ref or not law.versions:
        return law, ""
    cur_year = _year(law)
    for v in sorted((v for v in law.versions if v["year"] < cur_year), key=lambda x: -x["year"]):
        try:
            old = fetch_version(v["page"], law.title, online=online)
        except Exception:
            continue
        old_eff = parse_cn_date(old.effective)
        if old_eff is None or old_eff <= ref:
            old.status, old.versions = law.status, law.versions
            note = (f"《{law.title}》{law.version}版自{law.effective}起施行，"
                    f"{'该日期' if ref != date.today() else '目前'}适用的是{old.version}版，以下按{old.version}版核对")
            return old, note
    return law, f"注意：《{law.title}》{law.version}版自{law.effective}起施行，未能取得此前的版本，暂按{law.version}版核对"


def _items(a: Article, para: int | None) -> list[str]:
    return a.paras[para - 1]["items"] if para else [i for p in a.paras for i in p["items"]]


def has_subdivision(a: Article, para: int | None, item: int | None) -> bool:
    if para and para > len(a.paras):
        return False
    return not item or item <= len(_items(a, para))


def map_subdivision(old: Article, new: Article, para: int | None, item: int | None) -> str:
    """The paragraph/item of `new` matching the cited paragraph/item of `old`, e.g. "第三款" or
    "第一款第（一）项"; "" when nothing matches well enough."""
    label, new_para = "", None
    if para:
        scores = [similarity(old.paras[para - 1]["text"], p["text"]) for p in new.paras]
        if not scores or max(scores) < 0.6:
            return ""
        new_para = scores.index(max(scores)) + 1
        label = f"第{int2cn(new_para)}款"
    if item:
        src, cands = _items(old, para)[item - 1], _items(new, new_para)
        scores = [similarity(src, t) for t in cands]
        if scores and max(scores) >= 0.6:
            label += f"第（{int2cn(scores.index(max(scores)) + 1)}）项"
    return label


def check_old_versions(law: Law, c: Citation, r: Result, online: bool) -> None:
    """If the citation fits an earlier version of the law, say so and point to the current article."""
    current = law.source.get("page", "")
    olds = [v for v in law.versions if v["page"] != current and v["year"] < _year(law)][::-1][:3]
    claim = claim_text(c)
    cur_art = law.articles.get(c.article)
    own = best_window(claim, cur_art.text)[0] if (cur_art and len(norm(claim)) >= 8) else 0.0
    for v in olds:
        try:
            old = fetch_version(v["page"], law.title, online=online)
        except Exception:
            continue
        art = old.articles.get(c.article)
        if not art or not has_subdivision(art, c.para, c.item):
            continue   # the old version has no such article / paragraph / item either
        term = ""
        if c.quote:
            fits, _ = best_window(c.quote, art.text)
            ok = fits >= 0.95
        else:
            fits, _ = best_window(claim, art.text) if len(norm(claim)) >= 8 else (0.0, "")
            ok = fits >= 0.8 or (fits >= 0.55 and fits >= own + 0.3)
            if not ok and cur_art:
                # distinctive term: present in the old article, absent from the current one
                old_t, cur_t = norm(art.text), norm(cur_art.text)
                cands = [t for t, _h in rare_terms(claim, law) if len(t) >= 3 and t in old_t and t not in cur_t]
                if cands:
                    term, ok = max(cands, key=len), True
        if ok:
            k, s = find_best_article(law, art.text)
            r.status = "old_version"
            why = f"文中的“{term}”正是该条内容" if term else f"相似度 {fits:.0%}"
            r.messages.insert(0, f"这处引用与《{law.title}》{v['year']}年版的{art.label}相符（{why}）：很可能引用的是修订前的旧版条号")
            r.old_article = {"label": f"{old.version or v['year']}版{art.label}", "text": art.text}
            if k and s >= 0.6:
                new = law.articles[k]
                sub = map_subdivision(art, new, c.para, c.item) if (c.para or c.item) else ""
                r.suggestion = f"现行{law.version}版对应条文应为{art_label(k)}{sub}（与旧条文相似度 {s:.0%}）"
                r.current_article = {"label": f"{law.version}版{art_label(k)}", "text": new.text}
            return


def verify(c: Citation, online: bool, as_of: date | None) -> Result:
    law, where = get_law(c.law_name, online=online)
    if not law:
        return Result(c, "unresolved", law_title=resolve_title(c.law_name), messages=[where])
    law, note = in_force(law, as_of or date.today(), online)
    r = Result(c, "ok", law_title=law.title, law_where=where, law_version=law.version)
    if note:
        r.messages.append(note)
    _verify_article(law, c, r, as_of, online)
    if (r.status in ("no_article", "no_para", "no_item", "quote_mismatch", "suspect")
            and law.status != "已废止" and law.versions):
        check_old_versions(law, c, r, online)
    return r


def _verify_article(law: Law, c: Citation, r: Result, as_of: date | None, online: bool) -> None:
    if law.status == "已废止":
        ab = law.abolished or {}
        when = ab.get("date", "")
        by = ab.get("by", "")
        ref = date.fromisoformat(when) if re.match(r"\d{4}-\d{2}-\d{2}$", when or "") else None
        if ref and as_of and as_of < ref:
            r.messages.append(f"注意：《{law.title}》已于 {when} 废止{('，由《' + by + '》取代') if by else ''}；文书日期早于废止日，当时引用有效")
        else:
            r.status = "abolished"
            r.messages.append(f"《{law.title}》已于 {when or '（日期不详）'} 废止" + (f"，现由《{by}》取代，请改引新法相应条文" if by else ""))
            old = law.articles.get(c.article)
            if by and old:
                new, _w = get_law(by, online=online)
                if new:
                    k, s = find_best_article(new, old.text)
                    if k and s >= 0.5:
                        r.suggestion = f"新法对应条文可能是《{new.title}》{art_label(k)}（与旧条文相似度 {s:.0%}，请核对）"
            if not law.articles:
                return
    art = law.articles.get(c.article)
    if not art:
        mx = law.max_article()
        r.status = "no_article" if r.status != "abolished" else r.status
        r.messages.append(f"《{law.title}》（{law.version or '现行'}版）没有{art_label(c.article)}" + (f"（全法共 {mx} 条）" if mx and int(c.article.split('-')[0]) > mx else ""))
        probe = c.quote or claim_text(c)
        if probe and len(norm(probe)) >= 6:
            k, s = find_best_article(law, probe)
            if k and s >= 0.45 and not r.suggestion:
                r.suggestion = f"内容最接近的是{art_label(k)}（相似度 {s:.0%}）"
        return
    r.article_text = art.text
    ver = f"{law.version}版" if law.version else ""   # say which version: the old one may well have the paragraph
    if c.para:
        if c.para > len(art.paras):
            if r.status != "abolished":
                r.status = "no_para"
            r.messages.append(f"{ver}{art.label}只有 {len(art.paras)} 款，没有第{int2cn(c.para)}款")
            return
        para = art.paras[c.para - 1]
        target_text = "\n".join([para["text"]] + para["items"])
        items = para["items"]
    else:
        target_text = art.text
        items = [i for p in art.paras for i in p["items"]]
    if c.item:
        if c.item > len(items):
            if r.status != "abolished":
                r.status = "no_item"
            where_ = f"{ver}{art.label}{'第' + int2cn(c.para) + '款' if c.para else ''}"
            r.messages.append(f"{where_}不分项，没有第{int2cn(c.item)}项" if not items else
                              f"{where_}只有 {len(items)} 项，没有第{int2cn(c.item)}项")
            return
        target_text = items[c.item - 1]
    if c.quote:
        s, span = best_window(c.quote, target_text)
        r.score = round(s, 3)
        if s >= 0.97:
            r.status = "ok" if r.status != "abolished" else r.status
        elif s >= 0.75:
            if r.status != "abolished":
                r.status = "quote_diff"
            r.messages.append(f"引文与原文相似度 {s:.0%}：请逐字核对后改为原文")
        else:
            k, s2 = find_best_article(law, c.quote, exclude=c.article)
            if r.status != "abolished":
                r.status = "quote_mismatch"
            r.messages.append(f"引文与{art.label}原文相似度只有 {s:.0%}")
            if k and s2 >= 0.75:
                r.suggestion = f"这段引文实际出自{art_label(k)}（相似度 {s2:.0%}）"
    else:
        claim = claim_text(c)
        ov = topic_overlap(claim, target_text)
        own, _ = best_window(claim, target_text) if len(norm(claim)) >= 8 else (0.0, "")
        r.score = round(max(ov, own), 3)
        if r.status != "abolished":
            r.status = "check_meaning"
        if own >= 0.85 and r.status != "abolished":
            r.status = "ok"
            r.messages.append(f"文中表述与该条原文基本一致（{own:.0%}）")
        elif c.implicit_law and c.siblings:
            pass   # “依照本法第四十七条规定的…” inside another citation's sentence: the claim is about that citation
        elif len(norm(claim)) >= 8:
            k, s2 = find_best_article(law, claim, exclude=c.article)
            if k and s2 >= 0.5 and s2 > own + 0.2 and ov < 0.35:
                if r.status != "abolished":
                    r.status = "suspect"
                r.suggestion = f"文中所述内容与{art_label(k)}更吻合（相似度 {s2:.0%}，本条 {own:.0%}）"
            else:
                # A distinctive legal term in the sentence (寻衅滋事、回避…) that the cited article lacks
                # but another article has is a strong sign of a wrong (or outdated) article number.
                cited = norm(target_text)
                terms = [(t, h) for t, h in rare_terms(claim, law) if len(t) >= 2]
                in_cited = [t for t, h in terms if t in cited]
                elsewhere = [(t, h) for t, h in terms if c.article not in h and t not in cited and len(t) >= 4
                             and not set(h) & set(c.siblings)]   # the term may describe another article cited in the same sentence
                if elsewhere and not in_cited and r.status != "abolished":
                    t, h = max(elsewhere, key=lambda x: len(x[0]))
                    r.status = "suspect"
                    r.suggestion = f"文中提到的“{t}”见于{'、'.join(art_label(x) for x in h)}，而{art_label(c.article)}没有这一内容"


def check_text(text: str, online: bool = True, as_of: date | None = None) -> dict:
    cites = extract_citations(text)
    results = [verify(c, online, as_of) for c in cites]
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    problems = sum(1 for r in results if SEVERITY[r.status] >= 4)
    return {
        "total": len(results),
        "problems": problems,
        "counts": counts,
        "results": [r.to_dict() for r in results],
        "laws": sorted({(r.law_title, r.law_version, r.law_where) for r in results if r.law_title}),
    }


# ---------------------------------------------------------------- rendering

def short(s: str, n: int = 160) -> str:
    s = re.sub(r"\s+", " ", s)
    return s if len(s) <= n else s[:n] + "…"


def render_report(res: dict) -> str:
    out = [f"【法条引用核验】共识别 {res['total']} 处引用，其中 {res['problems']} 处有明确问题", ""]
    if not res["total"]:
        out.append("没有识别到“《法律名称》第X条”形式的引用。若文中用了简称或特殊写法，请改写后重试，或用 show 逐条查。")
        return "\n".join(out)
    order = sorted(enumerate(res["results"]), key=lambda x: (-SEVERITY[x[1]["status"]], x[0]))
    for n, (i, r) in enumerate(order, 1):
        out.append(f"{n}. {r['citation']}　{STATUS_LABEL[r['status']]}")
        out.append(f"   原句：{short(r['sentence'], 120)}")
        if r["quote"]:
            out.append(f"   文中引文：“{short(r['quote'], 120)}”")
        for m in r["messages"]:
            out.append(f"   · {m}")
        if r["suggestion"]:
            out.append(f"   → {r['suggestion']}")
        if r["status"] == "old_version" and r.get("old_article"):
            o, cur = r["old_article"], r.get("current_article")
            out.append(f"   旧版原文（{o['label']}）：{short(o['text'], 220)}")
            if cur:
                out.append(f"   现行对应条文（{cur['label']}）：{short(cur['text'], 220)}")
        elif r["article_text"] and r["status"] != "ok":
            out.append(f"   原文（{r['version'] or '现行'}版）：{short(r['article_text'], 220)}")
        out.append("")
    out.append("所用法律文本：")
    names = {"official": "用户导入的官方文本", "bundled": "随技能附带（转录自维基文库）", "cache": "本地缓存（维基文库）", "wikisource": "维基文库（刚获取）"}
    for t, v, w in res["laws"]:
        out.append(f" - 《{t}》{v + '版' if v else ''}：{names.get(w, w)}")
    out.append("")
    out.append("说明：○ 表示条号存在但文中没有直接引文，需要你对照原文判断文意是否相符；✗/△ 必须修改。"
               "转录文本仅供核对，正式文书请以国家法律法规数据库（flk.npc.gov.cn）的标准文本为准。")
    return "\n".join(out)


def render_article(law: Law, key: str, para: int | None, item: int | None, where: str) -> str:
    art = law.articles.get(key)
    head = f"《{law.title}》{law.version + '版' if law.version else ''}（{law.status}；来源：{where}）"
    if not art:
        return f"{head}\n没有{art_label(key)}（全法共 {law.max_article()} 条）"
    lines = [head, f"{art.chapter}" if art.chapter else ""]
    for pi, p in enumerate(art.paras, 1):
        mark = "→ " if para == pi else "  "
        lines.append(f"{mark}{art.label if pi == 1 else '　　'}（第{int2cn(pi)}款）{p['text']}")
        for ii, it in enumerate(p["items"], 1):
            m2 = "→ " if (item == ii and (para in (None, pi))) else "  "
            lines.append(f"{m2}　　{it}")
    return "\n".join(l for l in lines if l is not None)


def parse_ref(ref: str) -> tuple[str, int | None, int | None]:
    m = ART_TOKEN.search(ref) if "第" in ref else None
    if m:
        num, sub = cn2int(m.group(1)), cn2int(m.group(2)) if m.group(2) else None
        return art_key(num, sub), cn2int(m.group(3)) if m.group(3) else None, cn2int(m.group(4)) if m.group(4) else None
    parts = re.split(r"[.\-:]", ref)
    num = cn2int(parts[0])
    return art_key(num), (cn2int(parts[1]) if len(parts) > 1 else None), (cn2int(parts[2]) if len(parts) > 2 else None)


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    offline_help = "只用本地法律库，不联网（放在子命令前后都可以；也可设环境变量 FATIAO_OFFLINE=1）"
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help=offline_help)
    # Accept --offline after any subcommand too; SUPPRESS keeps a subcommand from resetting the global flag.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--offline", action="store_true", default=argparse.SUPPRESS, help=offline_help)
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", parents=[common])
    c.add_argument("text", nargs="?")
    c.add_argument("--file")
    c.add_argument("--as-of", help="文书日期 YYYY-MM-DD（判断引用时法律是否已废止）")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("show", parents=[common])
    s.add_argument("law")
    s.add_argument("ref", help="条号：47 / 第四十七条 / 47.2（第二款）/ 39.1.3")
    s.add_argument("--as-of", help="按该日期施行的版本显示 YYYY-MM-DD（默认今天）")
    se = sub.add_parser("search", parents=[common])
    se.add_argument("law")
    se.add_argument("keywords", nargs="+")
    se.add_argument("--as-of", help="按该日期施行的版本搜索 YYYY-MM-DD（默认今天）")
    se.add_argument("--limit", type=int, default=8)
    f = sub.add_parser("fetch", parents=[common])
    f.add_argument("law")
    f.add_argument("--alias", action="append", default=[])
    im = sub.add_parser("import", parents=[common])
    im.add_argument("file")
    im.add_argument("--title")
    im.add_argument("--version", default="")
    im.add_argument("--effective", default="")
    im.add_argument("--alias", action="append", default=[])
    sub.add_parser("list", parents=[common])
    a = ap.parse_args(argv)
    a.offline = a.offline or os.environ.get("FATIAO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")

    if a.cmd == "check":
        text = a.text
        if a.file:
            text = Path(a.file).read_text(encoding="utf-8-sig")
        if not text:
            text = sys.stdin.read()
        as_of = date.fromisoformat(a.as_of) if a.as_of else None
        res = check_text(text, online=not a.offline, as_of=as_of)
        print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else render_report(res))
        return 1 if res["problems"] else 0
    if a.cmd == "show":
        law, where = get_law(a.law, online=not a.offline)
        if not law:
            print(where)
            return 2
        law, note = in_force(law, date.fromisoformat(a.as_of) if a.as_of else date.today(), not a.offline)
        if note:
            print(note)
        key, para, item = parse_ref(a.ref)
        print(render_article(law, key, para, item, where))
        return 0
    if a.cmd == "search":
        law, where = get_law(a.law, online=not a.offline)
        if not law:
            print(where)
            return 2
        law, note = in_force(law, date.fromisoformat(a.as_of) if a.as_of else date.today(), not a.offline)
        if note:
            print(note)
        kws = [norm(k) for k in a.keywords]
        scored = []
        for k, art in law.articles.items():
            t = norm(art.text)
            hit = sum(t.count(w) for w in kws if w)
            if hit and all(w in t for w in kws):
                scored.append((hit, k, art))
        scored.sort(key=lambda x: (-x[0], int(x[1].split("-")[0])))
        print(f"《{law.title}》{law.version + '版' if law.version else ''} 中同时含有“{'”“'.join(a.keywords)}”的条文：{len(scored)} 条")
        for _, k, art in scored[:a.limit]:
            print(f"- {art.label}：{short(art.text, 200)}")
        return 0
    if a.cmd == "fetch":
        if a.offline:
            print("fetch 需要联网访问维基文库；离线时请改用 import 导入官方文本")
            return 2
        law = fetch_wikisource(resolve_title(a.law))
        save_law(CACHE / "wikisource", law, a.alias)
        print(f"已获取《{law.title}》{law.version}版，{len(law.articles)} 条，状态：{law.status}，来源：{law.source.get('url')}")
        return 0
    if a.cmd == "import":
        law = import_official(Path(a.file), a.title, a.version, a.effective)
        aliases = a.alias + ([law.title.replace(PRC, "")] if law.title.startswith(PRC) else [])
        save_law(CACHE / "official", law, aliases)
        print(f"已导入《{law.title}》{law.version}，{len(law.articles)} 条（优先于附带文本和维基文库使用）")
        return 0
    if a.cmd == "list":
        for base, label in ((CACHE / "official", "用户导入"), (BUNDLED, "随技能附带"), (CACHE / "wikisource", "维基文库缓存")):
            idx = _load_index(base)
            if idx["laws"]:
                print(f"[{label}] {base}")
                for t, info in sorted(idx["laws"].items()):
                    print(f"  《{t}》{info.get('version', '')} {info.get('status', '')} {info.get('articles', 0)}条")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
