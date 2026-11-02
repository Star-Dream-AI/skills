# Telegram Use

**English** | [中文](#中文说明)

An [Agent Skill](https://agentskills.io) that teaches AI agents to operate **Telegram** for a user,
safely and accurately, through any of three routes:

- **Telegram Web**, both versions: **K** (`web.telegram.org/k/`) and **A** (`web.telegram.org/a/`),
  via browser automation (DOM) or screenshots
- **Telegram Desktop** (the official Qt app on Windows, Linux and macOS), via screenshot-based
  computer use, keyboard shortcuts and `tg://` links
- **Bot API and MTProto** (Telethon / Pyrogram), with no UI at all

It covers the everyday tasks: finding chats, reading, sending and formatting, reply / forward /
edit / delete, files and photos, scheduled and silent messages, groups and channels, contacts,
folders, settings and export. For each one it says **where Web K, Web A and Desktop differ**
(for example, secret chats aren't available on Web or Desktop, and only Desktop can export
history).

Because the agent is acting in someone's real account, the skill opens with safety rules: confirm
before anything other people can see, check the chat header before every send, never touch login
codes, and test in Saved Messages.

## Contents

```
telegram-use/
├── SKILL.md                 client detection, safety rules, the observe → act → verify loop
├── references/
│   ├── web-k.md             Web K layout, URL routing, DOM hints, Playwright example
│   ├── web-a.md             Web A layout, URL routing, DOM hints, Playwright example
│   ├── desktop.md           Telegram Desktop layout, shortcuts, tg:// links, file dialogs, macOS note
│   ├── features.md          step-by-step recipes for each basic feature, with K / A / Desktop differences
│   └── api.md               Bot API and MTProto essentials, limits and pitfalls
├── scripts/
│   ├── web_probe.js         read-only probe: K or A? logged in? open chat? which selectors still match?
│   └── bot_api.py           stdlib Bot API helper (getMe / getUpdates / sendMessage with a dry run by default)
└── evals/                   3 test scenarios in `claude plugin eval` format
```

## Install

Copy the folder to `~/.claude/skills/telegram-use/` (or `<project>/.claude/skills/`), or install it
with `npx skills add Star-Dream-AI/skills`.

## A note on selectors

Telegram updates its web clients often. Class names in the references are **hints observed in
2024–2025**. The skill tells agents to check them (`web_probe.js` reports which hints still match)
and to prefer roles, labels and visible text. Corrections are welcome.

---

## 中文说明

这个 Agent Skill 教 AI agent 安全、准确地替用户操作 **Telegram**，支持三种方式：

- **Telegram 网页版**：**K 版**（`web.telegram.org/k/`）和 **A 版**（`web.telegram.org/a/`）都覆盖，可以用浏览器自动化读网页元素来操作，也可以看截图操作。
- **Telegram Desktop 电脑端**：官方客户端，看截图配合鼠标键盘操作，可以用快捷键和 `tg://` 链接。
- **Bot API / MTProto**（Telethon、Pyrogram）：不经过界面，直接写代码调用。

内容覆盖日常基本功能：找聊天、读消息、发消息和设置格式、回复、转发、编辑、删除、发文件和图片、定时消息、静音发送、群组和频道、联系人、文件夹、设置、导出聊天记录。每项都**写明网页 K 版、A 版和电脑端的区别**，比如网页版和电脑端都不能开私密聊天，只有电脑端能导出聊天记录。

agent 是在用户的真实账号里操作，所以 skill 一开头就是安全规则：别人能看到的操作要先确认；每次发送前核对聊天标题；不碰登录验证码；不确定的操作先在"收藏夹"（Saved Messages）里试。

网页版的元素选择器经常变化，参考文档里写的只是线索。skill 要求 agent 先用 `web_probe.js` 检查哪些选择器还能用，并且优先按按钮文字和标签来找元素。
