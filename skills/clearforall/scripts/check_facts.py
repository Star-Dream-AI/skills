#!/usr/bin/env python3
"""Check that simplified outputs still carry every critical fact, traceably.

What it verifies:

1. facts.json is well formed (ids unique, required fields present).
2. Every ``source_quote`` really occurs in the source text.  A quote that is
   not there means the "source" was paraphrased or invented, so traceability
   is broken.  This is a hard failure.
3. Every fact's ``value`` occurs in the source too, unless the fact is marked
   ``"derived": true`` *and* ``needs_review`` (computed numbers need a human).
4. Every output carries every fact's value, in any notation or language
   ("$1,250" / "1250 美元", "2027-03-31" / "2027年3月31日" / "March 31, 2027").
   Facts tagged with ``"outputs": [...]`` are only checked in those files.
5. In HTML outputs, each fact is wrapped in an element with ``data-fact="F#"``
   whose text contains the value, so a reviewer can jump from any claim to its
   source entry.
6. Numbers and dates in the outputs that appear nowhere in the source are
   reported: they may be invented or computed.
7. Uncertain facts are tied to a review item; while review items are open the
   HTML must show the draft notice.  With ``--final`` every review item must
   have a ``resolution`` written by a person.

Usage:
    python check_facts.py --facts facts.json --source source.txt out.html out.md [--final]
"""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cfa_common import (  # noqa: E402
    Report, ensure_utf8_stdout, extract_dates, extract_numbers, html_to_text,
    load_json, output_text, quote_in_source, read_text, value_present,
)

REQUIRED = ("id", "category", "claim", "value_type", "source_quote", "location")
CATEGORIES = {
    "deadline", "date", "amount", "eligibility", "exclusion", "requirement",
    "document", "procedure", "contact", "penalty", "right", "other",
}
VALUE_TYPES = {"date", "money", "number", "percent", "duration", "phone", "range", "text"}
DRAFT_NOTICE_ID = "cfa-draft-notice"


class _FactSpans(HTMLParser):
    """Collect the text inside every element carrying data-fact / data-review."""

    VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "source", "area", "col", "embed", "track", "base"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, list[str], list[str]]] = []
        self.fact_text: dict[str, list[str]] = {}
        self.review_ids: set[str] = set()
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if a.get("data-review"):
            self.review_ids.update(a["data-review"].split())
        if tag in self.VOID:
            return
        facts = (a.get("data-fact") or "").split()
        self.stack.append((tag, facts, []))

    def handle_endtag(self, tag):
        # Pop to the matching tag; tolerate sloppy nesting.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for t, facts, buf in self.stack[i:][::-1]:
                    text = "".join(buf)
                    for fid in facts:
                        self.fact_text.setdefault(fid, []).append(text)
                del self.stack[i:]
                return

    def handle_data(self, data):
        for _, _, buf in self.stack:
            buf.append(data)


def output_text_without_sources(path: str) -> str:
    raw = read_text(path)
    raw = re.sub(r"<(section|div|aside|ol)[^>]*\bid=\"sources\"[^>]*>.*?</\1>", "", raw, flags=re.S | re.I)
    return html_to_text(raw)


def check(facts_path: str, source_path: str, outputs: list[str], final: bool) -> Report:
    rep = Report("facts & traceability")
    data = load_json(facts_path)
    source = read_text(source_path)
    facts = data.get("facts", [])
    reviews = data.get("review_items", [])

    if not data.get("source", {}).get("title"):
        rep.warn("source.title is empty: record which document (and version/date) this came from")
    if not facts:
        rep.fail("facts.json has no facts")
        return rep

    # 1. schema
    ids = [f.get("id") for f in facts]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        rep.fail(f"duplicate fact ids: {sorted(dupes)}")
    for f in facts:
        missing = [k for k in REQUIRED if not str(f.get(k, "")).strip()]
        if missing:
            rep.fail(f"{f.get('id', '?')}: missing {', '.join(missing)}")
        if f.get("category") not in CATEGORIES:
            rep.warn(f"{f.get('id')}: unknown category '{f.get('category')}'")
        if f.get("value_type") not in VALUE_TYPES:
            rep.fail(f"{f.get('id')}: value_type must be one of {sorted(VALUE_TYPES)}")
        if f.get("value_type") not in {"text", None} and not str(f.get("value", "")).strip():
            rep.fail(f"{f.get('id')}: value_type {f.get('value_type')} needs a canonical value")

    # 2 + 3. grounded in the source
    src_nums = extract_numbers(source)
    src_full, src_partial = extract_dates(source)
    for f in facts:
        fid = f.get("id")
        if not quote_in_source(str(f.get("source_quote", "")), source):
            rep.fail(f"{fid}: source_quote not found verbatim in the source -> fix the quote, never paraphrase it")
        found, note = value_present(f, source)
        if not found:
            if f.get("derived") and f.get("needs_review"):
                rep.warn(f"{fid}: derived value {f.get('value')} (not in source) - flagged for review, OK")
            elif f.get("derived"):
                rep.fail(f"{fid}: derived value {f.get('value')} is not in the source and is not flagged needs_review")
            else:
                rep.fail(f"{fid}: value {f.get('value')} is not in the source ({note}); if computed, set derived + needs_review")
    rep.ok(f"checked {len(facts)} facts against the source")

    # 7a. review bookkeeping
    review_ids = {r.get("id") for r in reviews}
    flagged = [f for f in facts if f.get("needs_review")]
    for f in flagged:
        if not f.get("review_reason"):
            rep.fail(f"{f['id']}: needs_review without review_reason")
        if not any(f["id"] in r.get("fact_ids", []) for r in reviews):
            rep.fail(f"{f['id']}: needs_review but no review_items entry lists it")
    for r in reviews:
        if not r.get("question_for_reviewer"):
            rep.warn(f"{r.get('id')}: review item has no question_for_reviewer")
        if final and not str(r.get("resolution", "")).strip():
            rep.fail(f"{r.get('id')}: --final but this review item has no resolution from a person")
    open_reviews = [r for r in reviews if not str(r.get("resolution", "")).strip()]

    # 4-6. outputs
    for out in outputs:
        name = Path(out).name
        text = output_text(out)
        scoped = [f for f in facts if not f.get("outputs") or name in f["outputs"]]
        missing = []
        for f in scoped:
            ok, note = value_present(f, text)
            if not ok:
                missing.append(f"{f['id']} ({note})")
            elif note and "year" in note:
                rep.warn(f"{name}: {f['id']} {note}")
        if missing:
            rep.fail(f"{name}: missing fact values: {'; '.join(missing)}")
        else:
            rep.ok(f"{name}: all {len(scoped)} applicable fact values present")

        # 6. numbers not in source (the Sources list cites line numbers, so skip it)
        scan_text = text
        if name.lower().endswith((".html", ".htm")):
            scan_text = output_text_without_sources(out)
        out_nums = extract_numbers(scan_text)
        fact_vals = {str(f.get("value", "")) for f in facts}
        strange = sorted(
            n for n in out_nums - src_nums - fact_vals
            if not (n.isdigit() and int(n) <= 12) and n not in {"100"}
        )
        if strange:
            rep.warn(f"{name}: numbers not in the source: {', '.join(strange[:15])} - invented, computed or a step number? computed values need derived+needs_review")
        out_full, _ = extract_dates(text)
        new_dates = sorted(out_full - src_full - {str(f.get('value')) for f in facts})
        if new_dates:
            rep.warn(f"{name}: dates not in the source: {', '.join(new_dates)}")

        # 5 + 7b. HTML traceability and draft notice
        if name.lower().endswith((".html", ".htm")):
            p = _FactSpans()
            p.feed(read_text(out))
            untraced, wrong = [], []
            for f in scoped:
                spans = p.fact_text.get(f["id"])
                if not spans:
                    untraced.append(f["id"])
                    continue
                if f.get("value_type", "text") != "text":
                    if not any(value_present(f, s)[0] for s in spans):
                        wrong.append(f["id"])
            if untraced:
                rep.fail(f"{name}: no data-fact element for {', '.join(untraced)}")
            if wrong:
                rep.fail(f"{name}: data-fact element text does not contain the value for {', '.join(wrong)}")
            if not untraced and not wrong:
                rep.ok(f"{name}: every fact is traceable via data-fact")
            if open_reviews and DRAFT_NOTICE_ID not in p.ids:
                rep.fail(f"{name}: {len(open_reviews)} open review items but no element with id=\"{DRAFT_NOTICE_ID}\"")
            if not open_reviews and DRAFT_NOTICE_ID in p.ids and final:
                rep.warn(f"{name}: all reviews resolved but the draft notice is still shown")
            stray = p.review_ids - review_ids
            if stray:
                rep.warn(f"{name}: data-review ids not in facts.json: {sorted(stray)}")
    return rep


def main() -> int:
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--facts", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--final", action="store_true", help="require every review item to be resolved")
    ap.add_argument("outputs", nargs="+")
    args = ap.parse_args()
    rep = check(args.facts, args.source, args.outputs, args.final)
    print(rep.render())
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
