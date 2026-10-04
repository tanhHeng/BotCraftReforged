import copy

from botcraft.event.qq_event import QQEvent
from botcraft.event.qq_interaction import QQInteraction, QQInteractionData
from botcraft.message.message_data import QQMessageReceivedData
from botcraft.message.message_received import QQMessageReceived


class EventParser:
    MESSAGE_EVENTS = frozenset(('GROUP_AT_MESSAGE_CREATE', 'GROUP_MESSAGE_CREATE', 'C2C_MESSAGE_CREATE'))
    GENERIC_EVENTS = frozenset((
        'GROUP_ADD_ROBOT', 'GROUP_DEL_ROBOT', 'FRIEND_ADD', 'FRIEND_DEL',
        'GROUP_MSG_REJECT', 'GROUP_MSG_RECEIVE', 'C2C_MSG_REJECT', 'C2C_MSG_RECEIVE',
        'READY', 'RESUMED',
    ))

    def __init__(self, runtime):
        self._runtime = runtime

    def parse(self, payload):
        if not isinstance(payload, dict):
            raise TypeError('QQ dispatch payload must be a dict')
        event_type = payload.get('t')
        try:
            if event_type in self.MESSAGE_EVENTS:
                model = QQMessageReceivedData.deserialize(copy.deepcopy(payload.get('d')))
                if event_type == 'GROUP_AT_MESSAGE_CREATE' and isinstance(model.content, str):
                    model.content = model.content.lstrip(' ')
                return QQMessageReceived(self._runtime, payload, model)
            if event_type == 'INTERACTION_CREATE':
                model = QQInteractionData.deserialize(copy.deepcopy(payload.get('d')))
                return QQInteraction(self._runtime, payload, model)
        except (TypeError, ValueError, KeyError) as error:
            event = QQEvent(self._runtime, payload)
            event.model_parse_failed = True
            event.parse_error = error
            self._runtime.logger.warning('Failed to parse QQ event %r: %s', event_type, error, exc_info=True)
            return event
        event = QQEvent(self._runtime, payload)
        if event_type not in self.GENERIC_EVENTS:
            self._runtime.logger.warning('Unknown QQ event type: %r', event_type)
        return event
