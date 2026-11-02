---
tags: [astrbot-plugin-dev]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

写一个 AstrBot 提醒插件：用户发 `/提醒 30 记得给妈妈打电话 顺便问问周末安排`（第一个参数是多少分钟后，后面是提醒内容，内容里可能有空格），到点后机器人在原来的那个群或私聊里 @ 这个人发提醒内容。要求 AstrBot 重启后还没到点的提醒不能丢；插件被禁用或重载时不能留下僵尸任务或者重复提醒；/提醒列表 看自己还有哪些提醒。平台主要是 QQ（aiocqhttp）和 Telegram。插件名 astrbot_plugin_remind，作者 xmlans。
