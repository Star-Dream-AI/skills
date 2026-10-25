#!/usr/bin/env python3
"""Make sure personal data in the source does not leak into the outputs.

Public-service documents are often personal letters (a benefit decision, a
recertification notice) with a name, case number, address or ID number in
them.  A simplified version is likely to be printed, saved on a shared tablet
or forwarded, so by default none of that may appear in an output.

Public contact details of the agency (its hotline, office address) are fine:
record them in facts.json with category "contact" and they are allowed.

Usage:
    python check_privacy.py --source source.txt --facts facts.json out1.html out2.md
    python check_privacy.py --source source.txt --allow "Zhang" out.md   # user asked to keep it
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cfa_common import Report, digits_only, ensure_utf8_stdout, load_json, nfkc, output_text, read_text  # noqa: E402

LABEL_EN = r"(?:Case|Account|Client|Member|Policy|Application|Reference|Ref|Customer|Claim|Medicaid|SNAP|EBT|Card|Household)"
LABEL_ZH = r"(?:案件|档案|账户|帐户|账号|申请|参保|身份证|社保卡|医保卡|客户|个人|证件|受理|卡)"

PATTERNS = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("us-ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("cn-id-number", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("cn-mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("labeled-id", re.compile(LABEL_EN + r"\s*(?:No\.?|Number|Num\.?|#|ID)\s*[:#：]?\s*([A-Z0-9][A-Z0-9-]{3,})", re.I)),
    ("labeled-id", re.compile(LABEL_ZH + r"\s*(?:编号|号码|号)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9-]{3,})")),
    ("person-name", re.compile(r"(?:Dear|Name|Applicant|Client|Recipient|Head of Household)\s*[:：]?\s*(?:Mr\.|Ms\.|Mrs\.|Mx\.|Dr\.)?\s*([A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,2})")),
    ("person-name", re.compile(r"(?:尊敬的|姓名\s*[:：]|申请人\s*[:：]|参保人\s*[:：]|收件人\s*[:：])\s*([一-鿿]{2,4}?)(?=[\s,，:：先女同（(]|$)")),
    ("street-address", re.compile(r"\d{1,6}\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Lane|Ln\.?|Drive|Dr\.?|Boulevard|Blvd\.?|Court|Ct\.?|Way|Place|Pl\.?)(?:,?\s*(?:Apt|Unit|#)\.?\s*\w+)?")),
    ("street-address", re.compile(r"[一-鿿]{2,12}(?:路|街|巷|弄)\d+号(?:[一-鿿\d]{0,10}(?:室|单元|栋|楼))?")),
]
# Salutations that are not names.
NOT_NAMES = {"Sir", "Madam", "Customer", "Applicant", "Client", "Recipient", "Resident", "Neighbor"}


def find_pii(text: str) -> list[dict]:
    t = nfkc(text)
    found: list[dict] = []
    seen = set()
    for kind, pat in PATTERNS:
        for m in pat.finditer(t):
            value = (m.group(1) if m.groups() else m.group(0)).strip()
            if kind == "person-name" and value.split()[0] in NOT_NAMES:
                continue
            key = (kind, value)
            if key not in seen:
                seen.add(key)
                found.append({"kind": kind, "value": value})
    return found


def allowed_values(facts_path: str | None, extra: list[str]) -> list[str]:
    allowed = list(extra)
    if facts_path:
        data = load_json(facts_path)
        for f in data.get("facts", []):
            if f.get("category") == "contact":
                allowed += [str(f.get("value", "")), str(f.get("source_quote", ""))]
    return [a for a in allowed if a]


def leaked(pii: dict, text: str) -> bool:
    value = pii["value"]
    t = nfkc(text)
    if pii["kind"] in {"us-ssn", "cn-id-number", "cn-mobile", "labeled-id"}:
        if value.lower() in t.lower():
            return True
        # Same digits with different separators ("4471 0928 33").  Each run is
        # checked on its own so unrelated numbers are never stitched together.
        d = digits_only(value)
        return len(d) >= 6 and any(d in digits_only(run) for run in re.findall(r"[\d][\d\s.-]{4,}", t))
    if pii["kind"] == "person-name":
        # A full name, or the given name + family name in either order.
        parts = value.split()
        if len(parts) >= 2:
            return value in t or " ".join(reversed(parts)) in t
        return value in t
    if pii["kind"] == "street-address":
        head = re.match(r"\d+\s+\w+", value)
        return value in t or bool(head and head.group(0) in t)
    return value in t


def main() -> int:
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--facts", help="facts.json; contact facts are treated as public")
    ap.add_argument("--allow", action="append", default=[], help="value the user explicitly asked to keep")
    ap.add_argument("outputs", nargs="+")
    args = ap.parse_args()

    rep = Report("privacy")
    pii = find_pii(read_text(args.source))
    allow = allowed_values(args.facts, args.allow)
    pii = [p for p in pii if not any(p["value"] in a or digits_only(p["value"]) and digits_only(p["value"]) == digits_only(a) for a in allow)]
    if not pii:
        rep.ok("no personal data detected in the source (still read it yourself: detection is pattern-based)")
    for out in args.outputs:
        text = output_text(out)
        hits = [p for p in pii if leaked(p, text)]
        for p in hits:
            rep.fail(f"{Path(out).name}: contains {p['kind']} '{p['value']}' from the source")
        if pii and not hits:
            rep.ok(f"{Path(out).name}: none of the {len(pii)} personal data items appear")
    print(rep.render())
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
