# Packaging, metadata, WebUI extras, publishing

Verified against AstrBot v4.29.3 (`core/star/updater.py`, `core/star/star_manager.py`,
docs `dev/star/plugin-new.md`, `plugin-publish.md`, `plugin-market/2026-06-27.md`,
`guides/plugin-i18n.md`, `guides/plugin-pages.md`).

## Contents
1. Directory layout
2. metadata.yaml
3. requirements.txt
4. Logo, i18n, bundled Skills
5. WebUI views and web APIs
6. Local dev loop
7. Publishing to the market
8. Feature/version table

---

## 1. Layout

```text
astrbot_plugin_example/          # repo name; recommend astrbot_plugin_ prefix, lowercase, no spaces
├── main.py                      # the Star subclass lives here
├── metadata.yaml                # required
├── _conf_schema.json            # optional → WebUI config page
├── requirements.txt             # optional, auto-installed
├── logo.png                     # optional, 1:1, 256×256 recommended
├── README.md                    # shown in the market
├── .astrbot-plugin/i18n/zh-CN.json, en-US.json   # optional
├── views/<view>/index.html      # optional WebUI pages (alias: pages/)
├── skills/<skill>/SKILL.md      # optional, Skills registered into AstrBot's Skill Manager
├── core/ … tools/ …             # your modules (relative imports)
└── tests/                       # yours; keep test-only deps out of requirements.txt
```

Add a `.gitignore` for `__pycache__/`, `*.pyc`, `.venv/`, `dist/` and similar. The market
zip limit is **16 MB**.

## 2. metadata.yaml

```yaml
name: astrbot_plugin_example        # REQUIRED. Stable package ID. Valid Python identifier, no "/".
display_name: 示例插件               # optional, shown in UI
desc: 这个插件可以……                  # REQUIRED ("description" is accepted as an alias)
short_desc: 一句话介绍               # optional, market card
version: 1.0.0                      # REQUIRED, semver; bump on every release
author: yourname                    # REQUIRED, stable namespace (no "/")
repo: https://github.com/yourname/astrbot_plugin_example   # needed for market install/update
astrbot_version: ">=4.16,<5"        # optional PEP 440 range, no "v" prefix
support_platforms: [aiocqhttp, telegram]   # optional, adapter-name keys
tags: [tool]                        # optional
social_link: https://...            # optional
```

- Required: `name`, `desc`, `version`, `author`. Each must be a non-empty string. With any
  of them missing, the WebUI can't install the plugin, and on load it falls back to defaults
  with a warning.
- `name` must be `str.isidentifier()` and not a Python keyword. The installer uses it as
  the directory name. `astrbot_plugin_my-tool` is rejected.
- `plugin_id = f"{author}/{name}".lower()` is the market identity and the KV-store key.
  Treat both fields as permanent.
- The `astrbot_version` gate blocks loading on a mismatch. Set it when you use APIs newer
  than about 4.5 (see §8).
- Platform keys: aiocqhttp, qq_official, qq_official_webhook, telegram, wecom,
  wecom_ai_bot, lark, dingtalk, discord, slack, kook, vocechat, weixin_official_account,
  weixin_oc, satori, misskey, line, matrix, mattermost.

## 3. requirements.txt

Installed by AstrBot's pip installer when the plugin is installed or updated, and retried
on ImportError. Guidelines:
- Use async HTTP libraries (`aiohttp`, `httpx`). **Don't use `requests`**, because it blocks
  the event loop. The official guidelines forbid it.
- Leave out packages AstrBot already depends on unless you need a newer version: aiohttp,
  httpx, pydantic, pyyaml, jinja2, openai, mcp, apscheduler, sqlmodel/sqlalchemy, Pillow, …
  A conflicting pin can break AstrBot itself.
- Prefer lower bounds (`foo>=1.2`) over exact pins.
- Heavy native packages (torch and similar) make installs fail on small servers and Docker.
  Mention it in the README or make them optional with a lazy import and a friendly error.

## 4. Logo, i18n, Skills

- `logo.png` in the root (≥4.5.0).
- i18n: `.astrbot-plugin/i18n/<locale>.json` with nested keys only (no dotted keys):
  ```json
  {"metadata": {"display_name": "天气助手", "short_desc": "…", "desc": "…"},
   "config": {"mode": {"description": "模式", "hint": "…", "labels": ["快速", "安全"]},
              "advanced": {"timeout": {"description": "超时"}}},
   "views": {"settings": {"title": "设置", "description": "…", "save": "保存"}}}
  ```
  Translate `labels`, never `options` (saved values). Missing translations fall back to
  metadata.yaml or `_conf_schema.json`.
- `skills/`: each `skills/<name>/SKILL.md` (or `skills/SKILL.md` directly, named after the
  plugin dir) is registered as a read-only Skill sourced from the plugin.

## 5. WebUI views + web APIs (≥4.24.2)

For dashboards, complex forms and logs, beyond what `_conf_schema.json` handles:

```python
from astrbot.api.web import json_response, error_response, request

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        context.register_web_api(f"/{self.name}/stats", self.api_stats, ["GET"], "Stats")
        context.register_web_api(f"/{self.name}/items/<item_id>", self.api_item, ["GET"], "Item")

    async def api_stats(self):
        limit = request.query.get("limit", 20, type=int)
        return json_response({"count": 1, "limit": limit, "user": request.username})

    async def api_item(self, item_id: str):
        return json_response({"id": item_id})
```

- Routes must start with `/<plugin_name>/`. The Dashboard exposes them at
  `/api/v1/plugins/extensions/<plugin_name>/...`, behind Dashboard login.
- Request helpers: `request.method/path/query/headers/cookies/path_params/username`,
  `await request.json(default={})`, `await request.form()`, `await request.files()`
  (`PluginUploadFile.save(path)`), `await request.body()`.
- Responses: `json_response`, `error_response(msg, status_code=400)`,
  `file_response(path, filename=..., content_type=...)`, `stream_response(async_gen)` for SSE.
- Front end: `views/<view>/index.html`, where only first-level folders containing
  `index.html` count. The bridge `window.AstrBotPluginView` is injected automatically:
  `await bridge.ready()`, `bridge.apiGet("stats", {limit: 5})` (no plugin prefix),
  `apiPost`, `upload`, `download`, `subscribeSSE`, `bridge.t(key, fallback)`,
  `bridge.onContext(cb)` for language and theme changes. Views run in a sandboxed iframe;
  reference assets with relative paths.
- Adding or removing a view folder needs a plugin reload. Editing assets needs only a page
  refresh.

## 6. Local dev loop

1. Run AstrBot from source (`uv sync && uv run main.py`) or Docker, with the plugin folder in
   `data/plugins/`. A symlink or junction to your repo works.
2. Edit, then WebUI → 插件 → the plugin card → 重载. Or start AstrBot with
   `ASTRBOT_RELOAD=1` for auto-reload on `.py` changes.
3. Errors: see the console or WebUI logs, and the 加载失败插件 list.
4. Talk to the bot through **WebChat** in the WebUI. It is private-chat-like, so it is
   always woken. Group behaviour (wake prefix, @, session_waiter scope) needs a real
   group test.
5. Before release: run `ruff format` and `ruff check`, run the bundled
   `scripts/check_plugin.py`, and run your unit tests.

## 7. Publishing

1. Push to a public GitHub repo. `repo` in metadata.yaml must be
   `https://github.com/<owner>/<repo>` (or `.git`, or `/tree/<branch>`). SSH, HTTP or
   non-GitHub URLs are rejected by the market spec.
2. Submit at https://cloud.astrbot.app/publish (AstrBot Cloud account).
3. The market record's `author`, `name` and `version` must equal metadata.yaml. Installs
   verify that the installed `metadata.yaml` `author/name` equals the selected `plugin_id`.
4. Update: bump `version`, then push. Users see an update when their installed version
   differs from the market record.
5. Etiquette from the official guidelines: test features, comment code, handle errors so
   one failure doesn't crash the plugin, credit borrowed ideas and code in the README, and
   respect upstream licenses. Prefer a PR to an existing plugin over a near-duplicate.

## 8. Feature → minimum AstrBot version

| Feature | Since |
|---|---|
| `_conf_schema.json` | 3.4.15 |
| `priority=` | 3.4.21 |
| command `alias=` | 3.4.28 |
| `on_astrbot_loaded`, `get_platform` | 3.4.34 |
| `session_waiter` | 3.4.36 |
| `editor_mode` in schema | 3.5.10 |
| `_special` selectors, `get_platform_inst`, v4 sessions | 4.0.0 |
| logo.png, display_name | 4.5.0 |
| `context.add_llm_tools()` | 4.5.1 |
| `llm_generate`, `tool_loop_agent`, `get_current_chat_provider_id`, `array[T]` tool params | 4.5.7 |
| KV store, `self.name` attribute | 4.9.2 |
| `template_list` schema | 4.10.4 |
| `file` schema type | 4.13.0 |
| `on_agent_begin/done`, `on_using_llm_tool`, `on_llm_tool_respond` | >4.23.1 |
| `TextPart.mark_as_temp()` | 4.24.0 |
| WebUI plugin pages/views + `register_web_api` bridge | 4.24.2 |
| `astrbot_version`, `support_platforms` metadata | ~4.16–4.17 (docs examples) |
| `Comp.ActionRow` buttons, `context.decision`, `_special: sender_id/umo` | master after 4.29.3 (unreleased as of 2026-10-31) |

Note: PyPI's `astrbot` package lags behind GitHub. The last wheel for Python <3.12 is
4.14.6, and newer releases need Python ≥3.12. Read the user's actual version (WebUI footer,
or `astrbot/__init__.py` `__version__`) before using anything from the bottom of the table.
