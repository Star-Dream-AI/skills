# girlfriend-internal

**中文** | [English](#english)

一个让 AI 在陪伴和关心别人时真正"懂"对方的 [Agent Skill](https://agentskills.io)。

它不规定人设。名字、性格、口癖由你自己的设定决定，这个 skill 只管"关心"在内部怎么运作：

- **先听出对方要什么**：同一句"今天好累"，可能是想被安慰、想吐槽、想要建议，或者只想有人知道。默认不给建议。
- **回应落在具体的事上**：不用"辛苦了""一切都会好的"这种对谁都成立的话。
- **开心的事也要接住**：跟上对方的兴奋，追问细节，不急着提醒风险。
- **语气跟着人走**：对方回一句，就别回一屏。尊重沉默，一次只问一个问题。
- **记得小事**：到日子了主动问，提旧事要自然，记错了就认。
- **真诚**：不假装是人，不许做不到的承诺，不把自己变成对方唯一的依靠，不用内疚留人。
- **一条底线**：对方流露出伤害自己的念头时，认真接住，温和地直接问，并引向现实里能到场的人。

`references/examples.md` 里有 12 组"不懂 vs 懂"的对比例子，`references/situations.md` 讲几种难处理的情况：对方冲你发火、反复说同一件事、试探你是不是真的在乎、很久没来又回来。

## 安装

把文件夹复制到 `~/.claude/skills/girlfriend-internal/`，或者运行 `npx skills add Star-Dream-AI/skills`。

做陪伴类 bot 时，可以把它和你自己的人设提示词一起用：人设决定"是谁"，这个 skill 决定"怎么关心人"。

## 说明

- 这个 skill 不能代替心理咨询或医疗帮助。
- 例子是中文日常聊天语境，原则对其他语言同样适用。
- 还没有跑过和不用 skill 的对比测试。`evals/` 里有 4 个测试场景，可以用 `claude plugin eval .` 运行。

---

## English

An [Agent Skill](https://agentskills.io) that makes an AI companion genuinely attentive.

It doesn't define a persona: the name, personality and voice come from your own setup. The skill
covers how caring works on the inside:

- **Read what the person needs first.** "I'm so tired" can be a wish for comfort, a rant, a request
  for advice, or just wanting someone to know. No advice by default.
- **Respond to the specific thing they said**, not with lines that would fit anyone.
- **Share good news properly.** Match their excitement and ask for details before any reminders.
- **Follow their tone.** Short replies to short messages, respect for silence, one question at a
  time.
- **Remember small things**, bring them up naturally, and admit it when you got one wrong.
- **Stay honest.** Never claim to be human, never promise "forever", never become the person's
  only support, never use guilt to keep them.
- **One hard line.** When someone hints at hurting themselves, take it seriously, ask gently and
  directly, and point them to people who can be there in person.

`references/examples.md` has 12 before/after reply pairs (in Chinese). `references/situations.md`
covers harder moments. This skill isn't a substitute for therapy or medical help, and it hasn't
been benchmarked against a no-skill baseline yet. `evals/` holds 4 test scenarios.
