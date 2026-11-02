#!/usr/bin/env python3
"""Static checker for AstrBot plugins.

Finds the mistakes that make AstrBot plugins fail to load or silently misbehave,
based on AstrBot v4.29.3 source behaviour. Standard library only; uses PyYAML if
it happens to be installed.

Usage:
    python check_plugin.py <plugin_dir> [--json]

Exit code 1 when any ERROR is found, else 0.
"""

from __future__ import annotations

import ast
import json
import keyword
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"

REQUIRED_META = ("name", "desc", "version", "author")
PLATFORM_KEYS = {
    "aiocqhttp", "qq_official", "qq_official_webhook", "telegram", "wecom",
    "wecom_ai_bot", "lark", "dingtalk", "discord", "slack", "kook", "vocechat",
    "weixin_official_account", "weixin_oc", "satori", "misskey", "line", "matrix",
    "mattermost", "webchat",
}
SCHEMA_TYPES = {"string", "text", "int", "float", "bool", "list", "object", "dict",
                "template_list", "file"}
PLUGIN_SPECIALS = {"select_provider", "select_provider_tts", "select_provider_stt",
                   "select_persona", "select_knowledgebase", "sender_id", "umo"}
TOOL_TYPES = {"string", "number", "object", "array", "boolean"}
PY_TO_JSON = {"int": "number", "float": "number", "bool": "boolean", "str": "string",
              "dict": "object", "list": "array", "tuple": "array", "set": "array"}
MESSAGE_DECOS = {"command", "command_group", "regex", "event_message_type",
                 "platform_adapter_type", "permission_type", "custom_filter",
                 "button_action"}
# hook name -> number of parameters including self
HOOK_ARITY = {
    "on_astrbot_loaded": 1, "on_platform_loaded": 1, "on_plugin_loaded": 2,
    "on_plugin_unloaded": 2, "on_plugin_error": 6, "on_waiting_llm_request": 2,
    "on_llm_request": 3, "on_llm_response": 3, "on_agent_begin": 3,
    "on_agent_done": 4, "on_using_llm_tool": 4, "on_llm_tool_respond": 5,
    "on_decorating_result": 2, "after_message_sent": 2,
}
SHIPPED_DEPS = {"aiohttp", "httpx", "pydantic", "pyyaml", "jinja2", "openai", "mcp",
                "apscheduler", "sqlmodel", "sqlalchemy", "pillow", "quart",
                "aiosqlite", "anthropic", "google-genai", "docstring-parser"}
DEPRECATED_CALLS = {
    "get_using_provider": "sync get_using_provider() is deprecated; use await self.context.get_using_provider_async(umo=...) or get_current_chat_provider_id()",
    "get_using_tts_provider": "deprecated; use await get_using_tts_provider_async(umo=...)",
    "get_using_stt_provider": "deprecated; use await get_using_stt_provider_async(umo=...)",
    "register_llm_tool": "context.register_llm_tool() is deprecated; use @filter.llm_tool or self.context.add_llm_tools(FunctionTool(...))",
    "register_task": "context.register_task() is deprecated; start tasks in async initialize() and cancel them in terminate()",
    "register_commands": "context.register_commands() is deprecated; use @filter.command",
    "get_platform": "context.get_platform(type) is deprecated since 4.0; use self.context.get_platform_inst(event.get_platform_id())",
}


@dataclass
class Finding:
    level: str
    file: str
    line: int
    message: str


class Checker:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []
        self.sibling_modules = {p.stem for p in root.glob("*.py")} | {
            p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()
        }

    def add(self, level: str, file: Path | str, line: int, message: str) -> None:
        rel = str(Path(file).relative_to(self.root)) if isinstance(file, Path) else file
        self.findings.append(Finding(level, rel, line, message))

    # ---------------------------------------------------------------- metadata
    def check_metadata(self) -> dict:
        meta_path = next((self.root / n for n in ("metadata.yaml", "metadata.yml")
                          if (self.root / n).exists()), None)
        if meta_path is None:
            self.add(ERROR, "metadata.yaml", 0, "metadata.yaml is missing; AstrBot needs it to install and identify the plugin")
            return {}
        try:
            meta = load_yaml(meta_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            self.add(ERROR, meta_path, 0, f"metadata.yaml could not be parsed: {e}")
            return {}
        if not isinstance(meta, dict):
            self.add(ERROR, meta_path, 0, "metadata.yaml must be a mapping")
            return {}
        if "desc" not in meta and "description" in meta:
            meta["desc"] = meta["description"]
        for key in REQUIRED_META:
            value = meta.get(key)
            if key in meta and value is not None and not isinstance(value, str):
                self.add(ERROR, meta_path, 0, f"field '{key}' parsed as {type(value).__name__} ({value!r}); AstrBot requires a string, so quote it: {key}: \"{value}\"")
            elif not isinstance(value, str) or not value.strip():
                self.add(ERROR, meta_path, 0, f"required field '{key}' is missing or empty")
        name = meta.get("name")
        if isinstance(name, str) and name.strip():
            if "/" in name or "\\" in name:
                self.add(ERROR, meta_path, 0, "name must not contain path separators")
            elif not name.strip().isidentifier() or keyword.iskeyword(name.strip()):
                self.add(ERROR, meta_path, 0, f"name '{name}' is not a valid Python identifier (no '-', spaces, leading digits); WebUI install rejects it")
            elif not name.startswith("astrbot_plugin_"):
                self.add(INFO, meta_path, 0, "convention: name starts with 'astrbot_plugin_'")
            if name != name.lower():
                self.add(WARN, meta_path, 0, "keep name lowercase (plugin_id is lowercased)")
        author = meta.get("author")
        if isinstance(author, str) and "/" in author:
            self.add(ERROR, meta_path, 0, "author must not contain '/'")
        version = meta.get("version")
        if isinstance(version, str) and not re.match(r"^v?\d+\.\d+(\.\d+)?", version.strip()):
            self.add(WARN, meta_path, 0, f"version '{version}' is not semver-like (e.g. 1.0.0)")
        repo = meta.get("repo")
        if repo is None:
            self.add(WARN, meta_path, 0, "no 'repo' field; market install/update needs an https://github.com/<owner>/<repo> URL")
        elif isinstance(repo, str) and not re.match(
                r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git|/tree/[A-Za-z0-9_.-]+)?/?$", repo.strip()):
            self.add(WARN, meta_path, 0, f"repo '{repo}' is not an https GitHub repository URL accepted by the market")
        spec = meta.get("astrbot_version")
        if spec is not None:
            if not isinstance(spec, str):
                self.add(ERROR, meta_path, 0, "astrbot_version must be a quoted string like \">=4.16,<5\"")
            elif "v" in spec.lower():
                self.add(ERROR, meta_path, 0, "astrbot_version must not contain a 'v' prefix (PEP 440 specifier)")
            elif not re.match(r"^\s*(==|>=|<=|~=|!=|>|<)", spec):
                self.add(WARN, meta_path, 0, "astrbot_version should be a PEP 440 range such as \">=4.16,<5\"")
        platforms = meta.get("support_platforms")
        if platforms is not None:
            if not isinstance(platforms, list):
                self.add(ERROR, meta_path, 0, "support_platforms must be a list")
            else:
                for p in platforms:
                    if p not in PLATFORM_KEYS:
                        self.add(WARN, meta_path, 0, f"support_platforms entry '{p}' is not a known adapter key")
        if "support_platform" in meta or "platform" in meta:
            self.add(WARN, meta_path, 0, "'support_platform'/'platform' are deprecated; use 'support_platforms'")
        return meta

    # ------------------------------------------------------------------ schema
    def check_schema(self) -> None:
        path = self.root / "_conf_schema.json"
        if not path.exists():
            return
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            self.add(ERROR, path, e.lineno, f"_conf_schema.json is not valid JSON: {e.msg} (comments and trailing commas are not allowed)")
            return
        if not isinstance(schema, dict):
            self.add(ERROR, path, 0, "_conf_schema.json must be a JSON object")
            return
        self._check_schema_items(path, schema, "")

    def _check_schema_items(self, path: Path, items: dict, prefix: str) -> None:
        for key, spec in items.items():
            where = f"{prefix}{key}"
            if not isinstance(spec, dict):
                self.add(ERROR, path, 0, f"config '{where}': each entry must be an object with a 'type'")
                continue
            typ = spec.get("type")
            if typ not in SCHEMA_TYPES:
                self.add(ERROR, path, 0, f"config '{where}': type '{typ}' is unsupported; AstrBot raises TypeError and the config fails to load. Use one of {sorted(SCHEMA_TYPES)}")
                continue
            if typ == "object":
                sub = spec.get("items")
                if not isinstance(sub, dict):
                    self.add(ERROR, path, 0, f"config '{where}': type 'object' requires an 'items' sub-schema (KeyError on load otherwise)")
                else:
                    self._check_schema_items(path, sub, where + ".")
                if "default" in spec:
                    self.add(WARN, path, 0, f"config '{where}': 'default' on an object is ignored; put defaults on its items")
            if typ == "template_list" and not isinstance(spec.get("templates"), dict):
                self.add(ERROR, path, 0, f"config '{where}': template_list needs a 'templates' mapping")
            if "default" in spec:
                self._check_default(path, where, typ, spec["default"])
            if "description" not in spec and typ != "object":
                self.add(INFO, path, 0, f"config '{where}': add a 'description' so users know what it does")
            if spec.get("secret") and typ not in ("string", "list"):
                self.add(WARN, path, 0, f"config '{where}': 'secret' only applies to string or list")
            options = spec.get("options")
            if options is not None:
                if not isinstance(options, list):
                    self.add(ERROR, path, 0, f"config '{where}': options must be a list")
                elif "default" in spec and typ in ("string", "int", "float") and spec["default"] not in options:
                    self.add(WARN, path, 0, f"config '{where}': default {spec['default']!r} is not one of options")
                labels = spec.get("labels")
                if isinstance(options, list) and isinstance(labels, list) and len(labels) != len(options):
                    self.add(WARN, path, 0, f"config '{where}': labels must align with options by index")
            if "slider" in spec and typ not in ("int", "float"):
                self.add(WARN, path, 0, f"config '{where}': slider only applies to int/float")
            special = spec.get("_special")
            if special is not None and special not in PLUGIN_SPECIALS:
                self.add(WARN, path, 0, f"config '{where}': _special '{special}' is core-internal or unknown; plugins should use {sorted(PLUGIN_SPECIALS)}")
            if special == "select_knowledgebase" and typ != "list":
                self.add(WARN, path, 0, f"config '{where}': select_knowledgebase returns a list; use type list, default []")
            if special == "sender_id" and typ != "list":
                self.add(WARN, path, 0, f"config '{where}': sender_id selector stores a list; use type list, default []")

    def _check_default(self, path: Path, where: str, typ: str, default) -> None:
        ok = {
            "string": isinstance(default, str), "text": isinstance(default, str),
            "int": isinstance(default, int) and not isinstance(default, bool),
            "float": isinstance(default, (int, float)) and not isinstance(default, bool),
            "bool": isinstance(default, bool), "list": isinstance(default, list),
            "file": isinstance(default, list), "dict": isinstance(default, dict),
            "template_list": isinstance(default, list), "object": True,
        }.get(typ, True)
        if not ok:
            self.add(ERROR, path, 0, f"config '{where}': default {default!r} does not match type '{typ}'")

    # ------------------------------------------------------------ requirements
    def check_requirements(self) -> None:
        path = self.root / "requirements.txt"
        if not path.exists():
            return
        for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            pkg = re.split(r"[<>=!~\[;\s]", line, 1)[0].lower().replace("_", "-")
            if pkg == "requests":
                self.add(WARN, path, i, "requests blocks the event loop; use aiohttp or httpx (both ship with AstrBot)")
            elif pkg in SHIPPED_DEPS and "==" in line:
                self.add(WARN, path, i, f"'{pkg}' already ships with AstrBot; an exact pin can break AstrBot. Drop it or use a lower bound")
            elif pkg in ("pytest", "ruff", "black", "mypy", "pytest-asyncio"):
                self.add(WARN, path, i, f"'{pkg}' is a dev tool; keep it out of requirements.txt (installed for every user)")

    # -------------------------------------------------------------- python code
    def check_python(self) -> None:
        entry = self.root / "main.py"
        if not entry.exists():
            alt = self.root / f"{self.root.name}.py"
            if alt.exists():
                entry = alt
            else:
                self.add(ERROR, "main.py", 0, "no main.py (or <dir>.py); AstrBot skips the directory")
                return
        for py in sorted(self.root.rglob("*.py")):
            if any(part in ("tests", "test", ".venv", "venv", "__pycache__", "dist", "build")
                   for part in py.relative_to(self.root).parts):
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            except SyntaxError as e:
                self.add(ERROR, py, e.lineno or 0, f"syntax error: {e.msg}")
                continue
            self._check_module_generic(py, tree)
            if py == entry:
                self._check_entry(py, tree)

    def _check_module_generic(self, py: Path, tree: ast.Module) -> None:
        uses_astrbot = any(
            (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("astrbot"))
            or (isinstance(n, ast.Import) and any(a.name.startswith("astrbot") for a in n.names))
            for n in ast.walk(tree))
        # imports inside `except ImportError:` are deliberate fallbacks (e.g. for tests)
        fallback_ids = {
            id(n)
            for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)
            and h.type is not None and "ImportError" in ast.unparse(h.type) + ("ModuleNotFoundError" if "ModuleNotFoundError" in ast.unparse(h.type) else "")
            for stmt in h.body for n in ast.walk(stmt)
        } | {
            id(n)
            for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)
            and h.type is not None and "ModuleNotFoundError" in ast.unparse(h.type)
            for stmt in h.body for n in ast.walk(stmt)
        }
        for node in ast.walk(tree):
            if id(node) in fallback_ids:
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top == "requests":
                        self.add(WARN, py, node.lineno, "'requests' blocks the event loop; use aiohttp/httpx")
                    elif top in self.sibling_modules and top != py.stem:
                        self.add(ERROR, py, node.lineno, f"absolute import of sibling module '{top}' fails inside data.plugins.<dir>; use 'from . import {top}' / 'from .{top} import ...'")
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                top = node.module.split(".")[0]
                if top == "requests":
                    self.add(WARN, py, node.lineno, "'requests' blocks the event loop; use aiohttp/httpx")
                elif top in self.sibling_modules and top != py.stem:
                    self.add(ERROR, py, node.lineno, f"absolute import 'from {node.module} import ...' of a sibling module fails when loaded as a plugin package; use 'from .{node.module} import ...'")
            elif isinstance(node, ast.Call):
                name = call_name(node.func)
                if name == "time.sleep":
                    self.add(WARN, py, node.lineno, "time.sleep blocks the whole bot; use await asyncio.sleep(...)")
                elif name.startswith("requests."):
                    self.add(WARN, py, node.lineno, "blocking HTTP call; use aiohttp/httpx")
                elif name.endswith(".should_call_llm") and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value is True:
                    self.add(INFO, py, node.lineno, "event.should_call_llm(True) BLOCKS the default LLM reply (the name reads backwards); make sure that is intended")
                elif name.split(".")[-1] in DEPRECATED_CALLS and ("context" in name or name.startswith("StarTools")):
                    self.add(INFO, py, node.lineno, DEPRECATED_CALLS[name.split(".")[-1]])
                elif name == "print" and uses_astrbot:
                    self.add(INFO, py, node.lineno, "use 'from astrbot.api import logger' (or self.logger) instead of print")
        self._check_writes_into_plugin_dir(py, tree)

    def _check_writes_into_plugin_dir(self, py: Path, tree: ast.Module) -> None:
        for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module))]:
            body_nodes = list(ast.walk(func)) if not isinstance(func, ast.Module) else [
                n for stmt in func.body if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                for n in ast.walk(stmt)]
            uses_file = any(isinstance(n, ast.Name) and n.id == "__file__" for n in body_nodes)
            if not uses_file:
                continue
            writes = any(
                isinstance(n, ast.Call) and (
                    (call_name(n.func) == "open" and any(
                        isinstance(a, ast.Constant) and isinstance(a.value, str) and any(c in a.value for c in "wax")
                        for a in list(n.args[1:2]) + [k.value for k in n.keywords if k.arg == "mode"]))
                    or call_name(n.func).split(".")[-1] in ("write_text", "write_bytes", "mkdir", "dump", "connect"))
                for n in body_nodes)
            if writes:
                line = getattr(func, "lineno", 1)
                self.add(WARN, py, line, "this code derives a path from __file__ and writes/creates files: data in the plugin folder is wiped on update/reinstall. Use StarTools.get_data_dir() (data/plugin_data/<name>)")

    def _check_entry(self, py: Path, tree: ast.Module) -> None:
        imported_names: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imported_names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        filter_src = imported_names.get("filter", "")
        if filter_src and not filter_src.startswith("astrbot.api.event"):
            self.add(WARN, py, 1, f"'filter' is imported from '{filter_src}'; the decorators live in astrbot.api.event.filter")

        star_classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
                        and any(base_name(b) in ("Star", "star.Star") for b in n.bases)]
        if not star_classes:
            star_imported = [k for k, v in imported_names.items()
                             if k.lower().endswith("plugin") or k == "Main"]
            msg = "no class inheriting Star is defined in this file. AstrBot registers the plugin by the defining module, so a Star subclass imported from another module is not picked up correctly; define it in main.py"
            if star_imported:
                msg += f" (found imported names {star_imported})"
            self.add(ERROR, py, 1, msg)
        elif len(star_classes) > 1:
            self.add(WARN, py, star_classes[1].lineno, "more than one Star subclass in main.py; only the last one is used")

        uses_filter_deco = False
        handler_names: dict[str, int] = {}
        for cls in star_classes:
            methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if "__del__" in methods:
                self.add(ERROR, py, methods["__del__"].lineno, "defining __del__ makes AstrBot skip terminate() entirely; move cleanup into async def terminate(self)")
            init = methods.get("__init__")
            if init is not None:
                calls_super = any(isinstance(n, ast.Call) and call_name(n.func) in ("super().__init__", "Star.__init__")
                                  for n in ast.walk(init))
                sets_context = any(isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                                   and n.attr == "context" for n in ast.walk(init))
                if not calls_super and not sets_context:
                    self.add(ERROR, py, init.lineno, "__init__ must call super().__init__(context); otherwise self.context is never set")
                elif not calls_super:
                    self.add(WARN, py, init.lineno, "__init__ skips super().__init__(context): self.context is set manually but the per-plugin self.logger is missing")
                if len(init.args.args) < 2:
                    self.add(ERROR, py, init.lineno, "__init__ must accept (self, context[, config])")
                for n in ast.walk(init):
                    if isinstance(n, ast.Call) and call_name(n.func) in ("asyncio.create_task", "asyncio.ensure_future", "loop.create_task"):
                        self.add(WARN, py, n.lineno, "starting tasks in __init__: prefer async def initialize(), keep the task handle, and cancel it in terminate() (otherwise tasks run twice after a reload)")
                    if isinstance(n, ast.Call) and call_name(n.func).endswith("get_event_loop"):
                        self.add(WARN, py, n.lineno, "avoid get_event_loop() in __init__; do async setup in initialize()")
                if not any(isinstance(a, ast.arg) and a.arg == "config" for a in init.args.args) and (self.root / "_conf_schema.json").exists():
                    self.add(INFO, py, init.lineno, "_conf_schema.json exists but __init__ has no 'config' parameter; add (self, context, config: AstrBotConfig) to receive it")
            init_tasks = "initialize" in methods and any(
                isinstance(n, ast.Call) and call_name(n.func) in ("asyncio.create_task", "asyncio.ensure_future")
                for n in ast.walk(methods["initialize"]))
            if init_tasks and "terminate" not in methods:
                self.add(WARN, py, methods["initialize"].lineno, "initialize() starts tasks but there is no terminate() to cancel them; they leak and duplicate on every reload")
            for special in ("initialize", "terminate"):
                m = methods.get(special)
                if m is not None and not isinstance(m, ast.AsyncFunctionDef):
                    self.add(ERROR, py, m.lineno, f"{special}() must be 'async def' (AstrBot awaits it)")

            for m in methods.values():
                decos = [deco_info(d) for d in m.decorator_list]
                decos = [d for d in decos if d is not None]
                if not decos:
                    continue
                kinds = {d[0] for d in decos}
                is_filter = any(d[1] for d in decos)
                if not is_filter:
                    continue
                uses_filter_deco = True
                if m.name in handler_names:
                    self.add(ERROR, py, m.lineno, f"handler name '{m.name}' is reused (also line {handler_names[m.name]}); AstrBot keys handlers by module+function name, so one silently replaces the other")
                handler_names[m.name] = m.lineno
                hooks = kinds & HOOK_ARITY.keys()
                if hooks:
                    self._check_hook(py, m, hooks, kinds)
                elif "llm_tool" in kinds:
                    self._check_llm_tool(py, m, decos)
                elif kinds & MESSAGE_DECOS:
                    self._check_message_handler(py, m, decos)
            for n in ast.walk(cls):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                        (deco_info(d) or ("",))[0] == "session_waiter" for d in n.decorator_list):
                    self._check_waiter(py, n, cls)
        if uses_filter_deco and "filter" not in imported_names:
            self.add(ERROR, py, 1, "@filter.* decorators used but 'filter' is not imported: from astrbot.api.event import filter")

    def _check_hook(self, py: Path, m, hooks: set, kinds: set) -> None:
        hook = sorted(hooks)[0]
        if kinds & MESSAGE_DECOS:
            self.add(ERROR, py, m.lineno, f"@filter.{hook} cannot be combined with command/listener/permission filters on the same function")
        if not isinstance(m, ast.AsyncFunctionDef):
            self.add(ERROR, py, m.lineno, f"hook {hook} must be 'async def'")
        elif contains_yield(m):
            self.add(ERROR, py, m.lineno, f"hook {hook} contains 'yield'; AstrBot requires a plain coroutine, so this hook never runs. Use 'await event.send(...)'")
        want = HOOK_ARITY[hook]
        have = len(m.args.args)
        if m.args.vararg is None and have != want:
            self.add(ERROR, py, m.lineno, f"hook {hook} takes {want} parameters including self, found {have}")
        if hook == "on_astrbot_loaded":
            self.add(INFO, py, m.lineno, "on_astrbot_loaded only fires at AstrBot startup, not after a hot reload or WebUI install; put per-plugin setup in initialize()")

    def _check_message_handler(self, py: Path, m, decos) -> None:
        if not isinstance(m, ast.AsyncFunctionDef):
            kinds = {d[0] for d in decos}
            if "command_group" in kinds:
                return  # group placeholder body is never called
            self.add(ERROR, py, m.lineno, "message handlers must be 'async def' (a plain def/generator is never awaited)")
            return
        if len(m.args.args) < 2:
            self.add(ERROR, py, m.lineno, "handler must take (self, event, ...)")
            return
        for name, _is_filter, args in decos:
            if name == "command" and args:
                cmd = args[0] if isinstance(args[0], str) else (args[1] if len(args) > 1 and isinstance(args[1], str) else None)
                if cmd and " " in cmd.strip():
                    self.add(ERROR, py, m.lineno, f"command name '{cmd}' contains a space; use a command_group for multi-word commands")
        params = m.args.args[2:]
        defaults_offset = len(m.args.args) - len(m.args.defaults)
        for idx, p in enumerate(params):
            ann = annotation_name(p.annotation)
            if ann == "GreedyStr" and idx != len(params) - 1:
                self.add(ERROR, py, m.lineno, f"GreedyStr parameter '{p.arg}' must be the last parameter")
            absolute = idx + 2
            has_default = absolute >= defaults_offset
            if ann == "GreedyStr" and has_default:
                self.add(ERROR, py, m.lineno, f"'{p.arg}: GreedyStr' has a default value: AstrBot then uses the default's type (str) and the parameter only gets ONE word. Remove the default; an empty remainder already yields \"\"")
            if ann is None and not has_default and any(d[0] == "command" or d[0] == "command_group" for d in decos):
                self.add(WARN, py, m.lineno, f"command parameter '{p.arg}' has no annotation or default; AstrBot cannot convert it (annotate as str/int/float/bool/GreedyStr)")
        if params and any(d[0] == "command" for d in decos):
            last = params[-1]
            if annotation_name(last.annotation) == "str":
                self.add(INFO, py, m.lineno, f"'{last.arg}: str' receives only ONE whitespace-separated token ('/cmd hello world' gives 'hello'). For free text use 'from astrbot.core.star.filter.command import GreedyStr' and annotate '{last.arg}: GreedyStr'")

    def _check_llm_tool(self, py: Path, m, decos) -> None:
        if not isinstance(m, ast.AsyncFunctionDef):
            self.add(ERROR, py, m.lineno, "llm_tool handler must be 'async def'")
        doc = ast.get_docstring(m) or ""
        if not doc.strip():
            self.add(ERROR, py, m.lineno, "llm_tool needs a docstring: first line = description for the model, then an 'Args:' section with 'name(type): description'")
            return
        sig_params = [a.arg for a in m.args.args[2:]]
        documented = parse_google_args(doc)
        if sig_params and not documented:
            self.add(ERROR, py, m.lineno, "llm_tool docstring has no parseable 'Args:' section; the tool gets an empty schema and the model's arguments are dropped")
        for pname, ptype in documented.items():
            if not ptype:
                self.add(ERROR, py, m.lineno, f"llm_tool arg '{pname}' has no (type) in the docstring; AstrBot raises ValueError at import and the plugin fails to load")
                continue
            base = re.match(r"(\w+)(?:\[(\w+)\])?", ptype)
            main_t = PY_TO_JSON.get(base.group(1), base.group(1)) if base else ptype
            sub_t = PY_TO_JSON.get(base.group(2), base.group(2)) if base and base.group(2) else None
            if main_t not in TOOL_TYPES or (sub_t and sub_t not in TOOL_TYPES):
                hint = " ('integer' is not accepted; use number and cast with int())" if "integer" in ptype else ""
                self.add(ERROR, py, m.lineno, f"llm_tool arg '{pname}' type '{ptype}' is unsupported{hint}; use string/number/boolean/object/array (or array[string])")
            if pname not in sig_params and m.args.kwarg is None:
                self.add(ERROR, py, m.lineno, f"llm_tool docstring documents '{pname}' but the function has no such parameter (call fails with a parameter mismatch)")
        for pname in sig_params:
            if pname not in documented:
                self.add(WARN, py, m.lineno, f"llm_tool parameter '{pname}' is not documented in Args:, so the model never sends it (give it a default)")
        if contains_yield(m) and not contains_return_value(m):
            self.add(INFO, py, m.lineno, "this llm_tool only yields: yielded results go straight to the user and the model receives no tool result. Return a string for data the model should use")

    def _check_waiter(self, py: Path, fn, cls) -> None:
        if contains_yield(fn):
            self.add(ERROR, py, fn.lineno, "session_waiter callbacks cannot yield; send with 'await event.send(event.plain_result(...))'")
        src_calls = [n for n in ast.walk(cls) if isinstance(n, ast.Call) and call_name(n.func) == fn.name]
        if src_calls and not any(any(k.arg == "session_filter" for k in c.keywords) for c in src_calls):
            self.add(INFO, py, fn.lineno, "session_waiter without session_filter is keyed by unified_msg_origin: in a group, ANY member's next message feeds it. Pass a SessionFilter returning f'{umo}:{sender_id}' for per-user flows")

    def run(self) -> list[Finding]:
        self.check_metadata()
        self.check_schema()
        self.check_requirements()
        self.check_python()
        if not (self.root / "README.md").exists():
            self.add(INFO, "README.md", 0, "add a README.md (shown on the plugin market)")
        if (self.root / "data").is_dir():
            self.add(WARN, "data/", 0, "a 'data' folder inside the plugin is wiped on update; runtime data belongs in data/plugin_data/<name>")
        order = {ERROR: 0, WARN: 1, INFO: 2}
        return sorted(self.findings, key=lambda f: (order[f.level], f.file, f.line))


# --------------------------------------------------------------------- helpers
def call_name(func) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        inner = call_name(func.value)
        return f"{inner}.{func.attr}" if inner else func.attr
    if isinstance(func, ast.Call):
        return call_name(func.func) + "()"
    return ""


def base_name(node) -> str:
    return call_name(node)


def annotation_name(node) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.split(".")[-1]
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ast.unparse(node)


def deco_info(node):
    """Return (name, is_astrbot_filter, positional_constant_args) for a decorator."""
    target = node.func if isinstance(node, ast.Call) else node
    full = call_name(target)
    if not full:
        return None
    parts = full.split(".")
    name = parts[-1]
    is_filter = (parts[0] == "filter" and len(parts) == 2) or name in HOOK_ARITY or name in MESSAGE_DECOS or name == "llm_tool"
    if len(parts) == 2 and parts[0] != "filter" and name in ("command", "group", "custom_filter"):
        # @group.command("sub") on a command group object
        name = "command" if name == "command" else name
        is_filter = True
    args = []
    if isinstance(node, ast.Call):
        for a in node.args:
            args.append(a.value if isinstance(a, ast.Constant) else None)
    return name, is_filter, args


def contains_yield(fn) -> bool:
    for n in ast.walk(fn):
        if n is not fn and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(n, (ast.Yield, ast.YieldFrom)):
            if _owner(fn, n) is fn:
                return True
    return False


def contains_return_value(fn) -> bool:
    return any(isinstance(n, ast.Return) and n.value is not None and _owner(fn, n) is fn for n in ast.walk(fn))


def _owner(root, target):
    """Find the innermost function that contains target (or root)."""
    stack = [(root, root)]
    while stack:
        node, owner = stack.pop()
        if node is target:
            return owner
        for child in ast.iter_child_nodes(node):
            new_owner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) else owner
            stack.append((child, new_owner))
    return None


def parse_google_args(doc: str) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    lines = doc.splitlines()
    in_args = False
    indent = None
    for line in lines:
        stripped = line.strip()
        if re.match(r"^(Args|Arguments|Parameters|参数)\s*:\s*$", stripped):
            in_args = True
            indent = None
            continue
        if not in_args:
            continue
        if not stripped:
            continue
        cur = len(line) - len(line.lstrip())
        if re.match(r"^(Returns?|Raises|Yields|Examples?|Note)\s*:", stripped):
            break
        if indent is None:
            indent = cur
        if cur < (indent or 0):
            break
        if cur > indent:
            continue  # continuation line
        m = re.match(r"^([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?\s*:", stripped)
        if m:
            result[m.group(1)] = (m.group(2) or "").strip() or None
    return result


def load_yaml(text: str):
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml(text)


def _mini_yaml(text: str) -> dict:
    """Tiny YAML subset: top-level scalars, inline/block lists, folded continuation lines."""
    data: dict = {}
    key = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = re.sub(r"\s+#.*$", "", raw) if "'" not in raw and '"' not in raw else raw
        if not raw.startswith((" ", "\t")):
            m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
            if not m:
                raise ValueError(f"cannot parse line: {raw!r}")
            key, val = m.group(1), m.group(2).strip()
            if val in ("", "|", ">", "|-", ">-"):
                data[key] = None
            elif val.startswith("[") and val.endswith("]"):
                data[key] = [_scalar(v) for v in val[1:-1].split(",") if v.strip()]
            else:
                data[key] = _scalar(val)
        elif key is not None:
            s = line.strip()
            if s.startswith("- "):
                if not isinstance(data.get(key), list):
                    data[key] = []
                data[key].append(_scalar(s[2:]))
            else:
                prev = data.get(key)
                data[key] = (f"{prev} {s}" if isinstance(prev, str) and prev else s)
    return data


def _scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    if v in ("true", "True"):
        return True
    if v in ("false", "False"):
        return False
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)  # same as PyYAML: `version: 1.0` is a float, which AstrBot rejects
    return v


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    root = Path(args[0]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}")
        return 2
    findings = Checker(root).run()
    if "--json" in argv:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("OK: no problems found")
        for f in findings:
            loc = f"{f.file}:{f.line}" if f.line else f.file
            print(f"[{f.level}] {loc}: {f.message}")
        counts = {lvl: sum(1 for f in findings if f.level == lvl) for lvl in (ERROR, WARN, INFO)}
        print(f"\n{counts[ERROR]} error(s), {counts[WARN]} warning(s), {counts[INFO]} note(s)")
    return 1 if any(f.level == ERROR for f in findings) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
