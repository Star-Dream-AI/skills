# Lifecycle, configuration, storage, sessions

Verified against AstrBot v4.29.3 (`core/star/star_manager.py`, `core/star/base.py`,
`core/config/astrbot_config.py`, `core/utils/plugin_kv_store.py`,
`core/utils/session_waiter.py`, `core/star/star_tools.py`).

## Contents
1. How a plugin is discovered and loaded
2. Lifecycle: `__init__`, `initialize`, `terminate`, hot reload
3. Background tasks and timers
4. `_conf_schema.json` and `AstrBotConfig`
5. Storage: KV, data dir, files
6. Multi-turn conversations (`session_waiter`)
7. Logging

---

## 1. Discovery and loading

- Plugins live in `data/plugins/<dir>/`. The entry file is `main.py`, or else `<dir>.py`.
  The module path becomes `data.plugins.<dir>.main`.
- **Define the `Star` subclass in `main.py` itself.** `Star.__init_subclass__` registers the
  class under `cls.__module__`, and the loader then looks up `star_map["data.plugins.<dir>.main"]`.
  If the class is defined in `core.py` and imported into main.py, the key doesn't match. The
  loader then falls back to the legacy path, which only finds a class whose name ends with
  `Plugin` or is `Main`, and it skips the new-style class injection. Put helpers in other
  modules and keep the plugin class in main.py. Only one `Star` subclass per main.py: a
  second one overwrites the first.
- `@register("name", "author", "desc", "version", "repo")` is **optional and legacy**.
  `metadata.yaml` wins over it. New plugins can omit it.
- Inside the plugin package, use relative imports (`from .core import X`). The package is
  imported as `data.plugins.<dir>`, so absolute imports of sibling modules
  (`import core`) fail.
- `requirements.txt` is installed automatically (with a missing-only precheck) on install
  and update, and on import errors. Pin loosely, and don't list packages AstrBot already
  ships (aiohttp, httpx, pydantic, etc.) unless you need a specific version.
- Version gate: if `astrbot_version` in metadata.yaml doesn't match, loading fails with
  "AstrBot X does not satisfy plugin astrbot_version". The WebUI install can override it.
- Import errors and exceptions in `__init__` or `initialize` put the plugin in
  the WebUI's **加载失败插件** list with the traceback. Fix it there and press 重载.

Load order inside `load()`: import module → build `AstrBotConfig` from `_conf_schema.json`
(if present) → read metadata.yaml → inject class attributes `name`, `author`, `plugin_id` →
instantiate `Cls(context=..., config=...)` (it retries `Cls(context=...)` on TypeError) →
bind handlers → `await instance.initialize()` → fire `on_plugin_loaded`.

## 2. Lifecycle

```python
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):   # drop `config` if there is no schema
        super().__init__(context)          # sets self.context and self.logger
        self.config = config
        # sync, cheap setup only: read config, build objects, register tools / web APIs

    async def initialize(self):
        # async setup: open DB/HTTP sessions, start background tasks, warm caches
        self._task = asyncio.create_task(self._loop())

    async def terminate(self):
        # called on disable, reload and uninstall; undo everything initialize() did
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        await self._session.close()
```

- `self.name`, `self.author` and `self.plugin_id` (`"author/name"`, lowercased) are injected
  **before** `__init__` runs, so they're readable inside it.
- **Do not define `__del__`.** `_terminate_plugin` checks `__del__` first, and if the class
  defines it, `terminate()` is **never called**. `__del__` runs in a thread executor instead.
- `on_astrbot_loaded` fires only at core startup. After a WebUI hot reload or a fresh
  install it doesn't fire, so per-plugin setup belongs in `initialize()`.
- Hot reload (WebUI 插件 → 重载, or the file watcher when AstrBot runs with
  `ASTRBOT_RELOAD=1`) calls `terminate()`, purges the
  plugin's modules, re-imports and re-instantiates. Anything not cleaned up in
  `terminate()` (tasks, sockets, scheduler jobs, monkeypatches) leaks and **runs twice**
  after reload. Module-level globals are recreated, while state held by other libraries
  is not.
- When the plugin is disabled, the class isn't instantiated at all on load.

## 3. Background tasks and timers

Start them in `initialize()` and stop them in `terminate()`. Each loop iteration must
survive its own exceptions:

```python
async def _loop(self):
    while True:
        try:
            await self._tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger.exception("tick failed")     # never let one error kill the loop
        await asyncio.sleep(self.config.get("interval_sec", 60))
```

- Use `asyncio.sleep`, never `time.sleep`. Run blocking or CPU work with
  `await asyncio.to_thread(fn, ...)`. Everything shares one event loop, so a blocking call
  freezes the whole bot, every platform and every plugin.
- Active sends from timers need a stored UMO (see events-messages.md §4).
- `context.register_task` is deprecated; use `initialize()`.
- `self.context.cron_manager.add_basic_job(name=..., cron_expression="0 8 * * *", handler=..., persistent=False)`
  exists, but it creates a DB job record on each call. If you use it, keep the returned
  `job.job_id` and `await cron_manager.delete_job(job_id)` in `terminate()`, or you get one
  more job per reload. A plain asyncio loop (or APScheduler owned by the plugin) is easier
  to keep leak-free.

## 4. `_conf_schema.json` → `AstrBotConfig`

If `_conf_schema.json` exists, AstrBot creates `data/config/<plugin_dir>_config.json` from
it and passes an `AstrBotConfig` (a dict subclass) to `__init__`. Users edit it in WebUI
插件 → 配置.

```json
{
  "api_key":   {"type": "string", "description": "API Key", "default": "", "secret": true},
  "mode":      {"type": "string", "description": "模式", "options": ["fast", "safe"], "labels": ["快速", "安全"], "default": "fast"},
  "interval":  {"type": "int", "description": "间隔(秒)", "default": 60, "slider": {"min": 10, "max": 3600, "step": 10}},
  "prompt":    {"type": "text", "description": "提示词", "default": ""},
  "whitelist": {"type": "list", "description": "允许的会话", "default": [], "_special": "umo"},
  "provider":  {"type": "string", "description": "使用的模型", "default": "", "_special": "select_provider"},
  "advanced":  {"type": "object", "description": "高级", "items": {
      "timeout": {"type": "float", "default": 10.0}
  }}
}
```

Types (others raise `TypeError` and the config fails to load): `string, text, int, float,
bool, list, object, dict, template_list, file`.
- `object` **must** have `items` (a sub-schema); `config["advanced"]["timeout"]`.
- `dict` is a free-form mapping, optionally with `template_schema`.
- `template_list` uses `templates: {key: {name, items, display_item?, hide_hint_in_list?}}`.
  It is saved as a list of dicts with `__template_key`.
- `file` (≥4.13.0) holds uploaded files: `"default": [], "file_types": ["pdf"]`.

Field options: `description`, `hint`, `obvious_hint`, `default`, `invisible`,
`secret` (masks string or list-of-string in the UI only; the value is stored in plain
text, so never log it), `options` / `labels` / `subtitles`, `slider` (int/float),
`editor_mode` / `editor_language` / `editor_theme`, `_special`.

`_special` values for plugins: `select_provider`, `select_provider_tts`,
`select_provider_stt`, `select_persona` (all strings), `select_knowledgebase` (list),
`sender_id` (list of user IDs, new), `umo` (string = one, list = many, new). Other
`_special` values are core-internal, so don't use them.

Defaults when `default` is omitted: int 0, float 0.0, bool False, string or text "",
list [], file [], object {}, dict {}, template_list [].

Reading and saving:
```python
self.config.get("interval", 60)          # prefer .get with a fallback
self.config.interval                     # attribute access works; a missing key gives None
self.config["interval"] = 30
self.config.save_config()                # sync; await self.config.save_config_async() in async code
```

Schema migration on load (`check_config_integrity`): missing keys get defaults, keys no
longer in the schema are **removed**, and key order follows the schema. Existing values are
**not** type-coerced: a user's `"30"` string stays a string after you change the type to
int. Validate or coerce in code. Renaming a key loses the old value, so read the old key once
and migrate it.

The global AstrBot config (wake prefix, admins, provider settings) is
`self.context.get_config(umo)`. Pass the UMO, because different sessions can bind
different config files.

## 5. Storage

**KV** (≥4.9.2), stored in AstrBot's shared preferences DB and keyed by `plugin_id`:
```python
await self.put_kv_data("count", 3)       # int float str bytes bool dict list None
n = await self.get_kv_data("count", 0)
await self.delete_kv_data("count")
```
Good for small state. Changing `name` or `author` in metadata.yaml changes `plugin_id`, and
the plugin then loses its KV data.

**Files**: use the plugin data dir. **Never the plugin's own folder**, because updates and
reinstalls replace it.
```python
from astrbot.api.star import StarTools
self.data_dir = StarTools.get_data_dir()          # Path to data/plugin_data/<plugin name>, created if missing
# or explicitly: StarTools.get_data_dir("astrbot_plugin_xxx")
```
`get_data_dir()` without arguments resolves the caller module through `star_map`, so call it
from main.py code (`__init__` or a method). From a helper module, pass the name or pass the
Path in. An alternative is `Path(get_astrbot_data_path()) / "plugin_data" / self.name`
(`from astrbot.core.utils.astrbot_path import get_astrbot_data_path`). Uninstalling with
"delete data" removes `plugin_data/<name>` and the config file.

SQLite: one connection per plugin, opened in `initialize()` and closed in `terminate()`.
Run queries with `asyncio.to_thread`, or use `aiosqlite`, which must then be listed in
requirements.txt. Temporary files go under `get_astrbot_temp_path()` from the same module.

## 6. Multi-turn: `session_waiter`

```python
from astrbot.api.util import session_waiter, SessionController
from astrbot.core.utils.session_waiter import SessionFilter

class PerUser(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        return f"{event.unified_msg_origin}:{event.get_sender_id()}"

@filter.command("猜数字")
async def guess(self, event: AstrMessageEvent):
    target = random.randint(1, 100)
    yield event.plain_result("我想了一个 1-100 的数，猜吧（发送 退出 结束）")

    @session_waiter(timeout=60, record_history_chains=False)
    async def waiter(controller: SessionController, ev: AstrMessageEvent):
        text = ev.message_str.strip()
        if text == "退出":
            await ev.send(ev.plain_result("已退出"))
            controller.stop()
            return
        if not text.isdigit():
            await ev.send(ev.plain_result("请发数字"))      # can't yield in here
            return                                        # session keeps waiting
        n = int(text)
        if n == target:
            await ev.send(ev.plain_result("猜对了！"))
            controller.stop()
            return
        await ev.send(ev.plain_result("大了" if n > target else "小了"))
        controller.keep(timeout=60, reset_timeout=True)

    try:
        await waiter(event, session_filter=PerUser())
    except TimeoutError:
        yield event.plain_result("超时了")
    finally:
        event.stop_event()
```

- **The default session key is `event.unified_msg_origin`, not the sender.** Older docs
  say "sender_id", but the source uses `DefaultSessionFilter`, which returns the UMO. So
  in a group, without a custom filter, **any member's** next message feeds the waiter.
  Use a custom `SessionFilter` (as above) for per-user games; keep the default for
  group-wide games.
- Follow-up messages that match a live waiter don't need the wake prefix or an @. They go
  through whitelist, rate-limit and safety checks, then straight to the waiter, and they
  do **not** trigger other plugins or the LLM.
- `controller.keep(timeout, reset_timeout=True)` restarts the timer. `reset_timeout=False`
  adds to the remaining time. `controller.stop()` ends the session.
  `get_history_chains()` needs `record_history_chains=True`.
- Timeout raises `TimeoutError` out of `await waiter(...)`.
- Inside the waiter, send with `await ev.send(...)`, never `yield`.

## 7. Logging

`from astrbot.api import logger`, or `self.logger` (a per-plugin logger whose level is
adjustable in the WebUI). Don't use `print` or `logging.getLogger(__name__)` with your own
handlers. Never log secrets, tokens or full user messages at INFO. Write comments and logs
in English, which is AstrBot's convention.
