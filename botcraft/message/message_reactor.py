import re
from botcraft.utils.future_utils import report_error


class MessageReactor:
    def __init__(self, runtime):
        self.runtime = runtime

    def react(self, message):
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
