"""Native regular-plugin state machine with QQ callbacks and logging."""
from __future__ import annotations
from typing import TYPE_CHECKING
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.plugin.plugin_manager import PluginManager
from mcdreforged.plugin.plugin_event import PluginEvent
import re
from pathlib import Path
from mcdreforged.plugin.type.regular_plugin import RegularPlugin as NativeRegularPlugin
from mcdreforged.plugin.type.common import PluginState
from mcdreforged.plugin.plugin_event import EventListener, LiteralEvent
from mcdreforged.plugin.plugin_registry import DEFAULT_LISTENER_PRIORITY
from botcraft.plugin._native import bind_native
from botcraft.plugin.plugin_event import PluginEvents, normalize_event_id
from .plugin import Plugin


class RegularPlugin(Plugin, NativeRegularPlugin):
    def __init__(self: Self, plugin_manager: PluginManager, file_path: str | Path) -> None:
        """Initialize a regular plugin record without changing the native state machine.
        
        :param plugin_manager: Manager owning the record.
        :param file_path: Plugin file or directory to load.
        :return: No value is returned.
        """
        Plugin.__init__(self, plugin_manager)
        self.file_path = Path(file_path)
        self.file_name = self.file_path.name
        self.file_modify_time = None
        self._RegularPlugin__metadata = None
        self.entry_module_instance = None
        self.old_entry_module_instance = None
        self.decorated_event_listeners = []

    load = bind_native(NativeRegularPlugin.load, runtime=True)
    reload = bind_native(NativeRegularPlugin.reload, runtime=True)
    _native_unload = bind_native(NativeRegularPlugin._on_unload, runtime=True)

    def _reset(self: Self) -> None:
        NativeRegularPlugin._reset(self)
        self.decorated_event_listeners.clear()

    def _on_unload(self: Self) -> None:
        self._native_unload()
        self.decorated_event_listeners.clear()
        self.plugin_registry.clear()

    def _register_default_listeners(self: Self) -> None:
        for event in PluginEvents.get_event_list():
            callback = getattr(self.entry_module_instance, event.default_method_name, None)
            if callable(callback):
                listener = EventListener(self, callback, DEFAULT_LISTENER_PRIORITY)
                self.register_event_listener(event, listener)
                self.plugin_registry._legacy_listener_ids.add((id(listener), normalize_event_id(event)))
        for name, callback in vars(self.entry_module_instance).items():
            match = re.fullmatch(r'on_([a-z0-9_]+)_event', name, re.IGNORECASE)
            if match and callable(callback) and name.lower() != 'on_qq_event':
                self.register_event_listener(LiteralEvent(normalize_event_id(match.group(1))), EventListener(self, callback, DEFAULT_LISTENER_PRIORITY))
        for event, listener in self.decorated_event_listeners:
            self.register_event_listener(event, listener)
        self.decorated_event_listeners.clear()

    def register_event_listener(self: Self, event: PluginEvent | str, listener: EventListener) -> None:
        """Queue import-time listeners or register them on a loaded plugin.
        
        :param event: Event object or identifier.
        :param listener: Listener associated with this plugin.
        :return: No value is returned.
        """
        if self.in_states({PluginState.LOADING}):
            self.decorated_event_listeners.append((event, listener))
        else:
            Plugin.register_event_listener(self, event, listener)
