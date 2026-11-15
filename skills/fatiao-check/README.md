# fatiao-check · 法条引用核验

**中文** | [English](#english)

一个帮 AI **核对中国法律条文引用**的 [Agent Skill](https://agentskills.io)。

模型引用法条时，常会编造条号、张冠李戴、改动引文，或者引用已经废止的法律和修订前的旧条号，而且这些错误读起来都像真的。这个 skill 把文稿里每一处"《某法》第X条"都拿去对照原文：

- **条号、款、项是否存在**：比如《劳动合同法》没有第一百零二条，第三十九条也没有第七项。
- **引文是否出自这一条**：报告会指出引号里的话实际出自哪一条。
- **所述内容是否真是这一条**：文意明显属于另一条时，会提示正确的条号。
- **法律是否已废止**：例如《合同法》已于 2021-01-01 被《民法典》取代，报告会给出新法的对应条文。
- **是否用了修订前的旧条号**：例如《公司法》2023 年修订后，股东会职权从第三十七条变成了第五十九条。
- 能识别各种写法：书名号全称或简称、阿拉伯数字、"之一"条、条款项、并列、"至"、"本法第X条"等。

条文存在、但没有直接引文的地方，脚本会附上原文，由 AI 判断文意是否准确。

## 法律文本来源

1. **附带法律库**（离线可用）：53 部常用法律、行政法规的现行文本，加上近年修订过的法律的前两个版本（脚本按施行日期选用当时有效的版本，已通过但未施行的修正版不会被当作现行版），以及被《民法典》废止的九部旧法。总大小约 1.8MB。
2. **维基文库**：通过官方公开 API 联网补充其他法律，只发送法律名称，不会发送文稿内容。
3. **官方文本导入**：用户从国家法律法规数据库网站下载的 docx，可以用 `import` 导入，导入后优先使用。

中国法律、法规的条文不受著作权保护（《著作权法》第五条）。附带文本转录自维基文库，正式文书请以国家法律法规数据库的标准文本为准。

## 用法

```bash
python scripts/fatiao.py check --file 律师函.txt
python scripts/fatiao.py show 劳动合同法 47
python scripts/fatiao.py search 民法典 违约金 过分高于
python scripts/fatiao.py import 下载/中华人民共和国XX法.docx
```

只需要 Python 3.8 以上和标准库。

安装：把文件夹复制到 `~/.claude/skills/fatiao-check/`，或者运行 `npx skills add Star-Dream-AI/skills`。

更新附带的法律库（需要能访问维基文库）：

```bash
FATIAO_UA="你的工具名 (联系方式)" python scripts/build_seed.py
```

## 测试

```bash
python -m unittest discover -s tests
```

24 个离线测试，只用附带的法律库。`evals/` 里有 9 个对比测试场景，其中 4 个专测 2025–2026 年新修订的法律。

### 对比测试结果

在 4 份引用了新修订法律旧条号的文书上（《治安管理处罚法》《仲裁法》《反不正当竞争法》2025 年修订、《律师法》2026 年修正），两边都**禁止联网**，比较用和不用这个 skill 的结果（Sonnet，每种配置各跑 1 次）：

| | 用 skill | 不用 skill |
|---|---|---|
| 评分项通过率 | 12/12（100%） | 6/12（50%） |
| 平均耗时 | 46.6 秒 | 42.5 秒 |

不用 skill 时，模型大多知道这些法律修订过，但新条号只能凭记忆猜：把寻衅滋事写成第三十一条（应为第三十条），说不出《仲裁法》的新条号，也不知道《律师法》2026 年修正过。它还凭记忆误引原文，挑出了并不存在的措辞问题。用 skill 时，每处改正都附上了现行原文，还指出了实质变化，比如撤销仲裁裁决的期限由六个月改为三个月。

能联网时，不用 skill 的模型可以搜到新闻转载的新法全文，两边的通过率都是 100%。

## 局限

- 不提供法律意见，只核对引用是否准确。
- 地方性法规、部门规章，以及多数司法解释没有附带。可以联网获取，或者导入官方文本。
- 文意判断要靠 AI 读原文，脚本只做文字层面的比对。

---

## English

An Agent Skill that **verifies citations of PRC statutes** against the actual text. It flags
article, paragraph and item numbers that don't exist, quotes taken from a different article,
claims that belong to another article, laws that have been repealed (e.g. the Contract Law,
replaced by the Civil Code on 2021-01-01, with the matching Civil Code article suggested), and
article numbers from a pre-amendment version (e.g. the 2023 Company Law revision).

It ships an offline library of 53 frequently cited laws plus recent historical versions (about
1.8MB). It can fetch more from Wikisource through its public API, sending only law titles, and
it imports official texts that the user downloads from the National Database of Laws and
Regulations. Python 3.8+ standard library only. Chinese statutes are not protected by copyright.
This skill checks citations only and does not give legal advice.

In a no-internet comparison on four documents citing pre-revision article numbers of laws
amended in 2025–2026, Sonnet with the skill passed 12/12 checks and without it 6/12. Without
the skill the model often knew a revision had happened but guessed the new numbers wrongly or
gave none, and misquoted statute text from memory.
