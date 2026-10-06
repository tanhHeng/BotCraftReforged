"""Native plugin registries with QQ scope/help metadata and legacy provenance."""
import dataclasses
from collections.abc import Sequence
from typing import TYPE_CHECKING
from typing_extensions import Self
from mcdreforged.plugin.plugin_registry import (
    HelpMessage as NativeHelpMessage, PluginCommandHolder as NativePluginCommandHolder,
    PluginRegistry as NativePluginRegistry, PluginRegistryStorage as NativePluginRegistryStorage,
    DEFAULT_LISTENER_PRIORITY,
)
from mcdreforged.plugin.plugin_event import EventListener, PluginEvent
from mcdreforged.command.builder.nodes.basic import Literal
from botcraft.translation.translation_text import QQTranslationText
from .plugin_event import normalize_event_id

if TYPE_CHECKING:
    from botcraft.plugin.type.plugin import Plugin
    from botcraft.plugin.plugin_manager import PluginManager


@dataclasses.dataclass(frozen=True)
class PluginCommandHolder(NativePluginCommandHolder):
    scope: tuple[str, ...] = ('group', 'c2c')


class HelpMessage(NativeHelpMessage):
    def __init__(self, plugin, prefix, message, permission=0, scope=('group', 'c2c'), only_admin=False):
        if not isinstance(prefix, str) or not isinstance(message, (str, dict)):
            raise TypeError('Help prefix must be str and description must be str or translation dict')
        scope = tuple(scope)
        if not set(scope).issubset({'group', 'c2c'}):
            raise ValueError("scope must contain only 'group' and 'c2c'")
        self.plugin = plugin
        self.prefix = prefix
        self.message = message
        self.permission = permission
        self.scope = scope
        self.only_admin = only_admin
        self._HelpMessage__prefix_lower = prefix.lower()


class PluginRegistry(NativePluginRegistry):
    def __init__(self: Self, plugin: 'Plugin', target_storage: 'PluginRegistryStorage') -> None:
        """Create native registration storage with QQ provenance tracking.
        
        :param plugin: Plugin owning all registrations.
        :param target_storage: Combined registry receiving this plugin's registrations.
        :return: Initialize the plugin's registry.
        """
        super().__init__(plugin, target_storage)
        self._legacy_listener_ids = set()

    def clear(self: Self) -> None:
        """Clear native registrations and legacy listener provenance.
        
        :return: Remove registrations from this registry.
        """
        super().clear()
        self._legacy_listener_ids.clear()

    def register_event_listener(self: Self, event_id: PluginEvent | str, listener: EventListener) -> None:
        """Register a listener under its canonical QQ or lifecycle event.
        
        :param event_id: Event object or identifier normalized before native registration.
        :param listener: Owned native event listener.
        :return: Add the listener to this registry.
        """
        super().register_event_listener(normalize_event_id(event_id), listener)

    def register_command(self: Self, node: Literal, allow_duplicates: bool = False,
                         scope: Sequence[str] = ('group', 'c2c')) -> None:
        """Register a literal command root for QQ conversation scopes.
        
        :param node: Root command node.
        :param allow_duplicates: Whether native registration allows duplicate command roots.
        :param scope: Group and/or C2C scopes in which the command is exposed.
        :return: Store the owned command root and scope metadata.
        """
        if not isinstance(node, Literal):
            raise TypeError('Only Literal node is accepted as a root node')
        scope = tuple(scope)
        if not set(scope).issubset({'group', 'c2c'}):
            raise ValueError("scope must contain only 'group' and 'c2c'")
        self._command_roots.append(PluginCommandHolder(self.plugin, node, allow_duplicates, scope))


class PluginRegistryStorage(NativePluginRegistryStorage):
    def __init__(self: Self, plugin_manager: 'PluginManager') -> None:
        """Initialize the combined native registry and QQ help metadata.
        
        :param plugin_manager: Manager providing registered plugins and native registry ownership.
        :return: Initialize aggregate help and listener provenance storage.
        """
        super().__init__(plugin_manager)
        self.panel_help_messages = []
        self._legacy_listener_ids = set()

    def clear(self: Self) -> None:
        """Clear native and QQ aggregate registration data.
        
        :return: Remove aggregate help metadata and listener provenance.
        """
        super().clear()
        self.panel_help_messages.clear()
        self._legacy_listener_ids.clear()

    def collect(self: Self, plugin: 'Plugin', plugin_registry: PluginRegistry) -> None:
        """Collect one plugin's native and QQ registrations.
        
        :param plugin: Plugin whose registrations are being collected.
        :param plugin_registry: Registry containing the plugin's help and listener metadata.
        :return: Merge registrations into this aggregate storage.
        """
        super().collect(plugin, plugin_registry)
        self.panel_help_messages.extend(plugin_registry._help_messages)
        self._legacy_listener_ids.update(plugin_registry._legacy_listener_ids)

    def is_legacy_listener(self: Self, listener: EventListener, event_id: PluginEvent | str) -> bool:
        """Check whether an event listener uses legacy event arguments.
        
        :param listener: Listener identity to query.
        :param event_id: Event object or identifier normalized for lookup.
        :return: Whether the listener and event pair was registered through the legacy path.
        """
        return (id(listener), normalize_event_id(event_id)) in self._legacy_listener_ids
