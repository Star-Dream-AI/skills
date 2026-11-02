---
tags: [astrbot-plugin-dev]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

想写个 AstrBot 插件让机器人更有"人情味"：每次跟 LLM 对话的时候，把当前时间（精确到分钟）和这个用户对机器人的好感度告诉模型，让它据此调整语气。好感度规则：用户每次跟机器人聊天 +1，消息里有"谢谢"再 +2，有"滚"或者"烦"就 -5，范围 0-100，初始 50；重启 AstrBot 或更新插件后好感度不能丢。再给个 /好感度 指令查自己的分数。我们的 LLM 是按 token 计费的，别让这个插件把账单搞上去。插件名 astrbot_plugin_affinity。
