"""AbstractPlugin adapter: ownership and host-bound registration/event paths."""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any, TYPE_CHECKING, NoReturn
from typing_extensions import Self
from mcdreforged.command.builder.nodes.basic import Literal
from mcdreforged.plugin.plugin_event import PluginEvent
from botcraft.plugin.plugin_registry import HelpMessage
from botcraft.logging.logger import Logger as BotCraftLogger

if TYPE_CHECKING:
    from botcraft.plugin.plugin_manager import PluginManager
from mcdreforged.plugin.type.plugin import AbstractPlugin
from mcdreforged.plugin.type.common import PluginState
from mcdreforged.plugin.plugin_event import EventListener
from botcraft.plugin.plugin_event import normalize_event_id
from botcraft.plugin.plugin_registry import PluginRegistry
from botcraft.utils.exception import UnsupportedOperationError


class Plugin(AbstractPlugin):
    def __init__(self: Self, plugin_manager: PluginManager) -> None:
        """Initialize a plugin record owned by a BotCraft manager.
        
        :param plugin_manager: Manager providing the runtime and registry storage.
        :return: No value is returned.
        """
        self.plugin_manager = plugin_manager
        self.runtime = plugin_manager.runtime
        self.state = PluginState.UNINITIALIZED
        self.plugin_registry = PluginRegistry(self, plugin_manager.registry_storage)
        from botcraft.plugin.si.plugin_server_interface import QQPluginServerInterface
        self.server_interface = QQPluginServerInterface(self.runtime, self)

    @property
    def logger(self: Self) -> BotCraftLogger:
        """Return the runtime logger used by this plugin.
        
        :return: Logger shared with the owning runtime.
        """
        return self.runtime.logger

    def _check_state(self: Self) -> None:
        self.assert_state({PluginState.LOADED, PluginState.READY}, 'Only loaded or ready plugins may register')


    def register_event_listener(self: Self, event: PluginEvent | str, listener: EventListener) -> None:
        """Register a listener while the plugin is loaded or ready.
        
        :param event: Event object or identifier, including native lifecycle aliases.
        :param listener: Listener associated with this plugin.
        :return: No value is returned.
        """
        self._check_state()
        self.plugin_registry.register_event_listener(normalize_event_id(event), listener)

    def register_command(self: Self, node: Literal, *, allow_duplicates: bool = False, scope: Sequence[str] = ('group', 'c2c')) -> None:
        """Register a command root in the selected QQ scenes.
        
        :param node: Native literal command root.
        :param allow_duplicates: Allow the root to coexist with duplicate literals.
        :param scope: QQ scenes where the root is executable.
        :return: No value is returned.
        """
        self._check_state()
        self.plugin_registry.register_command(node, allow_duplicates, scope)

    def register_help_message(self: Self, help_message: HelpMessage) -> None:
        """Register a help record owned by this plugin.
        
        :param help_message: Help description, permissions and scene scope.
        :return: No value is returned.
        """
        self._check_state()
        self.plugin_registry.register_help_message(help_message)

    def register_translation(self: Self, language: str, mapping: Mapping[str, Any]) -> None:
        """Register plugin translation entries.
        
        :param language: Language identifier for these entries.
        :param mapping: Nested translation keys and open translation values.
        :return: No value is returned.
        """
        self._check_state()
        self.plugin_registry.register_translation(language, mapping)

    def register_server_handler(self: Self, *_args: Any, **_kwargs: Any) -> NoReturn:
        """Reject unsupported Minecraft server handler registration.
        
        :param _args: Native callback arguments, which are not supported by QQ plugins.
        :param _kwargs: Native callback keyword arguments, which are not supported by QQ plugins.
        :raises UnsupportedOperationError: Minecraft server handler registration has no QQ equivalent.
        """
        raise UnsupportedOperationError('QQ plugins cannot register server handlers')

    def register_info_filter(self: Self, *_args: Any, **_kwargs: Any) -> NoReturn:
        """Reject unsupported Minecraft info filter registration.
        
        :param _args: Native callback arguments, which are not supported by QQ plugins.
        :param _kwargs: Native callback keyword arguments, which are not supported by QQ plugins.
        :raises UnsupportedOperationError: Minecraft info filtering has no QQ equivalent.
        """
        raise UnsupportedOperationError('QQ plugins cannot register info filters')

    def get_plugin_command_source(self: Self) -> NoReturn:
        """Reject creation of an unsupported plugin command source.
        
        :raises UnsupportedOperationError: Plugins cannot fabricate a QQ command source.
        """
        raise UnsupportedOperationError('QQ plugins have no plugin command source')

    def receive_event(self: Self, event: PluginEvent | str, args: tuple[Any, ...]) -> None:
        """Synchronously invoke listeners for a ready plugin.
        
        :param event: Event object or identifier to dispatch.
        :param args: Plugin callback positional arguments.
        :return: No value is returned.
        """
        self.assert_state({PluginState.READY})
        for listener in self.plugin_registry.get_event_listeners(normalize_event_id(event)):
            try:
                self.plugin_manager.trigger_listener(listener, args).result()
            except Exception:
                self.runtime.logger.exception('Direct listener triggering failed: plugin %s, event %s, listener %s', self, event, listener)


