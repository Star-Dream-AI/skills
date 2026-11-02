# LLM, tools, agents, conversations

Verified against AstrBot v4.29.3 (`core/star/context.py`, `core/star/register/star_handler.py`,
`core/astr_agent_tool_exec.py`, `core/agent/tool.py`, `core/provider/entities.py`).

## Contents
1. Calling a model from a plugin
2. Function tools (two ways) and what their return values do
3. Agents (`tool_loop_agent`, agent-as-tool)
4. Shaping the default chat via `on_llm_request` (prompt-cache rules)
5. Conversations and personas
6. Other providers (embedding, TTS, STT, decision)

---

## 1. Calling a model

Modern API (≥4.5.7). Pick the provider the session is using:

```python
umo = event.unified_msg_origin
provider_id = await self.context.get_current_chat_provider_id(umo)   # raises ProviderNotFoundError if none
resp = await self.context.llm_generate(
    chat_provider_id=provider_id,
    prompt="总结这段话：...",
    system_prompt="你是摘要助手",          # optional
    image_urls=[...],                    # optional, URLs or local paths
    contexts=[...],                      # optional history: list of Message or {"role","content"} dicts
    # tools=ToolSet([...])               # tools are NOT executed by llm_generate
)
text = resp.completion_text
```

- `llm_generate` makes one call and doesn't run tools. Use `tool_loop_agent` for tool use.
- If both `contexts` and `prompt` are given, `prompt` is appended as the last user message.
- Let the user choose a model: add a `"_special": "select_provider"` string to
  `_conf_schema.json` and pass that ID; fall back to the session provider when it's empty.
- Legacy path, still working: `prov = await self.context.get_using_provider_async(umo=umo)`
  then `await prov.text_chat(prompt=..., contexts=..., system_prompt=...)`. The sync
  `get_using_provider()` is deprecated.
- `LLMResponse`: `.completion_text`, `.result_chain` (MessageChain), `.role`
  (`"assistant"`, `"tool"` or `"err"`), `.tools_call_name/args/ids`, `.raw_completion`.
  Check `role == "err"` before trusting the text.
- Wrap calls in try/except. Provider errors, timeouts and rate limits are normal.

**`yield event.request_llm(...)` vs `llm_generate`.** `request_llm` hands a
`ProviderRequest` back to AstrBot's own agent pipeline. That pipeline brings persona,
conversation history, the user's tools, `on_llm_request` hooks and the normal reply
sending, and the exchange is saved to the conversation when `conversation=` is set. Use it
when the plugin wants "the bot answers this, in character". Use `llm_generate` for
side-channel work such as summarizing, classifying or extracting, where the result is data
for your code and shouldn't land in chat history.

## 2. Function tools

### a) Decorator: simplest for plugin methods
```python
@filter.llm_tool(name="get_weather")          # name defaults to the function name
async def get_weather(self, event: AstrMessageEvent, city: str, days: int = 1):
    """查询天气预报。

    Args:
        city(string): 城市名，例如 杭州
        days(number): 预报天数，1-7
    """
    data = await self._fetch(city, int(days))
    return f"{city} 未来{days}天：{data}"     # str → fed back to the LLM as the tool result
```

The docstring is the schema. AstrBot does **not** read type annotations (`docstring_parser`
plus `PY_TO_JSON_TYPE`):
- It needs a Google-style `Args:` section with `name(type): description`. If the `Args:`
  section is missing, the tool has no parameters and the LLM's arguments go nowhere. If a
  parameter has no `(type)`, the decorator raises `ValueError` at import and the plugin
  fails to load.
- Types: only `string, number, boolean, object, array`. **`integer` is rejected** with a
  ValueError at load. Python names are mapped: `str`→string, `int`/`float`→number,
  `bool`→boolean, `dict`→object, `list`/`tuple`/`set`→array. `array[string]` sets
  `items` (≥4.5.7). Because ints arrive as JSON numbers, cast with `int(days)` before use.
- The first paragraph of the docstring is the tool description the LLM sees. Write it for
  the model: what the tool does, when to use it, units and formats.
- Every parameter is effectively required for the model. Give defaults in the Python
  signature for robustness anyway.
- `parameters=` passed to the decorator is ignored. For hand-written JSON Schema, use the
  class style.

### b) Class: full JSON Schema, reusable, can be passed to agents
```python
from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

@dataclass
class SearchTool(FunctionTool[AstrAgentContext]):
    name: str = "myplugin_search"
    description: str = "Search the plugin's knowledge base. Use for questions about X."
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "search keywords"}},
        "required": ["query"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        event = context.context.event          # AstrMessageEvent
        ctx = context.context.context          # the plugin Context
        return f"results for {kwargs['query']}"

# register in __init__ (≥4.5.1):
self.context.add_llm_tools(SearchTool())      # same name replaces the existing tool
```

Older docs show `async def run(self, event, **kwargs)`. That still works: the executor
prefers `handler`, then an overridden `call`, then `run`. Prefer `call`.

### What tool return values do (`_execute_local`)
| Handler does | Effect |
|---|---|
| `return "text"` (or any non-None) | stringified and returned to the LLM as the tool result |
| `return mcp.types.CallToolResult(...)` | passed through as is |
| `yield event.plain_result("...")` | **sent straight to the user** as a message; the LLM gets no content from it |
| return None | nothing goes back to the LLM |
| raises / wrong parameter names | the LLM gets an error string ("Tool handler parameter mismatch…") |

Rule of thumb: return data for the model to talk about, and yield only for things that
must reach the user verbatim (images, files). Tools time out after `tool_call_timeout`
(default 120 s in agents), so make long work async or a background task.

Tool names are global across all plugins and MCP servers. Prefix them (`myplugin_search`).
Enable or disable a tool at runtime with `await self.context.activate_llm_tool_async(name)`
or `deactivate_llm_tool_async(name)`. The deprecated
`context.register_llm_tool(name, func_args, desc, func)` needs `func_args` as a list of
dicts; strings raise `'str' object has no attribute 'pop'`.

## 3. Agents

```python
from astrbot.core.agent.tool import ToolSet

resp = await self.context.tool_loop_agent(
    event=event,
    chat_provider_id=provider_id,
    prompt="查一下B站上关于 AstrBot 的视频",
    system_prompt="...",
    tools=ToolSet([SearchTool(), OtherTool()]),
    max_steps=30,               # default 128
    tool_call_timeout=60,       # default 120
    # extra_user_content_parts=[TextPart(text="...").mark_as_temp()],
)
yield event.plain_result(resp.completion_text)
```

This runs the tool loop until the model stops calling tools. It raises if there's no final
response. Agent-as-tool (multi-agent) means a `FunctionTool` whose `call` itself runs
`ctx.tool_loop_agent(...)` with its own ToolSet and returns `resp.completion_text`.

There is also a decorator form, `@llm_tool`-registered handoff agents via
`from astrbot.api import agent` (`@agent(name=..., instruction=..., tools=[...])`). Prefer
explicit `tool_loop_agent` because it is easier to test and reason about.

## 4. `on_llm_request`: shaping the default chat

```python
from astrbot.api.provider import ProviderRequest
from astrbot.core.agent.message import TextPart

@filter.on_llm_request()
async def inject(self, event: AstrMessageEvent, req: ProviderRequest):
    # stable, long-lived rules → system prompt (cache-friendly because it rarely changes)
    req.system_prompt += "\n始终用中文回答。"
    # per-turn dynamic context → extra_user_content_parts, never the system prompt
    req.extra_user_content_parts.append(
        TextPart(text=f"<ctx>当前时间 {now}；好感度 {score}</ctx>").mark_as_temp()  # ≥4.24.0
    )
```

`ProviderRequest` fields: `prompt`, `system_prompt`, `contexts` (list of dicts, the
history), `image_urls`, `audio_urls`, `extra_user_content_parts`, `func_tool` (ToolSet),
`conversation`, `tool_calls_result`, `model`, `session_id` (obsolete).

Why this matters: providers cache the prompt prefix. If you put anything that changes every
turn into `system_prompt` (time, mood, memory snippets, retrieval results), you break the
cache on every request. AstrBot's docs estimate roughly 7–20× cost and slower first tokens.
- Stable persona or global rules go in `system_prompt`.
- Small per-turn context goes in `extra_user_content_parts`. Those parts are appended after
  the user's message and **saved into conversation history** unless they are marked
  `.mark_as_temp()` (≥4.24.0). For older versions, keep them short or accept that they
  persist.
- Large or occasional knowledge (long-term memory, documents) belongs in an `llm_tool`, so
  the model fetches it only when needed. Or retrieve a few relevant lines and inject only those.
- Don't rewrite `req.contexts` destructively unless the plugin is explicitly a
  context manager. Other plugins and AstrBot's truncation also touch it.
- `event.stop_event()` inside `on_llm_request` cancels this LLM call.
- `on_llm_response` (`resp: LLMResponse`) fires once per agent run with the final response.
  You can edit `resp.completion_text` there, which is useful for filters and post-processing.

## 5. Conversations and personas

```python
conv_mgr = self.context.conversation_manager
cid = await conv_mgr.get_curr_conversation_id(umo)                 # str | None
conv = await conv_mgr.get_conversation(umo, cid)                   # Conversation | None; .history is a JSON string
cid = await conv_mgr.new_conversation(umo, title="...", persona_id=None)
await conv_mgr.switch_conversation(umo, cid)
await conv_mgr.update_conversation(umo, cid, history=[...], title=None, persona_id=None)
await conv_mgr.delete_conversation(umo, cid)

# Append a turn the plugin generated (for example a proactive message) so the bot remembers it:
from astrbot.core.agent.message import UserMessageSegment, AssistantMessageSegment, TextPart
await conv_mgr.add_message_pair(
    cid=cid,
    user_message=UserMessageSegment(content=[TextPart(text="(定时提醒)")]),
    assistant_message=AssistantMessageSegment(content=[TextPart(text=reply)]),
)
```

`conv.history` is a **JSON string**, so `json.loads` it. `cid` can be None for a brand-new
session; create one or skip.

Personas:
```python
pm = self.context.persona_manager
p = await pm.get_persona(persona_id)          # raises ValueError if missing
all_ = await pm.get_all_personas()
default = await pm.get_default_persona_v3(umo)  # TypedDict: prompt, name, begin_dialogs, tools
```
(`create_persona`, `update_persona` and `delete_persona` also exist.) All of these are
`async` in 4.x, so await them. The sync helper is `get_persona_v3_by_id(persona_id)`.

## 6. Other providers

```python
embs = self.context.get_all_embedding_providers()     # no "current" embedding provider
vecs = await embs[0].get_embeddings(["a", "b"])        # .get_embedding(text), .get_dim()
tts = await self.context.get_using_tts_provider_async(umo=umo)   # .get_audio(text) → file path
stt = await self.context.get_using_stt_provider_async(umo=umo)   # .get_text(audio_url)
prov = self.context.get_provider_by_id("id")           # any provider by ID
self.context.get_all_providers()                       # chat providers
```
Embedding and STT/TTS can be absent, so check for empty or None and degrade.

**Decision provider** (very new, on master after v4.29.3; confirm
`hasattr(self.context, "decision")`). It gives low-latency structured choices:
```python
from astrbot.api.provider import DecisionChoiceQuestion, DecisionBooleanQuestion, DecisionError
try:
    ok = await self.context.decision.yes_no(question="Should the bot reply now?",
                                            state=recent_messages, threshold=0.7)
    pick = await self.context.decision.choose(question="Which strategy?",
                                              criteria={"short": "brief", "long": "detailed"},
                                              state=recent_messages)   # .choice, .probabilities, .confidence
except DecisionError:
    ...   # not configured, timeout, bad JSON: degrade
```
`ask({...questions...}, state=...)` answers several at once and returns
`DecisionChoiceAnswer`, `DecisionBooleanAnswer` or `DecisionScoreAnswer` per key.
