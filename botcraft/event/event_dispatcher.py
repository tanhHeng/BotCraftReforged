from concurrent.futures import Future
from typing import TYPE_CHECKING, Any
from typing_extensions import Self
from botcraft.event.qq_event import QQEvent

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
import json

from mcdreforged.executor.task_executor_queue import TaskPriority
from botcraft.event.event_parser import EventParser
from botcraft.message.message_received import QQMessageReceived
from botcraft.plugin.plugin_event import PluginEvents, normalize_event_id
from botcraft.utils.future_utils import observe_future

_LOG_CONTROL_CHARACTERS = {code: repr(chr(code))[1:-1] for code in (*range(32), *range(127, 160), 0x2028, 0x2029)}


class EventDispatcher:
    """Synchronous command and plugin event delivery from incoming QQ envelopes."""
    def __init__(self: Self, runtime: "Runtime") -> None:
        """Create the QQ event parser and dispatcher for a runtime.
        
        :param runtime: Runtime providing event execution, plugins and received-message logging.
        :return: The method returns no value.
        """
        self.runtime = runtime
        self.parser = EventParser(runtime)

    def submit_payload(self: Self, payload: dict[str, Any]) -> Future[None] | None:
        """Parse and register incoming facts before scheduling synchronous event processing.
        
        :param payload: Platform JSON dispatch envelope.
        :return: The observed processing future, or None when the runtime is stopping.
        """
        if self.runtime.is_stopping():
            return None
        event = self.parser.parse(payload)
        self.runtime.sender.register_incoming(event)
        future = self.runtime.sync_task_executor.submit(lambda: self.process(event), priority=TaskPriority.INFO)
        return observe_future(future, self.runtime.logger, 'QQ event dispatch')

    def _log_received_message(self: Self, event: QQEvent) -> None:
        if not self.runtime.get_config().log_received_messages or event.event_type not in self.parser.MESSAGE_EVENTS:
            return
        data = event.raw_payload.get('d')
        if not isinstance(data, dict):
            return
        parts = []
        for name in ('content', 'markdown', 'attachments', 'ark_data', 'msg_elements'):
            value = data.get(name)
            if name == 'content' and event.event_type == 'GROUP_AT_MESSAGE_CREATE' and isinstance(value, str):
                value = value.lstrip(' ')
            if value in (None, '', [], {}):
                continue
            if name == 'markdown' and isinstance(value, dict) and isinstance(value.get('content'), str):
                value = value['content']
            rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            parts.append(rendered if name in ('content', 'markdown') else f'[{name}] {rendered}')
        author = data.get('author')
        identity = author.get('id') if isinstance(author, dict) else None
        scene = 'C2C' if event.event_type == 'C2C_MESSAGE_CREATE' else 'Group'
        conversation = (author.get('user_openid') if isinstance(author, dict) else None) if scene == 'C2C' else data.get('group_openid')
        identity = identity[:6] if isinstance(identity, str) and identity else '-'
        conversation = conversation[:6] if isinstance(conversation, str) and conversation else '-'
        self.runtime.logger.info('[%s:%s] [User:%s] %s', scene,
                                 conversation.translate(_LOG_CONTROL_CHARACTERS),
                                 identity.translate(_LOG_CONTROL_CHARACTERS),
                                 ('|'.join(parts) if parts else '[empty]').translate(_LOG_CONTROL_CHARACTERS))

    def process(self: Self, event: QQEvent) -> None:
        """Process message commands and dispatch the received event to plugin listeners.
        
        :param event: Parsed or generic QQ event; model failures exclude legacy event listeners.
        :return: The method returns no value.
        """
        self._log_received_message(event)
        manager = self.runtime.plugin_manager
        if isinstance(event, QQMessageReceived):
            if event.original_user is not None:
                try:
                    self.runtime.users.record(event.original_user)
                except (ValueError, TypeError, OSError) as error:
                    from botcraft.utils.future_utils import report_error
                    report_error(error, self.runtime.logger, 'known C2C user record')
            from botcraft.message.message_reactor import MessageReactor
            MessageReactor(self.runtime).react(event)
        manager.dispatch_event(PluginEvents.QQ_EVENT, (event,))
        if isinstance(event, QQMessageReceived):
            manager.dispatch_event(PluginEvents.MESSAGE, (event,))
            if event.event_type in ('GROUP_AT_MESSAGE_CREATE', 'GROUP_MESSAGE_CREATE'):
                manager.dispatch_event(PluginEvents.GROUP_MESSAGE, (event,))
        manager.dispatch_event(normalize_event_id(event.event_type), (event,), exclude_legacy=event.model_parse_failed)
