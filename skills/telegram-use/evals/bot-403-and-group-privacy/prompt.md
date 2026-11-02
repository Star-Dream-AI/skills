---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Bash]
---

My Telegram bot (python, plain requests) gets 403 "Forbidden: bot can't initiate conversation with a user" when I call sendMessage with my friend's user id. Also I added the bot to our group but it only sees /commands, not normal messages. And getUpdates sometimes returns 409 Conflict. What's going on and how do I fix all three?
