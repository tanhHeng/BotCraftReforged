"""Native command registration/traversal adapted to real QQ sources and scope."""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from typing_extensions import Self
from botcraft.message.qtext.text import QTextBase

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
import collections
from mcdreforged.command.command_manager import CommandManager as NativeCommandManager, TraversePurpose
from mcdreforged.command.builder import command_builder_utils as utils
from mcdreforged.command.builder.exception import CommandError, RequirementNotMet
from mcdreforged.command.builder.nodes.basic import CallbackError, CommandSuggestion, CommandSuggestions
from mcdreforged.utils import string_utils
from botcraft.message.qtext.text import QText
from botcraft.command.command_source import QQCommandSource, ConsoleSource
from mcdreforged.plugin.type.common import PluginState


class ConsoleSuggestionSource(ConsoleSource):
    """Use console permissions and preferences without replying while completing."""

    def reply(self: Self, message: str | QTextBase, **kwargs: Any) -> None:
        """Suppress replies while completing console commands.
        
        :param message: Completion diagnostic that is intentionally not emitted.
        :param kwargs: Reply callback options that are intentionally ignored.
        :return: No value is returned.
        """
        return None


class CommandManager(NativeCommandManager):
    def __init__(self: Self, runtime: Runtime) -> None:
        """Initialize native command traversal for a BotCraft runtime.
        
        :param runtime: Runtime providing plugins, translations and logging.
        :return: No value is returned.
        """
        self.runtime = runtime
        self.logger = runtime.logger
        self.root_nodes = collections.defaultdict(list)
        self._CommandManager__preserve_command_error_display_flag = False

    def matches_root(self: Self, command: str) -> bool:
        """Determine whether a command begins with a registered QQ root.
        
        :param command: Command text to inspect.
        :return: Whether the first command element has registered roots.
        """
        return utils.get_element(command) in self.root_nodes

    def execute_command(self: Self, command: str, source: QQCommandSource) -> None:
        """Execute a registered command using a real QQ source.
        
        :param command: Command text to parse.
        :param source: QQ command source owned by this runtime.
        :return: No value is returned.
        """
        if not isinstance(command, str):
            raise TypeError('command must be str')
        self._check_source(source)
        return self._traverse(command, source, TraversePurpose.EXECUTE)

    def suggest_command(self: Self, command: str, source: QQCommandSource) -> CommandSuggestions:
        """Generate suggestions for registered QQ command roots.
        
        :param command: Partial command text to complete.
        :param source: QQ command source owned by this runtime.
        :return: Native command suggestions permitted for this source and scene.
        """
        if not isinstance(command, str):
            raise TypeError('command must be str')
        self._check_source(source)
        return self._traverse(command, source, TraversePurpose.SUGGEST)

    def _check_source(self: Self, source: QQCommandSource) -> None:
        if not isinstance(source, QQCommandSource) or source._runtime is not self.runtime:
            raise TypeError('execute_command requires a real QQCommandSource from this Runtime')

    def _format_error(self: Self, error: CommandError, source: QQCommandSource | ConsoleSource) -> None:
        if error.is_handled():
            return
        key = 'mcdreforged.command_exception.' + string_utils.hump_to_underline(type(error).__name__)
        try:
            if isinstance(error, RequirementNotMet) and error.has_custom_reason():
                message = error.get_reason()
            else:
                args = () if isinstance(error, RequirementNotMet) else error.get_error_data()
                message = self.runtime.translation_manager.tr(key, *args, language=source.get_preference().language, allow_failure=False)
            error.set_message(message)
        except KeyError:
            self.logger.debug('Cannot translate command error %s', key)
        source.reply(QText(error.to_rtext().to_plain_text()))

    def _traverse(self: Self, command: str, source: QQCommandSource, purpose: TraversePurpose) -> CommandSuggestions | None:
        roots = self.root_nodes.get(utils.get_element(command), [])
        suggestions = CommandSuggestions()
        if purpose is TraversePurpose.SUGGEST and not roots:
            return CommandSuggestions([CommandSuggestion('', literal) for literal in self.root_nodes])
        for holder in tuple(roots):
            plugin, node = holder.plugin, holder.node
            if not plugin.in_states({PluginState.READY}):
                continue
            try:
                with self.runtime.plugin_manager.with_plugin_context(plugin):
                    if source.scene not in holder.scope:
                        raise RequirementNotMet('', command, 'Command is not available in this QQ scene')
                    if purpose is TraversePurpose.EXECUTE:
                        node._entry_execute(source, command)
                    else:
                        suggestions.extend(node._entry_generate_suggestions(source, command))
            except CommandError as error:
                self._format_error(error, source)
            except Exception as error:
                data = {'source': source, 'node': node, 'plugin': plugin}
                if isinstance(error, CallbackError):
                    data['for'] = error.action
                    data['path'] = '[{}]'.format(', '.join(map(str, error.context.node_path)))
                    exc_info = error.exc_info
                else:
                    exc_info = True
                self.logger.error('Error when executing command %r, %s', command, ', '.join(f'{key}={value!r}' for key, value in data.items()), exc_info=exc_info)
        if purpose is TraversePurpose.SUGGEST:
            return suggestions

    def suggest_console(self: Self, command: str, source: ConsoleSource | None = None) -> CommandSuggestions:
        """Suggest only the framework administration tree for this console.
        
        :param command: Partial administration command text.
        :param source: Runtime console source, or None to use a silent completion source.
        :return: Native command suggestions for the administration tree.
        """
        if not isinstance(command, str):
            raise TypeError('command must be str')
        if source is None:
            source = ConsoleSuggestionSource(self.runtime)
        if not isinstance(source, ConsoleSource) or source._runtime is not self.runtime:
            raise TypeError('Console suggestions require this Runtime console source')
        node = self.runtime.builtin_command_root
        plugin = self.runtime.plugin_manager.get_plugin_from_id('botcraft')
        if node is None or plugin is None or not plugin.in_states({PluginState.READY}):
            return CommandSuggestions()
        if utils.get_element(command) not in node.literals:
            return CommandSuggestions([CommandSuggestion('', literal) for literal in node.literals])
        try:
            with self.runtime.plugin_manager.with_plugin_context(plugin):
                return node._entry_generate_suggestions(source, command)
        except CommandError as error:
            self._format_error(error, source)
        except Exception as error:
            self.logger.error('Error suggesting console command %r', command, exc_info=error.exc_info if isinstance(error, CallbackError) else True)
        return CommandSuggestions()

    def execute_console(self: Self, command: str, source: ConsoleSource) -> None:
        """Execute a command in the built-in console administration tree.
        
        :param command: Administration command text to parse.
        :param source: Console source owned by this runtime.
        :return: No value is returned.
        """
        if not isinstance(source, ConsoleSource) or source._runtime is not self.runtime:
            raise TypeError('Console execution requires this Runtime console source')
        node = self.runtime.builtin_command_root
        plugin = self.runtime.plugin_manager.get_plugin_from_id('botcraft')
        if node is None or plugin is None or utils.get_element(command) not in node.literals:
            return
        try:
            with self.runtime.plugin_manager.with_plugin_context(plugin):
                node._entry_execute(source, command)
        except CommandError as error:
            self._format_error(error, source)
        except Exception as error:
            self.logger.error('Error executing console command %r', command, exc_info=error.exc_info if isinstance(error, CallbackError) else True)
