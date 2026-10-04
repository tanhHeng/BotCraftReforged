"""Native plugin registries with QQ scope/help metadata and legacy provenance."""
import dataclasses
from mcdreforged.plugin.plugin_registry import (
    HelpMessage as NativeHelpMessage, PluginCommandHolder as NativePluginCommandHolder,
    PluginRegistry as NativePluginRegistry, PluginRegistryStorage as NativePluginRegistryStorage,
    DEFAULT_LISTENER_PRIORITY,
)
from mcdreforged.command.builder.nodes.basic import Literal
from .plugin_event import normalize_event_id


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
    def __init__(self, plugin, target_storage):
        super().__init__(plugin, target_storage)
        self._legacy_listener_ids = set()

    def clear(self):
        super().clear()
        self._legacy_listener_ids.clear()

    def register_event_listener(self, event_id, listener):
        super().register_event_listener(normalize_event_id(event_id), listener)

    def register_command(self, node, allow_duplicates=False, scope=('group', 'c2c')):
        if not isinstance(node, Literal):
            raise TypeError('Only Literal node is accepted as a root node')
        scope = tuple(scope)
        if not set(scope).issubset({'group', 'c2c'}):
            raise ValueError("scope must contain only 'group' and 'c2c'")
        self._command_roots.append(PluginCommandHolder(self.plugin, node, allow_duplicates, scope))


class PluginRegistryStorage(NativePluginRegistryStorage):
    def __init__(self, plugin_manager):
        super().__init__(plugin_manager)
        self.panel_help_messages = []
        self._legacy_listener_ids = set()

    def clear(self):
        super().clear()
        self.panel_help_messages.clear()
        self._legacy_listener_ids.clear()

    def collect(self, plugin, plugin_registry):
        super().collect(plugin, plugin_registry)
        self.panel_help_messages.extend(plugin_registry._help_messages)
        self._legacy_listener_ids.update(plugin_registry._legacy_listener_ids)

    def is_legacy_listener(self, listener, event_id):
        return (id(listener), normalize_event_id(event_id)) in self._legacy_listener_ids
