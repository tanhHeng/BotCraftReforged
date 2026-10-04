import time

from botcraft.event.qq_event import QQEvent
from botcraft.message.message_data import QQMessageReceivedData
from botcraft.message.user import Scene, User


class QQMessageReceived(QQEvent):
    def __init__(self, runtime, payload, model):
        if not isinstance(model, QQMessageReceivedData):
            raise TypeError('model must be QQMessageReceivedData')
        super().__init__(runtime, payload)
        self.received_at = time.monotonic()
        self.message_data = model
        self._command_source = None
        scene = Scene.C2C if self.event_type == 'C2C_MESSAGE_CREATE' else Scene.GROUP
        raw = self.raw_payload['d']
        author = raw.get('author')
        self.original_user = User.deserialize(author) if isinstance(author, dict) else None
        if self.original_user is not None:
            self.original_user.scene = scene
            self.original_user.group_openid = raw.get('group_openid') if scene == Scene.GROUP else None
        if model.author is not None:
            model.author.scene = scene
            model.author.group_openid = raw.get('group_openid') if scene == Scene.GROUP else None
        if model.mentions is not None:
            for user in model.mentions:
                user.scene = scene
                user.group_openid = raw.get('group_openid') if scene == Scene.GROUP else None

    def get_command_source(self):
        if self._command_source is None:
            user = self.original_user
            if user is None:
                raise ValueError('Message has no original author')
            user.require_identity()
            user.route()
            msg_id = self.raw_payload['d'].get('id')
            if not isinstance(msg_id, str) or not msg_id:
                raise ValueError('Message has no original message id')
            from botcraft.command.command_source import QQCommandSource
            self._command_source = QQCommandSource(self._runtime, self)
        return self._command_source
