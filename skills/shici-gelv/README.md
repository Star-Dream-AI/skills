# shici-gelv · 诗词格律

**中文** | [English](#english)

一个帮 AI 检查和写作**格律诗**的 [Agent Skill](https://agentskills.io)，覆盖五绝、七绝、五律、七律、排律和对联。

语言模型"听"不到声调，常把入声字（国、白、一、十、竹、读）当成平声，把邻韵当同韵，写完不合律的诗还说"合律"。这个 skill 附带一个离线检查脚本，平仄和韵部一律查表判断，不靠模型的感觉：

- **平水韵**：106 个韵部、8550 字，能识别入声字。韵书里查不到的字，会按异体字或唐代读音推定，并在报告中注明。
- **中华新韵**：中华诗词学会 2005 年版十四韵，按普通话读音判断平仄。
- **检查项目**：平仄（四种基本句式）、粘对、押韵、出韵、首句借邻韵、孤平、三平尾、三仄尾、拗救（本句自救、对句救）、特拗（平平仄平仄）、重字、对仗联同位重字、对联的仄起平落。
- **两读字提示**：看、胜、为、重、行、长这类平仄两读的字，报告会注明此处必须读平还是读仄，并列出常见义项，由 AI 按字义确认。
- **辅助工具**：`lookup` 查字，`rhymes` 列出韵部里的常用字，`patterns` 给出标准平仄谱。

规则依据王力《诗词格律》。

## 用法

```bash
python scripts/gelv.py check "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。"
python scripts/gelv.py check --file poem.txt --yun xin     # 中华新韵
python scripts/gelv.py lookup 国胜看
python scripts/gelv.py rhymes 阳
python scripts/gelv.py patterns 七律 --start 平起 --first-rhyme
```

只需要 Python 3.8 以上和标准库，离线运行。

安装：把文件夹复制到 `~/.claude/skills/shici-gelv/`，或者运行 `npx skills add Star-Dream-AI/skills`。

## 测试

```bash
python -m unittest discover -s tests
```

20 个回归测试，以《登鹳雀楼》《春望》《登高》《春日忆李白》（特拗）、《登乐游原》（拗救）、《静夜思》《春晓》（古体）等经典诗为例。`evals/` 里有 5 个对比测试场景，可以用 `claude plugin eval .` 运行。

## 局限

- 脚本不检查**词**的格律，因为没有内置词谱；也不评价诗的好坏、用典和对仗是否工整，这些留给 AI 和用户判断。
- 平水韵各版本收字略有出入，本表依据维基文库本。
- "中华通韵"（2019）暂未支持，因为没有找到可以核对的原文。

## 数据来源与协议

| 数据 | 来源 | 协议 |
|---|---|---|
| 平水韵字表 | [维基文库《平水韵》](https://zh.wikisource.org/wiki/平水韻)，经 [pingshui_rhyme](https://github.com/rbnyng/pingshui_rhyme) 整理 | 原文为公有领域；整理数据 MIT |
| 普通话读音 | [pypinyin](https://github.com/mozillazg/python-pinyin) | MIT |
| 简繁、异体对照 | [OpenCC](https://github.com/BYVoid/OpenCC) | Apache-2.0 |
| 异体字、唐代读音 | [Unicode Unihan](https://www.unicode.org/charts/unihan.html) | Unicode License v3 |

各协议原文见 `assets/data/licenses/`。`scripts/build_data.py` 可以从这些原始数据重新生成 `assets/data/`。

---

## English

An Agent Skill for checking and writing Chinese **regulated verse** (jintishi: 5- and 7-character
quatrains, 8-line regulated poems, extended regulated verse) and **couplets**.

Language models can't hear tones. They routinely treat old entering-tone characters as level tones
and mix neighbouring rhyme groups. This skill ships an offline checker that reads the tones and
rhyme groups from tables instead: the Pingshui rhyme scheme (106 groups) and the 2005 Zhonghua
Xinyun scheme (14 groups). It checks tone patterns, line linking, rhyme, and the classic faults
and licences (孤平, 三平尾, 拗救, 特拗) following Wang Li's *Shici Gelü*. Polyphonic characters are
flagged for the model to confirm by meaning.

Python 3.8+ standard library only. Data comes from Wikisource / pingshui_rhyme (MIT), pypinyin
(MIT), OpenCC (Apache-2.0) and Unicode Unihan (Unicode License v3). License texts are in
`assets/data/licenses/`.
