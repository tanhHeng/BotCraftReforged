from typing import TYPE_CHECKING, Any, Sequence
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.translation.translation_text import QQTranslationText
import html
import re
import warnings
import copy
from urllib.parse import quote
from botcraft.message.user import User
from abc import ABC, abstractmethod

from botcraft.message.qtext.keyboard import QKeyboardBase


_MARKDOWN_SPECIAL = re.compile(r'([\\`*_{}\[\]()#+\-.!|~])')


def escape_markdown(text: str) -> str:
    """Escape literal text for use in a QQ Markdown message.
    
    :param text: Literal text; HTML and Markdown special characters are escaped.
    :return: The escaped literal Markdown text.
    """
    if not isinstance(text, str):
        raise TypeError('Markdown escaping requires a string')
    # Escape HTML first so literal tags/quotes cannot become QQ Markdown markup.
    return _MARKDOWN_SPECIAL.sub(r'\\\1', html.escape(text, quote=False))


class QTextBase(ABC):
    """Base contract for concrete or translated QQ text with an optional keyboard."""
    def __init__(self: Self, text: str = '', *, keyboard: QKeyboardBase | None = None) -> None:
        """Create concrete message text and validate its optional keyboard.
        
        :param text: Literal string content; delayed translation objects are not accepted.
        :param keyboard: An optional validated keyboard attached to this message.
        :return: The method returns no value.
        """
        if not isinstance(text, str):
            raise TypeError('Message text must be a string')
        self.text = text
        self._keyboard = None
        self.set_keyboard(keyboard)

    def get_keyboard(self: Self) -> QKeyboardBase | None:
        """Return the keyboard attached to this message.
        
        :return: The attached keyboard, or None when none is attached.
        """
        return getattr(self, '_keyboard', None)

    def set_keyboard(self: Self, keyboard: QKeyboardBase | None) -> Self:
        """Validate and replace the attached keyboard without changing the text.
        
        :param keyboard: A keyboard to attach, or None to remove the current keyboard.
        :return: This message for chained operations.
        """
        if keyboard is not None:
            if not isinstance(keyboard, QKeyboardBase):
                raise TypeError('keyboard must be a QKeyboardBase or None')
            keyboard.to_payload()
        self._keyboard = keyboard
        return self

    @abstractmethod
    def append(self: Self, *parts: "str | QText | QMarkdown") -> Self:
        """Append supported concrete operands atomically; at most one keyboard may be present.
        
        :param parts: Concrete append operands supported by the message subtype.
        :return: This message with the appended content.
        """
        raise NotImplementedError

    @abstractmethod
    def copy(self: Self) -> Self:
        """Copy message content and independently copy its keyboard.
        
        :return: An independent message of the same concrete type.
        """
        raise NotImplementedError

    @abstractmethod
    def to_payload(self: Self) -> dict[str, Any]:
        """Validate and encode a QQ message payload, including its optional keyboard.
        
        :return: The encoded QQ message fields.
        """
        raise NotImplementedError

    @abstractmethod
    def to_plain_text(self: Self) -> str:
        """Return the stored text representation without the keyboard.
        
        :return: The text content; Markdown markup is retained for Markdown messages.
        """
        raise NotImplementedError

    def __add__(self: Self, other: "str | QText | QMarkdown | QQTranslationText") -> "QTextBase":
        """Combine messages without mutating either operand, promoting plain text to Markdown when needed.
        
        :param other: Supported concrete text or an existing delayed translation operand.
        :return: The combined message; delayed translation remains delayed.
        """
        if isinstance(self, QTextInput) and isinstance(other, (str, QText)):
            warnings.warn('QTextInput only supports Markdown; promoting plain text to QMarkdown', UserWarning, stacklevel=2)
        if isinstance(other, QTextBase) and hasattr(other, '_evaluate_translation'):
            return other.__radd__(self)
        if not isinstance(other, (str, QText, QMarkdown)):
            raise TypeError('Only str/QText/QMarkdown can be combined')
        if isinstance(self, QText) and isinstance(other, QMarkdown):
            keyboard = self.get_keyboard()
            if isinstance(other, QTextInput):
                warnings.warn('QTextInput only supports Markdown; promoting plain text to QMarkdown', UserWarning, stacklevel=2)
            promoted = QMarkdown(self._as_markdown(), keyboard=keyboard.copy() if keyboard is not None else None)
            return promoted.append(other)
        return self.copy().append(other)

    def __radd__(self: Self, other: str) -> "QTextBase":
        """Prepend a literal string to this message without mutating this message.
        
        :param other: The literal string placed before this message.
        :return: The combined message.
        """
        if not isinstance(other, str):
            raise TypeError('Only text content can be combined')
        return QText(other) + self

    def __str__(self: Self) -> str:
        return self.to_plain_text()

    def _payload_with_keyboard(self: Self, payload: dict[str, Any]) -> dict[str, Any]:
        keyboard = self.get_keyboard()
        if keyboard is not None:
            payload['keyboard'] = keyboard.to_payload()
        return payload

    def _as_markdown(self: Self) -> str:
        if isinstance(self, QMarkdown):
            return self.text
        if getattr(self, '_markup_source', None) == self.text:
            return self._markdown_text
        return escape_markdown(self.text)

    def _remember_markdown(self: Self, rendered: str) -> None:
        self._markup_source = self.text
        self._markdown_text = rendered

    def _append_parts(self: Self, parts: "Sequence[str | QText | QMarkdown]", *, markdown: bool) -> Self:
        text = self.text
        markdown_text = self._as_markdown()
        keyboard = self.get_keyboard()
        # Build everything first: failed later operands never partially mutate self.
        for part in parts:
            if isinstance(part, str):
                text += escape_markdown(part) if markdown else part
                markdown_text += escape_markdown(part)
            elif isinstance(part, QTextInput) and not markdown:
                raise TypeError('QTextInput only supports Markdown; use addition or QMarkdown')
            elif isinstance(part, QText) or (markdown and isinstance(part, QMarkdown)):
                text += part._as_markdown() if markdown else part.text
                markdown_text += part._as_markdown()
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
        if not markdown:
            self._remember_markdown(markdown_text)
        return self


class QText(QTextBase):
    """Plain QQ message content; append accepts only strings and QText."""
    def append(self: Self, *parts: "str | QText") -> Self:
        """Append content atomically while preserving the one-keyboard-per-message constraint.
        
        :param parts: Strings and QText operands only.
        :return: This message for chained operations.
        """
        return self._append_parts(parts, markdown=False)

    def copy(self: Self) -> Self:
        """Copy message content and independently copy its keyboard.
        
        :return: An independent message of the same concrete type.
        """
        keyboard = self.get_keyboard()
        result = type(self)(self.text, keyboard=keyboard.copy() if keyboard is not None else None)
        result._remember_markdown(self._as_markdown())
        return result

    def to_plain_text(self: Self) -> str:
        """Return the stored text representation without the keyboard.
        
        :return: The text content; Markdown markup is retained for Markdown messages.
        """
        return self.text

    def to_payload(self: Self) -> dict[str, Any]:
        """Validate and encode a QQ message payload, including its optional keyboard.
        
        :return: The encoded QQ message fields.
        """
        if not isinstance(self.text, str):
            raise TypeError('QText text must be a string')
        return self._payload_with_keyboard({'msg_type': 0, 'content': self.text})


class QMarkdown(QTextBase):
    """QQ Markdown message content with literal operands escaped during append."""
    def append(self: Self, *parts: "str | QText | QMarkdown") -> Self:
        """Append content atomically while preserving the one-keyboard-per-message constraint.
        
        :param parts: Strings and QText operands are escaped; QMarkdown operands retain their markup.
        :return: This message for chained operations.
        """
        return self._append_parts(parts, markdown=True)

    def copy(self: Self) -> Self:
        """Copy message content and independently copy its keyboard.
        
        :return: An independent message of the same concrete type.
        """
        keyboard = self.get_keyboard()
        return type(self)(self.text, keyboard=keyboard.copy() if keyboard is not None else None)

    def to_plain_text(self: Self) -> str:
        """Return the stored text representation without the keyboard.
        
        :return: The text content; Markdown markup is retained for Markdown messages.
        """
        return self.text

    def to_payload(self: Self) -> dict[str, Any]:
        """Validate and encode a QQ message payload, including its optional keyboard.
        
        :return: The encoded QQ message fields.
        """
        if not isinstance(self.text, str):
            raise TypeError('QMarkdown text must be a string')
        return self._payload_with_keyboard({'msg_type': 2, 'markdown': {'content': self.text}})


class QTextAt(QText):
    """A user mention usable in plain text and Markdown messages."""

    def __init__(self, target: User | str, *, keyboard: QKeyboardBase | None = None) -> None:
        """Create a mention from a group member OpenID.

        :param target: User with member_openid, or the explicit mention ID.
        :param keyboard: Optional message keyboard.
        :raises ValueError: The identity is missing or contains protocol delimiters.
        """
        identity = target.member_openid if isinstance(target, User) else target
        if not isinstance(identity, str):
            raise TypeError('Mention target must be User or a string ID')
        if not identity or any(char in identity for char in '<>\r\n"&'):
            raise ValueError('Invalid mention member_openid')
        super().__init__(f'<qqbot-at-user id="{identity}" />', keyboard=keyboard)
        self._remember_markdown(self.text)

    def copy(self) -> "QTextAt":
        """Copy the mention and its keyboard without reinterpreting its tag."""
        return copy.deepcopy(self)


class QTextInput(QMarkdown):
    """Markdown interaction inserting editable text into the client's input box."""

    def __init__(self, text: str, *, show: str | None = None, reference: bool = False,
                 keyboard: QKeyboardBase | None = None) -> None:
        """Create an input interaction, encoding raw attribute strings once.

        :param text: Unencoded input text, at most 100 Unicode characters.
        :param show: Optional unencoded label, at most 100 Unicode characters.
        :param reference: Whether the client includes a reply reference.
        :param keyboard: Optional message keyboard.
        :raises ValueError: An attribute exceeds the character limit.
        :raises TypeError: An attribute has an invalid type.
        """
        for name, value in (('text', text), ('show', show)):
            if value is None and name == 'show':
                continue
            if not isinstance(value, str):
                raise TypeError(f'{name} must be a string')
            if len(value) > 100:
                raise ValueError(f'{name} exceeds 100 characters before URL encoding')
        if type(reference) is not bool:
            raise TypeError('reference must be bool')
        tag = f'<qqbot-cmd-input text="{quote(text, safe="")}"'
        if show is not None:
            tag += f' show="{quote(show, safe="")}"'
        tag += f' reference="{str(reference).lower()}" />'
        super().__init__(tag, keyboard=keyboard)

    def copy(self) -> "QTextInput":
        """Copy the interaction and its keyboard without encoding again."""
        return copy.deepcopy(self)
