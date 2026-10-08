"""API v2 command buttons adapted from LazyBot qq_jrrp (GPL-3.0-only).

Command buttons insert text in groups; auto-send is only supported in C2C.
Modified 2026-10-05: native BotCraft keyboard classes and translated labels.
"""

from botcraft.api.qtext import (
    QKeyboardActionCommand, QKeyboardButton, QKeyboardCustom,
    QKeyboardPermission, QKeyboardPermissionType, QKeyboardRenderData,
)
from botcraft.api.types import QQPluginServerInterface

from .messages import COMMAND, submission_template


def command_keyboard(server: QQPluginServerInterface, *, is_c2c: bool,
                     submission_id: str | None = None) -> QKeyboardCustom:
    # Only successful submissions have a withdrawal target; authorization belongs to the handler.
    commands = [
        ('fortune', COMMAND, is_c2c),
        ('submit', submission_template(server), False),
        ('help', f'{COMMAND} help', is_c2c),
    ]
    if submission_id is not None:
        commands.append(('withdraw', f'{COMMAND} withdraw {submission_id}', False))
    buttons = []
    for button_id, command, auto_send in commands:
        buttons.append(QKeyboardButton(
            id=button_id,
            render_data=QKeyboardRenderData(
                label=server.tr(f'qq_jrrp.buttons.{button_id}'),
                style=1 if button_id == 'fortune' else 0,
            ),
            action=QKeyboardActionCommand(
                data=command, permission=QKeyboardPermission(QKeyboardPermissionType.ALL),
                enter=auto_send, reply=False,
                unsupport_tips=server.tr('qq_jrrp.buttons.unsupported'),
            ),
        ))
    return QKeyboardCustom([buttons[:2], buttons[2:]] if submission_id is not None else [buttons])
