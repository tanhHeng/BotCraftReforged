"""Native command registration/traversal adapted to real QQ sources and scope."""
import collections
from mcdreforged.command.command_manager import CommandManager as NativeCommandManager, TraversePurpose
from mcdreforged.command.builder import command_builder_utils as utils
from mcdreforged.command.builder.exception import CommandError, RequirementNotMet
from mcdreforged.command.builder.nodes.basic import CallbackError, CommandSuggestion, CommandSuggestions
from mcdreforged.utils import string_utils
from botcraft.message.qtext.text import QText
from botcraft.command.command_source import QQCommandSource, ConsoleSource
from mcdreforged.plugin.type.common import PluginState


class CommandManager(NativeCommandManager):
    def __init__(self, runtime):
        self.runtime = runtime
        self.logger = runtime.logger
        self.root_nodes = collections.defaultdict(list)
        self._CommandManager__preserve_command_error_display_flag = False

    def matches_root(self, command):
        return utils.get_element(command) in self.root_nodes

    def execute_command(self, command, source):
        if not isinstance(command, str):
            raise TypeError('command must be str')
        self._check_source(source)
        return self._traverse(command, source, TraversePurpose.EXECUTE)

    def suggest_command(self, command, source):
        if not isinstance(command, str):
            raise TypeError('command must be str')
        self._check_source(source)
        return self._traverse(command, source, TraversePurpose.SUGGEST)

    def _check_source(self, source):
        if not isinstance(source, QQCommandSource) or source._runtime is not self.runtime:
            raise TypeError('execute_command requires a real QQCommandSource from this Runtime')

    def _format_error(self, error, source):
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

    def _traverse(self, command, source, purpose):
        # Native traversal: first element lookup, per-root node entry, handled
        # CommandError and CallbackError diagnostics. Only QQ scope is added.
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

    def execute_console(self, command, source):
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
