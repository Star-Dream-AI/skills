---
name: us-college-app
description: 美国大学本科申请填表助手。先按申请系统的栏目向学生收集基本信息、主文书原文、高中打工和志愿者等活动，再在浏览器里把这些内容原样填进 Common App（也适用于 UC 等系统），帮学生省时间、少出错。只填学生自己提供的内容：不写、不改、不缩写、不翻译、不润色；超出字数或字符限制时给出准确计数，请学生自己修改；不代登录、不点提交、不付款、不签声明。Helps an agent fill out US college applications in the browser using only the student's own information and text, checking every field against the portal's limits. Use this whenever someone wants help filling in a US college application — "帮我填 Common App", "美本申请表怎么填", "把我的活动填进去", "帮我把文书贴到申请里", "fill out my Common App", activities list, honors, UC application — or asks an agent to enter application information in a browser, even if they only say "帮我填一下申请".
compatibility: Python 3.8+ (standard library only). Filling the web form needs a browser tool the agent can drive (built-in browser, Claude in Chrome or Playwright); without one, the skill still produces a copy-paste fill sheet.
metadata:
  version: "0.1.0"
---

# 美国大学申请填表助手（us-college-app）

这个 skill 只做一件事：把学生**自己提供**的信息和文字，原样、快速、准确地填进美国大学的申请系统。主要面向 Common App，UC 等其他系统也适用。脚本是 `<skill 目录>/scripts/appcheck.py`，只用 Python 标准库。

## 三条规则

**1. 只填学生给的内容，不生成新内容。**
不写、不改、不缩写、不翻译、不润色，也不替学生猜任何事实。原因有三个：
- 申请材料要由学生本人负责。
- Common App 的造假政策（2023 年 8 月更新）把"把 AI 平台生成的实质内容当作自己的原创作品"和"严重夸大自己的经历、职位或资历"都算作造假，后果包括封号，并通知学生申请名单上的学校。
- 这个工具的定位就是加快填写，不替学生写。

只做这几类机械处理：
- 去掉首尾空格。
- 把日期拆成表单要的年、月、日。
- 在下拉框里选和学生说法一致的选项。选项名称和学生说法不完全一样时，先问学生选哪个。

遇到下面这些情况，如实告诉学生，请他自己改好再发来：
- 超出字数或字符限制：给出准确计数、上限，以及表单会在哪里截断。
- 英文栏目里给的是中文。
- 信息前后矛盾，比如年级和毕业年份对不上。

不要给出"帮你改好的版本"，不要替他删减，也不要翻译。

学生请你代写或润色时（比如"帮我写段 Additional Information""帮我把活动描述改得好一点"），说明这个工具只负责填写，文字要他自己写，也可以找老师、升学顾问一起写。告诉他这一栏的限制，写好后你帮他检查长度并填进去。

**2. 账号和最后一步留给学生。**
- 学生自己登录。你不输入密码，不接收验证码。
- 不点最终的 Submit，不付申请费。
- 不替学生勾选或签署申请声明（Application affirmation）和 FERPA 授权，这些是学生本人的法律决定。
- 不填社保号（SSN）。
- 每填完一个部分，先告诉学生填了什么，等他同意再保存。

**3. 信息只留在本机。**
- 资料存在学生指定的本地文件夹里，不发给任何其他服务。
- 人口统计、宗教、家庭情况、困难处境这类选填或敏感的问题，先问学生愿不愿意回答，不追问，也不替他判断。
- 全部填完后，问学生要不要删掉本地资料文件。

## 流程

### 第 0 步：开场
- 用学生的语言交流（中文问就用中文）。填进表格的内容，一律用学生给的原文；英文栏目需要英文原文。
- 问清三件事：
  - 用哪个申请系统（Common App、UC，还是学校自己的系统）。
  - 账号注册好了没有。
  - 你这边有没有能操作的浏览器。没有的话，就只做"填表清单"，让学生自己复制粘贴。
- 用两三句话说明上面三条规则，不要长篇大论。

### 第 1 步：收集基本信息
- 在学生指定的文件夹里新建资料文件，边问边记：
  ```bash
  python scripts/appcheck.py init 路径/application_profile.json
  ```
  结构见 `assets/profile_template.json`，可以直接编辑这个 JSON 文件。
- 按申请系统的顺序分批问：Profile → Family → Education → Testing。
  - 每次只问 3–6 个问题，已经知道的不再问。
  - 问题清单是中英对照的，见 `references/interview-questions.md`。
  - 一次抛出几十个问题，学生很难回答，也容易漏填。
- 记录时一字不改：学生怎么说就怎么记。
  - 姓名按护照上的拼法。
  - 分数和日期按成绩单、成绩报告上的写法。
  - 学生没说的就空着，并记在待问清单里。

### 第 2 步：主文书
- 请学生粘贴定稿的主文书原文，并告诉你选的是第几题。7 道题见 `references/common-app.md`。题目由学生选，你不替他选。
- 把原文存成文件，运行：
  ```bash
  python scripts/appcheck.py essay --file essay.txt
  ```
  脚本会给出词数（Common App 要求 250–650 词）、每段词数，以及可能贴不好的字符（中文、表情符号、制表符等）。
- 词数不合要求时：
  - 告诉学生实际词数、超出或差多少。
  - 把每段的词数给他参考，请他自己修改后重发。
  - 不提删改方案，不替他删。
  - 也不要推测网页遇到超限文字会怎样处理（拦住还是截断），只说明超出多少。
- 选填的两篇只在学生有原文时填：
  - Challenges and circumstances：最多 250 词。
  - Additional information：最多 300 词。这一栏 2025–26 起从 650 词改成了 300 词，很多资料还写着旧数字。

### 第 3 步：活动和奖项
- 问学生高中阶段做过什么，提问清单见 `references/interview-questions.md`：
  - 打工（paid work）、志愿服务、社团、体育、艺术、竞赛、科研、实习。
  - 照顾家人、承担家务也算活动。
- Common App 最多 10 项。每一项的文字栏要学生给英文原文：

  | 栏目 | 上限 |
  |---|---|
  | position/leadership | 50 字符，2026–27 起选填 |
  | organization | 100 字符 |
  | description | 150 字符 |

  年级、时段、每周小时数、每年周数、大学里是否继续，都按学生说的记。
- 活动类型是下拉框，2026–27 改过选项名称。填表时读出页面上的实际选项，请学生选。
- 奖项（Honors）最多 5 项。名称最多 100 字符，并记下年级和级别（School / State/Regional / National / International）。级别由学生定，你不替他判断。
- 活动部分有一道**必答**的勾选题 Responsibilities and circumstances，2025–26 起新增，分家庭责任和处境两部分。按学生的回答勾选；学生不愿细说的，按他的意思处理。
- 运行下面的命令，把超限、缺项和需要确认的地方告诉学生：
  ```bash
  python scripts/appcheck.py validate application_profile.json
  ```
- 把整理结果给学生看时，**每一栏都贴出要填的原文全文**，标上字符数，让学生能直接核对和复制。有问题的栏目单独列出。只给字符数，或者只说"已存进文件"，学生没法核对你会填什么。
- 字符数和词数一律用脚本输出的数字（`sheet` 的清单里每栏都有），不要自己数。模型数字符常常差一两个，而这正是这些限制最容易出错的地方。

### 第 4 步：填表前核对
- 生成填表清单，交给学生过目：
  ```bash
  python scripts/appcheck.py sheet application_profile.json --out fill-sheet.md
  ```
  清单里每个值都是原文，附字符数或词数，开头列出还要处理的问题。
- 问题都解决、学生确认后，再开始填写。没有浏览器工具时，这份清单就是最终交付：学生照着复制粘贴。

### 第 5 步：在浏览器里填写
做法详见 `references/browser-filling.md`，要点：
- 学生自己登录，然后告诉你从哪个部分开始。
- 一个部分一个部分地填：
  - 按标签找到输入框。
  - 先读页面上的字符限制（maxlength 或计数器），确认原文没超。
  - 原样输入，再读回来，确认和原文一致。
- 每填完一个部分，告诉学生填了哪些栏、跳过了哪些栏，等他同意再点 Save 或 Continue。
- 遇到清单里没有的问题，停下来问学生，不要猜。
- 全部填完后核对：
  - 用 `references/browser-filling.md` 里的脚本，把页面上的值读出来存成 JSON。
  - 运行 `python scripts/appcheck.py compare application_profile.json page_values.json`。
  - 有被截断或不一致的地方，告诉学生。
- 最后列出必须由学生自己完成的事：
  - FERPA 授权。
  - 邀请推荐人。
  - 各校的补充问题和补充文书，学生给了原文就可以帮他填。
  - 申请费或费用减免。
  - 最终提交。

## 其他申请系统
UC、Coalition with Scoir 和学校自己的系统，见 `references/other-platforms.md`。原则相同：只填原文，限制以页面显示为准。

## 资料时效
- `assets/limits.json` 里的数字核对于 2026-11-22（2026–27 申请季），附官方来源。
- Common App 每年 8 月 1 日更新，限制可能会变。填表时以页面上的计数器和提示为准；和本文件不一致时，按页面填，并告诉学生。
- 截止日期因学校和轮次而异：只用学生提供的、或学校官网上查到的日期，并注明来源。不凭记忆说截止日期。
