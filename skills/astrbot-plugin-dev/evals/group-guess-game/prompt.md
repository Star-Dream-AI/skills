---
tags: [astrbot-plugin-dev]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

帮我写一个 AstrBot 插件，给我们 QQ 群（NapCat 接的 aiocqhttp）玩猜数字：群友发 /猜数字 开始一局，机器人心里想一个 1-100 的数，然后这个人直接发数字就行（不用再加 / 前缀），机器人回大了小了，猜中或者 2 分钟没动静就结束，发"退出"也能结束。重点是群里好几个人可以同时各玩各的，别人的消息不能串到我的局里。再加个可以在 WebUI 改的配置：数字上限（默认100）和超时秒数。插件名 astrbot_plugin_guess，作者 xmlans。
