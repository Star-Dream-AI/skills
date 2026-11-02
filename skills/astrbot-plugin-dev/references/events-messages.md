# Events, sessions and sending messages

Verified against AstrBot v4.29.3 (`core/platform/astr_message_event.py`,
`core/message/components.py`, `core/message/message_event_result.py`,
`core/platform/message_session.py`, `core/star/context.py`).

## Contents
1. AstrMessageEvent: reading
2. unified_msg_origin (UMO) and sessions
3. Message components
4. Passive replies vs active sends
5. Platform-specific APIs (QQ / OneBot, Telegram)
6. Platform capability notes

---

## 1. AstrMessageEvent

| Member | Meaning |
|---|---|
| `event.message_str` / `get_message_str()` | plain text of the message. On woken messages the wake prefix is already stripped and the text is `.strip()`ed |
| `event.get_messages()` / `event.message_obj.message` | parsed chain, `list[BaseMessageComponent]` |
| `event.message_obj` | `AstrBotMessage`: `type`, `self_id`, `session_id`, `message_id`, `group_id`, `sender` (`MessageMember` with `user_id`, `nickname`), `message`, `message_str`, `raw_message` (the adapter's original object), `timestamp` |
| `get_sender_id()` / `get_sender_name()` | sender; IDs are strings |
| `get_group_id()` | `""` in private chats |
| `get_self_id()` | bot's own ID |
| `get_message_type()` | `MessageType.GROUP_MESSAGE` / `FRIEND_MESSAGE` / `OTHER_MESSAGE` |
| `is_private_chat()` | |
| `is_admin()` | AstrBot admin (`admins_id`), not a group admin |
| `is_wake_up()` / `is_at_or_wake_command` | woken (see handlers.md §2) |
| `get_platform_name()` | adapter **type**, e.g. `"aiocqhttp"`, `"telegram"` |
| `get_platform_id()` | adapter **instance** ID chosen by the user, e.g. `"my_qq"`. Use it with `context.get_platform_inst()` |
| `unified_msg_origin` | session key string, see §2 |
| `set_extra(k, v)` / `get_extra(k, default)` | per-event scratch space shared across plugins and stages. Prefix your keys |
| `get_result()` / `set_result()` / `clear_result()` | current outgoing result |
| `stop_event()` / `continue_event()` / `is_stopped()` | propagation |
| `should_call_llm(True)` | **blocks** the default LLM reply (the name reads backwards) |
| `request_llm(prompt=..., system_prompt=..., image_urls=..., contexts=..., conversation=..., tool_set=...)` | build a `ProviderRequest`; `yield` it from a handler to run AstrBot's own agent pipeline with persona and history |
| `await send(chain)` | send now |
| `await send_typing()` / `stop_typing()` | where the platform supports it |
| `await react(emoji)` | native reaction where overridden, otherwise sends the emoji as text |
| `await get_group(group_id=None)` | `Group` info, enriched by some adapters |
| `get_button_interaction()` | click payload for `button_action` handlers (very new) |

## 2. unified_msg_origin (UMO)

`str(MessageSession)` = `"{platform_id}:{message_type.value}:{session_id}"`, for example
`"my_qq:GroupMessage:123456789"` or `"tg_bot:FriendMessage:987654"`.

- `platform_id` is the user-chosen adapter instance ID, not the adapter type.
- `session_id` for groups is normally the group ID. If the admin enabled per-user session
  isolation (`unique_session`), it also contains the sender, so don't parse UMOs by
  splitting on assumptions. Use `MessageSession.from_str(umo)` (it splits on the first two
  `:`) and `event.get_group_id()` / `get_sender_id()` for identity.
- The UMO is the key for active sends, conversations, per-session config
  (`context.get_config(umo)`) and providers (`get_current_chat_provider_id(umo)`).
- Persist UMOs, not event objects. Events die with the message.

## 3. Message components (`import astrbot.api.message_components as Comp`)

Common, works on most platforms:
- `Comp.Plain(text)`. aiocqhttp strips leading and trailing whitespace on send; pad with
  `"​"` if it matters.
- `Comp.At(qq=user_id, name="")`, `Comp.AtAll()`. `qq` is the platform user ID on every
  platform, despite the name.
- `Comp.Image.fromURL(url)`, `.fromFileSystem(path)`, `.fromBase64(b64)`, `.fromBytes(b)`
- `Comp.Record(file=path, url=path)`, `Comp.Record.fromFileSystem(path)`, `.fromURL(url)`.
  Use wav for widest compatibility.
- `Comp.Video.fromFileSystem(path=...)`, `.fromURL(url=...)`
- `Comp.File(file=path_or_url, name="x.pdf")`. Not every platform supports it.
- `Comp.Reply(id=message_id)`. Quote a message. Incoming replies carry `sender_id`,
  `message_str` and `chain`.

OneBot v11 / aiocqhttp only:
- `Comp.Face(id=21)`, `Comp.Poke(...)`, `Comp.Node(uin=..., name=..., content=[...])`, and
  `Comp.Nodes([...])` for a merged-forward message.

Also exists: `Share`, `Music`, `Json`, `Forward`, `Unknown`, `ActionRow` / `Button` (very new).

Reading incoming media:
```python
for seg in event.get_messages():
    if isinstance(seg, Comp.Image):
        url = seg.url or seg.file          # adapters fill one or both
    elif isinstance(seg, Comp.At) and str(seg.qq) == str(event.get_self_id()):
        ...                                # the bot was mentioned
```

## 4. Passive vs active messages

**Passive** (reply in the handler):
```python
yield event.plain_result("hi")
yield event.chain_result([Comp.At(qq=event.get_sender_id()), Comp.Plain(" 你好")])
```

**Active** (later, from a task or timer, or into another chat):
```python
from astrbot.api.event import MessageChain

chain = MessageChain().message("提醒：喝水").file_image("/abs/path.png")   # also .at(name, qq), .url_image(url), .base64_image(b64)
ok: bool = await self.context.send_message(umo, chain)   # False if no platform instance matches
```

- `send_message` takes a UMO string or a `MessageSession`. It raises `ValueError` on a
  malformed UMO and returns `False` when the platform instance is gone (renamed or deleted
  adapter).
- QQ Official (`qq_official`) does not support active messages. WeCom and DingTalk are also
  restricted (see §6). Always handle `False`.
- `MessageChain([...components])` works too: `MessageChain(chain=[Comp.Plain("x")])`.
- `StarTools.send_message(session, chain)` is the same call through a classmethod facade,
  usable from helper modules without `self.context`.

**Text-to-image**:
```python
url = await self.text_to_image("long text", return_url=True)           # Star method
url = await self.html_render(JINJA_TMPL, {"items": [...]}, options={"full_page": True, "type": "png"})
yield event.image_result(url)
```
Rendering uses the configured t2i endpoint, which is a network service by default. Treat it
as possibly slow or failing and catch exceptions.

## 5. Platform-specific APIs

Narrow the event type before using platform clients, and keep the generic path working on
other platforms.

**QQ via OneBot v11 (aiocqhttp: NapCat, Lagrange…)**
```python
if event.get_platform_name() == "aiocqhttp":
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
    assert isinstance(event, AiocqhttpMessageEvent)
    client = event.bot                         # aiocqhttp CQHttp
    info = await client.api.call_action("get_group_member_info",
                                        group_id=int(event.get_group_id()),
                                        user_id=int(event.get_sender_id()))
    is_group_admin = info.get("role") in ("owner", "admin")
    await client.api.call_action("delete_msg", message_id=event.message_obj.message_id)
```
The action names come from the OneBot v11 / NapCat / Lagrange API docs. OneBot wants ints
for `group_id` / `user_id`.

**Telegram**
```python
if event.get_platform_name() == "telegram":
    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
    assert isinstance(event, TelegramPlatformEvent)
    bot = event.client                         # python-telegram-bot ExtBot
    member = await bot.get_chat_member(chat_id=event.get_group_id(), user_id=int(event.get_sender_id()))
```

**Getting a platform instance without an event** (for timers):
```python
platform = self.context.get_platform_inst(platform_id)        # ≥4.0; get_platform(type) is deprecated
for p in self.context.platform_manager.get_insts(): ...
```
For aiocqhttp, `platform.get_client().api.call_action(...)`.

## 6. Platform capability notes (from the official matrix; check the docs for changes)

| Platform | At | Image | Record | Video | Reply | Active send |
|---|---|---|---|---|---|---|
| QQ personal (aiocqhttp) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (+ Poke, Face, Node/Nodes) |
| Telegram | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| QQ Official | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ (platform forces @) |
| Lark/Feishu | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| WeCom | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| DingTalk | ❌ | ✅ (http URLs only) | ❌ | ❌ | ❌ | ❌ |

When a feature is platform-only, declare `support_platforms` in metadata.yaml and degrade
gracefully elsewhere.
