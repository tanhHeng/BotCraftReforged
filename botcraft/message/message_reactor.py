from typing import TYPE_CHECKING
from typing_extensions import Self
from botcraft.message.message_received import QQMessageReceived

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
import re
from botcraft.utils.future_utils import report_error


class MessageReactor:
    """Command dispatch for supported incoming message text."""
    def __init__(self: Self, runtime: "Runtime") -> None:
        """Create a reactor for incoming QQ command messages.
        
        :param runtime: Runtime providing command execution and error reporting.
        :return: The method returns no value.
        """
        self.runtime = runtime

    def react(self: Self, message: QQMessageReceived) -> None:
        """Execute a matching command using the original received message as its source.
        
        :param message: Received message; only string content is inspected and a leading bot mention may be removed.
        :return: The method returns no value.
        """
        content = message.message_data.content
        if not isinstance(content, str):
            return
        # Remove only a leading bot mention retained by the platform, never command prefixes or other mentions.
        bot_id = getattr(self.runtime, 'bot_user_id', None)
        if bot_id and message.event_type == 'GROUP_AT_MESSAGE_CREATE':
            content = re.sub(r'^\s*<@!?' + re.escape(bot_id) + r'>\s*', '', content)
        if self.runtime.command_manager.matches_root(content):
            try:
                source = message.get_command_source()
                self.runtime.command_manager.execute_command(content, source)
            except (ValueError, TypeError) as error:
                report_error(error, self.runtime.logger, 'QQ command source')
