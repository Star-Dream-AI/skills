#!/usr/bin/env python3
"""Run every ClearForAll check on one output folder and write a report.

Expected folder layout (names other than facts.json are discovered):

    out/
      source.txt        plain-text copy of the original document
      facts.json        the fact ledger
      *.md              plain-language versions
      *.html            accessible pages
      review.md         questions for a human reviewer (required if any review items)

Usage:
    python validate_all.py out/ [--source out/source.txt] [--final] [--allow VALUE]

Exit code 0 means no FAIL lines.  WARN lines still deserve a look.
The report is also saved as out/validation-report.txt.
"""

from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_facts  # noqa: E402
import check_html  # noqa: E402
import check_privacy  # noqa: E402
import readability  # noqa: E402
from cfa_common import Report, ensure_utf8_stdout, load_json, read_text  # noqa: E402

NOT_OUTPUTS = {"review.md", "validation-report.txt", "readme.md", "notes.md"}


def main() -> int:
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--source", help="default: <folder>/source.txt")
    ap.add_argument("--facts", help="default: <folder>/facts.json")
    ap.add_argument("--final", action="store_true", help="every review item must be resolved by a person")
    ap.add_argument("--allow", action="append", default=[], help="personal value the user asked to keep")
    args = ap.parse_args()

    folder = Path(args.folder)
    source = Path(args.source) if args.source else folder / "source.txt"
    facts = Path(args.facts) if args.facts else folder / "facts.json"
    reports: list[Report] = []
    setup = Report("setup")
    reports.append(setup)
    for need in (source, facts):
        if not need.exists():
            setup.fail(f"missing {need}")
    outputs = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in {".md", ".html", ".htm"} and p.name.lower() not in NOT_OUTPUTS
    ) if folder.is_dir() else []
    htmls = [p for p in outputs if p.suffix.lower() in {".html", ".htm"}]
    mds = [p for p in outputs if p.suffix.lower() == ".md"]
    if not htmls:
        setup.fail("no HTML output found")
    if not mds:
        setup.warn("no plain-language .md output found")

    if not setup.failed:
        reports.append(check_facts.check(str(facts), str(source), [str(p) for p in outputs], args.final))
        for h in htmls:
            reports.append(check_html.lint(str(h)))
        for o in outputs:
            reports.append(readability.analyse(str(o), None, None))

        priv = Report("privacy")
        buf = io.StringIO()
        sys_argv = sys.argv
        try:
            sys.argv = ["check_privacy.py", "--source", str(source), "--facts", str(facts)]
            for a in args.allow:
                sys.argv += ["--allow", a]
            sys.argv += [str(p) for p in outputs]
            with redirect_stdout(buf):
                code = check_privacy.main()
        finally:
            sys.argv = sys_argv
        for line in buf.getvalue().splitlines():
            if line.startswith("[FAIL]"):
                priv.fail(line[7:])
            elif line.startswith("[WARN]"):
                priv.warn(line[7:])
            elif line.startswith("[PASS]"):
                priv.ok(line[7:])
        if code and not priv.failed:
            priv.fail("privacy check failed")
        reports.append(priv)

        rv = Report("review hand-off")
        data = load_json(facts)
        items = data.get("review_items", [])
        review_md = folder / "review.md"
        if items:
            if not review_md.exists():
                rv.fail(f"{len(items)} review items but no review.md for the human reviewer")
            else:
                text = read_text(review_md)
                missing = [r["id"] for r in items if r.get("id") and r["id"] not in text]
                if missing:
                    rv.fail(f"review.md does not mention {', '.join(missing)}")
                else:
                    rv.ok(f"review.md lists all {len(items)} review items")
        else:
            rv.warn("no review items: confirm the source really has no ambiguity, contradiction, hedge or translation risk")
        reports.append(rv)

    text = "\n\n".join(r.render() for r in reports)
    totals = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for r in reports:
        for k, v in r.counts().items():
            totals[k] += v
    verdict = "FAIL" if any(r.failed for r in reports) else "PASS"
    summary = f"\n\n=== {verdict}: {totals['PASS']} pass, {totals['WARN']} warn, {totals['FAIL']} fail ==="
    if verdict == "PASS" and not args.final:
        summary += "\nDraft only: a person must answer review.md before anything is shared."
    print(text + summary)
    if folder.is_dir():
        (folder / "validation-report.txt").write_text(text + summary + "\n", encoding="utf-8")
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
