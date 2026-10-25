#!/usr/bin/env python3
"""List every line of a source document that carries a likely critical fact.

This is a safety net, not an extractor you can trust blindly: it finds lines
with dates, money, percentages, numbers, phone numbers, deadline words and
eligibility words so that nothing gets skipped when you build facts.json by
hand.  It also lists numeric dates whose day/month order is ambiguous and
personal data that must not leak into the outputs.

Usage:
    python extract_facts.py source.txt               # human-readable list
    python extract_facts.py source.txt --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cfa_common import (  # noqa: E402
    ensure_utf8_stdout, extract_dates, extract_numbers, extract_phones,
    find_ambiguous_dates, nfkc, read_text,
)
from check_privacy import find_pii  # noqa: E402

DEADLINE_WORDS = re.compile(
    r"deadline|due|no later than|by\s+\w+\s+\d|before|until|postmark|expire|within\s+\d+|"
    r"截止|截至|之前|以前|逾期|届时|期限|期间|内(?:办理|提交|缴纳|申请)|起至|至\d|日前",
    re.I,
)
ELIGIBILITY_WORDS = re.compile(
    r"eligib|qualif|must|required|only if|unless|except|not eligible|regardless|at least|"
    r"income limit|household|resident|citizen|"
    r"符合|条件|资格|须|必须|应当|不得|不予|除外|以下|以上|不超过|不低于|户籍|常住|对象|人员",
    re.I,
)
DOC_WORDS = re.compile(r"proof|document|bring|copy of|ID\b|identification|材料|证明|证件|复印件|身份证|户口", re.I)
HEDGE_WORDS = re.compile(r"\bmay\b|\bmight\b|subject to|at the discretion|generally|in principle|if funds|原则上|一般|视情况|酌情|可能|有关规定|另行通知", re.I)


def scan(text: str) -> dict:
    lines = text.splitlines()
    candidates = []
    for no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        tags = []
        full, partial = extract_dates(line)
        if full or partial:
            tags.append("date")
        t = nfkc(line)
        if re.search(r"[$¥€£]\s*\d|\d\s*(?:元|美元|dollars?|USD|RMB|块)", t, re.I):
            tags.append("money")
        if re.search(r"\d\s*%|percent|百分之", t, re.I):
            tags.append("percent")
        if extract_phones(line):
            tags.append("phone")
        if DEADLINE_WORDS.search(line):
            tags.append("deadline-word")
        if ELIGIBILITY_WORDS.search(line):
            tags.append("eligibility-word")
        if DOC_WORDS.search(line):
            tags.append("document-word")
        if HEDGE_WORDS.search(line):
            tags.append("hedge-word")
        nums = sorted(n for n in extract_numbers(line) if n not in {"0", "1"})
        if nums and not tags:
            tags.append("number")
        if tags:
            candidates.append({
                "line": no,
                "tags": tags,
                "numbers": nums,
                "dates": sorted(full),
                "text": line.strip(),
            })
    return {
        "line_count": len(lines),
        "candidates": candidates,
        "ambiguous_dates": find_ambiguous_dates(text),
        "personal_data": find_pii(text),
    }


def main() -> int:
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="plain-text source document (UTF-8)")
    ap.add_argument("--json", help="also write the result to this JSON file")
    args = ap.parse_args()

    result = scan(read_text(args.source))
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(result['candidates'])} candidate lines out of {result['line_count']}\n")
    for c in result["candidates"]:
        print(f"L{c['line']:>4} [{', '.join(c['tags'])}] {c['text']}")
    if result["ambiguous_dates"]:
        print("\nAmbiguous numeric dates (day/month order unclear; spell the month out and flag if unsure):")
        for d in result["ambiguous_dates"]:
            print(f"  {d}")
    if result["personal_data"]:
        print("\nPersonal data found (keep it OUT of every output unless the user explicitly asks):")
        for p in result["personal_data"]:
            print(f"  {p['kind']}: {p['value']}")
    print("\nLines tagged hedge-word often need a needs_review flag: keep the uncertainty, never firm it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
