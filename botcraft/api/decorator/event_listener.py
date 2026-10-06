"""Decorators that register against the active QQ plugin, not MCDR globals."""
from typing import Callable, TypeVar
from mcdreforged.plugin.plugin_event import PluginEvent, EventListener
from botcraft.plugin.plugin_event import normalize_event_id
from botcraft.plugin.si.qq_server_interface_mixin import ServerInterfaceMixin

_Callback = TypeVar('_Callback', bound=Callable[..., object])


def qq_event_listener(event: PluginEvent | str, *, priority: int = 1000) -> Callable[[_Callback], _Callback]:
    """Register the decorated callback against the current QQ plugin.
    
    :param event: Event object or ID to listen for; the plugin context is resolved on decoration.
    :param priority: Native event-listener priority.
    :return: A decorator that registers and returns the original callback unchanged.
    """
    if not isinstance(event, (PluginEvent, str)):
        raise TypeError('An event parameter is required')
    def wrapper(callback: _Callback) -> _Callback:
        plugin = ServerInterfaceMixin.psi()._plugin
        listener = EventListener(plugin, callback, priority)
        plugin.register_event_listener(normalize_event_id(event), listener)
        return callback
    return wrapper


def event_listener(event: PluginEvent | str, *, priority: int = 1000) -> Callable[[_Callback], _Callback]:
    """Register a callback against the current QQ plugin using the QQ decorator.
    
    :param event: Event object or ID to listen for.
    :param priority: Native event-listener priority.
    :return: A decorator preserving the original callback and its callable type.
    """
    return qq_event_listener(event, priority=priority)
