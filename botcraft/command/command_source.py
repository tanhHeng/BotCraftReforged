from __future__ import annotations

from concurrent.futures import Future
from typing import Iterator, TYPE_CHECKING
from typing_extensions import Self

from mcdreforged.preference.preference_manager import PreferenceItem
from botcraft.message.message_received import QQMessageReceived
from botcraft.message.message_receipt import QQMessageReceipt
from botcraft.message.qtext.text import QTextBase

if TYPE_CHECKING:
    from botcraft.plugin.si.server_interface import QQServerInterface
    from botcraft.runtime import Runtime

from contextlib import contextmanager
from copy import deepcopy
from mcdreforged.command.command_source import CommandSource


class QQCommandSource(CommandSource):
    """Preserve original received facts; resolve permissions and language from current services."""
    def __init__(self: Self, runtime: Runtime, message: QQMessageReceived) -> None:
        """Capture the original facts of a QQ message as a command source.
        
        :param runtime: Runtime that received the message.
        :param message: Received message from this runtime with a valid user route and msg_id.
        :return: No value is returned.
        """
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

    def get_server(self: Self) -> QQServerInterface:
        """Get the basic QQ interface owning this source.
        
        :return: The source runtime's basic server interface.
        """
        return self._runtime.server_interface

    def get_permission_level(self: Self) -> int:
        """Resolve this source's current permission level.
        
        :return: The effective numeric PermissionLevel value for the original user.
        """
        return self._runtime.permission_manager.get_permission(self)

    def get_preference(self: Self) -> PreferenceItem:
        """Get current preferences for this source's original user.
        
        :return: A preference copy resolved by the current preference service.
        """
        return self._runtime.preference_manager.get_preference(self)

    @contextmanager
    def preferred_language_context(self: Self) -> Iterator[None]:
        """Temporarily select this source's current preferred language.
        
        :return: A context manager restoring the previous language on exit.
        """
        with self._runtime.translation_manager.language_context(self.get_preference().language):
            yield

    def reply(self: Self, message: str | QTextBase, *, refer_msg: QQMessageReceived | QQMessageReceipt | None = None, return_future: bool = False) -> Future[QQMessageReceipt] | None:
        """Reply using the original received message's passive association.
        
        :param message: Plain or QQ text, evaluated in this source's preferred language.
        :param refer_msg: Optional same-conversation message containing a reference index, not a passive msg_id.
        :param return_future: Whether to expose the concurrent future; False does not wait for delivery.
        :return: A future resolving to the sent receipt when requested, otherwise None.
        """
        return self.get_server().reply(self, message, refer_msg=refer_msg, return_future=return_future)


class ConsoleSource(CommandSource):
    """Framework administration source, not accepted by the public execute_command API."""
    def __init__(self: Self, runtime: Runtime) -> None:
        """Create the framework administration source for a runtime.
        
        :param runtime: Runtime whose console commands and preferences this source uses.
        :return: No value is returned.
        """
        self._runtime = runtime

    @property
    def is_console(self: Self) -> bool:
        """Identify this source as the framework console.
        
        :return: Always True for the framework console.
        """
        return True

    def get_server(self: Self) -> QQServerInterface:
        """Get the basic QQ interface owning this console source.
        
        :return: The runtime's basic server interface.
        """
        return self._runtime.server_interface

    def get_permission_level(self: Self) -> int:
        """Get the framework console's administration permission.
        
        :return: The console permission level of 4.
        """
        return 4

    def get_preference(self: Self) -> PreferenceItem:
        """Get the current framework console preference.
        
        :return: A console preference copy or the current default preference.
        """
        return self._runtime.preference_manager.get_console_preference()

    @contextmanager
    def preferred_language_context(self: Self) -> Iterator[None]:
        """Temporarily select the console's preferred language.
        
        :return: A context manager restoring the previous language on exit.
        """
        with self._runtime.translation_manager.language_context(self.get_preference().language):
            yield

    def reply(self, message, **kwargs):
        from botcraft.message.qtext.text import QTextBase
        if isinstance(message, QTextBase):
            message = message.to_plain_text()
        elif hasattr(message, 'to_plain_text'):
            message = message.to_plain_text()
        self._runtime.logger.info('%s', message)
