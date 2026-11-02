# Handlers, filters and hooks

Verified against AstrBot v4.29.3 source (`astrbot/core/star/register/star_handler.py`,
`astrbot/core/star/filter/*`, `astrbot/core/pipeline/*`). Version tags such as
"≥4.24" mark when a feature appeared; when the user's AstrBot is older, avoid it or
declare `astrbot_version` in metadata.yaml.

## Contents
1. Import surface
2. How a message reaches your handler (pipeline + wake rules)
3. Commands, parameters, groups, aliases
4. Listeners: message type, platform, regex, custom filters
5. Permissions
6. Buttons
7. Priority and propagation
8. Hooks (LLM, agent, tools, decorate, sent, lifecycle)
9. Return / yield semantics

---

## 1. Import surface

```python
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, StarTools, register   # register is optional/legacy
from astrbot.api import logger, AstrBotConfig, FunctionTool, ToolSet, llm_tool
import astrbot.api.message_components as Comp
from astrbot.api.provider import ProviderRequest, LLMResponse, Provider
from astrbot.api.platform import AstrBotMessage, MessageType, MessageMember, Group
from astrbot.api.util import session_waiter, SessionController, SessionWaiter
from astrbot.core.utils.session_waiter import SessionFilter     # not re-exported in api
from astrbot.core.star.filter.command import GreedyStr          # not re-exported in api
```

Always `from astrbot.api.event import filter`. It deliberately shadows Python's built-in
`filter()`, so don't call the builtin in that module. Use a list comprehension instead.

Everything exported by `astrbot.api.event.filter`:
`command, command_group, regex, event_message_type, platform_adapter_type, permission_type,
custom_filter, button_action, llm_tool, on_astrbot_loaded, on_platform_loaded,
on_plugin_loaded, on_plugin_unloaded, on_plugin_error, on_waiting_llm_request,
on_llm_request, on_llm_response, on_agent_begin, on_agent_done, on_using_llm_tool,
on_llm_tool_respond, on_decorating_result, after_message_sent`, plus the enums
`EventMessageType, PermissionType, PlatformAdapterType` and the classes `CustomFilter`,
`ButtonActionFilter`.

## 2. How a message reaches your handler

Pipeline order (`pipeline/stage_order.py`):
WakingCheck → WhitelistCheck → SessionStatusCheck → RateLimit → ContentSafetyCheck →
PreProcess → **Process** (plugins, then the default LLM) → ResultDecorate → Respond.

**Waking.** The waking stage decides whether a message counts as addressed to the bot
(`event.is_at_or_wake_command`):
- It starts with a configured `wake_prefix` (default `/`), and it is not a group message
  whose first segment @-mentions someone else. The prefix is then **stripped** from
  `event.message_str`.
- It @-mentions the bot, @-mentions everyone (unless `ignore_at_all`), or replies to a
  bot message.
- It is a private chat and `friend_message_needs_wake_prefix` is false, which is the default.

**Commands only match woken messages.** `CommandFilter.filter` returns False unless
`is_at_or_wake_command`. In a group, a bare "签到" does not trigger `@filter.command("签到")`.
The user needs to send "/签到" or "@bot 签到". Use `@filter.regex` or a listener for
prefix-less keywords.

**Listeners see every message.** `event_message_type`, `platform_adapter_type` and
`regex` don't check wake state. A listener with `EventMessageType.ALL` runs on every group
message, so keep it cheap and return early.

**After handlers, the default LLM call** runs only when all of these hold
(`process_stage/stage.py`):
nothing has been sent yet (`event._has_send_oper` false), the message is woken, the event is
not stopped, `event.call_llm` is false, and `provider_settings.enable` is true.
So a command that yields a reply suppresses the LLM automatically, and a listener that stays
silent lets the LLM answer as usual.

**Watch out for `should_call_llm`.** `event.should_call_llm(True)` sets `call_llm=True`,
which **blocks** the default LLM call. The name reads backwards.
To block the LLM, call `event.should_call_llm(True)`, or `event.stop_event()` to block
everything downstream.

**Enabled-plugin sets and session toggles.** Admins can disable a plugin per session or per
config (`plugin_set`). Your handler then simply doesn't run, with no error.

## 3. Commands

```python
@filter.command("add", alias={"加法", "plus"}, priority=0, desc="optional override of docstring")
async def add(self, event: AstrMessageEvent, a: int, b: int = 0):
    """Add two numbers"""   # the docstring is shown in the WebUI and help
    yield event.plain_result(f"{a + b}")
```

Parameter parsing (`filter/command.py`): after the command name, the rest is split on
whitespace and mapped **one token per parameter**, starting from the third parameter
(after `self` and `event`).

| Annotation / default | Behaviour |
|---|---|
| `x: str` | gets one token only: `/echo hello world` gives `x="hello"` |
| `x: GreedyStr` | gets all remaining text joined by spaces (`""` if none); must be the last parameter and must have **no default value** |
| `x: int` / `float` | converted, and a bad value replies "参数 x 类型错误" and stops the event |
| `x: bool` | true/yes/1 or false/no/0, anything else is an error |
| `x: int = 5` | optional; type taken from the default value |
| `x = None` | digits become int, otherwise str |
| `x: int \| None` | converted with the non-None type |
| missing required | replies "必要参数缺失。该指令完整参数: ..." and stops |

When a parameter has a default, AstrBot ignores its annotation and converts by the
default's type (`handler_params[k] = default`). So `x: GreedyStr = ""` behaves like a
one-word `str`, and `x: int = None` passes the raw value through the `None` rule.
Extra tokens beyond the declared parameters are silently ignored.
Repeated spaces are collapsed before splitting, so `GreedyStr` can't preserve
newlines or multiple spaces. For verbatim text, read `event.message_str` and strip the
command name yourself.
For free text (a question, a prompt, a URL with spaces), use `GreedyStr`, or parse
`event.message_str` yourself.

```python
from astrbot.core.star.filter.command import GreedyStr

@filter.command("ask")
async def ask(self, event: AstrMessageEvent, question: GreedyStr):
    ...
```

Command names can't contain spaces. Nest commands with groups:

```python
@filter.command_group("math", alias={"数学"})
def math(self):            # body is never called; keep it `pass`
    pass

@math.command("add")
async def math_add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(str(a + b))        # /math add 1 2

@math.group("calc")        # subgroup: .group, NOT .command_group
def calc(self):
    pass

@calc.command("sub")
async def calc_sub(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(str(a - b))        # /math calc sub 3 1
```

Sending the bare group name (`/math`) replies with the command tree.
Handler function names must be unique within the module. The registry key is
`f"{module}_{function_name}"`, so two handlers both named `add` collide. Name them
`math_add` and `calc_add`.

## 4. Listeners

```python
@filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)   # PRIVATE_MESSAGE, OTHER_MESSAGE, ALL
async def on_group(self, event: AstrMessageEvent): ...

@filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP | filter.PlatformAdapterType.TELEGRAM)
async def on_qq_tg(self, event: AstrMessageEvent): ...
# also accepts the adapter-name string: @filter.platform_adapter_type("telegram")

@filter.regex(r"^(早安|早上好)")       # uses re.search on message_str, ignores wake state
async def morning(self, event: AstrMessageEvent): ...
```

`PlatformAdapterType` members: AIOCQHTTP, QQOFFICIAL, QQOFFICIAL_WEBHOOK, TELEGRAM, WECOM,
WECOM_AI_BOT, LARK, DINGTALK, DISCORD, SLACK, KOOK, VOCECHAT, WEIXIN_OFFICIAL_ACCOUNT,
SATORI, MISSKEY, LINE, MATRIX, WEIXIN_OC, MATTERMOST, WEBCHAT, ALL.
The adapter-name keys used by `event.get_platform_name()` and `support_platforms` are
aiocqhttp, qq_official, qq_official_webhook, telegram, wecom, wecom_ai_bot, lark, dingtalk,
discord, slack, kook, vocechat, weixin_official_account, satori, misskey, line, matrix,
weixin_oc, mattermost, webchat.

Stacked filters are combined with **AND**. For OR across your own conditions, write a
custom filter:

```python
from astrbot.api.event.filter import CustomFilter
from astrbot.core.config import AstrBotConfig

class IsVip(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return event.get_sender_id() in VIP_IDS

@filter.custom_filter(IsVip)              # pass the class; `IsA | IsB` / `IsA & IsB` also work
@filter.command("vip")
async def vip(self, event: AstrMessageEvent): ...
```

If any filter raises, AstrBot replies "插件 <name>: <error>" to the chat and stops the event.

## 5. Permissions

```python
@filter.permission_type(filter.PermissionType.ADMIN)          # raise_error=True by default
@filter.command("reload_cache")
async def reload_cache(self, event: AstrMessageEvent): ...
```

- `ADMIN` means an **AstrBot admin**: the sender ID is in the global `admins_id` config,
  which is what `event.is_admin()` checks. It is **not** a QQ or Telegram group admin. To
  check platform group roles, call the platform API (see `events-messages.md`).
- `GROUP_ADMIN`: in groups it requires an AstrBot admin; in private chats it lets anyone through.
- `SHARED_GROUP_ADMIN`: in groups it allows AstrBot admins, or anyone when the session is
  isolated per user.
- `MEMBER`: everyone.
- On denial with `raise_error=True`, AstrBot replies "您(ID: …)的权限不足以使用此指令…" (if
  `no_permission_reply` is on) and stops. With `raise_error=False`, your handler is skipped
  silently.
- WebUI admins can override a command's permission (`alter_cmd`). Don't rely on the decorator
  as the only security boundary for destructive actions; also check `event.is_admin()`
  inside the handler.

## 6. Buttons (very new)

These are on AstrBot master after v4.29.3, and no release changelog mentions them as of
2026-10-31. Before relying on them, confirm the user's install has them
(`hasattr(Comp, "ActionRow")` and `hasattr(filter, "button_action")`). If you can't confirm,
offer a text-command fallback.

```python
yield event.chain_result([
    Comp.Plain("请选择："),
    Comp.ActionRow(buttons=[
        Comp.Button(id="myplugin:ok", label="确认",
                    action=Comp.Button.CallbackAction(data={"item": 42}),
                    style=Comp.Button.Style.PRIMARY),
        Comp.Button(id="myplugin:docs", label="文档",
                    action=Comp.Button.UrlAction(url="https://docs.astrbot.app")),
    ], action_timeout=60, fallback_text="本平台不支持按钮，请发送 /ok"),
])

@filter.button_action("myplugin:ok")      # no ID: matches every button
async def on_ok(self, event: AstrMessageEvent):
    it = event.get_button_interaction()
    if it is None:
        return
    yield event.plain_result(f"ok {it.data['item']}")
```

`CallbackAction.data` must be JSON-serializable. Prefix button IDs with your plugin name.
Button clicks only reach handlers that have a `button_action` filter.
OneBot v11 (aiocqhttp), Misskey, WeChat Official Account and weixin_oc fall back to text, so
set `fallback_text`.

## 7. Priority and propagation

- `priority=` is accepted by every decorator. The default is 0, and **higher runs first**:
  the registry sorts by `-priority` across all plugins. Gatekeeping plugins (blacklists,
  join gates, rate limits) use large values such as 100000.
- `event.stop_event()` stops later handlers (in all plugins), the default LLM call and
  later hooks. Already-yielded results are still sent. `event.continue_event()` undoes it.
- When a handler finishes without stopping, `event.clear_result()` runs before the next
  handler, so each handler's yield is sent independently.
- If a handler raises, AstrBot logs it, fires `on_plugin_error`, replies
  ":( 在调用插件 … 时出现异常：…" to woken messages, and **stops the event**.

## 8. Hooks

Hooks must be plain `async def` coroutines. AstrBot asserts
`inspect.iscoroutinefunction`, so a hook containing `yield` fails that assertion. The error
is only logged and the hook never runs. **Never `yield` in a hook**; use
`await event.send(...)`. Hooks can't be combined with command, listener or permission
filters on the same function.

| Decorator | Signature (after `self`) | When / notes |
|---|---|---|
| `on_astrbot_loaded()` | `()` | once, at core startup, **not** after a hot reload or a WebUI install, so put per-plugin setup in `initialize()` instead |
| `on_platform_loaded()` | `()` | after platform adapters start |
| `on_plugin_loaded()` | `(metadata: StarMetadata)` | whenever any plugin finishes loading |
| `on_plugin_unloaded()` | `(metadata: StarMetadata)` | whenever any plugin is terminated |
| `on_plugin_error()` | `(event, plugin_name, handler_name, error, traceback_text)` | a handler raised; `event.stop_event()` here suppresses the default error reply |
| `on_waiting_llm_request()` | `(event)` | about to queue for the session LLM lock; good for "思考中…" |
| `on_llm_request()` | `(event, req: ProviderRequest)` | mutate `req` before the call; `event.stop_event()` cancels the LLM call |
| `on_llm_response()` | `(event, resp: LLMResponse)` | after the final LLM response of an agent run (fires once per run, not per tool step) |
| `on_agent_begin()` (>4.23.1) | `(event, run_context: ContextWrapper[AstrAgentContext])` | |
| `on_using_llm_tool()` (>4.23.1) | `(event, tool: FunctionTool, tool_args: dict \| None)` | |
| `on_llm_tool_respond()` (>4.23.1) | `(event, tool, tool_args, tool_result: CallToolResult \| None)` | |
| `on_agent_done()` (>4.23.1) | `(event, run_context, resp: LLMResponse)` | after `on_llm_response` |
| `on_decorating_result()` | `(event)` | edit `event.get_result().chain` in place before sending (prefix, TTS, t2i). `get_result()` can be None, so check it |
| `after_message_sent()` | `(event)` | after the respond stage sent something |

Imports used in hook signatures:
```python
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.agent.tool import FunctionTool
from mcp.types import CallToolResult
```

`on_llm_request` is the main hook for prompt work. The cache-friendly rules are in
`llm.md` §4.

## 9. Return / yield semantics for message handlers

`call_handler` (`pipeline/context_utils.py`) accepts both forms:

- **Async generator**: each `yield <MessageEventResult>` is sent right away, before the
  handler resumes (the onion model). A bare `yield` passes control without sending.
- **Coroutine**: `return event.plain_result("...")` sends once. Returning None sends nothing.
- Results: `event.plain_result(text)`, `event.image_result(url_or_path)` (it checks
  `startswith("http")`), `event.chain_result([...])`, `event.make_result().message(..).url_image(..)`.
- Inside callbacks you can't yield from (session waiters, tasks, hooks), use
  `await event.send(MessageChain([...]))` or `await event.send(event.plain_result("..."))`.
  A `MessageEventResult` is a `MessageChain`.
- If the handler's arguments don't match the parsed command parameters, AstrBot logs
  "Plugin Handler arguments do not match its definition." and the handler silently does
  nothing.
