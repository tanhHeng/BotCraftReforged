"""Native events/listeners with BotCraft lifecycle and canonical QQ IDs."""
from typing_extensions import Self
from mcdreforged.plugin.plugin_event import PluginEvent, LiteralEvent, MCDREvent, EventListener


class Event(MCDREvent):
    pass


class PluginEvents:
    PLUGIN_LOADED = Event('botcraft.plugin_loaded', 'on_load')
    PLUGIN_UNLOADED = Event('botcraft.plugin_unloaded', 'on_unload')
    BOTCRAFT_START = Event('botcraft.start', 'on_botcraft_start')
    BOTCRAFT_STOP = Event('botcraft.stop', 'on_botcraft_stop')
    QQ_EVENT = Event('botcraft.qq_event', 'on_qq_event')
    MESSAGE = Event('botcraft.message', 'on_message')
    GROUP_AT_MESSAGE = Event('group_at_message_create', 'on_group_at_message')
    GROUP_MESSAGE = Event('group_message_create', 'on_group_message')
    C2C_MESSAGE = Event('c2c_message_create', 'on_c2c_message')
    INTERACTION = Event('interaction_create', 'on_interaction')

    @classmethod
    def get_event_list(cls: type[Self]) -> list[Event]:
        """Return the known BotCraft lifecycle and QQ events.
        
        :return: Declared event objects in definition order.
        """
        return [value for value in vars(cls).values() if isinstance(value, Event)]

    @classmethod
    def get_event(cls: type[Self], event_id: str) -> PluginEvent:
        """Resolve a known event or construct a canonical literal event.
        
        :param event_id: Event identifier to normalize.
        :return: Known event object or a literal event for the normalized identifier.
        """
        canonical = normalize_event_id(event_id)
        return next((event for event in cls.get_event_list() if event.id == canonical), LiteralEvent(canonical))

    @classmethod
    def is_known_event(cls: type[Self], event_id: str) -> bool:
        """Determine whether an identifier names a declared BotCraft event.
        
        :param event_id: Event identifier to normalize.
        :return: Whether the canonical identifier belongs to a declared event.
        """
        return any(event.id == normalize_event_id(event_id) for event in cls.get_event_list())


def normalize_event_id(event: PluginEvent | str) -> str:
    """Normalize lifecycle aliases and QQ event identifiers.
    
    :param event: Event object or nonempty identifier.
    :return: Lowercase identifier with native lifecycle aliases mapped to BotCraft.
    """
    value = event.id if isinstance(event, PluginEvent) else event
    if not isinstance(value, str) or not value:
        raise TypeError('event must be PluginEvent or non-empty str')
    native_lifecycle = {'mcdr.plugin_loaded': 'botcraft.plugin_loaded', 'mcdr.plugin_unloaded': 'botcraft.plugin_unloaded'}
    canonical = value.lower()
    return native_lifecycle.get(canonical, canonical)
