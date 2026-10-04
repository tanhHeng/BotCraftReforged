"""Official QQ keyboard payloads with atomic, chainable field setters."""
import copy
import re
from abc import ABC, abstractmethod
from enum import IntEnum


class QKeyboardActionType(IntEnum):
    JUMP = 0
    CALLBACK = 1
    COMMAND = 2


class QKeyboardPermissionType(IntEnum):
    SPECIFY = 0
    ADMIN = 1
    ALL = 2


def _optional(value, cls, name):
    if value is not None and type(value) is not cls:
        raise TypeError('{} must be {}'.format(name, cls.__name__))


def _enum(value, cls, name):
    if not isinstance(value, cls) and type(value) is not int:
        raise TypeError('{} must be a legal integer or {}'.format(name, cls.__name__))
    try:
        return cls(value)
    except ValueError:
        raise ValueError('Invalid {}: {!r}'.format(name, value)) from None


def _nested(value, cls, name):
    if value is not None:
        if not isinstance(value, cls):
            raise TypeError('{} must be {}'.format(name, cls.__name__))
        value.to_payload()


class _KeyboardObject:
    _fields = ()

    def copy(self):
        return copy.deepcopy(self)

    def _state(self):
        return {name: getattr(self, name) for name in self._fields}

    def _initialize(self, state):
        self._validate(state)
        for name, value in state.items():
            setattr(self, name, value)

    def _set(self, name, value):
        state = self._state()
        state[name] = value
        self._validate(state)
        setattr(self, name, state[name])
        return self

    def to_payload(self):
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
    def copy(self):
        return copy.deepcopy(self)

    @abstractmethod
    def to_payload(self):
        raise NotImplementedError


class QKeyboardTemplate(QKeyboardBase):
    def __init__(self, id):
        self.set_id(id)

    def set_id(self, value):
        if type(value) is not str:
            raise TypeError('Keyboard template id must be a string')
        if not value:
            raise ValueError('Keyboard template id must not be empty')
        self.id = value
        return self

    def to_payload(self):
        if type(self.id) is not str or not self.id:
            raise ValueError('Keyboard template requires a non-empty string id')
        return {'id': self.id}


class QKeyboardRenderData(_KeyboardObject):
    _fields = ('label', 'visited_label', 'style')

    def __init__(self, label=None, visited_label=None, style=None):
        self._initialize(dict(label=label, visited_label=visited_label, style=style))

    def _validate(self, state):
        _optional(state['label'], str, 'label')
        _optional(state['visited_label'], str, 'visited_label')
        _optional(state['style'], int, 'style')
        if state['label'] is not None and len(state['label']) > 10:
            raise ValueError('Button label exceeds 10 characters')
        if state['style'] is not None and state['style'] not in (0, 1, 3, 4):
            raise ValueError('Unsupported keyboard render style')

    def set_label(self, value):
        return self._set('label', value)

    def set_visited_label(self, value):
        return self._set('visited_label', value)

    def set_style(self, value):
        return self._set('style', value)


class QKeyboardModal(_KeyboardObject):
    _fields = ('content', 'confirm_text', 'cancel_text')

    def __init__(self, content=None, confirm_text=None, cancel_text=None):
        self._initialize(dict(content=content, confirm_text=confirm_text, cancel_text=cancel_text))

    def _validate(self, state):
        for name, limit in (('content', 40), ('confirm_text', 4), ('cancel_text', 4)):
            value = state[name]
            _optional(value, str, name)
            if value is not None and len(value) > limit:
                raise ValueError('{} exceeds {} characters'.format(name, limit))
        content = state['content']
        if content and re.search(r'(?:[a-z][a-z0-9+.-]*://|www\.)', content, re.IGNORECASE):
            raise ValueError('Modal content must not contain a URL')

    def set_content(self, value):
        return self._set('content', value)

    def set_confirm_text(self, value):
        return self._set('confirm_text', value)

    def set_cancel_text(self, value):
        return self._set('cancel_text', value)


class QKeyboardPermission(_KeyboardObject):
    _fields = ('type', 'specify_user_ids')

    def __init__(self, type=QKeyboardPermissionType.ALL, specify_user_ids=None):
        self._initialize(dict(type=type, specify_user_ids=specify_user_ids))

    def _validate(self, state):
        state['type'] = _enum(state['type'], QKeyboardPermissionType, 'permission type')
        users = state['specify_user_ids']
        if state['type'] == QKeyboardPermissionType.SPECIFY:
            if type(users) is not list:
                raise TypeError('SPECIFY permission requires a user id list')
            if not users or any(type(user) is not str or not user for user in users):
                raise ValueError('SPECIFY permission requires non-empty string user ids')
        elif users is not None:
            raise ValueError('ADMIN/ALL permissions do not accept a user list')

    def set_type(self, value):
        value = _enum(value, QKeyboardPermissionType, 'permission type')
        if value != self.type:
            raise ValueError('Create a new permission object to switch permission type')
        return self._set('type', value)

    def set_specify_user_ids(self, value):
        return self._set('specify_user_ids', value)


class QKeyboardAction(_KeyboardObject):
    _fields = ('type', 'permission', 'data', 'unsupport_tips', 'enter', 'reply', 'anchor', 'modal')
    _fixed_type = None

    def __init__(self, type=QKeyboardActionType.JUMP, permission=None, data=None,
                 unsupport_tips=None, enter=None, reply=None, anchor=None, modal=None):
        self._initialize(dict(type=type, permission=permission, data=data,
                              unsupport_tips=unsupport_tips, enter=enter, reply=reply,
                              anchor=anchor, modal=modal))

    def _validate(self, state):
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

    def set_type(self, value):
        return self._set('type', value)

    def set_permission(self, value):
        return self._set('permission', value)

    def set_data(self, value):
        return self._set('data', value)

    def set_unsupport_tips(self, value):
        return self._set('unsupport_tips', value)

    def set_enter(self, value):
        return self._set('enter', value)

    def set_reply(self, value):
        return self._set('reply', value)

    def set_anchor(self, value):
        return self._set('anchor', value)

    def set_modal(self, value):
        return self._set('modal', value)


class QKeyboardActionJump(QKeyboardAction):
    _fixed_type = QKeyboardActionType.JUMP

    def __init__(self, data=None, **kwargs):
        super().__init__(type=self._fixed_type, data=data, **kwargs)


class QKeyboardActionCallback(QKeyboardAction):
    _fixed_type = QKeyboardActionType.CALLBACK

    def __init__(self, data, **kwargs):
        super().__init__(type=self._fixed_type, data=data, **kwargs)


class QKeyboardActionCommand(QKeyboardAction):
    _fixed_type = QKeyboardActionType.COMMAND

    def __init__(self, data, **kwargs):
        super().__init__(type=self._fixed_type, data=data, **kwargs)


class QKeyboardButton(_KeyboardObject):
    _fields = ('id', 'render_data', 'action', 'group_id')

    def __init__(self, id=None, render_data=None, action=None, group_id=None):
        self._initialize(dict(id=id, render_data=render_data, action=action, group_id=group_id))

    def _validate(self, state):
        _optional(state['id'], str, 'id')
        _optional(state['group_id'], str, 'group_id')
        _nested(state['render_data'], QKeyboardRenderData, 'render_data')
        _nested(state['action'], QKeyboardAction, 'action')

    def set_id(self, value):
        return self._set('id', value)

    def set_render_data(self, value):
        return self._set('render_data', value)

    def set_action(self, value):
        return self._set('action', value)

    def set_group_id(self, value):
        return self._set('group_id', value)


class QKeyboardCustom(QKeyboardBase):
    def __init__(self, rows=None):
        self.set_rows([] if rows is None else rows)

    @staticmethod
    def _encode_rows(rows):
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

    def set_rows(self, value):
        self._encode_rows(value)
        self.rows = value
        return self

    def to_payload(self):
        return {'content': {'rows': self._encode_rows(self.rows)}}
