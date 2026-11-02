import asyncio
import datetime

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star


class TranslatePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.task = asyncio.get_event_loop().create_task(self.daily_push())

    def __del__(self):
        self.task.cancel()

    async def daily_push(self):
        while True:
            now = datetime.datetime.now()
            if now.hour == self.config["push_hour"] and now.minute == 0:
                for umo in self.config["push_sessions"]:
                    await self.context.send_message(umo, MessageChain().message("今日单词：serendipity"))
            await asyncio.sleep(60)

    @filter.command("翻译")
    async def translate(self, event: AstrMessageEvent, text: str):
        """把一句话翻译成默认目标语言"""
        prov = self.context.get_using_provider()
        resp = await prov.text_chat(prompt=f"Translate to {self.config['target_lang']}: {text}")
        yield event.plain_result(resp.completion_text)

    @filter.llm_tool(name="translate_text")
    async def translate_tool(self, event: AstrMessageEvent, text: str, lang: str, formality: int = 0):
        """Translate text into another language.

        Args:
            text(string): the text to translate
            lang(string): target language
            formality(integer): 0 casual, 1 formal
        """
        prov = self.context.get_using_provider()
        resp = await prov.text_chat(prompt=f"Translate to {lang} (formality {formality}): {text}")
        yield event.plain_result(resp.completion_text)

    @filter.on_llm_request()
    async def add_hint(self, event: AstrMessageEvent, req: ProviderRequest):
        req.system_prompt += f"\n当前时间：{datetime.datetime.now():%H:%M:%S}。如果用户要求翻译，优先调用 translate_text 工具。"
        yield
