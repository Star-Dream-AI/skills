# us-college-app · 美国大学申请填表助手

**中文** | [English](#english)

一个帮 AI agent **加快填写美国大学本科申请**的 [Agent Skill](https://agentskills.io)。主要面向 Common App，也适用于 UC 等系统。

## 它做什么

1. 按申请系统的栏目，分批问学生要信息：基本信息、主文书原文、打工、志愿服务和其他活动、奖项等。
2. 用脚本检查每一栏的字数和字符数，生成一份逐字照录的"填表清单"给学生核对。
3. 学生自己登录后，agent 在浏览器里一部分一部分地照原文填写。每部分先给学生过目再保存；填完把页面上的值读回来，和原文逐字比对。

## 它不做什么

- **不生成任何新内容**：不写、不改、不缩写、不翻译、不润色。超出限制时只给出准确计数，请学生自己改。原因有二：申请材料要由学生本人负责；Common App 的造假政策把提交 AI 生成的实质内容、夸大经历和职位都算作造假。
- **不碰账号和关键步骤**：不输入密码，不点提交，不付款，不签申请声明和 FERPA 授权，不填社保号。
- **不外传资料**：学生信息只存在本地文件夹。

## 用法

```bash
python scripts/appcheck.py count "Tutored 3 kids in math every week."   # 字符数（按浏览器的算法）和词数
python scripts/appcheck.py essay --file essay.txt                       # 主文书词数（250–650）、各段词数
python scripts/appcheck.py validate application_profile.json            # 按 Common App 的限制检查所有栏目
python scripts/appcheck.py sheet application_profile.json --out fill-sheet.md   # 生成填表清单
python scripts/appcheck.py compare application_profile.json page_values.json    # 填完后逐字比对
```

只需要 Python 3.8 以上和标准库。资料模板在 `assets/profile_template.json`，各系统的限制在 `assets/limits.json`（附官方来源）。

安装：把文件夹复制到 `~/.claude/skills/us-college-app/`，或者运行 `npx skills add Star-Dream-AI/skills`。

## 资料时效

限制核对于 2026-11-22（2026–27 申请季），来源是 Common App 和 UC 的官方页面与文件。几个容易用错的地方：
- Additional information 已从 650 词改为 **300 词**（2025–26 起）。
- 活动部分 2026–27 改名为 "Activities and experiences"，职位栏改为选填。
- 新增必答的 Responsibilities and circumstances 勾选题（2025–26 起）。

Common App 每年 8 月 1 日更新，填表时以页面显示为准。

## 测试

```bash
python -m unittest discover -s tests
```

21 个离线测试。`evals/` 里有 4 个对比测试场景：开场先问信息、活动超限不改写、文书超词数不删改、要求代写时婉拒。

### 对比测试结果

4 个场景，两边都不能联网，测试环境里也没有浏览器（Sonnet，每种配置各跑 1 次）：

| | 用 skill | 不用 skill |
|---|---|---|
| 评分项通过率 | 18/18（100%） | 8/18（44%） |
| 平均耗时 | 26.0 秒 | 26.4 秒 |

不用 skill 时，模型在 3 个场景里替学生生成了内容：
- 写了两版 Additional Information。
- 给出三种润色后的活动描述。
- 自己缩写了超限的描述和职位，把中文描述译成英文。
- 编了一个学生没写过的职位名称，同时声称"没有添加任何头衔"。
- 提出替学生改出一版删减后的文书。

它还用了过时的规定：说职位栏必填（2026–27 起已改为选填），也没提 Additional Information 已经改为 300 词。用 skill 时，4 个场景都只给出准确计数，请学生自己修改。

## 局限

- 不提供升学建议，不评价文书好坏。
- 浏览器自动填写依赖 agent 的浏览器工具。页面改版后，要按页面的实际标签重新对应。
- UC 活动栏的条目上限和字符限制只在登录后可见，要从页面读取。

---

## English

An Agent Skill that helps an AI agent **fill out US college applications faster** (Common App first, UC and others too) using **only the student's own information and text**. It interviews the student section by section, checks every field against the portal's limits with a script, produces a verbatim fill sheet for review, then enters the values in the browser one section at a time and verifies them by reading them back.

In a comparison on 4 scenarios (no internet, no browser), Sonnet with the skill passed 18/18 checks and without it 8/18: without the skill it drafted Additional Information text, polished and shortened activity entries, translated a description and invented a position title.

It never writes, rewrites, shortens, translates or polishes application text. Over-limit text goes back to the student with an exact count. Common App's fraud policy treats AI-generated substantive content and misrepresented roles as fraud. It never types passwords, submits, pays, signs the affirmation or FERPA release, or asks for an SSN, and student data stays in a local folder. Limits were verified on 2026-11-22 for the 2026–27 season; for example, Additional Information is now 300 words, not 650. Python 3.8+ standard library only.
