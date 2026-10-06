"""Official QQ keyboard payloads with atomic, chainable field setters."""
from typing import Any, TypeAlias, TypeVar, Union
from typing_extensions import Self
import copy
import re
from abc import ABC, abstractmethod
from enum import IntEnum

T = TypeVar("T", str, int, bool)
E = TypeVar("E", bound=IntEnum)
KeyboardField: TypeAlias = Union[str, int, bool, list[str], "_KeyboardObject", None]
KeyboardState: TypeAlias = dict[str, KeyboardField]


class QKeyboardActionType(IntEnum):
    """Official button action codes; legal integer codes are also accepted."""
    JUMP = 0
    CALLBACK = 1
    COMMAND = 2


class QKeyboardPermissionType(IntEnum):
    """Official permission codes for specified users, administrators or everyone."""
    SPECIFY = 0
    ADMIN = 1
    ALL = 2


def _optional(value: T | None, cls: type[T], name: str) -> None:
    if value is not None and type(value) is not cls:
        raise TypeError('{} must be {}'.format(name, cls.__name__))


def _enum(value: E | int, cls: type[E], name: str) -> E:
    if not isinstance(value, cls) and type(value) is not int:
        raise TypeError('{} must be a legal integer or {}'.format(name, cls.__name__))
    try:
        return cls(value)
    except ValueError:
        raise ValueError('Invalid {}: {!r}'.format(name, value)) from None


def _nested(value: "_KeyboardObject | None", cls: "type[_KeyboardObject]", name: str) -> None:
    if value is not None:
        if not isinstance(value, cls):
            raise TypeError('{} must be {}'.format(name, cls.__name__))
        value.to_payload()


class _KeyboardObject:
    _fields = ()

    def copy(self: Self) -> Self:
        """Deep-copy this keyboard component.
        
        :return: An independent component of the same concrete type.
        """
        return copy.deepcopy(self)

    def _state(self: Self) -> KeyboardState:
        return {name: getattr(self, name) for name in self._fields}

    def _initialize(self: Self, state: KeyboardState) -> None:
        self._validate(state)
        for name, value in state.items():
            setattr(self, name, value)

    def _set(self: Self, name: str, value: KeyboardField) -> Self:
        state = self._state()
        state[name] = value
        self._validate(state)
        setattr(self, name, state[name])
        return self

    def to_payload(self: Self) -> dict[str, Any]:
        """Validate and encode the component, omitting None but retaining False and zero.
        
        :return: An independent dictionary containing the encoded component fields.
        """
        state = self._state()
        self._validate(state)
        result = {}
        for name, value in state.items():
            if value is not None:
                if isinstance(value, _KeyboardObject):
                    value = value.to_payload()
                elif isinstance(value, IntEnum):
                    value = value.value
                else:
                    value = copy.deepcopy(value)
                result[name] = value
        return result


class QKeyboardBase(ABC):
    """Base contract for template and custom QQ keyboards."""
    def copy(self: Self) -> Self:
        """Deep-copy this keyboard and its nested components.
        
        :return: An independent keyboard of the same concrete type.
        """
        return copy.deepcopy(self)

    @abstractmethod
    def to_payload(self: Self) -> dict[str, Any]:
        """Validate and encode the keyboard for a QQ message payload.
        
        :return: The encoded keyboard fields.
        """
        raise NotImplementedError


class QKeyboardTemplate(QKeyboardBase):
    """A keyboard referencing a non-empty official template ID."""
    def __init__(self: Self, id: str) -> None:
        """Create a keyboard referring to an official template.
        
        :param id: A non-empty platform keyboard template ID.
        :return: The method returns no value.
        """
        self.set_id(id)

    def set_id(self: Self, value: str) -> Self:
        """Validate and replace the template ID.
        
        :param value: A non-empty platform keyboard template ID.
        :return: This keyboard for chained operations.
        """
        if type(value) is not str:
            raise TypeError('Keyboard template id must be a string')
        if not value:
            raise ValueError('Keyboard template id must not be empty')
        self.id = value
        return self

    def to_payload(self: Self) -> dict[str, Any]:
        """Validate and encode the referenced keyboard template.
        
        :return: A dictionary containing the non-empty template ID.
        """
        if type(self.id) is not str or not self.id:
            raise ValueError('Keyboard template requires a non-empty string id')
        return {'id': self.id}


class QKeyboardRenderData(_KeyboardObject):
    """Optional button labels and style, validated before mutation."""
    _fields = ('label', 'visited_label', 'style')

    def __init__(self: Self, label: str | None = None, visited_label: str | None = None, style: int | None = None) -> None:
        """Create and validate a QKeyboardRenderData component.
        
        :param label: Optional label with at most 10 characters.
        :param visited_label: Optional label shown after the button is visited.
        :param style: Optional render style: 0, 1, 3 or 4; zero is retained.
        :return: The method returns no value.
        """
        self._initialize(dict(label=label, visited_label=visited_label, style=style))

    def _validate(self: Self, state: KeyboardState) -> None:
        _optional(state['label'], str, 'label')
        _optional(state['visited_label'], str, 'visited_label')
        _optional(state['style'], int, 'style')
        if state['label'] is not None and len(state['label']) > 10:
            raise ValueError('Button label exceeds 10 characters')
        if state['style'] is not None and state['style'] not in (0, 1, 3, 4):
            raise ValueError('Unsupported keyboard render style')

    def set_label(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the label field.
        
        :param value: Optional label with at most 10 characters. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('label', value)

    def set_visited_label(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the visited label field.
        
        :param value: Optional label shown after the button is visited. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('visited_label', value)

    def set_style(self: Self, value: int | None) -> Self:
        """Validate and atomically replace the style field.
        
        :param value: Optional render style: 0, 1, 3 or 4; zero is retained. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('style', value)


class QKeyboardModal(_KeyboardObject):
    """Optional confirmation dialog text with platform length restrictions."""
    _fields = ('content', 'confirm_text', 'cancel_text')

    def __init__(self: Self, content: str | None = None, confirm_text: str | None = None, cancel_text: str | None = None) -> None:
        """Create and validate a QKeyboardModal component.
        
        :param content: Optional confirmation text with at most 40 characters and no URL.
        :param confirm_text: Optional confirmation button text with at most 4 characters.
        :param cancel_text: Optional cancellation button text with at most 4 characters.
        :return: The method returns no value.
        """
        self._initialize(dict(content=content, confirm_text=confirm_text, cancel_text=cancel_text))

    def _validate(self: Self, state: KeyboardState) -> None:
        for name, limit in (('content', 40), ('confirm_text', 4), ('cancel_text', 4)):
            value = state[name]
            _optional(value, str, name)
            if value is not None and len(value) > limit:
                raise ValueError('{} exceeds {} characters'.format(name, limit))
        content = state['content']
        if content and re.search(r'(?:[a-z][a-z0-9+.-]*://|www\.)', content, re.IGNORECASE):
            raise ValueError('Modal content must not contain a URL')

    def set_content(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the content field.
        
        :param value: Optional confirmation text with at most 40 characters and no URL. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('content', value)

    def set_confirm_text(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the confirm text field.
        
        :param value: Optional confirmation button text with at most 4 characters. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('confirm_text', value)

    def set_cancel_text(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the cancel text field.
        
        :param value: Optional cancellation button text with at most 4 characters. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('cancel_text', value)


class QKeyboardPermission(_KeyboardObject):
    """A validated audience rule whose type cannot be switched after creation."""
    _fields = ('type', 'specify_user_ids')

    def __init__(self: Self, type: QKeyboardPermissionType | int = QKeyboardPermissionType.ALL, specify_user_ids: list[str] | None = None) -> None:
        """Create and validate a QKeyboardPermission component.
        
        :param type: A legal enum value or integer code; booleans are not accepted as codes.
        :param specify_user_ids: Non-empty string ID list for SPECIFY; omitted for ADMIN and ALL.
        :return: The method returns no value.
        """
        self._initialize(dict(type=type, specify_user_ids=specify_user_ids))

    def _validate(self: Self, state: KeyboardState) -> None:
        state['type'] = _enum(state['type'], QKeyboardPermissionType, 'permission type')
        users = state['specify_user_ids']
        if state['type'] == QKeyboardPermissionType.SPECIFY:
            if type(users) is not list:
                raise TypeError('SPECIFY permission requires a user id list')
            if not users or any(type(user) is not str or not user for user in users):
                raise ValueError('SPECIFY permission requires non-empty string user ids')
        elif users is not None:
            raise ValueError('ADMIN/ALL permissions do not accept a user list')

    def set_type(self: Self, value: QKeyboardPermissionType | int) -> Self:
        """Validate the permission type without allowing it to switch to another type.
        
        :param value: A legal enum value or integer code.
        :return: This component for chained operations.
        """
        value = _enum(value, QKeyboardPermissionType, 'permission type')
        if value != self.type:
            raise ValueError('Create a new permission object to switch permission type')
        return self._set('type', value)

    def set_specify_user_ids(self: Self, value: list[str] | None) -> Self:
        """Validate and atomically replace the specify user ids field.
        
        :param value: Non-empty string ID list for SPECIFY; omitted for ADMIN and ALL. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('specify_user_ids', value)


class QKeyboardAction(_KeyboardObject):
    """A validated action with optional fields; None is omitted, False and zero are kept."""
    _fields = ('type', 'permission', 'data', 'unsupport_tips', 'enter', 'reply', 'anchor', 'modal')
    _fixed_type = None

    def __init__(self: Self, type: QKeyboardActionType | int = QKeyboardActionType.JUMP, permission: QKeyboardPermission | None = None, data: str | None = None, unsupport_tips: str | None = None, enter: bool | None = None, reply: bool | None = None, anchor: int | None = None, modal: QKeyboardModal | None = None) -> None:
        """Create and validate a QKeyboardAction component.
        
        :param type: A legal enum value or integer code; booleans are not accepted as codes.
        :param permission: Optional permission rule.
        :param data: Action data; required for callback and command actions.
        :param unsupport_tips: Optional text shown when the action is unsupported.
        :param enter: Optional enter flag; False is retained in the payload.
        :param reply: Optional reply flag; False is retained in the payload.
        :param anchor: Optional anchor value; zero is retained in the payload.
        :param modal: Optional confirmation dialog.
        :return: The method returns no value.
        """
        self._initialize(dict(type=type, permission=permission, data=data,
                              unsupport_tips=unsupport_tips, enter=enter, reply=reply,
                              anchor=anchor, modal=modal))

    def _validate(self: Self, state: KeyboardState) -> None:
        state['type'] = _enum(state['type'], QKeyboardActionType, 'action type')
        if self._fixed_type is not None and state['type'] != self._fixed_type:
            raise ValueError('Action subclass type cannot be changed')
        _nested(state['permission'], QKeyboardPermission, 'permission')
        _nested(state['modal'], QKeyboardModal, 'modal')
        _optional(state['data'], str, 'data')
        _optional(state['unsupport_tips'], str, 'unsupport_tips')
        _optional(state['enter'], bool, 'enter')
        _optional(state['reply'], bool, 'reply')
        _optional(state['anchor'], int, 'anchor')
        if state['type'] in (QKeyboardActionType.CALLBACK, QKeyboardActionType.COMMAND) and state['data'] is None:
            raise ValueError('Callback/command actions require data')

    def set_type(self: Self, value: QKeyboardActionType | int) -> Self:
        """Validate and set the action type; fixed-type subclasses cannot change their type.
        
        :param value: A legal enum value or integer code.
        :return: This component for chained operations.
        """
        return self._set('type', value)

    def set_permission(self: Self, value: QKeyboardPermission | None) -> Self:
        """Validate and atomically replace the permission field.
        
        :param value: Optional permission rule. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('permission', value)

    def set_data(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the data field.
        
        :param value: Action data; required for callback and command actions. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('data', value)

    def set_unsupport_tips(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the unsupport tips field.
        
        :param value: Optional text shown when the action is unsupported. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('unsupport_tips', value)

    def set_enter(self: Self, value: bool | None) -> Self:
        """Validate and atomically replace the enter field.
        
        :param value: Optional enter flag; False is retained in the payload. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('enter', value)

    def set_reply(self: Self, value: bool | None) -> Self:
        """Validate and atomically replace the reply field.
        
        :param value: Optional reply flag; False is retained in the payload. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('reply', value)

    def set_anchor(self: Self, value: int | None) -> Self:
        """Validate and atomically replace the anchor field.
        
        :param value: Optional anchor value; zero is retained in the payload. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('anchor', value)

    def set_modal(self: Self, value: QKeyboardModal | None) -> Self:
        """Validate and atomically replace the modal field.
        
        :param value: Optional confirmation dialog. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('modal', value)


class QKeyboardActionJump(QKeyboardAction):
    """A jump action with a fixed JUMP action type."""
    _fixed_type = QKeyboardActionType.JUMP

    def __init__(self: Self, data: str | None = None, **kwargs: QKeyboardPermission | QKeyboardModal | str | bool | int | None) -> None:
        """Create and validate a QKeyboardActionJump component.
        
        :param data: Action data; required for callback and command actions.
        :param kwargs: Other QKeyboardAction fields: permission, unsupport_tips, enter, reply, anchor and modal.
        :return: The method returns no value.
        """
        super().__init__(type=self._fixed_type, data=data, **kwargs)


class QKeyboardActionCallback(QKeyboardAction):
    """A callback action with required data and a fixed CALLBACK type."""
    _fixed_type = QKeyboardActionType.CALLBACK

    def __init__(self: Self, data: str, **kwargs: QKeyboardPermission | QKeyboardModal | str | bool | int | None) -> None:
        """Create and validate a QKeyboardActionCallback component.
        
        :param data: Action data; required for callback and command actions.
        :param kwargs: Other QKeyboardAction fields: permission, unsupport_tips, enter, reply, anchor and modal.
        :return: The method returns no value.
        """
        super().__init__(type=self._fixed_type, data=data, **kwargs)


class QKeyboardActionCommand(QKeyboardAction):
    """A command action with required data and a fixed COMMAND type."""
    _fixed_type = QKeyboardActionType.COMMAND

    def __init__(self: Self, data: str, **kwargs: QKeyboardPermission | QKeyboardModal | str | bool | int | None) -> None:
        """Create and validate a QKeyboardActionCommand component.
        
        :param data: Action data; required for callback and command actions.
        :param kwargs: Other QKeyboardAction fields: permission, unsupport_tips, enter, reply, anchor and modal.
        :return: The method returns no value.
        """
        super().__init__(type=self._fixed_type, data=data, **kwargs)


class QKeyboardButton(_KeyboardObject):
    """A validated button component; custom keyboards enforce ID uniqueness."""
    _fields = ('id', 'render_data', 'action', 'group_id')

    def __init__(self: Self, id: str | None = None, render_data: QKeyboardRenderData | None = None, action: QKeyboardAction | None = None, group_id: str | None = None) -> None:
        """Create and validate a QKeyboardButton component.
        
        :param id: Optional button ID; IDs must be unique within a custom keyboard.
        :param render_data: Optional button label and style configuration.
        :param action: Optional validated button action.
        :param group_id: Optional platform button group ID.
        :return: The method returns no value.
        """
        self._initialize(dict(id=id, render_data=render_data, action=action, group_id=group_id))

    def _validate(self: Self, state: KeyboardState) -> None:
        _optional(state['id'], str, 'id')
        _optional(state['group_id'], str, 'group_id')
        _nested(state['render_data'], QKeyboardRenderData, 'render_data')
        _nested(state['action'], QKeyboardAction, 'action')

    def set_id(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the id field.
        
        :param value: Optional button ID; IDs must be unique within a custom keyboard. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('id', value)

    def set_render_data(self: Self, value: QKeyboardRenderData | None) -> Self:
        """Validate and atomically replace the render data field.
        
        :param value: Optional button label and style configuration. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('render_data', value)

    def set_action(self: Self, value: QKeyboardAction | None) -> Self:
        """Validate and atomically replace the action field.
        
        :param value: Optional validated button action. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('action', value)

    def set_group_id(self: Self, value: str | None) -> Self:
        """Validate and atomically replace the group id field.
        
        :param value: Optional platform button group ID. Use None to omit an optional field.
        :return: This component for chained operations.
        """
        return self._set('group_id', value)


class QKeyboardCustom(QKeyboardBase):
    """A custom keyboard holding button rows with unique non-None button IDs."""
    def __init__(self: Self, rows: list[list[QKeyboardButton]] | None = None) -> None:
        """Create a custom keyboard from button rows.
        
        :param rows: A list of button lists, or None for an empty keyboard. Button IDs must be unique.
        :return: The method returns no value.
        """
        self.set_rows([] if rows is None else rows)

    @staticmethod
    def _encode_rows(rows: list[list[QKeyboardButton]]) -> list[dict[str, list[dict[str, Any]]]]:
        if type(rows) is not list:
            raise TypeError('Keyboard rows must be a list of button lists')
        result = []
        ids = set()
        for row in rows:
            if type(row) is not list:
                raise TypeError('Each keyboard row must be a list')
            buttons = []
            for button in row:
                if not isinstance(button, QKeyboardButton):
                    raise TypeError('Keyboard rows must contain QKeyboardButton objects')
                payload = button.to_payload()
                if button.id is not None:
                    if button.id in ids:
                        raise ValueError('Duplicate keyboard button id: {}'.format(button.id))
                    ids.add(button.id)
                buttons.append(payload)
            result.append({'buttons': buttons})
        return result

    def set_rows(self: Self, value: list[list[QKeyboardButton]]) -> Self:
        """Validate all rows and button IDs before replacing the rows.
        
        :param value: Button rows with unique non-None IDs across the entire keyboard.
        :return: This keyboard for chained operations.
        """
        self._encode_rows(value)
        self.rows = value
        return self

    def to_payload(self: Self) -> dict[str, Any]:
        """Validate every button and ID, then encode the custom keyboard.
        
        :return: The custom keyboard content and encoded button rows.
        """
        return {'content': {'rows': self._encode_rows(self.rows)}}
