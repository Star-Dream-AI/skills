#!/usr/bin/env python3
"""Rough plain-language metrics for English and Chinese text.

Numbers are a guide, not a goal: a short sentence that drops an "only if" is
worse than a long one that keeps it.  Use the report to find the sentences
worth rewriting, then rewrite them by hand.

English: average words per sentence, share of sentences over 25 words,
Flesch-Kincaid grade (syllables estimated), bureaucratic phrases.
Chinese: average characters per sentence, sentences over 40 characters,
公文套话 (officialese) that has a plainer equivalent.

Tables, headings and the sources / review sections are skipped, because they
are not running prose.

Usage:
    python readability.py plain-en.md
    python readability.py page.html --lang zh --max-avg 30
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cfa_common import CJK_RE, Report, ensure_utf8_stdout, html_to_text, read_text  # noqa: E402

JARGON_EN = [
    "pursuant to", "hereinafter", "notwithstanding", "aforementioned", "in accordance with",
    "shall", "heretofore", "therein", "thereof", "whereas", "in lieu of", "prior to",
    "subsequent to", "commence", "utilize", "remuneration", "in the event that",
    "with respect to", "for the purpose of", "is required to", "it is incumbent",
]
JARGON_ZH = [
    "兹", "特此", "予以", "上述", "依据", "按照有关规定", "有关事项", "现将", "如下",
    "凡", "须", "应予", "均", "暨", "相关部门", "原则上", "视同", "参照执行",
    "统筹", "落实", "进一步", "切实", "不予", "届时", "自行",
]
SKIP_SECTION = re.compile(r"^(#+\s*)?(sources?|where this (information )?comes from|references?|for reviewers?|review|needs? (human )?review|信息来源|来源|出处|待复核|需要人工复核|复核)", re.I)


def prose(raw: str, is_html: bool) -> str:
    if is_html:
        # Drop tables and the sources / review blocks before extracting text.
        raw = re.sub(r"<table.*?</table>", "\n", raw, flags=re.S | re.I)
        raw = re.sub(r"<(section|aside|div)[^>]*(id|class)=\"[^\"]*(source|review|draft)[^\"]*\"[^>]*>.*?</\1>", "\n", raw, flags=re.S | re.I)
        raw = re.sub(r"<h[1-6][^>]*>.*?</h[1-6]>", "\n", raw, flags=re.S | re.I)
        text = html_to_text(raw)
    else:
        kept, skipping = [], False
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("#"):
                skipping = bool(SKIP_SECTION.match(s))
                continue
            if skipping or s.startswith("|") or s.startswith("<!--") or s.startswith("---"):
                continue
            kept.append(re.sub(r"[*_`>]|\[([^\]]*)\]\([^)]*\)", r"\1", line))
        text = "\n".join(kept)
    return text


def sentences(text: str, zh: bool) -> list[str]:
    # A line break also ends a "sentence" (list items rarely end with a period).
    parts = re.split(r"(?<=[。！？!?；;])|\n+" if zh else r"(?<=[.!?])\s+|\n+", text)
    out = []
    for p in parts:
        p = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", p).strip()
        if len(p) > 1:
            out.append(p)
    return out


def syllables(word: str) -> int:
    w = word.lower().strip(".,;:!?\"'()")
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def analyse(path: str, lang: str | None, max_avg: float | None) -> Report:
    raw = read_text(path)
    text = prose(raw, path.lower().endswith((".html", ".htm")))
    cjk = len(CJK_RE.findall(text))
    zh = lang == "zh" or (lang is None and cjk > len(re.findall(r"[A-Za-z]+", text)))
    rep = Report(f"readability ({'zh' if zh else 'en'}): {Path(path).name}")
    sents = sentences(text, zh)
    if not sents:
        rep.fail("no prose found")
        return rep

    if zh:
        lengths = [len(CJK_RE.findall(s)) + len(re.findall(r"[A-Za-z0-9]+", s)) for s in sents]
        avg = sum(lengths) / len(lengths)
        limit = max_avg or 30
        long = [s for s, n in zip(sents, lengths) if n > 40]
        (rep.ok if avg <= limit else rep.fail)(f"average {avg:.1f} characters per sentence (target <= {limit})")
        jargon = sorted(j for j in JARGON_ZH if j in text)
    else:
        word_counts = [len(re.findall(r"[A-Za-z0-9'’$%.-]+", s)) for s in sents]
        words = sum(word_counts)
        avg = words / len(sents)
        limit = max_avg or 20
        long = [s for s, n in zip(sents, word_counts) if n > 25]
        syl = sum(syllables(w) for s in sents for w in re.findall(r"[A-Za-z]+", s))
        fk = 0.39 * avg + 11.8 * (syl / max(words, 1)) - 15.59
        (rep.ok if avg <= limit else rep.fail)(f"average {avg:.1f} words per sentence (target <= {limit})")
        (rep.ok if fk <= 8 else rep.warn)(f"Flesch-Kincaid grade ~{fk:.1f} (target <= 8; numbers and names inflate it)")
        low = text.lower()
        jargon = sorted({j for j in JARGON_EN if re.search(r"\b" + re.escape(j) + r"\b", low)})

    share = len(long) / len(sents)
    (rep.ok if share <= 0.1 else rep.warn)(f"{len(long)} of {len(sents)} sentences are long ({share:.0%})")
    for s in long[:5]:
        rep.warn(f"long sentence: {s[:90]}{'...' if len(s) > 90 else ''}")
    if jargon:
        rep.warn(f"officialese with a plainer alternative: {', '.join(jargon)}")
    return rep


def main() -> int:
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--lang", choices=["en", "zh"], help="default: auto-detect per file")
    ap.add_argument("--max-avg", type=float, help="max average sentence length (en words / zh characters)")
    args = ap.parse_args()
    failed = False
    for f in args.files:
        rep = analyse(f, args.lang, args.max_avg)
        print(rep.render())
        failed |= rep.failed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
