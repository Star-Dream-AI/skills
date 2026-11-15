#!/usr/bin/env python3
"""Build the bundled law library (assets/laws/) from 维基文库 via its public API.

The bundled copy lets the skill work offline — 维基文库 is unreachable from
mainland China without a proxy.  Re-run this script to refresh the texts after
laws are amended.  Requests are sequential, identify themselves with a
User-Agent (set FATIAO_UA) and use maxlag, per Wikimedia API etiquette.

Chinese statutes are not protected by copyright (著作权法第五条), so the texts
may be redistributed.

Usage:  FATIAO_UA="your-tool (contact)" python build_seed.py [--only 劳动合同法 ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fatiao  # noqa: E402

P = fatiao.PRC
# (Wikisource title, extra aliases). Short names without 中华人民共和国 are added automatically.
SEED = [
    (P + "宪法", []),
    (P + "民法典", []),
    (P + "刑法", []),
    (P + "民事诉讼法", ["民诉法"]),
    (P + "刑事诉讼法", ["刑诉法"]),
    (P + "行政诉讼法", ["行诉法"]),
    (P + "行政处罚法", []),
    (P + "行政许可法", []),
    (P + "行政复议法", []),
    (P + "国家赔偿法", []),
    (P + "劳动法", []),
    (P + "劳动合同法", ["劳合法"]),
    (P + "劳动争议调解仲裁法", ["劳动仲裁法"]),
    (P + "社会保险法", ["社保法"]),
    (P + "就业促进法", []),
    (P + "公司法", []),
    (P + "合伙企业法", []),
    (P + "证券法", []),
    (P + "消费者权益保护法", ["消法", "消保法"]),
    (P + "产品质量法", []),
    (P + "食品安全法", []),
    (P + "反不正当竞争法", []),
    (P + "反垄断法", []),
    (P + "广告法", []),
    (P + "电子商务法", ["电商法"]),
    (P + "个人信息保护法", ["个保法"]),
    (P + "网络安全法", ["网安法"]),
    (P + "数据安全法", ["数安法"]),
    (P + "著作权法", []),
    (P + "商标法", []),
    (P + "专利法", []),
    (P + "道路交通安全法", ["道交法"]),
    (P + "治安管理处罚法", ["治安法", "治安处罚法"]),
    (P + "未成年人保护法", ["未保法"]),
    (P + "妇女权益保障法", []),
    (P + "仲裁法", []),
    (P + "律师法", []),
    (P + "个人所得税法", ["个税法"]),
    (P + "税收征收管理法", ["税收征管法"]),
    (P + "城市房地产管理法", ["房地产管理法"]),
    (P + "土地管理法", []),
    (P + "劳动合同法实施条例", ["劳动合同法实施条例"]),
    ("工伤保险条例", []),
    ("职工带薪年休假条例", ["带薪年休假条例"]),
    # 被《民法典》第一千二百六十条废止的九部法律（旧文书里仍常见）
    (P + "合同法", []),
    (P + "物权法", []),
    (P + "侵权责任法", []),
    (P + "婚姻法", []),
    (P + "继承法", []),
    (P + "民法通则", []),
    (P + "民法总则", []),
    (P + "担保法", []),
    (P + "收养法", []),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="只构建这些（可用简称）")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    todo = SEED
    if a.only:
        want = {fatiao.resolve_title(x) for x in a.only} | set(a.only)
        todo = [x for x in SEED if x[0] in want or x[0].replace(P, "") in want]
    failed = []
    for title, aliases in todo:
        try:
            law = fatiao.fetch_wikisource(title)
        except Exception as e:  # report and continue
            failed.append((title, str(e)))
            print(f"✗ {title}: {e}")
            continue
        short = [title.replace(P, "")] if title.startswith(P) else []
        fatiao.save_law(fatiao.BUNDLED, law, short + aliases)
        # the two versions before the current one, so old article numbers are recognised offline
        if law.status != "已废止":
            current = law.source.get("page", "")
            for v in [x for x in law.versions if x["page"] != current][-2:]:
                try:
                    old = fatiao.fetch_version(v["page"], law.title)
                    old.title = v["page"]
                    fatiao.save_law(fatiao.BUNDLED / "versions", old)
                    time.sleep(1.0)
                except Exception as e:
                    print(f"  ⚠ 旧版 {v['page']} 获取失败：{e}")
        mx = law.max_article()
        missing = [n for n in range(1, mx + 1) if str(n) not in law.articles]
        flag = f"  ⚠ 缺 {len(missing)} 条：{missing[:8]}" if missing else ""
        print(f"✓ {title} {law.version} {law.status} {len(law.articles)} 条（最大第{mx}条）{flag}")
        time.sleep(1.0)
    if failed:
        print("\n失败：")
        for t, e in failed:
            print(f"  {t}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
