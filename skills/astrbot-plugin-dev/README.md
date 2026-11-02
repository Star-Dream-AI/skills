# astrbot-plugin-dev

让 AI 真正懂 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件开发的 skill。内容对照 AstrBot **v4.29.3** 源码逐条核实过，覆盖写插件、修插件、审查插件和发布到插件市场。

A skill that makes AI agents genuinely competent at AstrBot plugin development. Every API fact is checked against the AstrBot v4.29.3 source, not just the docs.

## 为什么需要它 / Why

模型大多读过 AstrBot 的文档，但文档有的已经过时，有的和源码对不上。这个 skill 写的是源码里的真实行为，例如：

- `x: str` 参数只能拿到一个词，`/echo hello world` 只得到 `hello`。要接收整段文本得用 `GreedyStr`，而且不能给它设默认值，设了就会退回只取一个词。
- 类里只要定义了 `__del__`，AstrBot 就会跳过 `terminate()`，后台任务会在每次重载后多跑一份。
- 钩子里写了 `yield`，这个钩子就会被直接跳过，日志里只有一行报错。
- `session_waiter` 默认按整个群（UMO）共享会话，群里任何人的下一条消息都会被它接走。
- `event.should_call_llm(True)` 的作用其实是**阻止**默认的 LLM 回复。
- `metadata.yaml` 里的 `version: 1.0` 会被 YAML 读成浮点数，导致插件安装失败。
- llm_tool 的参数类型写成 `integer`，插件会在导入时直接报错。
- 每轮都变的内容写进 `system_prompt`，会破坏提示词缓存，费用大约涨 7～20 倍。

## 评测结果 / Evaluation

4 个真实任务，每个任务各跑一次「有 skill」和「无 skill」，共 34 条评分标准（详见 `evals/`）：

| | 有 skill | 无 skill |
|---|---|---|
| 评分通过率 | **100%** | 94% |
| 根因解释与源码一致 | ✅ | 部分错误（`__del__` 的成因、漏掉 llm_tool `integer` 导致的加载失败） |
| 动态上下文不进历史、不破坏缓存 | ✅ `extra_user_content_parts` + `mark_as_temp()` | ❌ 拼进 `req.prompt`，每轮都会累积进历史 |
| 交付的插件自带可运行单元测试 | **4/4** | 0/4 |
| 平均 token | 11.4 万 | 7.4 万 |

用 skill 的好处：原因判断准，默认省钱，交付时附带测试，静态检查能拦住装不上的错误，也清楚哪些功能只有新版才有。代价是多用约 55% 的 token。

## 内容 / Contents

```
SKILL.md                         工作流、选机制对照表、20 条易踩的坑、按症状排查表
references/
  handlers.md                    指令/参数解析/监听器/权限/优先级/全部钩子签名
  events-messages.md             事件 API、UMO、消息组件、主动发送、QQ/Telegram 原生 API
  llm.md                         llm_generate、tool_loop_agent、两种工具写法、提示词缓存、对话与人格
  lifecycle-config-storage.md    加载流程、生命周期与热重载、_conf_schema.json、KV/文件存储、session_waiter
  packaging-publish.md           metadata.yaml、依赖、i18n、WebUI 页面、发布、功能-版本对照表
scripts/
  check_plugin.py                静态检查器（只用标准库）
  new_plugin.py                  插件脚手架（生成的插件直接通过检查器和测试）
  fake_astrbot.py                假 AstrBot，不装 AstrBot 也能跑插件单元测试
evals/                           评测用例
```

## 用法 / Usage

装好之后直接跟 AI 说「写个 AstrBot 插件……」「这个插件为什么不触发」就会自动触发。脚本也可以单独用：

```bash
python scripts/new_plugin.py ./plugins --name astrbot_plugin_weather --author you --display 天气 --desc "查天气"
python scripts/check_plugin.py ./plugins/astrbot_plugin_weather
cd plugins/astrbot_plugin_weather && python -m pytest tests -q
```

The scripts need Python 3.10+ and only the standard library.
