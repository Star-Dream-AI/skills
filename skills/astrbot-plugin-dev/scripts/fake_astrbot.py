"""A small, faithful-enough fake of the AstrBot plugin API for unit tests.

Copy this file into your plugin's tests/ folder. It lets you import and drive a
plugin's main.py without installing AstrBot (which needs Python >= 3.12 and many
dependencies). Command parsing mirrors AstrBot v4.29.3 (CommandFilter): one
whitespace token per parameter, GreedyStr takes the rest, int/float/bool are
converted. llm_tool docstrings are validated the same way AstrBot does, so a
broken tool schema fails your test instead of failing in production.

What it does NOT emulate: the wake prefix, permissions, priorities across
plugins, the real LLM pipeline, platform adapters. Test those in a real AstrBot
(WebChat for private chat, a real group for group behaviour).

Usage (pytest or unittest):

    import asyncio, fake_astrbot as fa
    plugin = fa.load_plugin(PLUGIN_DIR, config={"greeting": "hi"})
    asyncio.run(plugin.initialize())
    texts = asyncio.run(fa.run_command(plugin, "hello 张三"))
    assert texts == ["hi, 张三"]
    ev = fa.FakeEvent("早上好", group_id="123")
    texts = asyncio.run(fa.run_listeners(plugin, ev))
"""

from __future__ import annotations

import enum
import importlib.util
import inspect
import json
import logging
import re
import sys
import tempfile
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------ registry
REGISTRY: dict[str, Any] = {}


def reset_registry() -> None:
    REGISTRY.clear()
    REGISTRY.update(commands=[], listeners=[], hooks={}, llm_tools={}, buttons=[])


reset_registry()


# ---------------------------------------------------------------- components
class ComponentType(str, enum.Enum):
    Plain = "Plain"
    At = "At"
    AtAll = "AtAll"
    Image = "Image"
    Record = "Record"
    Video = "Video"
    File = "File"
    Reply = "Reply"
    Face = "Face"
    Poke = "Poke"
    Node = "Node"
    Nodes = "Nodes"


class BaseMessageComponent:
    type: ComponentType

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __repr__(self):
        fields = {k: v for k, v in self.__dict__.items()}
        return f"{type(self).__name__}({fields})"

    def __eq__(self, other):
        return type(self) is type(other) and self.__dict__ == other.__dict__


class Plain(BaseMessageComponent):
    type = ComponentType.Plain

    def __init__(self, text: str = "", **kw):
        super().__init__(text=text, **kw)


class At(BaseMessageComponent):
    type = ComponentType.At

    def __init__(self, qq="", name="", **kw):
        super().__init__(qq=qq, name=name, **kw)


class AtAll(At):
    type = ComponentType.AtAll

    def __init__(self, **kw):
        super().__init__(qq="all", **kw)


class _Media(BaseMessageComponent):
    def __init__(self, file: str | None = "", url: str = "", **kw):
        super().__init__(file=file, url=url, **kw)

    @classmethod
    def fromURL(cls, url: str, **_):
        return cls(file=url, url=url)

    @classmethod
    def fromFileSystem(cls, path, **_):
        return cls(file=f"file:///{path}", path=str(path))

    @classmethod
    def fromBase64(cls, b64: str, **_):
        return cls(file=f"base64://{b64}")

    @classmethod
    def fromBytes(cls, data: bytes):
        import base64

        return cls(file="base64://" + base64.b64encode(data).decode())


class Image(_Media):
    type = ComponentType.Image


class Record(_Media):
    type = ComponentType.Record


class Video(_Media):
    type = ComponentType.Video

    @classmethod
    def fromFileSystem(cls, path, **_):
        return cls(file=f"file:///{path}", path=str(path))


class File(BaseMessageComponent):
    type = ComponentType.File

    def __init__(self, name: str = "", file: str = "", url: str = "", **kw):
        super().__init__(name=name, file=file, url=url, **kw)


class Reply(BaseMessageComponent):
    type = ComponentType.Reply

    def __init__(self, id="", sender_id="", message_str="", chain=None, **kw):
        super().__init__(id=id, sender_id=sender_id, message_str=message_str, chain=chain or [], **kw)


class Face(BaseMessageComponent):
    type = ComponentType.Face


class Poke(BaseMessageComponent):
    type = ComponentType.Poke


class Node(BaseMessageComponent):
    type = ComponentType.Node


class Nodes(BaseMessageComponent):
    type = ComponentType.Nodes


# ------------------------------------------------------------- message chain
class MessageChain:
    def __init__(self, chain: list | None = None, **_):
        self.chain: list = list(chain or [])
        self._stopped = False

    def message(self, text: str):
        self.chain.append(Plain(text))
        return self

    def at(self, name: str, qq):
        self.chain.append(At(qq=qq, name=name))
        return self

    def at_all(self):
        self.chain.append(AtAll())
        return self

    def url_image(self, url: str):
        self.chain.append(Image.fromURL(url))
        return self

    def file_image(self, path: str):
        self.chain.append(Image.fromFileSystem(path))
        return self

    def base64_image(self, b64: str):
        self.chain.append(Image.fromBase64(b64))
        return self

    def use_t2i(self, _flag: bool):
        return self

    def use_markdown(self, _flag: bool | None = True):
        return self

    def get_plain_text(self, with_other_comps_mark: bool = False) -> str:
        parts = []
        for c in self.chain:
            if isinstance(c, Plain):
                parts.append(c.text)
            elif with_other_comps_mark:
                parts.append(f"[{c.type.value}]")
        return " ".join(parts) if with_other_comps_mark else "".join(parts)

    def __repr__(self):
        return f"{type(self).__name__}({self.chain!r})"


class MessageEventResult(MessageChain):
    def stop_event(self):
        self._stopped = True
        return self

    def continue_event(self):
        self._stopped = False
        return self

    def is_stopped(self) -> bool:
        return self._stopped


CommandResult = MessageEventResult


class MessageType(enum.Enum):
    GROUP_MESSAGE = "GroupMessage"
    FRIEND_MESSAGE = "FriendMessage"
    OTHER_MESSAGE = "OtherMessage"


# --------------------------------------------------------------------- event
class FakeEvent:
    """Mimics AstrMessageEvent. `sent` collects everything passed to send()."""

    def __init__(self, text: str = "", *, sender_id: str = "10001", sender_name: str = "tester",
                 group_id: str = "", platform: str = "aiocqhttp", platform_id: str = "test",
                 self_id: str = "bot", admin: bool = False, components: list | None = None,
                 woken: bool = True, message_id: str = "1"):
        self.message_str = text.strip()
        self._components = components if components is not None else ([Plain(text)] if text else [])
        self._sender_id, self._sender_name, self._group_id = str(sender_id), sender_name, str(group_id)
        self._platform, self._platform_id, self._self_id = platform, platform_id, self_id
        self.role = "admin" if admin else "member"
        self.is_wake = self.is_at_or_wake_command = woken
        self.call_llm = False
        self._result: MessageEventResult | None = None
        self._stopped = False
        self._extras: dict = {}
        self.sent: list[MessageChain] = []
        self.message_obj = types.SimpleNamespace(
            message=self._components, message_str=self.message_str, message_id=message_id,
            group_id=self._group_id, self_id=self_id, raw_message=None,
            sender=types.SimpleNamespace(user_id=self._sender_id, nickname=sender_name),
            type=self.get_message_type(), session_id=self._group_id or self._sender_id)

    # identity
    @property
    def unified_msg_origin(self) -> str:
        return f"{self._platform_id}:{self.get_message_type().value}:{self._group_id or self._sender_id}"

    def get_platform_name(self): return self._platform
    def get_platform_id(self): return self._platform_id
    def get_message_str(self): return self.message_str
    def get_messages(self): return self._components
    def get_message_type(self):
        return MessageType.GROUP_MESSAGE if self._group_id else MessageType.FRIEND_MESSAGE
    def get_group_id(self): return self._group_id
    def get_self_id(self): return self._self_id
    def get_sender_id(self): return self._sender_id
    def get_sender_name(self): return self._sender_name
    def get_session_id(self): return self._group_id or self._sender_id
    def is_private_chat(self): return not self._group_id
    def is_admin(self): return self.role == "admin"
    def is_wake_up(self): return self.is_wake

    # extras
    def set_extra(self, k, v): self._extras[k] = v
    def get_extra(self, k=None, default=None): return self._extras if k is None else self._extras.get(k, default)
    def clear_extra(self): self._extras.clear()

    # result / propagation
    def set_result(self, result):
        if isinstance(result, str):
            result = MessageEventResult().message(result)
        self._result = result
    def get_result(self): return self._result
    def clear_result(self): self._result = None
    def stop_event(self): self._stopped = True
    def continue_event(self): self._stopped = False
    def is_stopped(self): return self._stopped or bool(self._result and self._result.is_stopped())
    def should_call_llm(self, call_llm: bool): self.call_llm = call_llm  # True BLOCKS the default LLM

    def make_result(self): return MessageEventResult()
    def plain_result(self, text: str): return MessageEventResult().message(text)
    def image_result(self, url_or_path: str):
        r = MessageEventResult()
        return r.url_image(url_or_path) if url_or_path.startswith("http") else r.file_image(url_or_path)
    def chain_result(self, chain: list):
        r = MessageEventResult()
        r.chain = chain
        return r

    def request_llm(self, prompt: str, **kw):
        return ProviderRequest(prompt=prompt, **{k: v for k, v in kw.items() if k in ProviderRequest.__dataclass_fields__})

    async def send(self, message: MessageChain):
        self.sent.append(message)

    async def send_typing(self): ...
    async def stop_typing(self): ...
    async def react(self, emoji: str): self.sent.append(MessageChain([Plain(emoji)]))


AstrMessageEvent = FakeEvent


# ------------------------------------------------------------------ provider
@dataclass
class ProviderRequest:
    prompt: str | None = None
    session_id: str | None = ""
    image_urls: list = field(default_factory=list)
    audio_urls: list = field(default_factory=list)
    extra_user_content_parts: list = field(default_factory=list)
    func_tool: Any = None
    contexts: list = field(default_factory=list)
    system_prompt: str = ""
    conversation: Any = None
    tool_calls_result: Any = None
    model: str | None = None


class LLMResponse:
    def __init__(self, role: str = "assistant", completion_text: str = "", **kw):
        self.role, self.completion_text = role, completion_text
        self.result_chain = None
        self.tools_call_args, self.tools_call_name, self.tools_call_ids = [], [], []
        for k, v in kw.items():
            setattr(self, k, v)


class TextPart:
    def __init__(self, text: str = "", **_):
        self.text = text
        self.temp = False

    def mark_as_temp(self):
        self.temp = True
        return self


# -------------------------------------------------------------------- config
class AstrBotConfig(dict):
    saved = 0

    def save_config(self, replace_config: dict | None = None, **_):
        if replace_config:
            self.update(replace_config)
        self.saved += 1

    async def save_config_async(self, replace_config: dict | None = None, **_):
        self.save_config(replace_config)
        return True

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            return None


def config_from_schema(schema: dict, overrides: dict | None = None) -> AstrBotConfig:
    defaults = {"int": 0, "float": 0.0, "bool": False, "string": "", "text": "", "list": [],
                "file": [], "object": {}, "dict": {}, "template_list": []}

    def build(s: dict) -> dict:
        out = {}
        for k, v in s.items():
            if v["type"] not in defaults:
                raise TypeError(f"unsupported config type {v['type']}")
            out[k] = build(v["items"]) if v["type"] == "object" else v.get("default", defaults[v["type"]])
        return out

    conf = AstrBotConfig(build(schema))
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(conf.get(k), dict):
            conf[k].update(v)
        else:
            conf[k] = v
    return conf


# ------------------------------------------------------------------- context
class FakeContext:
    """Records active sends and tools. Set `llm_reply` to control llm_generate()."""

    def __init__(self, llm_reply: Any = "ok"):
        self.sent: list[tuple[str, MessageChain]] = []
        self.tools: list = []
        self.llm_reply = llm_reply  # str, or callable(prompt=..., **kw) -> str
        self.llm_calls: list[dict] = []
        self.global_config = {"wake_prefix": ["/"], "admins_id": [], "provider_settings": {"enable": True}}

    async def send_message(self, session, message_chain) -> bool:
        if isinstance(session, str) and session.count(":") < 2:
            raise ValueError("不合法的 session 字符串")
        self.sent.append((str(session), message_chain))
        return True

    async def get_current_chat_provider_id(self, umo: str) -> str:
        return "fake_provider"

    async def llm_generate(self, *, chat_provider_id: str, prompt: str | None = None, **kw) -> LLMResponse:
        self.llm_calls.append({"provider": chat_provider_id, "prompt": prompt, **kw})
        text = self.llm_reply(prompt=prompt, **kw) if callable(self.llm_reply) else self.llm_reply
        return LLMResponse("assistant", text)

    async def tool_loop_agent(self, *, event, chat_provider_id: str, prompt: str | None = None, **kw):
        return await self.llm_generate(chat_provider_id=chat_provider_id, prompt=prompt, **kw)

    def add_llm_tools(self, *tools):
        self.tools.extend(tools)

    def get_config(self, umo: str | None = None):
        return self.global_config

    def register_web_api(self, route, handler, methods, desc):
        REGISTRY.setdefault("web_apis", []).append((route, handler, methods, desc))

    def get_platform_inst(self, platform_id):
        return None

    def get_all_providers(self): return []
    def get_all_embedding_providers(self): return []


# ---------------------------------------------------------------------- star
class Star:
    name: str = "astrbot_plugin_under_test"
    author: str = "tester"
    plugin_id: str = "tester/astrbot_plugin_under_test"

    def __init__(self, context, config: dict | None = None):
        self.context = context
        self.logger = logging.getLogger(f"astrbot.plugin.{self.name}")
        self._kv: dict = {}

    async def initialize(self): ...
    async def terminate(self): ...

    async def put_kv_data(self, key, value): self._kv[key] = value
    async def get_kv_data(self, key, default): return self._kv.get(key, default)
    async def delete_kv_data(self, key): self._kv.pop(key, None)

    async def text_to_image(self, text: str, return_url: bool = True, **_):
        return "https://t2i.invalid/fake.png"

    async def html_render(self, tmpl: str, data: dict, return_url: bool = True, **_):
        return "https://t2i.invalid/fake.png"


Context = FakeContext
_DATA_ROOT = Path(tempfile.mkdtemp(prefix="astrbot_fake_data_"))


class StarTools:
    @classmethod
    def get_data_dir(cls, plugin_name: str | None = None) -> Path:
        p = _DATA_ROOT / (plugin_name or Star.name)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    async def send_message(cls, session, chain):
        return await _CURRENT["context"].send_message(session, chain)


_CURRENT: dict = {}


def register(*_a, **_k):
    return lambda cls: cls


# ------------------------------------------------------------------- filters
class GreedyStr(str):
    """Marks a final command parameter that receives all remaining text."""


class EventMessageType(enum.Flag):
    GROUP_MESSAGE = enum.auto()
    PRIVATE_MESSAGE = enum.auto()
    OTHER_MESSAGE = enum.auto()
    ALL = GROUP_MESSAGE | PRIVATE_MESSAGE | OTHER_MESSAGE


class PermissionType(enum.Flag):
    ADMIN = enum.auto()
    MEMBER = enum.auto()
    GROUP_ADMIN = enum.auto()
    SHARED_GROUP_ADMIN = enum.auto()


class PlatformAdapterType(enum.Flag):
    AIOCQHTTP = enum.auto(); QQOFFICIAL = enum.auto(); QQOFFICIAL_WEBHOOK = enum.auto()
    TELEGRAM = enum.auto(); WECOM = enum.auto(); WECOM_AI_BOT = enum.auto(); LARK = enum.auto()
    DINGTALK = enum.auto(); DISCORD = enum.auto(); SLACK = enum.auto(); KOOK = enum.auto()
    VOCECHAT = enum.auto(); WEIXIN_OFFICIAL_ACCOUNT = enum.auto(); SATORI = enum.auto()
    MISSKEY = enum.auto(); LINE = enum.auto(); MATRIX = enum.auto(); WEIXIN_OC = enum.auto()
    MATTERMOST = enum.auto(); WEBCHAT = enum.auto(); ALL = enum.auto()


class CustomFilter:
    def __init__(self, raise_error: bool = True, **_):
        self.raise_error = raise_error

    def filter(self, event, cfg) -> bool:
        raise NotImplementedError


def _meta(fn) -> dict:
    fn = getattr(fn, "__func__", fn)
    if not hasattr(fn, "_fa"):
        fn._fa = {"filters": [], "perm": None}
    return fn._fa


class _Group:
    def __init__(self, names: list[str]):
        self.names = names

    def command(self, name: str, alias: set | None = None, **kw):
        full = [f"{p} {n}" for p in self.names for n in [name, *(alias or ())]]
        return _register_command(full, kw, leaf=name)

    def group(self, name: str, alias: set | None = None, **kw):
        full = [f"{p} {n}" for p in self.names for n in [name, *(alias or ())]]

        def deco(_fn):
            return _Group(full)
        return deco


def _register_command(names: list[str], kw: dict, leaf: str | None = None):
    if leaf is not None and (" " in leaf.strip() or not leaf.strip()):
        raise ValueError(f"command name {leaf!r} must be one word; use a command_group")

    def deco(fn):
        if not inspect.iscoroutinefunction(fn) and not inspect.isasyncgenfunction(fn):
            raise TypeError(f"command handler {fn.__name__} must be async def")
        REGISTRY["commands"].append({"names": names, "fn": fn, "priority": kw.get("priority", 0)})
        _meta(fn)["command"] = names
        return fn
    return deco


def _listener(kind: str, value):
    def deco(fn):
        if not inspect.iscoroutinefunction(fn) and not inspect.isasyncgenfunction(fn):
            raise TypeError(f"handler {fn.__name__} must be async def")
        m = _meta(fn)
        m["filters"].append((kind, value))
        if "listener_registered" not in m:
            REGISTRY["listeners"].append(fn)  # skipped at run time if it is also a command
            m["listener_registered"] = True
        return fn
    return deco


def _hook(name: str):
    def factory(**_kw):
        def deco(fn):
            if not inspect.iscoroutinefunction(fn):
                raise TypeError(f"hook {name} ({fn.__name__}) must be a plain 'async def' without yield; "
                                "AstrBot asserts iscoroutinefunction and silently skips it otherwise")
            REGISTRY["hooks"].setdefault(name, []).append(fn)
            return fn
        return deco
    return factory


_SUPPORTED = {"string", "number", "object", "array", "boolean"}
_PY2JSON = {"int": "number", "float": "number", "bool": "boolean", "str": "string", "dict": "object",
            "list": "array", "tuple": "array", "set": "array"}


def parse_tool_docstring(fn) -> tuple[str, list[dict]]:
    """Replicates AstrBot's docstring → tool schema conversion (raises like AstrBot)."""
    doc = inspect.getdoc(fn) or ""
    desc_lines, args, in_args = [], [], False
    for line in doc.splitlines():
        s = line.strip()
        if re.match(r"^(Args|Arguments|Parameters)\s*:\s*$", s):
            in_args = True
            continue
        if in_args:
            if re.match(r"^(Returns?|Raises|Yields|Examples?)\s*:", s):
                break
            m = re.match(r"^(\w+)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$", s)
            if m:
                name, typ, d = m.group(1), (m.group(2) or "").strip(), m.group(3)
                if not typ:
                    raise ValueError(f"LLM 函数工具 {fn.__name__} 的参数 {name} 缺少类型注释。")
                mm = re.match(r"(\w+)\[(\w+)\]", typ)
                main_t, sub_t = (mm.group(1), mm.group(2)) if mm else (typ, None)
                main_t = _PY2JSON.get(main_t, main_t)
                sub_t = _PY2JSON.get(sub_t, sub_t) if sub_t else None
                if main_t not in _SUPPORTED or (sub_t and sub_t not in _SUPPORTED):
                    raise ValueError(f"LLM 函数工具 {fn.__name__} 不支持的参数类型：{typ}")
                spec = {"type": main_t, "name": name, "description": d}
                if sub_t and main_t == "array":
                    spec["items"] = {"type": sub_t}
                args.append(spec)
        elif s:
            desc_lines.append(s)
    return " ".join(desc_lines), args


def llm_tool(name: str | None = None, **_kw):
    def deco(fn):
        desc, args = parse_tool_docstring(fn)
        REGISTRY["llm_tools"][name or fn.__name__] = {"fn": fn, "description": desc, "args": args}
        return fn
    return deco


filter = types.SimpleNamespace(  # noqa: A001 - mirrors astrbot.api.event.filter
    command=lambda command_name, alias=None, **kw: _register_command([command_name, *(alias or ())], kw, leaf=command_name),
    command_group=lambda name, alias=None, **kw: (lambda _fn: _Group([name, *(alias or ())])),
    regex=lambda pattern, **kw: _listener("regex", re.compile(pattern)),
    event_message_type=lambda t, **kw: _listener("type", t),
    platform_adapter_type=lambda t, **kw: _listener("platform", t),
    permission_type=lambda t, raise_error=True, **kw: (lambda fn: (_meta(fn).__setitem__("perm", (t, raise_error)), fn)[1]),
    custom_filter=lambda f, *a, **kw: _listener("custom", f),
    button_action=lambda action_id=None, **kw: _listener("button", action_id),
    llm_tool=llm_tool,
    EventMessageType=EventMessageType, PermissionType=PermissionType,
    PlatformAdapterType=PlatformAdapterType, CustomFilter=CustomFilter,
    **{h: _hook(h) for h in (
        "on_astrbot_loaded", "on_platform_loaded", "on_plugin_loaded", "on_plugin_unloaded",
        "on_plugin_error", "on_waiting_llm_request", "on_llm_request", "on_llm_response",
        "on_agent_begin", "on_agent_done", "on_using_llm_tool", "on_llm_tool_respond",
        "on_decorating_result", "after_message_sent")},
)


# ----------------------------------------------------------- session waiter
class SessionController:
    def __init__(self):
        self.stopped = False
        self.timeout = None

    def stop(self, error: Exception | None = None):
        self.stopped = True

    def keep(self, timeout: float = 0, reset_timeout=False):
        self.timeout = timeout

    def get_history_chains(self):
        return []


class SessionFilter:
    def filter(self, event) -> str:
        return event.unified_msg_origin


def session_waiter(timeout: int = 30, record_history_chains: bool = False):
    """In tests: `await waiter(event)` consumes queued replies from `event.replies`
    (a list of FakeEvent) until controller.stop(); raises TimeoutError when they run out."""
    def deco(fn):
        async def wrapper(event, session_filter=None):
            controller = SessionController()
            for reply in list(getattr(event, "replies", [])):
                await fn(controller, reply)
                event.sent.extend(reply.sent)
                if controller.stopped:
                    return
            raise TimeoutError
        return wrapper
    return deco


# ----------------------------------------------------------------- installer
def install() -> None:
    """Register the fake `astrbot` modules in sys.modules (idempotent)."""
    if "astrbot" in sys.modules and getattr(sys.modules["astrbot"], "__fake__", False):
        return
    mods = {n: types.ModuleType(n) for n in (
        "astrbot", "astrbot.api", "astrbot.api.event", "astrbot.api.event.filter", "astrbot.api.star",
        "astrbot.api.message_components", "astrbot.api.provider", "astrbot.api.platform",
        "astrbot.api.util", "astrbot.api.web", "astrbot.core", "astrbot.core.agent",
        "astrbot.core.agent.message", "astrbot.core.star", "astrbot.core.star.filter",
        "astrbot.core.star.filter.command", "astrbot.core.utils", "astrbot.core.utils.session_waiter",
        "astrbot.core.utils.astrbot_path", "astrbot.core.config")}
    mods["astrbot"].__fake__ = True
    log = logging.getLogger("astrbot")
    api = mods["astrbot.api"]
    api.logger, api.AstrBotConfig, api.llm_tool = log, AstrBotConfig, llm_tool
    api.FunctionTool, api.ToolSet = object, list
    ev = mods["astrbot.api.event"]
    ev.filter, ev.AstrMessageEvent, ev.MessageChain = filter, FakeEvent, MessageChain
    ev.MessageEventResult, ev.CommandResult = MessageEventResult, CommandResult
    for k, v in vars(filter).items():
        setattr(mods["astrbot.api.event.filter"], k, v)
    st = mods["astrbot.api.star"]
    st.Star, st.Context, st.StarTools, st.register = Star, FakeContext, StarTools, register
    comp = mods["astrbot.api.message_components"]
    for cls in (BaseMessageComponent, ComponentType, Plain, At, AtAll, Image, Record, Video, File,
                Reply, Face, Poke, Node, Nodes):
        setattr(comp, cls.__name__, cls)
    pv = mods["astrbot.api.provider"]
    pv.ProviderRequest, pv.LLMResponse, pv.Provider = ProviderRequest, LLMResponse, object
    plat = mods["astrbot.api.platform"]
    plat.MessageType, plat.AstrMessageEvent = MessageType, FakeEvent
    plat.AstrBotMessage = plat.MessageMember = plat.Group = types.SimpleNamespace
    util = mods["astrbot.api.util"]
    util.session_waiter, util.SessionController = session_waiter, SessionController
    sw = mods["astrbot.core.utils.session_waiter"]
    sw.session_waiter, sw.SessionController, sw.SessionFilter = session_waiter, SessionController, SessionFilter
    mods["astrbot.core.agent.message"].TextPart = TextPart
    mods["astrbot.core.star.filter.command"].GreedyStr = GreedyStr
    mods["astrbot.core.config"].AstrBotConfig = AstrBotConfig
    ap = mods["astrbot.core.utils.astrbot_path"]
    ap.get_astrbot_data_path = lambda: str(_DATA_ROOT)
    ap.get_astrbot_temp_path = lambda: str(_DATA_ROOT / "temp")
    ap.get_astrbot_plugin_data_path = lambda: str(_DATA_ROOT / "plugin_data")
    web = mods["astrbot.api.web"]
    web.json_response = lambda data, **kw: {"json": data, **kw}
    web.error_response = lambda msg, status_code=400, **kw: {"error": msg, "status": status_code}
    web.request = types.SimpleNamespace()
    sys.modules.update(mods)


def load_plugin(plugin_dir: str | Path, config: dict | None = None, context: FakeContext | None = None):
    """Import plugin_dir/main.py as a package (relative imports work) and instantiate it."""
    install()
    reset_registry()
    plugin_dir = Path(plugin_dir).resolve()
    pkg_name = "fa_plugin_" + re.sub(r"\W", "_", plugin_dir.name)
    for mod in [m for m in sys.modules if m == pkg_name or m.startswith(pkg_name + ".")]:
        del sys.modules[mod]
    init_py = plugin_dir / "__init__.py"
    if init_py.exists():
        pkg_spec = importlib.util.spec_from_file_location(
            pkg_name, init_py, submodule_search_locations=[str(plugin_dir)])
        pkg = importlib.util.module_from_spec(pkg_spec)
        sys.modules[pkg_name] = pkg
        pkg_spec.loader.exec_module(pkg)
    else:  # namespace-like package so `from .helpers import x` works
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(plugin_dir)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg
    spec = importlib.util.spec_from_file_location(f"{pkg_name}.main", plugin_dir / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    star_classes = [v for v in vars(module).values()
                    if isinstance(v, type) and issubclass(v, Star) and v is not Star and v.__module__ == module.__name__]
    if not star_classes:
        raise RuntimeError("main.py defines no Star subclass (AstrBot would not register it either)")
    cls = star_classes[-1]
    meta = _read_meta(plugin_dir)
    cls.name = meta.get("name", cls.name)
    cls.author = meta.get("author", cls.author)
    cls.plugin_id = f"{cls.author}/{cls.name}".lower()
    ctx = context or FakeContext()
    _CURRENT["context"] = ctx
    schema_path = plugin_dir / "_conf_schema.json"
    if schema_path.exists():
        conf = config_from_schema(json.loads(schema_path.read_text(encoding="utf-8")), config)
        try:
            instance = cls(context=ctx, config=conf)
        except TypeError:
            instance = cls(context=ctx)
    else:
        instance = cls(context=ctx)
    instance._fa_module = module
    return instance


def _read_meta(plugin_dir: Path) -> dict:
    p = plugin_dir / "metadata.yaml"
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(name|author)\s*:\s*['\"]?([^'\"#]+?)['\"]?\s*(#.*)?$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


# ------------------------------------------------------------------- driving
async def collect(result) -> list[MessageChain]:
    """Drive a handler's return value (async generator or coroutine) like AstrBot does."""
    out: list[MessageChain] = []
    if inspect.isasyncgen(result):
        async for item in result:
            if isinstance(item, MessageChain):
                out.append(item)
    elif inspect.iscoroutine(result):
        item = await result
        if isinstance(item, MessageChain):
            out.append(item)
    return out


def _convert(params: list[str], fn) -> dict:
    """Mirror of CommandFilter.validate_and_convert_params (AstrBot v4.29.3)."""
    sig = inspect.signature(fn, eval_str=True)
    plist = list(sig.parameters.items())[2:]  # skip self, event
    result = {}
    for i, (name, p) in enumerate(plist):
        spec = p.annotation if p.default is inspect.Parameter.empty else p.default
        if spec is GreedyStr:
            if i != len(plist) - 1:
                raise ValueError(f"参数 '{name}' (GreedyStr) 必须是最后一个参数。")
            result[name] = " ".join(params[i:])
            break
        if i >= len(params):
            if p.default is inspect.Parameter.empty:
                raise ValueError("必要参数缺失。")
            result[name] = p.default
            continue
        raw = params[i]
        try:
            if spec is None:
                result[name] = int(raw) if raw.isdigit() else raw
            elif isinstance(spec, str) or spec is str:
                result[name] = raw
            elif isinstance(spec, bool) or spec is bool:
                low = raw.lower()
                if low in ("true", "yes", "1"):
                    result[name] = True
                elif low in ("false", "no", "0"):
                    result[name] = False
                else:
                    raise ValueError
            elif isinstance(spec, int) or spec is int:
                result[name] = int(raw)
            elif isinstance(spec, float) or spec is float:
                result[name] = float(raw)
            elif typing.get_origin(spec) in (typing.Union, types.UnionType):
                non_none = [a for a in typing.get_args(spec) if a is not type(None)]
                result[name] = non_none[0](raw) if len(non_none) == 1 else raw
            elif spec is inspect.Parameter.empty:
                result[name] = raw
            else:
                result[name] = spec(raw)
        except ValueError:
            raise ValueError(f"参数 {name} 类型错误。")
    return result


async def run_command(plugin, text: str, event: FakeEvent | None = None, *, texts: bool = True):
    """Dispatch `text` (without the wake prefix) to the matching command, like AstrBot.

    Returns the plain text of every yielded result (or the MessageChains if texts=False).
    Raises LookupError if no command matches, ValueError on parameter errors.
    """
    msg = re.sub(r"\s+", " ", text.strip())
    event = event or FakeEvent(msg)
    event.message_str = msg
    best = None
    for cmd in sorted(REGISTRY["commands"], key=lambda c: -c["priority"]):
        for full in cmd["names"]:
            if msg == full or msg.startswith(full + " "):
                if best is None or len(full) > len(best[1]):
                    best = (cmd, full)
    if best is None:
        raise LookupError(f"no command matches {text!r}")
    cmd, full = best
    meta = getattr(cmd["fn"], "_fa", {})
    perm = meta.get("perm")
    if perm and perm[0] == PermissionType.ADMIN and not event.is_admin():
        return ["[denied: admin only]"] if texts else []
    params = [p for p in msg[len(full):].strip().split(" ") if p]
    kwargs = _convert(params, cmd["fn"])
    results = await collect(cmd["fn"](plugin, event, **kwargs))
    results += event.sent
    return [r.get_plain_text() for r in results] if texts else results


async def run_listeners(plugin, event: FakeEvent, *, texts: bool = True):
    """Run every non-command listener whose filters accept the event."""
    out: list[MessageChain] = []
    for fn in REGISTRY["listeners"]:
        if "command" in getattr(fn, "_fa", {}):
            continue
        ok = True
        for kind, value in getattr(fn, "_fa", {}).get("filters", []):
            if kind == "regex":
                ok = bool(value.search(event.message_str))
            elif kind == "type":
                want = {MessageType.GROUP_MESSAGE: EventMessageType.GROUP_MESSAGE,
                        MessageType.FRIEND_MESSAGE: EventMessageType.PRIVATE_MESSAGE}[event.get_message_type()]
                ok = bool(want & value)
            elif kind == "custom":
                f = value(True) if isinstance(value, type) else value
                ok = f.filter(event, {})
            if not ok:
                break
        if ok:
            out += await collect(fn(plugin, event))
            if event.is_stopped():
                break
    out += event.sent
    return [r.get_plain_text() for r in out] if texts else out


async def run_hook(plugin, name: str, *args):
    """Call every registered hook `name` (e.g. 'on_llm_request') with args."""
    for fn in REGISTRY["hooks"].get(name, []):
        await fn(plugin, *args)


async def call_tool(plugin, name: str, event: FakeEvent | None = None, **kwargs):
    """Call an @filter.llm_tool by name. Returns (value_for_llm, messages_sent_to_user)."""
    tool = REGISTRY["llm_tools"][name]
    event = event or FakeEvent()
    res = tool["fn"](plugin, event, **kwargs)
    if inspect.isasyncgen(res):
        sent = [x async for x in res if isinstance(x, MessageChain)]
        return None, sent + event.sent
    value = await res
    return (None if value is None else str(value)), event.sent
