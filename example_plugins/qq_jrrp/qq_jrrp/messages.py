"""Native QQ Markdown adapted from LazyBot qq_jrrp (GPL-3.0-only).

Source API: https://bot.q.qq.com/wiki/develop/api-v2/
Modified 2026-10-05: delayed translated BotCraft output, without reference replies.
"""

from datetime import date

from botcraft.api.qtext import QMarkdown, QText
from botcraft.api.types import QQPluginServerInterface
from botcraft.translation.translation_manager import TranslationParameter, TranslationOption
from botcraft.translation.translation_text import QQTranslationText

from .fortune import luck_category
from .storage import Sentence

COMMAND = '/jrrp'
TEXT_MARKER = '!\u6587\u672c\n'
SOURCE_MARKER = '\n!\u51fa\u5904\n'
_MARKDOWN_ESCAPES = str.maketrans({char: f'\\{char}' for char in '\\`*_{}[]()#+-.!|>~<'})


def _rtr(server: QQPluginServerInterface, key: str, *args: TranslationParameter,
         markdown: bool = False, **kwargs: TranslationOption) -> QQTranslationText:
    # Bind the plugin namespace without fixing the recipient language.
    return server.rtr('qq_jrrp.' + key, *args, markdown=markdown, **kwargs)


def _escape(text: str) -> str:
    return text.translate(_MARKDOWN_ESCAPES)


def quote(text: str) -> str:
    return '\n'.join(f'> {_escape(line)}' for line in text.split('\n'))


def sentence_markdown(server: QQPluginServerInterface, sentence: Sentence) -> QQTranslationText:
    return _rtr(server, 'sentence', markdown=True, text=QMarkdown(quote(sentence.sentence)),
                source=QText(sentence.source))


def submission_template(server: QQPluginServerInterface) -> str:
    return str(server.tr('qq_jrrp.submission_template'))


def submission_markdown(server: QQPluginServerInterface) -> QQTranslationText:
    return _rtr(server, 'submission', markdown=True,
                template=_rtr(server, 'submission_quotation', markdown=True))


def fortune_markdown(server: QQPluginServerInterface, number: int,
                     sentence: Sentence | None, today: date) -> QQTranslationText:
    category = luck_category(number)
    quotation = sentence_markdown(server, sentence) if sentence is not None else _rtr(server, 'empty', markdown=True)
    return _rtr(server, 'fortune', markdown=True,
                title=_rtr(server, f'categories.{category}.title'),
                description=_rtr(server, f'categories.{category}.description'),
                score=100 - number,
                date=_rtr(server, 'date', year=today.year, month=today.month, day=today.day),
                quotation=quotation)
