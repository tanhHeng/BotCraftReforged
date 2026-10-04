import html
import re
from abc import ABC, abstractmethod

from botcraft.message.qtext.keyboard import QKeyboardBase


_MARKDOWN_SPECIAL = re.compile(r'([\\`*_{}\[\]()#+\-.!|~])')


def escape_markdown(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError('Markdown escaping requires a string')
    # Escape HTML first so literal tags/quotes cannot become QQ Markdown markup.
    return _MARKDOWN_SPECIAL.sub(r'\\\1', html.escape(text, quote=False))


class QTextBase(ABC):
    def __init__(self, text='', *, keyboard=None):
        if not isinstance(text, str):
            raise TypeError('Message text must be a string')
        self.text = text
        self._keyboard = None
        self.set_keyboard(keyboard)

    def get_keyboard(self):
        return getattr(self, '_keyboard', None)

    def set_keyboard(self, keyboard):
        if keyboard is not None:
            if not isinstance(keyboard, QKeyboardBase):
                raise TypeError('keyboard must be a QKeyboardBase or None')
            keyboard.to_payload()
        self._keyboard = keyboard
        return self

    @abstractmethod
    def append(self, *parts):
        raise NotImplementedError

    @abstractmethod
    def copy(self):
        raise NotImplementedError

    @abstractmethod
    def to_payload(self):
        raise NotImplementedError

    @abstractmethod
    def to_plain_text(self):
        raise NotImplementedError

    def __add__(self, other):
        if isinstance(other, QTextBase) and hasattr(other, '_evaluate_translation'):
            return other.__radd__(self)
        if not isinstance(other, (str, QText, QMarkdown)):
            raise TypeError('Only str/QText/QMarkdown can be combined')
        if isinstance(self, QText) and isinstance(other, QMarkdown):
            keyboard = self.get_keyboard()
            promoted = QMarkdown(escape_markdown(self.text), keyboard=keyboard.copy() if keyboard is not None else None)
            return promoted.append(other)
        return self.copy().append(other)

    def __radd__(self, other):
        if not isinstance(other, str):
            raise TypeError('Only text content can be combined')
        return QText(other) + self

    def __str__(self):
        return self.to_plain_text()

    def _payload_with_keyboard(self, payload):
        keyboard = self.get_keyboard()
        if keyboard is not None:
            payload['keyboard'] = keyboard.to_payload()
        return payload

    def _append_parts(self, parts, *, markdown):
        text = self.text
        keyboard = self.get_keyboard()
        # Build everything first: failed later operands never partially mutate self.
        for part in parts:
            if isinstance(part, str):
                text += escape_markdown(part) if markdown else part
            elif isinstance(part, QText) or (markdown and isinstance(part, QMarkdown)):
                text += escape_markdown(part.text) if markdown and isinstance(part, QText) else part.text
                right_keyboard = part.get_keyboard()
                if right_keyboard is not None:
                    if keyboard is not None:
                        raise ValueError('A combined message may contain only one keyboard')
                    keyboard = right_keyboard.copy()
            else:
                raise TypeError('Invalid {} append operand: {}'.format(type(self).__name__, type(part).__name__))
        if keyboard is not None:
            keyboard.to_payload()
        self.text = text
        self._keyboard = keyboard
        return self


class QText(QTextBase):
    def append(self, *parts):
        return self._append_parts(parts, markdown=False)

    def copy(self):
        keyboard = self.get_keyboard()
        return type(self)(self.text, keyboard=keyboard.copy() if keyboard is not None else None)

    def to_plain_text(self):
        return self.text

    def to_payload(self):
        if not isinstance(self.text, str):
            raise TypeError('QText text must be a string')
        return self._payload_with_keyboard({'msg_type': 0, 'content': self.text})


class QMarkdown(QTextBase):
    def append(self, *parts):
        return self._append_parts(parts, markdown=True)

    def copy(self):
        keyboard = self.get_keyboard()
        return type(self)(self.text, keyboard=keyboard.copy() if keyboard is not None else None)

    def to_plain_text(self):
        return self.text

    def to_payload(self):
        if not isinstance(self.text, str):
            raise TypeError('QMarkdown text must be a string')
        return self._payload_with_keyboard({'msg_type': 2, 'markdown': {'content': self.text}})
