#!/usr/bin/env python3
"""Scaffold a new AstrBot plugin that passes check_plugin.py out of the box.

Usage:
    python new_plugin.py <target_parent_dir> --name astrbot_plugin_xxx --author you \
        [--display "显示名"] [--desc "一句话描述"] [--repo https://github.com/you/astrbot_plugin_xxx] \
        [--min-version 4.9.2] [--no-config] [--no-tests]

Creates <target_parent_dir>/<name>/ with main.py, metadata.yaml, _conf_schema.json,
requirements.txt, README.md, .gitignore and tests/ (with fake_astrbot.py copied in).
Refuses to overwrite an existing non-empty directory.
"""

from __future__ import annotations

import argparse
import keyword
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

MAIN_PY = '''"""{display}: {desc}"""

import asyncio
import contextlib

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.star.filter.command import GreedyStr


class {cls}(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = StarTools.get_data_dir()  # data/plugin_data/<name>, survives updates
        self._task: asyncio.Task | None = None

    async def initialize(self):
        """Async setup. Runs on load and after every hot reload."""
        logger.info("{name} loaded")

    async def terminate(self):
        """Undo everything initialize() started; called on disable, reload and uninstall."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    @filter.command("{cmd}")
    async def {cmd}_cmd(self, event: AstrMessageEvent, text: GreedyStr):
        # GreedyStr must have NO default: with a default AstrBot treats it as a plain one-word str.
        # When nothing follows the command it receives "".
        """{desc}"""
        greeting = self.config.get("greeting", "你好")
        name = text.strip() or event.get_sender_name()
        yield event.plain_result(f"{{greeting}}, {{name}}!")
'''

SCHEMA = '''{
  "greeting": {
    "type": "string",
    "description": "问候语",
    "hint": "回复时放在名字前面",
    "default": "你好"
  }
}
'''

METADATA = '''name: {name}
display_name: {display}
desc: {desc}
version: "1.0.0"
author: {author}
repo: {repo}
astrbot_version: ">={min_version}"
'''

README = '''# {display}

{desc}

## 指令

| 指令 | 说明 |
|---|---|
| `/{cmd} [名字]` | {desc} |

## 配置

在 AstrBot WebUI → 插件 → {display} → 配置 中修改。

## 开发

```bash
python -m pytest tests -q          # 用 tests/fake_astrbot.py，无需安装 AstrBot
```

把本目录放进 AstrBot 的 `data/plugins/`，在 WebUI 插件页点「重载」即可调试。
'''

GITIGNORE = '''__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.ruff_cache/
dist/
build/
*.zip
'''

TEST = '''import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fake_astrbot as fa  # noqa: E402

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def run(coro):
    return asyncio.run(coro)


def test_greets_sender_by_default():
    plugin = fa.load_plugin(PLUGIN_DIR)
    run(plugin.initialize())
    ev = fa.FakeEvent("{cmd}", sender_name="小明")
    assert run(fa.run_command(plugin, "{cmd}", ev)) == ["你好, 小明!"]


def test_takes_whole_remaining_text_and_config():
    plugin = fa.load_plugin(PLUGIN_DIR, config={{"greeting": "Hi"}})
    assert run(fa.run_command(plugin, "{cmd} 张 三")) == ["Hi, 张 三!"]


def test_terminate_is_safe_without_task():
    plugin = fa.load_plugin(PLUGIN_DIR)
    run(plugin.terminate())
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parent")
    ap.add_argument("--name", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--display", default=None)
    ap.add_argument("--desc", default="一个 AstrBot 插件")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--command", default="hello")
    ap.add_argument("--min-version", default="4.9.2")
    ap.add_argument("--no-config", action="store_true")
    ap.add_argument("--no-tests", action="store_true")
    a = ap.parse_args()

    name = a.name.strip()
    if not name.isidentifier() or keyword.iskeyword(name) or name != name.lower():
        print(f"name '{name}' must be a lowercase Python identifier, e.g. astrbot_plugin_weather")
        return 2
    if "/" in a.author:
        print("author must not contain '/'")
        return 2
    if not a.command.isidentifier():
        print("--command must be a single identifier-like word (it is also used for the handler name)")
        return 2
    target = Path(a.parent).resolve() / name
    if target.exists() and any(target.iterdir()):
        print(f"refusing to overwrite non-empty directory {target}")
        return 1
    target.mkdir(parents=True, exist_ok=True)

    short = name.removeprefix("astrbot_plugin_")
    cls = "".join(p.capitalize() for p in short.split("_") if p) + "Plugin"
    display = a.display or short
    repo = a.repo or f"https://github.com/{a.author}/{name}"
    fmt = dict(name=name, author=a.author, display=display, desc=a.desc, repo=repo,
               cls=cls, cmd=a.command, min_version=a.min_version)

    main_py = MAIN_PY.format(**fmt)
    if a.no_config:
        main_py = (main_py
                   .replace("from astrbot.api import AstrBotConfig, logger", "from astrbot.api import logger")
                   .replace("def __init__(self, context: Context, config: AstrBotConfig):", "def __init__(self, context: Context):")
                   .replace("        self.config = config\n", "")
                   .replace('greeting = self.config.get("greeting", "你好")', 'greeting = "你好"'))
    (target / "main.py").write_text(main_py, encoding="utf-8")
    (target / "metadata.yaml").write_text(METADATA.format(**fmt), encoding="utf-8")
    if not a.no_config:
        (target / "_conf_schema.json").write_text(SCHEMA, encoding="utf-8")
    (target / "requirements.txt").write_text("# runtime dependencies only; aiohttp/httpx/pydantic already ship with AstrBot\n", encoding="utf-8")
    (target / "README.md").write_text(README.format(**fmt), encoding="utf-8")
    (target / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    if not a.no_tests:
        tests = target / "tests"
        tests.mkdir(exist_ok=True)
        shutil.copy(HERE / "fake_astrbot.py", tests / "fake_astrbot.py")
        test_src = TEST.format(**fmt)
        if a.no_config:
            test_src = test_src.replace('config={"greeting": "Hi"}', "").replace('["Hi, 张 三!"]', '["你好, 张 三!"]')
        (tests / f"test_{short}.py").write_text(test_src, encoding="utf-8")
    print(f"created {target}")
    print("next: edit main.py, then run check_plugin.py and the tests")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
