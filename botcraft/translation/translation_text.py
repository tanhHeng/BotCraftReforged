"""QQ lazy translation: no native global interface and no network-thread evaluation."""
import copy
from typing import TypeAlias
from typing_extensions import Self

from botcraft.message.qtext.keyboard import QKeyboardBase
from botcraft.message.qtext.text import QTextBase, QText, QMarkdown
from botcraft.translation.translation_manager import TranslationManager, TranslationParameter, TranslationOption

DelayedOperationValue: TypeAlias = str | QTextBase | QKeyboardBase | None | tuple[str | QTextBase, ...]


class QQTranslationText(QTextBase):
    def __init__(self, manager, translation_key, *args, **kwargs):
        self.manager = manager
        self.translation_key = translation_key
        self.args = args
        self.kwargs = kwargs
        self._operations = []

    def _evaluate_translation(self, manager=None, language=None):
        manager = self.manager
        selected = manager._current_language() if language is None else language
        kwargs = dict(self.kwargs)
        kwargs['language'] = selected
        result = manager.tr(self.translation_key, *self.args, **kwargs)
        if isinstance(result, str):
            result = QText(result)
        for operation, value in self._operations:
            if operation == 'keyboard':
                result.set_keyboard(copy.deepcopy(value))
            elif operation == 'append':
                resolved = [manager.evaluate(part, language=selected) for part in value]
                for part in resolved:
                    result = result + part
            elif operation == 'right':
                result = result + manager.evaluate(value, language=selected)
            elif operation == 'left':
                result = manager.evaluate(value, language=selected) + result
            else:
                raise RuntimeError('Unknown delayed text operation')
        return result

    @staticmethod
    def _validate_part(part: str | QTextBase) -> None:
        if not isinstance(part, (str, QText, QMarkdown, QQTranslationText)):
            raise TypeError('QQ text composition requires str, QText, QMarkdown or delayed translation')

    def append(self: Self, *parts: str | QTextBase) -> Self:
        """Defer concatenation of concrete or translated text.
        
        :param parts: Plain, concrete or delayed QQ text appended in order.
        :return: This delayed message, with concatenation recorded for evaluation.
        """
        for part in parts:
            self._validate_part(part)
        self._operations.append(('append', tuple(parts)))
        return self

    def __add__(self: Self, other: str | QTextBase) -> Self:
        self._validate_part(other)
        result = self.copy()
        result._operations.append(('right', other.copy() if isinstance(other, QTextBase) else other))
        return result

    def __radd__(self: Self, other: str | QTextBase) -> Self:
        self._validate_part(other)
        result = self.copy()
        result._operations.append(('left', other.copy() if isinstance(other, QTextBase) else other))
        return result

    def copy(self):
        snapshots = {}
        def snapshot(value):
            if id(value) not in snapshots:
                snapshots[id(value)] = value.copy() if isinstance(value, QTextBase) else copy.deepcopy(value)
            return snapshots[id(value)]
        result = QQTranslationText(self.manager, self.translation_key, *(snapshot(value) for value in self.args),
                                   **{key: snapshot(value) for key, value in self.kwargs.items()})
        result._operations = []
        for operation, value in self._operations:
            if operation == 'append':
                value = tuple(part.copy() if isinstance(part, QTextBase) else copy.deepcopy(part) for part in value)
            elif isinstance(value, QTextBase):
                value = value.copy()
            else:
                value = copy.deepcopy(value)
            result._operations.append((operation, value))
        return result

    def set_keyboard(self: Self, keyboard: QKeyboardBase | None) -> Self:
        """Attach a concrete keyboard without evaluating translation.
        
        :param keyboard: Valid concrete keyboard, or None to clear the keyboard at this operation.
        :return: This delayed message with an independent keyboard snapshot.
        """
        # Validation uses the concrete sender's keyboard contract without evaluating translation.
        QText().set_keyboard(keyboard)
        self._operations.append(('keyboard', copy.deepcopy(keyboard)))
        return self

    def get_keyboard(self: Self) -> QKeyboardBase | None:
        """Evaluate the message in the current language and read its keyboard.
        
        :return: Evaluated keyboard, or None when no keyboard is attached.
        """
        return self._evaluate_translation().get_keyboard()

    def to_payload(self: Self) -> dict[str, object]:
        """Evaluate delayed text into a concrete QQ send payload.
        
        :return: Concrete text or Markdown payload with its optional keyboard.
        """
        return self._evaluate_translation().to_payload()

    def to_plain_text(self: Self) -> str:
        """Evaluate delayed text and return its textual content.
        
        :return: Translated content, retaining Markdown markup for Markdown messages.
        """
        return self._evaluate_translation().to_plain_text()

    def __str__(self: Self) -> str:
        return self.to_plain_text()
