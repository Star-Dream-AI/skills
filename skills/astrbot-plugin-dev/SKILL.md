---
name: astrbot-plugin-dev
description: Expert guide for building, fixing, reviewing and publishing AstrBot plugins (AstrBot 插件开发, Star 插件, astrbot_plugin_*), verified against the AstrBot v4.29.3 source. Covers the Star class and lifecycle (initialize/terminate, hot reload), @filter commands, command groups, parameter parsing (GreedyStr), regex and message listeners, permissions, priorities, event hooks (on_llm_request, on_llm_response, on_decorating_result…), sending passive and active messages with unified_msg_origin, message components, platform APIs (QQ OneBot/aiocqhttp, Telegram), LLM calls, llm_tool function tools, agents, conversations and personas, prompt-cache-friendly prompt injection, _conf_schema.json config, KV and file storage, session_waiter multi-turn flows, metadata.yaml, WebUI views, and the plugin market. Ships a static checker, a scaffold and a fake-AstrBot test harness. Use this whenever the user mentions AstrBot or its plugins, a bot built on AstrBot (QQ机器人, NapCat, Lagrange, Telegram bot, 飞书/钉钉/企业微信 bot running AstrBot), metadata.yaml together with main.py and Star, `from astrbot.api`, `@filter.command`, `@filter.llm_tool`, `_conf_schema.json`, or says things like "写个 AstrBot 插件", "帮我看看这个插件为什么不触发", "给机器人加个指令", "插件怎么发布到插件市场", "AstrBot 插件报错", even when they don't say the word "plugin".
compatibility: Python 3.10+ for the bundled scripts (standard library only; PyYAML is used if installed). Live testing needs a running AstrBot instance (source, Docker or the desktop launcher).
---

# AstrBot plugin development

AstrBot is a multi-platform LLM chatbot framework. A plugin is a `Star` subclass in
`data/plugins/<dir>/main.py`, with a `metadata.yaml` next to it. The plugin registers
handlers with decorators from `astrbot.api.event.filter`. Everything here was checked
against the AstrBot **v4.29.3** source (GitHub master, 2026-10-31). The references note
the version where each feature appeared.

Models usually know the AstrBot *docs*, which are partly outdated and partly wrong. Most
bugs come from the gap between the docs and the actual behaviour, so this skill mostly
records that behaviour.

## Workflow

1. **Get the context before writing code.** Read the user's existing plugin files first.
   Find out the AstrBot version (WebUI footer, `astrbot/__init__.py`, or the version they
   mention) and the target platforms (QQ via aiocqhttp, Telegram, QQ Official, Lark…).
   Ask only for what you can't infer. If the version is unknown, use APIs from ≤4.9 or
   declare `astrbot_version` in metadata.yaml.
2. **Scaffold or edit.** For a new plugin, run
   `python scripts/new_plugin.py <parent_dir> --name astrbot_plugin_xxx --author <id> --display "名称" --desc "描述"`.
   It writes a layout that already passes the checker, with tests and the fake harness.
3. **Pick the right mechanism** (table below), then write the code. Read the matching
   reference file for exact signatures. Don't write AstrBot API calls from memory.
4. **Verify.**
   - `python scripts/check_plugin.py <plugin_dir>` catches load-breaking and silent bugs
     statically. Fix every ERROR. Read WARN and INFO and act on the real ones.
   - Run the unit tests: `tests/fake_astrbot.py` (copied by the scaffold, or copy it from
     `scripts/`) imports main.py without AstrBot installed, dispatches commands with
     AstrBot's real parsing rules, runs listeners, hooks and llm_tools, and records sends.
   - Live test in a real AstrBot. WebChat covers private-chat behaviour. Group behaviour
     (wake prefix, @, session scope) needs a real group. Say clearly what you could not
     test live.
5. **Deliver.** Give the files, how to install or reload them (copy into `data/plugins/`,
   then WebUI → 插件 → 重载), the config fields, what you tested, and what remains to test
   live.

## Mental model: what happens to a message

Waking check → whitelist → session on/off → rate limit → content safety → preprocess →
**plugin handlers (by priority)** → **default LLM reply** → decorate → send.

- **Woken** means the message has the wake prefix (default `/`, which is stripped from
  `message_str`), @-mentions the bot, replies to the bot, or is a private chat.
  **Commands only fire on woken messages**, so in a group a bare `签到` does not trigger
  `@filter.command("签到")`. Regex and message-type listeners fire on **every** message.
- The default LLM answers only if the message is woken, nothing has been sent yet, the
  event isn't stopped and `event.call_llm` is False. A command that replies therefore
  suppresses the LLM by itself. `event.stop_event()` stops everything downstream.
- Handlers are async generators (each `yield event.plain_result(...)` is sent immediately)
  or coroutines (`return event.plain_result(...)`). Where you can't yield (hooks, waiters,
  tasks), use `await event.send(...)`.

## Choosing a mechanism

| The user wants… | Use | Reference |
|---|---|---|
| `/cmd args` | `@filter.command("cmd", alias={...})` | handlers.md §3 |
| `/group sub args` | `@filter.command_group` + `@grp.command` | handlers.md §3 |
| keyword without a prefix, or watching all chat | `@filter.regex` / `@filter.event_message_type` (cheap, early return) | handlers.md §4 |
| admin-only | `@filter.permission_type(PermissionType.ADMIN)` (AstrBot admins, not group admins) | handlers.md §5 |
| block or gate users before other plugins | listener with high `priority` + `event.stop_event()` | handlers.md §7 |
| give the LLM a capability | `@filter.llm_tool` (docstring schema) or a `FunctionTool` class + `add_llm_tools` | llm.md §2 |
| change persona, add context, filter replies | `on_llm_request` / `on_llm_response` hooks | llm.md §4 |
| plugin-side LLM work (summarize, classify) | `context.llm_generate` / `tool_loop_agent` | llm.md §1, §3 |
| multi-turn game or wizard | `session_waiter` (+ a per-user `SessionFilter`) | lifecycle-config-storage.md §6 |
| timer, reminder, polling | task started in `initialize()`, cancelled in `terminate()`, then `context.send_message(umo, chain)` | lifecycle-config-storage.md §3, events-messages.md §4 |
| user-editable settings | `_conf_schema.json` → `config` | lifecycle-config-storage.md §4 |
| persist state | KV (`put_kv_data`) or files in `StarTools.get_data_dir()` | lifecycle-config-storage.md §5 |
| prefix, suffix or transform every reply | `on_decorating_result` | handlers.md §8 |
| platform-native API (recall, kick, member info) | `event.bot.api.call_action` (aiocqhttp) / `event.client` (Telegram) | events-messages.md §5 |
| a dashboard page | `views/<name>/index.html` + `context.register_web_api` | packaging-publish.md §5 |
| publish to the market | metadata.yaml + GitHub + cloud.astrbot.app/publish | packaging-publish.md §7 |

## Canonical shape

```python
import asyncio, contextlib
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.star.filter.command import GreedyStr


class WeatherPlugin(Star):                       # defined in main.py itself
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = StarTools.get_data_dir()  # data/plugin_data/<name>
        self._task = None

    async def initialize(self):                  # async setup; runs again after every reload
        self._task = asyncio.create_task(self._loop())

    async def terminate(self):                   # undo initialize(); never define __del__
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    @filter.command("天气", alias={"weather"})
    async def weather(self, event: AstrMessageEvent, city: GreedyStr):   # no default on GreedyStr
        """查询天气：/天气 城市"""
        if not city:
            yield event.plain_result("用法：/天气 城市")
            return
        try:
            text = await self._fetch(city)       # aiohttp/httpx, never requests
        except Exception:
            logger.exception("weather fetch failed")
            yield event.plain_result("天气服务暂时不可用")
            return
        yield event.plain_result(text)

    @filter.llm_tool(name="weather_lookup")
    async def weather_tool(self, event: AstrMessageEvent, city: str):
        """Look up current weather for a city. Use when the user asks about weather.

        Args:
            city(string): city name, e.g. 杭州
        """
        return await self._fetch(city)           # returned str goes back to the LLM
```

## Rules that bite (verified in source; each one causes a real failure)

Loading
1. The `Star` subclass must be **defined in main.py**. Registration is keyed by the defining
   module, so a class imported from `core.py` isn't picked up properly. Helpers go in
   other modules and are imported with **relative** imports (`from .core import X`).
2. metadata.yaml needs `name`, `desc`, `version` and `author` as **strings**. `version: 1.0`
   is a float and gets rejected, so quote it. `name` must be a valid Python identifier
   (no `-`). It and `author` form `plugin_id`, which is also the KV key, so never rename them.
3. `_conf_schema.json` types: `string text int float bool list object dict template_list file`.
   `integer` makes the config fail to load. `object` needs `items`.
4. An `@filter.llm_tool` docstring needs `Args:` with `name(type): desc`. A missing type
   raises at import and the plugin fails to load. `integer` is not a valid type here
   either; use `number` and cast.

Lifecycle
5. Async setup goes in `async def initialize()`, cleanup in `async def terminate()`.
   **Defining `__del__` makes AstrBot skip `terminate()`.** Anything not cleaned up runs
   twice after a hot reload.
6. `on_astrbot_loaded` fires only at core startup, not after a reload or install.
7. Never block the loop: no `time.sleep`, no `requests`, no heavy CPU work inline. Use
   `asyncio.sleep`, aiohttp/httpx and `asyncio.to_thread`.

Handlers
8. `x: str` takes **one word**. For free text, use `x: GreedyStr` as the last parameter
   **with no default**. A default makes AstrBot ignore the annotation.
9. Command names can't contain spaces, and handler function names must be unique per
   module (the registry key is `module_function`).
10. Hooks must be plain `async def` without `yield`; otherwise they are skipped and only
    an error is logged. Hooks can't share a function with command or listener filters.
11. `PermissionType.ADMIN` means AstrBot admins (`admins_id`), not QQ or Telegram group
    admins. Use the platform API for group roles.
12. `event.should_call_llm(True)` **blocks** the default LLM reply; the name reads backwards.
13. Priority: higher runs first, and the default is 0. A raised exception replies with an
    error and stops the event.

Messages, LLM, state
14. Active sends need a stored `unified_msg_origin` (`platform_id:MessageType:session_id`).
    `context.send_message` returns False when the platform instance is gone. QQ Official
    can't send actively.
15. `session_waiter` sessions are keyed by **UMO by default**, so in a group any member's
    next message feeds the waiter. Pass a `SessionFilter` that returns UMO plus sender ID
    for per-user flows.
16. Per-turn dynamic context (time, mood, retrieved memory) goes in
    `req.extra_user_content_parts` (with `.mark_as_temp()`, ≥4.24), **not**
    `req.system_prompt`. Changing the system prompt every turn breaks provider prompt
    caching, which AstrBot's docs put at roughly 7–20× the cost.
17. An `llm_tool` that `return`s a string feeds the LLM. One that `yield`s a result sends
    it to the user, and the LLM gets nothing.
18. Persistent data goes in `StarTools.get_data_dir()` (`data/plugin_data/<name>`), never
    the plugin folder, which updates wipe. Config values aren't type-coerced on schema
    changes, so validate them.
19. Platform-specific code must check `event.get_platform_name()` and degrade elsewhere.
    Declare `support_platforms` when needed.
20. Use `from astrbot.api import logger` or `self.logger`, not print. Never log secrets.
    Fields marked `secret` in the schema are only masked in the UI.

## Debugging by symptom

| Symptom | Likely cause |
|---|---|
| Plugin not in the list, or in 加载失败插件 | import error, a broken metadata.yaml or schema, `astrbot_version` mismatch, the class not defined in main.py, absolute sibling imports. Read the traceback in the WebUI log |
| Command works in private chat but not in the group | the group message lacks the wake prefix or @ (rule: commands need waking). Or the plugin is disabled for that session |
| `/echo hello world` gives only "hello" | `str` parameter; use `GreedyStr` with no default |
| The LLM also answers after my listener | the listener sent nothing. Call `event.stop_event()`, or `event.should_call_llm(True)` |
| Hook never runs | `yield` inside it, a sync `def`, a wrong parameter count, or combined with a command filter |
| Tool never called, or called without arguments | missing or incorrect `Args:` docstring, a vague description, a name collision with another plugin |
| Background job runs twice | started without being cancelled in `terminate()`, or `__del__` defined |
| Data lost after an update | written inside the plugin folder |
| A stranger's message hijacks my game | `session_waiter` with no per-user `SessionFilter` |
| Costs jumped after adding the plugin | dynamic text appended to `system_prompt` in `on_llm_request` |

## Reference files (read the one you need)

- `references/handlers.md`: imports, the pipeline and waking, commands and parameter
  parsing, listeners, permissions, buttons, priority, every hook signature, yield and
  return semantics.
- `references/events-messages.md`: AstrMessageEvent API, UMO format, message components,
  passive and active sending, t2i, QQ/OneBot and Telegram native APIs, the platform
  capability matrix.
- `references/llm.md`: `llm_generate`, `tool_loop_agent`, both tool styles and what their
  return values do, prompt-cache rules for `on_llm_request`, conversations, personas,
  embedding, TTS, STT, decision providers.
- `references/lifecycle-config-storage.md`: loading internals, lifecycle and hot reload,
  background tasks, the full `_conf_schema.json` spec and migration behaviour, KV and file
  storage, `session_waiter`, logging.
- `references/packaging-publish.md`: layout, metadata.yaml, requirements, i18n, bundled
  skills, WebUI views and web APIs, the dev loop, market publishing, the feature-to-version
  table.

## When the answer isn't here

Don't invent an API. Read the source the user actually runs:
`python -c "import astrbot, os; print(os.path.dirname(astrbot.__file__))"`, or the
`astrbot/` folder of their AstrBot checkout, or https://github.com/AstrBotDevs/AstrBot.
The useful files are `astrbot/api/` (the public surface),
`astrbot/core/star/register/star_handler.py` (decorators), `astrbot/core/star/context.py`
(Context), `astrbot/core/platform/astr_message_event.py` (events) and
`astrbot/core/pipeline/` (when things fire). Say which version you checked. Very new
features (interactive buttons, `context.decision`, `_special: umo/sender_id`) exist only
on recent builds, so feature-detect them with `hasattr` or ask.
