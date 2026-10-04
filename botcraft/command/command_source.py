from contextlib import contextmanager
from copy import deepcopy
from mcdreforged.command.command_source import CommandSource


class QQCommandSource(CommandSource):
    """Preserve original received facts; resolve permissions and language from current services."""
    def __init__(self, runtime, message):
        from botcraft.message.message_received import QQMessageReceived
        if not isinstance(message, QQMessageReceived) or message._runtime is not runtime:
            raise TypeError('QQ source requires a message from this Runtime')
        user = deepcopy(message.original_user)
        user.require_identity()
        scene, conversation = user.route()
        msg_id = message.raw_payload.get('d', {}).get('id')
        if not isinstance(msg_id, str) or not msg_id:
            raise ValueError('Received message has no valid msg_id')
        self._runtime = runtime
        self.origin_received = message
        self.user = user
        self.scene = scene
        self.conversation = conversation
        self.msg_id = msg_id
        self.message_data = message.message_data

    def get_server(self):
        return self._runtime.server_interface

    def get_permission_level(self):
        return self._runtime.permission_manager.get_permission(self)

    def get_preference(self):
        return self._runtime.preference_manager.get_preference(self)

    @contextmanager
    def preferred_language_context(self):
        with self._runtime.translation_manager.language_context(self.get_preference().language):
            yield

    def reply(self, message, *, refer_msg=None, return_future=False):
        return self.get_server().reply(self, message, refer_msg=refer_msg, return_future=return_future)


class ConsoleSource(CommandSource):
    """Framework administration source, not accepted by the public execute_command API."""
    def __init__(self, runtime):
        self._runtime = runtime

    @property
    def is_console(self):
        return True

    def get_server(self):
        return self._runtime.server_interface

    def get_permission_level(self):
        return 4

    def get_preference(self):
        return self._runtime.preference_manager.get_console_preference()

    @contextmanager
    def preferred_language_context(self):
        with self._runtime.translation_manager.language_context(self.get_preference().language):
            yield

    def reply(self, message, **kwargs):
        from botcraft.message.qtext.text import QTextBase
        if isinstance(message, QTextBase):
            message = message.to_plain_text()
        elif hasattr(message, 'to_plain_text'):
            message = message.to_plain_text()
        self._runtime.logger.info('%s', message)
