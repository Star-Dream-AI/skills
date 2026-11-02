---
tags: [astrbot-plugin-dev]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

我写了个 AstrBot 翻译插件（astrbot_plugin_translate 文件夹），但问题一堆：
1. WebUI 里装不上 / 插件页面显示加载失败，配置页也出不来
2. 好不容易跑起来后 `/翻译 how are you today` 只翻译了 how
3. 想让 LLM 调用 translate_text 工具后自己组织回答，结果用户直接收到一条生硬的翻译，LLM 那边什么都没拿到
4. 每次在 WebUI 点重载，每日推送就多一份，最后一天收到好几条
5. on_llm_request 里加的提示词好像根本没生效，而且听说这样写很费钱

帮我把这些都修好，改完的插件放回同一个文件夹，并告诉我每个问题的原因。

Input files: astrbot_plugin_translate/
