"""Reply passively with the text supplied to /echo."""
from types import ModuleType
from botcraft.api.command import CommandContext, GreedyText, QQCommandSource, SimpleCommandBuilder
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
    # Declare the command path separately from its argument node type.
    builder = SimpleCommandBuilder()
    builder.command('/echo <text>', echo)
    # GreedyText preserves spaces in the supplied reply text.
    builder.arg('text', GreedyText)
    builder.register(server)
    # Help resolves this language dictionary for the viewer or panel language.
    server.register_help_message('/echo', {
        'zh_cn': '复述提供的文本',
        'en_us': 'Echo the supplied text',
    })