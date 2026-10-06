"""Reply passively with the text supplied to /echo."""
from types import ModuleType
from botcraft.api.command import CommandContext, GreedyText, Literal, QQCommandSource
from botcraft.api.types import QQPluginServerInterface


PLUGIN_METADATA = {
    'id': 'echo',
    'version': '1.0.0',
    'name': 'Echo',
    'description': 'Passively echo the supplied text',
    'dependencies': {'botcraft': '>=0.1.0'},
}


def echo(source: QQCommandSource, context: CommandContext) -> None:
    # The original source supplies the passive reply association.
    source.reply(context['text'])


def on_load(server: QQPluginServerInterface, prev_module: ModuleType | None) -> None:
    server.register_command(Literal('/echo').then(GreedyText('text').runs(echo)))
    server.register_help_message('/echo', 'Echo the supplied text')