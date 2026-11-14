#!/usr/bin/env python3
"""诗词格律检查（近体诗 / 对联）——平水韵 & 中华新韵。

Standard library only, fully offline. Rules follow 王力《诗词格律》: 四种基本句式、
粘对、押平声韵、一三五不论（孤平、三平尾例外）、拗救、特拗（平平仄平仄）。

Subcommands
  check     检查一首近体诗或一副对联
  lookup    查字的平仄、平水韵韵部、新韵韵部
  rhymes    列出某个韵部的常用字（写诗找韵脚用）
  patterns  打印标准平仄谱（五绝/七绝/五律/七律，平起/仄起，首句入韵与否）

Examples
  python gelv.py check "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。"
  python gelv.py check --file poem.txt --yun xin --json
  python gelv.py lookup 看胜国白
  python gelv.py rhymes 侵            # 平水韵 下平十二侵
  python gelv.py rhymes --char 心     # 心 所在的韵部
  python gelv.py rhymes --yun xin 九文
  python gelv.py patterns 七律 --start 仄起 --first-rhyme
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "assets" / "data"
CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003ffff]")
PING, ZE, BOTH, UNKNOWN = "平", "仄", "中", "?"
NUM_CN = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

# 平水韵平声邻韵（只用于说明"首句借邻韵"，近体诗韵脚中间不可借）
NEIGHBORS = [
    {"上平一东", "上平二冬"},
    {"上平三江", "下平七阳"},
    {"上平四支", "上平五微", "上平八齐"},
    {"上平六鱼", "上平七虞"},
    {"上平九佳", "上平十灰"},
    {"上平十一真", "上平十二文", "上平十三元"},
    {"上平十四寒", "上平十五删", "下平一先"},
    {"下平二萧", "下平三肴", "下平四豪"},
    {"下平八庚", "下平九青", "下平十蒸"},
    {"下平十三覃", "下平十四盐", "下平十五咸"},
]

# 中华新韵（中华诗词学会 2005，十四韵）：韵母 -> 韵部
XINYUN = {
    "a": "一麻", "ia": "一麻", "ua": "一麻",
    "o": "二波", "e": "二波", "uo": "二波",
    "ie": "三皆", "üe": "三皆", "ê": "三皆",
    "ai": "四开", "uai": "四开",
    "ei": "五微", "ui": "五微",
    "ao": "六豪", "iao": "六豪",
    "ou": "七尤", "iu": "七尤",
    "an": "八寒", "ian": "八寒", "uan": "八寒", "üan": "八寒",
    "en": "九文", "in": "九文", "un": "九文", "ün": "九文",
    "ang": "十唐", "iang": "十唐", "uang": "十唐",
    "eng": "十一庚", "ing": "十一庚", "ong": "十一庚", "iong": "十一庚", "ueng": "十一庚",
    "i": "十二齐", "ü": "十二齐", "er": "十二齐",
    "-i": "十三支",
    "u": "十四姑",
}
XINYUN_ORDER = ["一麻", "二波", "三皆", "四开", "五微", "六豪", "七尤", "八寒", "九文", "十唐", "十一庚", "十二齐", "十三支", "十四姑"]

# 变调读音不是字的本调，查新韵时去掉
SANDHI = {"一": {"yí", "yì"}, "不": {"bú"}, "七": {"qí"}, "八": {"bá"}}

# 常见平仄两读字的义项提示（脚本只判声调，字义由使用者确认）
POLY_HINTS = {
    "看": "平 kān（看守；诗中“看”作“观看”也常读平）/ 仄 kàn；两读常通用",
    "望": "平 wáng（古读，望远）/ 仄 wàng；两读常通用",
    "忘": "平 wáng（古读）/ 仄 wàng；两读常通用",
    "听": "平 tīng / 仄 tìng（听任、听凭）；“聆听”义两读常通用",
    "醒": "平 xīng / 仄 xǐng；两读常通用",
    "过": "平 guō（经过，古多读平）/ 仄 guò（过错、过分）",
    "胜": "平 shēng（禁得起、尽，如“不胜”）/ 仄 shèng（胜利、优美）",
    "为": "平 wéi（做、是、成为）/ 仄 wèi（为了、因为、替）",
    "重": "平 chóng（重复、重叠）/ 仄 zhòng（轻重、重要）",
    "行": "平 xíng（行走）/ 平 háng（行列）/ 仄 xìng（品行）",
    "长": "平 cháng（长短）/ 仄 zhǎng（生长、长者）",
    "更": "平 gēng（更改、打更）/ 仄 gèng（更加）",
    "教": "平 jiāo（使、令，如“不教胡马”）/ 仄 jiào（教化、教导）",
    "令": "平 líng（使、令）/ 仄 lìng（命令、美好）",
    "思": "平 sī（思念、思考）/ 仄 sì（名词“思绪、情思”，古读去声）",
    "中": "平 zhōng（中间）/ 仄 zhòng（射中、中毒）",
    "应": "平 yīng（应该、应当）/ 仄 yìng（回应、应答）",
    "相": "平 xiāng（互相）/ 仄 xiàng（宰相、相貌）",
    "将": "平 jiāng（将要、带领）/ 仄 jiàng（将领）",
    "骑": "平 qí（骑马，动词）/ 仄 jì（坐骑、骑兵，名词）",
    "乘": "平 chéng（乘坐）/ 仄 shèng（车乘，名词）",
    "难": "平 nán（困难）/ 仄 nàn（灾难、责难）",
    "分": "平 fēn（分开）/ 仄 fèn（名分、本分）",
    "间": "平 jiān（中间）/ 仄 jiàn（间隔、离间）",
    "传": "平 chuán（传递）/ 仄 zhuàn（传记）",
    "调": "平 tiáo（调和）/ 仄 diào（曲调、调动）",
    "量": "平 liáng（量度）/ 仄 liàng（数量、度量）",
    "数": "仄 shǔ / 仄 shù（两读皆仄；“数罟”读 cù）",
    "论": "平 lún（议论，古多读平）/ 仄 lùn",
    "空": "平 kōng（天空、空虚）/ 仄 kòng（空闲）",
    "冠": "平 guān（帽子）/ 仄 guàn（冠军、戴冠）",
    "当": "平 dāng（应当、担当）/ 仄 dàng（恰当、典当）",
    "兴": "平 xīng（兴起）/ 仄 xìng（兴致、比兴）",
    "号": "平 háo（号叫）/ 仄 hào（名号）",
    "禁": "平 jīn（禁得起）/ 仄 jìn（禁止）",
    "供": "平 gōng（供给）/ 仄 gòng（供奉）",
    "华": "平 huá（华丽、中华）/ 仄 huà（华山、姓）",
    "不": "仄（入声，绝大多数用法）/ 平 fǒu（同“否”，近体诗中极少用）",
    "叹": "平 tān（古读）/ 仄 tàn；两读常通用",
    "汗": "平 hán（可汗）/ 仄 hàn（汗水）",
}
# 平仄两读、意义基本不变、诗中可随格律取读的字：今音读法本身合律时不再提示
FREE_DUAL = {"看", "望", "忘", "听", "醒", "过", "叹", "论", "空"}
# 韵书虽有另一读、实际诗中几乎只用一种声调的字
PRACTICAL = {"不": (ZE, "“不”另有平声读法（同“否”），近体诗中几乎都读仄声，按仄计")}


# ---------------------------------------------------------------- data

@lru_cache(maxsize=1)
def _pingshui():
    groups = json.loads((DATA / "pingshui.json").read_text(encoding="utf-8"))
    index: dict[str, list[dict]] = {}
    for g in groups:
        for ch in g["chars"]:
            index.setdefault(ch, []).append(g)
    return groups, index


@lru_cache(maxsize=1)
def _charmap():
    return json.loads((DATA / "charmap.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _pinyin():
    return json.loads((DATA / "pinyin.json").read_text(encoding="utf-8"))


def to_simplified(ch: str) -> str:
    return _charmap()["t2s"].get(ch, ch)


def pingshui_groups(ch: str, with_source: bool = False):
    """All 平水韵 groups for a character (simplified or traditional input).

    Falls back to variant spellings (异体字) when neither the character nor its
    traditional form is in the table; ``with_source`` also returns the variants used.
    """
    _, index = _pingshui()
    cm = _charmap()
    seen, out = set(), []
    for c in [ch] + cm["s2t"].get(ch, []):
        for g in index.get(c, []):
            if g["id"] not in seen:
                seen.add(g["id"])
                out.append(g)
    via: list[str] = []
    if not out:
        for c in cm.get("var", {}).get(ch, []):
            for g in index.get(c, []):
                if g["id"] not in seen:
                    seen.add(g["id"])
                    out.append(g)
                    if c not in via:
                        via.append(c)
    return (out, via) if with_source else out


TONE_MARKS = {
    "ā": ("a", 1), "á": ("a", 2), "ǎ": ("a", 3), "à": ("a", 4),
    "ē": ("e", 1), "é": ("e", 2), "ě": ("e", 3), "è": ("e", 4),
    "ī": ("i", 1), "í": ("i", 2), "ǐ": ("i", 3), "ì": ("i", 4),
    "ō": ("o", 1), "ó": ("o", 2), "ǒ": ("o", 3), "ò": ("o", 4),
    "ū": ("u", 1), "ú": ("u", 2), "ǔ": ("u", 3), "ù": ("u", 4),
    "ǖ": ("ü", 1), "ǘ": ("ü", 2), "ǚ": ("ü", 3), "ǜ": ("ü", 4),
    "ń": ("n", 2), "ň": ("n", 3), "ǹ": ("n", 4), "ḿ": ("m", 2),
    "ê̄": ("ê", 1), "ế": ("ê", 2), "ê̌": ("ê", 3), "ề": ("ê", 4),
}
INITIALS = ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x", "r", "z", "c", "s")
Y_W = {
    "yi": "i", "ya": "ia", "ye": "ie", "yao": "iao", "you": "iu", "yan": "ian", "yin": "in",
    "yang": "iang", "ying": "ing", "yong": "iong", "yo": "o", "yu": "ü", "yue": "üe", "yuan": "üan",
    "yun": "ün", "wu": "u", "wa": "ua", "wo": "uo", "wai": "uai", "wei": "ui", "wan": "uan",
    "wen": "un", "wang": "uang", "weng": "ueng",
}


def parse_pinyin(s: str) -> tuple[str, str, int]:
    """'xīn' -> ('xin', 'in', 1). Tone 0 = neutral."""
    s = unicodedata.normalize("NFC", s.strip().lower())
    tone, plain = 0, ""
    i = 0
    while i < len(s):
        two = s[i:i + 2]
        if two in TONE_MARKS:
            base, tone = TONE_MARKS[two]
            plain += base
            i += 2
            continue
        ch = s[i]
        if ch in TONE_MARKS:
            base, tone = TONE_MARKS[ch]
            plain += base
        else:
            plain += "ü" if ch == "v" else ch
        i += 1
    syl = plain
    if syl in Y_W:
        return syl, Y_W[syl], tone
    if syl.startswith("y") or syl.startswith("w"):
        return syl, syl[1:], tone
    if syl in ("er", "ê", "m", "n", "ng", "hm", "hng"):
        return syl, syl, tone
    for ini in INITIALS:
        if syl.startswith(ini):
            fin = syl[len(ini):]
            if ini in ("j", "q", "x") and fin.startswith("u"):
                fin = "ü" + fin[1:]
            if ini in ("zh", "ch", "sh", "r", "z", "c", "s") and fin == "i":
                fin = "-i"
            return syl, fin, tone
    return syl, syl, tone


def readings(ch: str) -> list[str]:
    raw = _pinyin()["readings"].get(ch, "")
    out = [r for r in raw.split(",") if r and r not in SANDHI.get(ch, set())]
    return out


def xin_readings(ch: str) -> list[str]:
    """Readings that count for 中华新韵: the main reading, plus the alternatives
    named in POLY_HINTS for well-known 多音字 (dictionary rarities are ignored)."""
    rs = readings(ch)
    if ch in PRACTICAL:
        return rs[:1]
    hint = POLY_HINTS.get(ch) or POLY_HINTS.get(to_simplified(ch))
    if not hint:
        return rs[:1]
    named = [r for r in rs if r in hint]
    return named or rs[:2]


def tone_class(tone: int) -> str | None:
    return PING if tone in (1, 2) else ZE if tone in (3, 4) else None


def mandarin_primary(ch: str) -> str | None:
    for r in readings(ch):
        tc = tone_class(parse_pinyin(r)[2])
        if tc:
            return tc
    return None


@dataclass
class CharTone:
    ch: str
    pz: str                          # 平 / 仄 / 中（两读） / ?（未收录）
    groups: list[str] = field(default_factory=list)       # 韵部名
    ping_groups: list[str] = field(default_factory=list)  # 平声韵部（押韵用）
    is_ru: bool = False              # 平水韵入声
    note: str = ""
    guessed: bool = False            # 韵书未收录，声调是推定的


def char_tone(ch: str, yun: str) -> CharTone:
    if yun == "pingshui":
        gs, via = pingshui_groups(ch, with_source=True)
        if not gs:
            guess = _charmap().get("guess", {}).get(ch)
            if guess:
                return CharTone(ch, guess["pz"], guessed=True, note=f"平水韵未收录，按{guess['basis']}推定为{guess['pz']}声，请核实")
            mp = mandarin_primary(ch)
            if mp:
                return CharTone(ch, mp, guessed=True, note=f"平水韵未收录（多为后起字），暂按普通话定为{mp}声；若古为入声则应为仄，请核实")
            return CharTone(ch, UNKNOWN, note="平水韵未收录，读音不明")
        pzs = {g["pz"] for g in gs}
        pz = BOTH if len(pzs) > 1 else pzs.pop()
        note = f"按异体字“{'、'.join(via)}”查得" if via else ""
        if ch in PRACTICAL:
            pz, note = PRACTICAL[ch]
            gs = [g for g in gs if g["pz"] == pz]
        return CharTone(
            ch,
            pz,
            groups=[g["id"] for g in gs],
            ping_groups=[g["id"] for g in gs if g["pz"] == PING],
            is_ru=any(g["tone"] == "入" for g in gs),
            note=note,
        )
    # 中华新韵：以今音为准。字典里的又读多为罕用义，只有常见的多音字才算两读。
    rs = xin_readings(ch)
    if not rs:
        return CharTone(ch, UNKNOWN, note="拼音数据未收录")
    pzs, groups, ping_groups = set(), [], []
    for r in rs:
        _syl, fin, tone = parse_pinyin(r)
        tc = tone_class(tone)
        if not tc:
            continue
        pzs.add(tc)
        g = XINYUN.get(fin)
        if g:
            label = f"{g}（{r}）"
            if label not in groups:
                groups.append(label)
            if tc == PING and g not in ping_groups:
                ping_groups.append(g)
    if not pzs:
        return CharTone(ch, UNKNOWN, note="只有轻声读音")
    return CharTone(ch, BOTH if len(pzs) > 1 else pzs.pop(), groups=groups, ping_groups=ping_groups)


def matches(got: str, need: str) -> bool:
    return got == need or got in (BOTH, UNKNOWN)


def opposite(pz: str) -> str:
    return ZE if pz == PING else PING


def group_label(gid: str) -> str:
    return gid


# ---------------------------------------------------------------- parsing

def split_lines(text: str) -> list[str]:
    parts = re.split(r"[，。！？；、,.!?;:：\s/|]+", text)
    out = []
    for p in parts:
        chars = "".join(CJK.findall(p))
        if chars:
            out.append(chars)
    return out


def detect_form(lines: list[str]) -> tuple[str, str]:
    n = len(lines)
    lens = {len(x) for x in lines}
    if n == 2 and len(lens) == 1:
        return "对联", ""
    if len(lens) == 1 and lens & {5, 7}:
        L = lens.pop()
        size = "五言" if L == 5 else "七言"
        if n == 4:
            return f"{size}绝句", ""
        if n == 8:
            return f"{size}律诗", ""
        if n > 8 and n % 2 == 0:
            return f"{size}排律", ""
        return "", f"共 {n} 句：近体诗为四句（绝句）、八句（律诗）或更多的偶数句（排律）"
    detail = "、".join(f"第{i + 1}句{len(x)}字" for i, x in enumerate(lines))
    return "", f"句子长短不一（{detail}）：近体诗每句都是五字或都是七字"


# ---------------------------------------------------------------- checking

FIVE = {"A": "仄仄平平仄", "B": "平平仄仄平", "a": "平平平仄仄", "b": "仄仄仄平平"}
SEVEN = {"A": "平平仄仄平平仄", "B": "仄仄平平仄仄平", "a": "仄仄平平平仄仄", "b": "平平仄仄仄平平"}
TYPE_NAME = {"A": "仄起仄收", "B": "平起平收", "a": "平起仄收", "b": "仄起平收"}
TYPE_NAME7 = {"A": "平起仄收", "B": "仄起平收", "a": "仄起仄收", "b": "平起平收"}


@dataclass
class Issue:
    level: str        # error / warn / info
    line: int | None  # 1-based 句号
    msg: str
    pos: list[int] = field(default_factory=list)  # 1-based 字位

    def to_dict(self):
        return {"level": self.level, "line": self.line, "pos": self.pos, "msg": self.msg}


def line_type(key: str, end: str) -> str:
    if key == ZE and end == ZE:
        return "A"
    if key == PING and end == PING:
        return "B"
    if key == PING and end == ZE:
        return "a"
    return "b"


def find_rhyme(tones: list[list[CharTone]], yun: str) -> tuple[str | None, list[Issue], bool]:
    """Pick the rhyme group from the even lines; return (group, issues, first_line_rhymes)."""
    issues: list[Issue] = []
    n = len(tones)
    feet = [(i, tones[i][-1]) for i in range(1, n, 2)]
    # 偶数句韵脚投票；首句以平声收尾时多半入韵，也算一票（打破“两个韵脚各执一词”的平局）
    voters = list(feet)
    if tones[0][-1].pz in (PING, BOTH) and tones[0][-1].ping_groups:
        voters.append((0, tones[0][-1]))
    cnt = Counter(g for _, t in voters for g in t.ping_groups)
    top = cnt.most_common()
    main = top[0][0] if top else None
    tied = [g for g, k in top if top and k == top[0][1]]
    if len(tied) > 1:
        # 平局时优先选偶数句里出现的韵部（首句本可借邻韵）
        even_groups = Counter(g for _, t in feet for g in t.ping_groups)
        tied.sort(key=lambda g: -even_groups.get(g, 0))
        main = tied[0]
        if even_groups.get(tied[0], 0) == even_groups.get(tied[1], 0):
            desc = "；".join(f"“{t.ch}”属{'、'.join(t.ping_groups) or '仄声'}" for _, t in feet)
            issues.append(Issue("error", None, f"韵脚不同韵（{desc}）：近体诗一韵到底，须统一到同一韵部"))
            return main, issues, False
    for i, t in feet:
        if main and main in t.ping_groups:
            continue
        if t.pz == ZE:
            issues.append(Issue("error", i + 1, f"韵脚“{t.ch}”是仄声字：近体诗押平声韵（{('、'.join(t.groups)) or '未收录'}）", [len(tones[i])]))
        elif t.pz == UNKNOWN:
            issues.append(Issue("warn", i + 1, f"韵脚“{t.ch}”的韵部无法确定：{t.note}", [len(tones[i])]))
        else:
            where = "、".join(t.ping_groups) or "、".join(t.groups)
            near = ""
            if yun == "pingshui" and main and any(main in s and set(t.ping_groups) & s for s in NEIGHBORS):
                near = "（属邻韵：近体诗只有首句可借邻韵，偶数句不可）"
            issues.append(Issue("error", i + 1, f"出韵：韵脚“{t.ch}”属{where}，与全诗所押{main}不同{near}", [len(tones[i])]))
    if feet and all(t.pz == ZE for _, t in feet):
        issues.append(Issue("info", None, "全诗押仄声韵：这是古体诗（如古绝）的写法，近体格律不适用。若本来就想写古体诗，平仄不必按本报告修改"))
    # 韵脚重复
    feet_chars = Counter(t.ch for _, t in feet)
    for ch, k in feet_chars.items():
        if k > 1:
            issues.append(Issue("warn", None, f"韵脚“{ch}”重复使用 {k} 次：近体诗韵脚一般不重复"))
    first = tones[0][-1]
    first_rhymes = False
    if first.pz in (PING, BOTH) and main:
        if main in first.ping_groups:
            first_rhymes = True
        elif yun == "pingshui" and any(main in s and set(first.ping_groups) & s for s in NEIGHBORS):
            first_rhymes = True
            issues.append(Issue("info", 1, f"首句韵脚“{first.ch}”属邻韵（{'、'.join(first.ping_groups)}），首句借邻韵（“孤雁出群”）是允许的", [len(tones[0])]))
        elif first.pz == PING:
            issues.append(Issue("warn", 1, f"首句以平声“{first.ch}”收尾却不入韵（属{'、'.join(first.ping_groups) or '未收录'}）：首句平收一般应入韵", [len(tones[0])]))
    return main, issues, first_rhymes


def check_line(t: list[CharTone], typ: str, nxt: tuple[str, list[CharTone]] | None) -> tuple[list[Issue], bool]:
    """Check one 句 against its template. Returns (issues, ao_needs_rescue_resolved_flag)."""
    L = len(t)
    off = 0 if L == 5 else 2
    tmpl = (FIVE if L == 5 else SEVEN)[typ]
    issues: list[Issue] = []

    def g(j: int) -> str:            # 五言等价位置 j=0..4
        return t[j + off].pz

    strict = {1, 3, 4} if L == 5 else {1, 3, 5, 6}
    bad = [p for p in range(L) if p in strict and not matches(t[p].pz, tmpl[p])]
    explained: set[int] = set()

    if typ == "B":
        if g(0) == ZE and g(2) == ZE:
            issues.append(Issue("error", None, f"犯孤平：“{''.join(c.ch for c in t)}”（{''.join(c.pz for c in t)}）除韵脚外只有一个平声字。可把第{3 + off}字改为平声（拗救）", [1 + off, 3 + off]))
        elif g(0) == ZE and g(2) == PING:
            issues.append(Issue("info", None, f"孤平拗救：第{1 + off}字用仄，第{3 + off}字用平补救，合律", [1 + off, 3 + off]))
    elif typ == "b":
        if g(2) == PING:
            issues.append(Issue("error", None, f"三平尾：末三字皆平（第{3 + off}字应为仄），是近体诗大忌", [3 + off, 4 + off, 5 + off]))
    elif typ == "a":
        if g(2) == ZE and g(3) == PING:
            explained.add(3 + off)
            form_name = "平平仄平仄" if L == 5 else "仄仄平平仄平仄"
            if g(0) in (PING, BOTH, UNKNOWN):
                issues.append(Issue("info", None, f"特拗（{form_name}）：第{3 + off}、{4 + off}字平仄互换，是唐宋诗常见的合律特定格式", [3 + off, 4 + off]))
            else:
                issues.append(Issue("error", None, f"“{''.join(c.pz for c in t)}”不合律：特拗格式（{form_name}）的第{1 + off}字必须用平", [1 + off, 3 + off, 4 + off]))
        elif g(2) == ZE:
            issues.append(Issue("info", None, f"三仄尾：末三字皆仄，可以接受，但不如“平平平仄仄”常用", [3 + off, 4 + off, 5 + off]))
    elif typ == "A":
        if g(3) == ZE:
            explained.add(3 + off)
            rescued = False
            if nxt and nxt[0] == "B":
                nt = nxt[1]
                if nt[2 + off].pz in (PING, BOTH):
                    rescued = True
            which = f"第{4 + off}字" if g(2) != ZE else f"第{3 + off}、{4 + off}字"
            if rescued:
                issues.append(Issue("info", None, f"出句{which}拗（用仄），对句第{3 + off}字用平相救，合律（对句救）", [3 + off, 4 + off]))
            else:
                issues.append(Issue("error", None, f"{which}应为平声：拗而未救（若要保留，须在对句第{3 + off}字用平声相救）", [4 + off]))
        elif g(2) == ZE:
            issues.append(Issue("info", None, f"第{3 + off}字用仄（仄仄仄平仄）：小拗，一般可不救", [3 + off]))

    for p in bad:
        if p in explained:
            continue
        need = tmpl[p]
        issues.append(Issue("error", None, f"第{p + 1}字“{t[p].ch}”应为{need}声", [p + 1]))
    return issues, True


def check_shi(lines: list[str], form: str, yun: str) -> dict:
    tones = [[char_tone(c, yun) for c in ln] for ln in lines]
    n, L = len(lines), len(lines[0])
    off = 0 if L == 5 else 2
    issues: list[Issue] = []

    main, rh_issues, first_rhymes = find_rhyme(tones, yun)
    issues += rh_issues

    # --- decide each line's type
    types: list[str] = []
    keys: list[str] = []
    for i, t in enumerate(tones):
        k = t[1 + off].pz
        if k not in (PING, ZE):
            if i == 0:
                k2 = tones[1][1 + off].pz if n > 1 else UNKNOWN
                k = opposite(k2) if k2 in (PING, ZE) else ZE
            elif i % 2 == 1:
                k = opposite(keys[i - 1])
            else:
                k = keys[i - 1]
        e = t[-1].pz
        if i % 2 == 1:
            want_end = PING
        elif i == 0:
            want_end = PING if first_rhymes else ZE
        else:
            want_end = ZE
        if e not in (PING, ZE):
            e = want_end
        keys.append(k)
        types.append(line_type(k, e))
        # 收尾声调与句位不合
        if t[-1].pz in (PING, ZE) and t[-1].pz != want_end:
            if i % 2 == 1:
                pass  # 已在押韵检查中报告
            elif i > 0:
                issues.append(Issue("error", i + 1, f"出句末字“{t[-1].ch}”应为仄声：除首句外，单数句不押韵、以仄声收尾", [L]))
        # 七言第 2 字与第 4 字应相反
        if L == 7 and t[1].pz in (PING, ZE) and t[3].pz in (PING, ZE) and t[1].pz == t[3].pz:
            pass  # 由逐字检查报告（第 2 字）

    # --- per-line template check
    line_reports = []
    for i, t in enumerate(tones):
        nxt = (types[i + 1], tones[i + 1]) if (i % 2 == 0 and i + 1 < n) else None
        li, _ = check_line(t, types[i], nxt)
        for x in li:
            x.line = i + 1
        issues += li
        tmpl = (FIVE if L == 5 else SEVEN)[types[i]]
        line_reports.append({
            "line": i + 1,
            "text": lines[i],
            "type": (TYPE_NAME if L == 5 else TYPE_NAME7)[types[i]],
            "template": tmpl,
            "tones": "".join(c.pz for c in t),
            "chars": [{"ch": c.ch, "pz": c.pz, "groups": c.groups, "ru": c.is_ru, "note": c.note} for c in t],
        })

    # --- 粘对
    for i in range(1, n):
        if i % 2 == 1 and keys[i] == keys[i - 1]:
            issues.append(Issue("error", i + 1, f"失对：第{i}、{i + 1}句的第二字（“{tones[i - 1][1].ch}”“{tones[i][1].ch}”）应平仄相反", [2]))
        if i % 2 == 0 and keys[i] != keys[i - 1]:
            issues.append(Issue("error", i + 1, f"失粘：第{i + 1}句第二字“{tones[i][1].ch}”应与第{i}句第二字“{tones[i - 1][1].ch}”平仄相同", [2]))

    # --- 重字
    cnt = Counter(c for ln in lines for c in ln)
    reps = []
    for ch, k in cnt.items():
        if k < 2:
            continue
        stacked = any(ln.count(ch * 2) for ln in lines) and all(ch * 2 in ln or ch not in ln for ln in lines)
        if not stacked:
            reps.append(f"“{ch}”×{k}")
    if reps:
        issues.append(Issue("warn", None, f"重字：{'、'.join(reps)}。近体诗一般避免重复用字（有意的叠字、复沓除外）"))

    # --- 对仗提醒
    if "律诗" in form or "排律" in form:
        pairs = [(2, 3), (4, 5)] if n == 8 else [(k, k + 1) for k in range(2, n - 2, 2)]
        for a, b in pairs:
            same = [p + 1 for p in range(L) if lines[a][p] == lines[b][p]]
            if same:
                issues.append(Issue("warn", a + 1, f"第{a + 1}、{b + 1}句须对仗，但第{'、'.join(map(str, same))}字上下同字：对仗忌同位重字", same))

    def errors_with(i: int, p: int, pz: str) -> int:
        """Errors on line i (and the 出句 it may rescue) if char p were read as pz."""
        t = list(tones[i])
        t[p] = CharTone(t[p].ch, pz)
        nxt = (types[i + 1], tones[i + 1]) if (i % 2 == 0 and i + 1 < n) else None
        e = sum(1 for x in check_line(t, types[i], nxt)[0] if x.level == "error")
        if i % 2 == 1:
            e += sum(1 for x in check_line(tones[i - 1], types[i - 1], (types[i], t))[0] if x.level == "error")
        return e

    two_reads = []
    for i, t in enumerate(tones):
        for p, c in enumerate(t):
            if c.pz != BOTH:
                continue
            ep, ez = errors_with(i, p, PING), errors_with(i, p, ZE)
            if ep == ez:
                continue                      # 读平读仄都一样，无须确认
            need = PING if ep < ez else ZE
            meaning_based = c.ch in POLY_HINTS and c.ch not in FREE_DUAL
            if mandarin_primary(c.ch) == need and not meaning_based:
                continue                      # 按今音读就对，不会误读
            hint = POLY_HINTS.get(c.ch) or POLY_HINTS.get(to_simplified(c.ch)) or ""
            two_reads.append({"line": i + 1, "pos": p + 1, "ch": c.ch, "need": need, "hint": hint, "groups": c.groups})

    ru = sorted({c.ch for t in tones for c in t if c.is_ru and mandarin_primary(c.ch) == PING}) if yun == "pingshui" else []
    unknown = [{"line": i + 1, "pos": p + 1, "ch": c.ch, "note": c.note, "guessed": c.guessed}
               for i, t in enumerate(tones) for p, c in enumerate(t) if c.pz == UNKNOWN or c.guessed or (c.note and "异体" in c.note)]

    second = tones[0][1].pz if tones[0][1].pz in (PING, ZE) else (keys[0] if L == 5 else opposite(keys[0]))
    start = "平起" if second == PING else "仄起"
    return finish(form, yun, issues, line_reports, two_reads, ru, unknown, extra={
        "rhyme_group": main,
        "first_line_rhymes": first_rhymes,
        "start": start + ("首句入韵" if first_rhymes else "首句不入韵"),
    })


def check_duilian(lines: list[str], yun: str) -> dict:
    up, down = lines
    L = len(up)
    tu = [char_tone(c, yun) for c in up]
    td = [char_tone(c, yun) for c in down]
    issues: list[Issue] = []
    eu, ed = tu[-1].pz, td[-1].pz
    reversed_ = eu == PING and ed == ZE
    if reversed_:
        issues.append(Issue("error", None, "上下联可能颠倒：上联应以仄声收尾，下联应以平声收尾（仄起平落）。把两联对调后再检查"))
    else:
        if eu == PING:
            issues.append(Issue("error", 1, f"上联末字“{up[-1]}”应为仄声", [L]))
        if ed == ZE:
            issues.append(Issue("error", 2, f"下联末字“{down[-1]}”应为平声", [L]))
    line_reports = []
    if reversed_:
        tmpls = [None, None]
    elif L in (5, 7):
        off = 0 if L == 5 else 2
        ku = tu[1 + off].pz if tu[1 + off].pz in (PING, ZE) else (opposite(td[1 + off].pz) if td[1 + off].pz in (PING, ZE) else ZE)
        kd = opposite(ku)
        tyu, tyd = line_type(ku, ZE), line_type(kd, PING)
        for idx, (t, ty, nxt) in enumerate(((tu, tyu, (tyd, td)), (td, tyd, None)), 1):
            li, _ = check_line(t, ty, nxt)
            for x in li:
                x.line = idx
            issues += li
        if td[1 + off].pz in (PING, ZE) and tu[1 + off].pz == td[1 + off].pz:
            issues.append(Issue("error", 2, "上下联第二字（节奏点）平仄应相反", [2]))
        tmpls = [(FIVE if L == 5 else SEVEN)[tyu], (FIVE if L == 5 else SEVEN)[tyd]]
    else:
        tmpls = [None, None]
        for p in range(1, L - 1, 2):
            a, b = tu[p].pz, td[p].pz
            if a in (PING, ZE) and a == b:
                issues.append(Issue("warn", 2, f"第{p + 1}字上下联同为{a}声：节奏点（偶数字）一般平仄相对；若按词组划分节奏，请以词组末字为准", [p + 1]))
    for idx, (text, t, tm) in enumerate(((up, tu, tmpls[0]), (down, td, tmpls[1])), 1):
        line_reports.append({
            "line": idx, "text": text, "type": "上联" if idx == 1 else "下联", "template": tm,
            "tones": "".join(c.pz for c in t),
            "chars": [{"ch": c.ch, "pz": c.pz, "groups": c.groups, "ru": c.is_ru, "note": c.note} for c in t],
        })
    same_pos = [p + 1 for p in range(L) if up[p] == down[p]]
    if same_pos:
        issues.append(Issue("warn", None, f"上下联第{'、'.join(map(str, same_pos))}字用了同一个字：对联忌同位重字（有意的修辞除外）", same_pos))
    shared = sorted(set(up) & set(down) - {up[p] for p in range(L) if up[p] == down[p]})
    if shared:
        issues.append(Issue("warn", None, f"上下联都用了：{'、'.join(shared)}。对联一般避免上下联重复用字（成组的叠字、复字修辞除外）"))
    two_reads = []
    for i, t in enumerate((tu, td)):
        for p, c in enumerate(t):
            if c.pz != BOTH or not (p == L - 1 or p % 2 == 1):
                continue
            need = tmpls[i][p] if tmpls[i] else (ZE if i == 0 else PING) if p == L - 1 else ""
            meaning_based = c.ch in POLY_HINTS and c.ch not in FREE_DUAL
            if not meaning_based and (not need or mandarin_primary(c.ch) == need):
                continue
            two_reads.append({"line": i + 1, "pos": p + 1, "ch": c.ch, "need": need, "hint": POLY_HINTS.get(c.ch, ""), "groups": c.groups})
    unknown = [{"line": i + 1, "pos": p + 1, "ch": c.ch, "note": c.note, "guessed": c.guessed}
               for i, t in enumerate((tu, td)) for p, c in enumerate(t) if c.pz == UNKNOWN or c.guessed or (c.note and "异体" in c.note)]
    ru = sorted({c.ch for t in (tu, td) for c in t if c.is_ru and mandarin_primary(c.ch) == PING}) if yun == "pingshui" else []
    issues.append(Issue("info", None, "词性、结构是否相对（名对名、动对动、虚对虚）需要人工判断，脚本不检查"))
    return finish("对联", yun, issues, line_reports, two_reads, ru, unknown, extra={})


def finish(form, yun, issues, line_reports, two_reads, ru, unknown, extra) -> dict:
    errors = [x for x in issues if x.level == "error"]
    warns = [x for x in issues if x.level == "warn"]
    if errors:
        verdict = f"不合律（{len(errors)} 处错误）"
    elif any(u.get("guessed") or u.get("note", "").startswith("平水韵未收录") or "未收录" in u.get("note", "") for u in unknown):
        verdict = "基本合律（有韵书未收录、读音为推定的字，需人工确认）"
    elif warns or two_reads:
        verdict = "合律（有提示需确认）"
    else:
        verdict = "合律"
    return {
        "form": form,
        "yun": "平水韵" if yun == "pingshui" else "中华新韵",
        "verdict": verdict,
        "ok": not errors,
        **extra,
        "lines": line_reports,
        "issues": [x.to_dict() for x in sorted(issues, key=lambda x: ({"error": 0, "warn": 1, "info": 2}[x.level], x.line or 0))],
        "two_reading_chars": two_reads,
        "ru_sheng_read_ping_in_mandarin": ru,
        "unknown_chars": unknown,
    }


def check_text(text: str, yun: str = "pingshui", form: str = "auto") -> dict:
    lines = split_lines(text)
    if not lines:
        return {"ok": False, "verdict": "没有找到汉字", "issues": [], "lines": []}
    detected, problem = detect_form(lines)
    if form not in ("auto", ""):
        want = {"五绝": "五言绝句", "七绝": "七言绝句", "五律": "五言律诗", "七律": "七言律诗"}.get(form, form)
        if detected and want != detected and not (want == "排律" and "排律" in detected):
            problem = f"按“{form}”检查，但文本看起来是{detected}（{len(lines)} 句，每句 {len(lines[0])} 字）"
        detected = detected or want
    if problem and (not detected or "按“" in problem):
        return {"ok": False, "verdict": "体裁不符", "form": form, "issues": [{"level": "error", "line": None, "pos": [], "msg": problem}], "lines": [{"line": i + 1, "text": x} for i, x in enumerate(lines)]}
    if detected == "对联":
        return check_duilian(lines, yun)
    return check_shi(lines, detected, yun)


# ---------------------------------------------------------------- rendering

LEVEL_MARK = {"error": "✗", "warn": "!", "info": "i"}


def render(res: dict, other: dict | None = None) -> str:
    out = []
    head = f"【格律检查】{res.get('form') or '未知体裁'} · {res.get('yun', '')}"
    if res.get("start"):
        head += f" · {res['start']}"
    if res.get("rhyme_group"):
        head += f" · 韵部：{res['rhyme_group']}"
    out.append(head)
    out.append("")
    for ln in res.get("lines", []):
        if "tones" not in ln:
            out.append(f"第{ln['line']}句 {ln['text']}")
            continue
        bad = {p for x in res["issues"] if x["level"] == "error" and x["line"] == ln["line"] for p in x["pos"]}
        marks = "".join("^" if (k + 1) in bad else " " for k in range(len(ln["text"])))
        tmpl = f"  谱：{ln['template']}（{ln['type']}）" if ln.get("template") else f"  {ln['type']}"
        out.append(f"第{ln['line']}句 {ln['text']}  实：{ln['tones']}{tmpl}")
        if marks.strip():
            out.append(" " * (len(f"第{ln['line']}句 ") * 2 - 2) + "".join(m + " " for m in marks).rstrip())
    out.append("")
    out.append(f"结论：{res['verdict']}")
    for x in res.get("issues", []):
        where = f"第{x['line']}句：" if x.get("line") else ""
        out.append(f" {LEVEL_MARK[x['level']]} {where}{x['msg']}")
    if res.get("two_reading_chars"):
        out.append("")
        out.append("平仄两读字（脚本按合律计算，请按字义确认这里的读音对得上）：")
        for t in res["two_reading_chars"]:
            need = f"此处须读{t['need']}声" if t["need"] else "两读"
            out.append(f" - 第{t['line']}句第{t['pos']}字“{t['ch']}”：{need}。{t['hint']}")
    if res.get("unknown_chars"):
        out.append("")
        out.append("需核实读音的字（韵书未收录、按异体字或唐音/今音推定）：")
        for u in res["unknown_chars"]:
            out.append(f" - 第{u['line']}句第{u['pos']}字“{u['ch']}”：{u['note']}")
    if res.get("ru_sheng_read_ping_in_mandarin"):
        out.append("")
        out.append(f"入声字（平水韵属仄声，普通话却读平声，最容易误判）：{'、'.join(res['ru_sheng_read_ping_in_mandarin'])}")
    if other:
        out.append("")
        out.append(f"参考：按{other['yun']}检查 → {other['verdict']}")
    out.append("")
    out.append("图例：平/仄；中=平仄两读；?=未收录。✗ 错误  ! 提示  i 说明（合律的拗救等）")
    return "\n".join(out)


# ---------------------------------------------------------------- other commands

def cmd_lookup(chars: str) -> str:
    out = []
    for ch in CJK.findall(chars):
        ps = char_tone(ch, "pingshui")
        xy = char_tone(ch, "xin")
        rs = readings(ch)
        lines = [f"{ch}"]
        if ps.groups:
            lines.append(f"  平水韵：{ps.pz}（{'、'.join(ps.groups)}）" + ("  入声" if ps.is_ru else ""))
        else:
            lines.append(f"  平水韵：未收录。{ps.note}")
        lines.append(f"  中华新韵：{xy.pz}（{'、'.join(xy.groups) or '无'}）")
        lines.append(f"  普通话：{'、'.join(rs) or '未收录'}")
        hint = POLY_HINTS.get(ch)
        if hint:
            lines.append(f"  义项：{hint}")
        out.append("\n".join(lines))
    return "\n".join(out) or "没有汉字"


def find_group(query: str) -> list[dict]:
    groups, _ = _pingshui()
    q = "".join(to_simplified(c) for c in query.strip()).replace("韵", "").replace("声", "").replace("聲", "")
    hits = [g for g in groups if g["id"] == q]
    if not hits:
        hits = [g for g in groups if g["name"] == q or g["id"].endswith(q) or g["name"].endswith(q)]
    return hits


def common_sorted(chars: list[str]) -> tuple[list[str], list[str], int]:
    lvl = _pinyin()["gb2312_level"]
    l1, l2, rest = [], [], 0
    for c in chars:
        s = to_simplified(c)
        v = lvl.get(s, 0)
        if v == 1 and s not in l1:
            l1.append(s)
        elif v == 2 and s not in l2:
            l2.append(s)
        elif not v:
            rest += 1
    return l1, l2, rest


def cmd_rhymes(query: str | None, char: str | None, yun: str, show_all: bool, pz: str) -> str:
    if yun == "pingshui":
        if char:
            gs = pingshui_groups(char)
            if not gs:
                return f"“{char}”平水韵未收录"
            targets = gs
        else:
            targets = find_group(query or "")
            if not targets:
                groups, _ = _pingshui()
                return "没有找到这个韵部。平声韵部：\n" + " ".join(g["id"] for g in groups if g["pz"] == PING)
        out = []
        for g in targets:
            l1, l2, rest = common_sorted(list(g["chars"]))
            out.append(f"{g['id']}（{g['pz']}声，源：{g['name_t']}）共 {len(g['chars'])} 字")
            out.append(f"  常用：{''.join(l1)}")
            out.append(f"  次常用：{''.join(l2)}")
            if show_all:
                out.append(f"  全部（繁体原表）：{g['chars']}")
            elif rest:
                out.append(f"  另有 {rest} 个生僻字（加 --all 查看原表）")
        if char:
            out.insert(0, f"“{char}”所在韵部：{'、'.join(g['id'] for g in targets)}")
        return "\n".join(out)
    # 新韵
    target = None
    if char:
        ct = char_tone(char, "xin")
        if not ct.groups:
            return f"“{char}”无法确定新韵韵部"
        target = ct.groups[0].split("（")[0]
    else:
        q = (query or "").replace("韵", "")
        for name in XINYUN_ORDER:
            if q and (q == name or name.endswith(q) or q.endswith(name[-1])):
                target = name
                break
    if not target:
        return "没有找到这个新韵韵部。十四韵：" + " ".join(XINYUN_ORDER)
    lvl = _pinyin()["gb2312_level"]
    l1, l2 = [], []
    for ch, v in lvl.items():
        for r in xin_readings(ch):
            _s, fin, tone = parse_pinyin(r)
            if XINYUN.get(fin) == target and tone_class(tone) == pz:
                (l1 if v == 1 else l2).append(ch)
                break
    return f"中华新韵·{target}（{pz}声）\n  常用：{''.join(l1)}\n  次常用：{''.join(l2)}"


def cmd_patterns(form: str, start: str, first_rhyme: bool) -> str:
    size = 7 if form.startswith("七") else 5
    n = 8 if "律" in form else 4
    T = FIVE if size == 5 else SEVEN
    # 首句类型
    if size == 5:
        if start == "仄起":
            first = "b" if first_rhyme else "A"
        else:
            first = "B" if first_rhyme else "a"
    else:
        if start == "平起":
            first = "b" if first_rhyme else "A"
        else:
            first = "B" if first_rhyme else "a"
    seq = [first]
    pair = {"A": "B", "a": "b", "B": "A", "b": "a"}
    # 对句：与出句相对且平收
    def partner(t):
        return {"A": "B", "a": "b"}[t] if t in ("A", "a") else None
    if first in ("B", "b"):
        # 首句入韵：首句平收，对句为相对的平收句
        seq.append({"B": "b", "b": "B"}[first])
    else:
        seq.append(partner(first))
    while len(seq) < n:
        prev = seq[-1]
        # 粘：下一出句与上一对句同起，仄收
        nxt_out = {"B": "a", "b": "A"}[prev]
        seq.append(nxt_out)
        seq.append(partner(nxt_out))
    out = [f"{form}·{start}·首句{'入' if first_rhyme else '不入'}韵（王力《诗词格律》标准格式）"]
    for i, t in enumerate(seq[:n], 1):
        mark = "（韵）" if (i % 2 == 0 or (i == 1 and first_rhyme)) else ""
        out.append(f"  {i}. {T[t]}{mark}")
    out.append("说明：一三五（七言）/一三（五言）多可不论，但要避开孤平（平收句“仄平仄仄平”）和三平尾；"
               "“平平仄平仄”（特拗）可用；出句第四字（七言第六字）拗用仄时，须在对句第三字（七言第五字）用平相救。")
    return "\n".join(out)


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="检查近体诗或对联")
    c.add_argument("text", nargs="?", help="诗文（也可用 --file 或标准输入）")
    c.add_argument("--file")
    c.add_argument("--yun", choices=["pingshui", "xin"], default="pingshui", help="韵书：平水韵（默认）或中华新韵")
    c.add_argument("--form", default="auto", help="五绝/七绝/五律/七律/排律/对联（默认自动识别）")
    c.add_argument("--json", action="store_true")
    lk = sub.add_parser("lookup", help="查字")
    lk.add_argument("chars")
    rh = sub.add_parser("rhymes", help="列出韵部用字")
    rh.add_argument("group", nargs="?")
    rh.add_argument("--char")
    rh.add_argument("--yun", choices=["pingshui", "xin"], default="pingshui")
    rh.add_argument("--pz", choices=["平", "仄"], default="平", help="新韵：列平声还是仄声字")
    rh.add_argument("--all", action="store_true")
    pt = sub.add_parser("patterns", help="标准平仄谱")
    pt.add_argument("form", choices=["五绝", "七绝", "五律", "七律"])
    pt.add_argument("--start", choices=["平起", "仄起"], default="仄起")
    pt.add_argument("--first-rhyme", action="store_true", help="首句入韵")
    a = ap.parse_args(argv)

    if a.cmd == "lookup":
        print(cmd_lookup(a.chars))
        return 0
    if a.cmd == "rhymes":
        print(cmd_rhymes(a.group, a.char, a.yun, a.all, a.pz))
        return 0
    if a.cmd == "patterns":
        print(cmd_patterns(a.form, a.start, a.first_rhyme))
        return 0
    if a.cmd != "check":
        ap.print_help()
        return 2
    text = a.text
    if a.file:
        text = Path(a.file).read_text(encoding="utf-8-sig")
    if not text:
        text = sys.stdin.read()
    res = check_text(text, a.yun, a.form)
    other = None
    if res.get("lines") and "tones" in (res["lines"][0] if res["lines"] else {}):
        other_yun = "xin" if a.yun == "pingshui" else "pingshui"
        other = check_text(text, other_yun, a.form)
    if a.json:
        res["other_yun"] = {"yun": other["yun"], "verdict": other["verdict"]} if other else None
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render(res, other))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
