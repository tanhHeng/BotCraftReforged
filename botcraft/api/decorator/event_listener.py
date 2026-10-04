"""Decorators that register against the active QQ plugin, not MCDR globals."""
from typing import Callable, Union
from mcdreforged.plugin.plugin_event import PluginEvent, EventListener
from botcraft.plugin.plugin_event import normalize_event_id
from botcraft.plugin.si.qq_server_interface_mixin import ServerInterfaceMixin


def qq_event_listener(event: Union[PluginEvent, str], *, priority: int = 1000):
    if not isinstance(event, (PluginEvent, str)):
        raise TypeError('An event parameter is required')
    def wrapper(callback: Callable):
        plugin = ServerInterfaceMixin.psi()._plugin
        listener = EventListener(plugin, callback, priority)
        plugin.register_event_listener(normalize_event_id(event), listener)
        return callback
    return wrapper


def event_listener(event: Union[PluginEvent, str], *, priority: int = 1000):
    return qq_event_listener(event, priority=priority)
