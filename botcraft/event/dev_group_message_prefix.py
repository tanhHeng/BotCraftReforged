"""Temporary dev workaround for retained self-mention prefixes in full group delivery.

Delete this module and its EventParser import/call once QQ fixes the platform
content. MentionedUser remains part of the supported message model.
"""
from botcraft.message.user import MentionedUser


def normalize_group_message_content(
    content: str | None, mentions: list[MentionedUser] | None,
) -> str | None:
    """Strip one proven self-mention prefix without modifying mention facts.

    :param content: Full-group message text, or None when absent.
    :param mentions: Parsed mention facts; missing identity never triggers a guess.
    :return: Text without the leading self-mention and ASCII separator spaces,
        or the original value when the prefix cannot be identified.
    """
    if not isinstance(content, str) or not mentions:
        return content
    start = 0
    while start < len(content) and content[start] == ' ':
        start += 1
    if not content.startswith('<@', start):
        return content
    end = content.find('>', start + 2)
    if end == -1:
        return content
    identity = content[start + 2:end]
    if not identity or not any(
        mention.is_you is True and mention.id == identity for mention in mentions
    ):
        return content
    end += 1
    while end < len(content) and content[end] == ' ':
        end += 1
    return content[end:]
