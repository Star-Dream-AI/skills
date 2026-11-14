#!/usr/bin/env python3
"""Rebuild assets/data/*.json from the original open-source datasets.

You only need this to refresh or audit the bundled data; the checker itself
never touches the network.

Sources (download them yourself, then point this script at the files):

  pingshui   pingshui_rhyme 0.20 (MIT, https://github.com/rbnyng/pingshui_rhyme)
             file: pingshui_rhyme/data/organized_ping_ze_rhyme_dict.json
             scraped from 維基文庫《平水韻》 https://zh.wikisource.org/wiki/平水韻
  pinyin     pypinyin 0.55.0 (MIT, https://github.com/mozillazg/python-pinyin)
             file: pypinyin/pinyin_dict.json
  st / ts    OpenCC (Apache-2.0, https://github.com/BYVoid/OpenCC)
             files: data/dictionary/STCharacters.txt, TSCharacters.txt,
                    TWVariants.txt, HKVariants.txt
  unihan     Unicode Unihan database (Unicode License v3,
             https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip)
             files: Unihan_Variants.txt, Unihan_Readings.txt (kTang)

The rhyme table is written with the traditional glyphs of 維基文庫, which do not
always match OpenCC's traditional forms (为→爲 but the table has 為; 啼 is listed
as 嗁).  Variant data from OpenCC and Unihan bridges those gaps; every lookup made
through a variant is reported as such by the checker.

Usage:
  python build_data.py --pingshui organized_ping_ze_rhyme_dict.json \
      --pinyin pinyin_dict.json --st STCharacters.txt --ts TSCharacters.txt \
      --variants TWVariants.txt HKVariants.txt --unihan Unihan_Variants.txt \
      --tang Unihan_Readings.txt
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "data"
CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003ffff]")
NUM = "一二三四五六七八九十"


def simplify_group(name: str) -> tuple[str, str]:
    """'上平聲一東' -> ('上平', '一东'); '入聲十七洽' -> ('入', '十七洽')."""
    for prefix, short in (("上平聲", "上平"), ("下平聲", "下平"), ("上聲", "上"), ("去聲", "去"), ("入聲", "入")):
        if name.startswith(prefix):
            return short, name[len(prefix):]
    raise ValueError(name)


def in_gb2312(ch: str) -> int:
    """0 = not in GB2312, 1 = level-1 (3755 most common), 2 = level-2."""
    try:
        b = ch.encode("gb2312")
    except UnicodeEncodeError:
        return 0
    if len(b) != 2:
        return 0
    return 1 if b[0] <= 0xD7 else 2


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pingshui", required=True)
    ap.add_argument("--pinyin", required=True)
    ap.add_argument("--st", required=True)
    ap.add_argument("--ts", required=True)
    ap.add_argument("--variants", nargs="*", default=[], help="OpenCC TWVariants.txt / HKVariants.txt")
    ap.add_argument("--unihan", help="Unihan_Variants.txt")
    ap.add_argument("--tang", help="Unihan_Readings.txt (kTang, for chars the rhyme table lacks)")
    a = ap.parse_args()

    # --- simplified <-> traditional (character level)
    s2t: dict[str, list[str]] = {}
    for line in Path(a.st).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        k, v = line.split("\t")
        s2t[k] = v.split()
    t2s: dict[str, str] = {}
    for line in Path(a.ts).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        k, v = line.split("\t")
        t2s[k] = v.split()[0]

    # --- 平水韵: keep source order, strip scraping junk (non-CJK)
    raw = json.loads(Path(a.pingshui).read_text(encoding="utf-8"))
    groups = []
    for tone_class in ("ping", "ze"):
        for _section, grps in raw[tone_class].items():
            for name, parts in grps.items():
                chars = "".join(CJK.findall("".join(parts)))
                tone, short = simplify_group(name)
                short_s = "".join(t2s.get(c, c) for c in short)
                groups.append({
                    "id": f"{tone}{short_s}",           # 上平一东
                    "tone": tone,                        # 上平 / 下平 / 上 / 去 / 入
                    "pz": "平" if tone_class == "ping" else "仄",
                    "name": short_s,                     # 一东
                    "name_t": name,                      # 上平聲一東 (source spelling)
                    "chars": chars,
                })
    assert len(groups) == 106, len(groups)

    # Only keep conversion entries that matter for the rhyme table.
    ps_chars = {c for g in groups for c in g["chars"]}
    s2t_used = {s: [t for t in ts if t in ps_chars] for s, ts in s2t.items()}
    s2t_used = {s: ts for s, ts in s2t_used.items() if ts and ts != [s]}
    t2s_used = {t: s for t, s in t2s.items() if t in ps_chars and s != t}

    # --- pinyin: common chars (GB2312) + every char that appears in the rhyme table or its simplified forms
    py_raw = json.loads(Path(a.pinyin).read_text(encoding="utf-8"))
    keep = ps_chars | set(t2s_used.values())
    pinyin = {}
    for cp, readings in py_raw.items():
        ch = chr(int(cp))
        if ch in keep or in_gb2312(ch):
            pinyin[ch] = readings
    level = {ch: in_gb2312(ch) for ch in pinyin if in_gb2312(ch)}

    # --- variant bridge for chars the rhyme table spells differently
    graph: dict[str, set[str]] = {}

    def link(x: str, y: str) -> None:
        if x != y:
            graph.setdefault(x, set()).add(y)
            graph.setdefault(y, set()).add(x)

    for path in a.variants:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                k, v = line.split("\t")
                for t in v.split():
                    link(k, t)
    if a.unihan:
        wanted = {"kTraditionalVariant", "kSimplifiedVariant", "kSemanticVariant", "kZVariant", "kSpecializedSemanticVariant"}
        for line in Path(a.unihan).read_text(encoding="utf-8").splitlines():
            if not line.startswith("U+"):
                continue
            cp, field, val = line.split("\t")
            if field not in wanted:
                continue
            src = chr(int(cp[2:], 16))
            for tok in val.split():
                link(src, chr(int(tok.split("<")[0][2:], 16)))
    for s, ts in s2t.items():
        for t in ts:
            link(s, t)

    def direct(ch: str) -> bool:
        return ch in ps_chars or any(t in ps_chars for t in s2t_used.get(ch, []))

    marks = re.compile(r"[̀-ͯ]")

    def syllables(ch: str) -> list[str]:
        out = []
        for r in py_raw.get(str(ord(ch)), "").split(","):
            plain = marks.sub("", unicodedata.normalize("NFD", r)).replace("ü", "v")
            if plain and plain not in out:
                out.append(plain)
        return out

    var: dict[str, list[str]] = {}
    for ch in set(pinyin) | set(level):
        if direct(ch):
            continue
        syl = syllables(ch)
        if not syl:
            continue
        primary = syl[0]
        seen, frontier, found = {ch}, [ch], []
        for _depth in range(2):
            nxt = []
            for x in frontier:
                for y in sorted(graph.get(x, ())):
                    if y in seen:
                        continue
                    seen.add(y)
                    # Only borrow a variant's rhyme groups when it can be read like this char.
                    if primary not in syllables(y):
                        continue
                    if y in ps_chars:
                        found.append(y)
                    nxt.append(y)
            if found:
                break
            frontier = nxt
        if found:
            var[ch] = found

    # --- last resort for chars still missing: tone from the Tang reading (Unihan kTang)
    guess: dict[str, dict] = {}
    if a.tang:
        tang = {}
        for line in Path(a.tang).read_text(encoding="utf-8").splitlines():
            if "\tkTang\t" in line:
                cp, _f, val = line.split("\t")
                tang[chr(int(cp[2:], 16))] = val.split()[0]
        for ch in set(pinyin) | set(level):
            if direct(ch) or ch in var or ch not in tang:
                continue
            t = tang[ch]
            core = t.lstrip("*")
            if core[-1:] in ("p", "t", "k"):
                guess[ch] = {"pz": "仄", "basis": f"唐音 {t}，-{core[-1]} 收尾为入声"}
            elif marks.search(unicodedata.normalize("NFD", core)):
                guess[ch] = {"pz": "仄", "basis": f"唐音 {t}，带声调符号为上/去声"}
            else:
                guess[ch] = {"pz": "平", "basis": f"唐音 {t}，无声调符号为平声"}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pingshui.json").write_text(json.dumps(groups, ensure_ascii=False, indent=0), encoding="utf-8")
    (OUT / "charmap.json").write_text(json.dumps({"s2t": s2t_used, "t2s": t2s_used, "var": var, "guess": guess}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"variants: {len(var)} chars bridged to a variant spelling in the rhyme table")
    print(f"guess: {len(guess)} missing chars get a tone from their Tang reading")
    (OUT / "pinyin.json").write_text(json.dumps({"readings": pinyin, "gb2312_level": level}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"pingshui: {len(groups)} groups, {sum(len(g['chars']) for g in groups)} entries, {len(ps_chars)} distinct chars")
    print(f"charmap: s2t {len(s2t_used)}, t2s {len(t2s_used)}")
    print(f"pinyin: {len(pinyin)} chars ({sum(1 for v in level.values() if v == 1)} GB2312 level-1)")


if __name__ == "__main__":
    main()
