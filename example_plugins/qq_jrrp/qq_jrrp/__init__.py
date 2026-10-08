"""LazyAlienWS qq_jrrp port for BotCraft (GPL-3.0-only).

Source: https://github.com/UnknownBits/LazyAlienWS/blob/main/plugins/qq_jrrp.py
Modified 2026-10-01: native QQ Markdown, command keyboards and safe JSON persistence.
Modified 2026-10-05: public BotCraft group/C2C APIs, translations, exact aliases,
stdlib record validation and help registration; reference replies are omitted.
"""

from datetime import date
from pathlib import Path
from types import ModuleType

from botcraft.api.command import GreedyText, Literal, QQCommandSource
from botcraft.message.message_received import QQMessageReceived
from botcraft.api.types import QQPluginServerInterface

from .fortune import daily_luck
from .keyboard import command_keyboard
from .messages import (
    COMMAND, _rtr, fortune_markdown,
    sentence_markdown, submission_markdown,
)
from .storage import Sentence, SentenceStore

_ALIASES = frozenset(('\u4eca\u65e5\u4eba\u54c1', '#\u4eca\u65e5\u4eba\u54c1'))


def parse_submission(payload: str, sender: str) -> Sentence | None:
    payload = payload.replace('\r\n', '\n')
    if not payload.startswith("'''\n"):
        return None
    # Only a complete marker line closes the quote; preserve its internal whitespace.
    text, separator, source = payload[4:].partition("\n'''\n")
    if not separator or not text.strip() or not source.strip():
        return None
    return Sentence(sender, text, source.strip())


def _reply(server: QQPluginServerInterface, source: QQCommandSource, response) -> None:
    response.set_keyboard(command_keyboard(server, source.user.id, is_c2c=source.scene == 'c2c'))
    source.reply(response)


def jrrp_handler(server: QQPluginServerInterface, store: SentenceStore, source: QQCommandSource) -> None:
    with source.preferred_language_context():
        try:
            today = date.today()
            number = daily_luck(source.user.id, today)
            response = fortune_markdown(server, number, store.choose(number, today), today)
        except (OSError, ValueError):
            server.logger.exception('qq_jrrp sentence storage failed')
            response = _rtr(server, 'storage_error', markdown=True)
        _reply(server, source, response)


def help_handler(server: QQPluginServerInterface, source: QQCommandSource) -> None:
    with source.preferred_language_context():
        _reply(server, source, _rtr(server, 'help', markdown=True))


def post_handler(server: QQPluginServerInterface, store: SentenceStore, source: QQCommandSource,
                 payload: str | None = None) -> None:
    with source.preferred_language_context():
        try:
            if payload is None:
                response = submission_markdown(server)
            else:
                sender = f"{server.get_botcraft_config()['appid']}:{source.scene}:{source.user.id}"
                sentence = parse_submission(payload, sender)
                if sentence is None:
                    response = _rtr(server, 'post_invalid', markdown=True, instructions=submission_markdown(server))
                else:
                    store.add(sentence)
                    response = _rtr(server, 'post_success', markdown=True, quotation=sentence_markdown(server, sentence))
        except (OSError, ValueError):
            server.logger.exception('qq_jrrp sentence storage failed')
            response = _rtr(server, 'storage_error', markdown=True)
        _reply(server, source, response)


def withdraw_handler(server: QQPluginServerInterface, store: SentenceStore, source: QQCommandSource) -> None:
    with source.preferred_language_context():
        try:
            sender = f"{server.get_botcraft_config()['appid']}:{source.scene}:{source.user.id}"
            sentence = store.withdraw(sender)
            response = (
                _rtr(server, 'withdraw_missing', markdown=True) if sentence is None
                else _rtr(server, 'withdraw_success', markdown=True, quotation=sentence_markdown(server, sentence))
            )
        except (OSError, ValueError):
            server.logger.exception('qq_jrrp sentence storage failed')
            response = _rtr(server, 'storage_error', markdown=True)
        _reply(server, source, response)


def on_load(server: QQPluginServerInterface, prev_module: ModuleType | None) -> None:
    store = SentenceStore(Path(server.get_data_folder()) / 'luck_sentence.json')
    root = Literal(COMMAND).requires(lambda source: source.has_permission(0))
    root.runs(lambda source: jrrp_handler(server, store, source))
    root.then(Literal('help').runs(lambda source: help_handler(server, source)))
    root.then(Literal('post').runs(lambda source: post_handler(server, store, source)).then(
        GreedyText('payload').runs(lambda source, context: post_handler(server, store, source, context['payload']))
    ))
    root.then(Literal('withdraw').runs(lambda source: withdraw_handler(server, store, source)))
    server.register_command(root, scope=('group', 'c2c'))
    server.register_help_message(COMMAND, _rtr(server, 'panel_description'), scope=('group', 'c2c'))


def on_message(server: QQPluginServerInterface, event: QQMessageReceived) -> None:
    # Exact aliases only: command-tree execution already handles /jrrp.
    # Do not remove apparent mentions or guess identities from message text.
    content = event.message_data.content
    if isinstance(content, str) and content.strip() in _ALIASES:
        server.execute_command(COMMAND, event.get_command_source())
