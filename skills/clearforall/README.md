# ClearForAll

**English** | [中文](#中文说明)

An open [Agent Skill](https://agentskills.io) that helps nonprofits, caseworkers and volunteers turn
complex public-service documents (benefit notices, government letters, insurance and eligibility
rules) into accurate **plain-language text** and **accessible HTML**, in **English and Chinese**.

Simplifying an official notice is risky: one dropped "only if" or one wrong deadline can cost
someone their benefits. ClearForAll puts accuracy first:

- **Nothing is lost.** Every number, date, eligibility rule, required document and contact goes into
  a fact ledger (`facts.json`) with a verbatim quote and location from the source. Validators check
  that every output still carries every value, in any notation or language.
- **Every claim is traceable.** Each fact on the HTML page links to the exact source quote.
- **Uncertainty is flagged, not guessed.** Contradictions, hedges ("may", "原则上"), computed values
  and risky translations go to a `review.md` checklist for a human. Pages stay marked as drafts
  until a person resolves them.
- **Private and local.** Everything runs offline with the Python standard library. Nothing is
  uploaded or published, personal details are kept out of the outputs, and the HTML loads no
  third-party resources.

## Install

Copy this folder into your agent's skills directory:

| Agent | Location |
|---|---|
| Claude Code (all projects) | `~/.claude/skills/clearforall/` |
| Claude Code (one project) | `<project>/.claude/skills/clearforall/` |
| Other Agent Skills-compatible agents | see your agent's docs |

Requires Python 3.8+. There are no other dependencies.

## Use

Ask in your own words, for example:

> Our food pantry clients get confused by this energy assistance notice (heap-notice.txt). Can you
> make an easy-to-read version and a page we can show on a tablet?

> 帮我把这份医保缴费通知做成老人看得懂的简明版，再做一个英文版。

The skill produces a folder like this:

```
clearforall-output/<name>/
├── facts.json            fact ledger: every critical fact with source quote + location
├── plain-en.md / plain-zh.md
├── page-en.html / page-zh.html
├── review.md             questions a person must answer before sharing
└── validation-report.txt
```

## Validators

You can also run the validators on their own (`python scripts/<name>.py --help`):

| Script | Checks |
|---|---|
| `extract_facts.py` | lists every line with dates, money, deadlines, eligibility words, hedges and personal data |
| `check_facts.py` | quotes exist verbatim in the source; every fact value appears in every output; HTML `data-fact` traceability; numbers not in the source |
| `check_html.py` | language tags, headings, landmarks, table headers, link text, font size, no third-party resources |
| `readability.py` | sentence length and officialese (English and Chinese) |
| `check_privacy.py` | names, case numbers, addresses and ID numbers from the source don't leak into outputs |
| `validate_all.py` | runs everything on an output folder and writes a report |

## Evaluation

`evals/` holds three realistic test cases in the `claude plugin eval` format: an English energy
assistance notice, a Chinese medical insurance notice translated into both languages, and a
personal English benefits letter explained in Chinese. In the first round against the same model
without the skill:

| | With skill | Without skill |
|---|---|---|
| Assertions passed (31) | 100% | 90% |
| Average time | 308 s | 105 s |
| Average tokens | 109k | 63k |

The base model already copies numbers accurately. The skill's gains are in judgment: it traces
each fact to its source, marks computed amounts as computed instead of presenting them as fact, and
flags a letter that contradicts itself instead of passing it on.

Run the cases yourself with Claude Code: `claude plugin eval . --allow-tools Write,Edit,Bash --scaffold`.

## Limits

- The outputs are **drafts**. A person who knows the program should answer `review.md` before
  anything is shared.
- The validators find patterns. They catch dropped or changed values, but they can't tell whether a
  sentence still means the same thing. That is what the review step is for.
- Scanned documents have to be transcribed or OCR'd locally first.

## License

[Apache-2.0](../../LICENSE) (the license of the Star Dream AI Skills repository)

---

## 中文说明

ClearForAll 是一个开源的 Agent Skill，帮公益机构、社工和志愿者把复杂的公共服务文件（补助通知、政府来信、医保社保政策、申请须知）改写成**准确的简明文字**和**无障碍网页**，支持**中文和英文**。

简化官方通知有风险：漏掉一个"仅限"，或者写错一个截止日期，都可能让人错过补助。ClearForAll 把准确放在第一位：

- **不丢信息**：每个数字、日期、申请条件、所需材料、联系方式都记进事实清单（`facts.json`），附原文逐字引文和位置。校验脚本会检查每份输出是否都保留了这些值，换了写法或语言也能识别。
- **可溯源**：网页上每条关键信息都能对应到原文引文。
- **不确定就标出来，不猜**：前后矛盾、"可能""原则上"这类模糊说法、自己算出来的数字、难翻译的术语，都列进 `review.md` 交给人工核实。核实完之前，页面一直显示"草稿"。
- **隐私优先、全部本地**：只用 Python 标准库离线运行，不上传、不发布任何内容。输出里不放姓名、案件号、住址等个人信息，网页不加载任何第三方资源。

### 安装

把这个文件夹复制到 `~/.claude/skills/clearforall/`（所有项目可用），或复制到 `<项目>/.claude/skills/clearforall/`（只在这个项目可用）。需要 Python 3.8 以上，没有其他依赖。

### 使用

直接用自己的话说就行，例如："帮我把这份通知改成老人看得懂的版本，再做一个能在平板上看的网页。"

### 注意

输出的都是**草稿**，分享之前要有熟悉该项目的人逐条回答 `review.md` 里的问题。校验脚本能发现数字和日期被漏掉或改动，但判断不了一句话的意思有没有变，这要靠人工复核。
