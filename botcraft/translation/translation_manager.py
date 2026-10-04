"""Native translation lookup/fallback with QQ text formatting and scoped evaluation."""
import asyncio
import copy
import threading
from contextlib import contextmanager
from importlib.resources import files

from mcdreforged.translation.language_fallback_handler import LanguageFallbackHandler
from mcdreforged.translation.translation_manager import TranslationManager as NativeTranslationManager
from mcdreforged.utils import translation_utils

from botcraft.config import load_resource_yaml


class TranslationManager(NativeTranslationManager):
    def __init__(self, runtime):
        super().__init__(runtime.logger)
        self.runtime = runtime
        self._tls = threading.local()

    def load_translations(self):
        # Reused native managers and plugins retain their native translated log keys.
        super().load_translations()
        for resource in files('botcraft').joinpath('resources/lang').iterdir():
            if resource.name.endswith('.yml'):
                language = resource.name[:-4]
                translation_utils.update_storage(self.translations, language, load_resource_yaml('resources/lang/' + resource.name))
                self.available_languages.add(language)

    def _current_language(self):
        context = getattr(self._tls, 'context', None)
        if context is not None:
            if context['suspended']:
                raise RuntimeError('Translation language context cannot cross await')
            return context['language']
        return self.language

    @contextmanager
    def language_context(self, language):
        if language is None:
            language = self.runtime.get_language()
        if not isinstance(language, str):
            raise TypeError('Translation language must be str')
        previous = getattr(self._tls, 'context', None)
        context = {'language': language, 'suspended': False}
        self._tls.context = context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            handle = None
        else:
            handle = loop.call_soon(context.__setitem__, 'suspended', True)
        try:
            yield
            if context['suspended']:
                raise RuntimeError('Translation language context cannot cross await')
        finally:
            if handle is not None:
                handle.cancel()
            self._tls.context = previous

    def _plugin_translations(self):
        manager = getattr(self.runtime, 'plugin_manager', None)
        return manager.registry_storage.translations if manager is not None else None

    def tr(self, key, *args, language=None, allow_failure=True, fallback_handler=None, **kwargs):
        from botcraft.message.qtext.text import QTextBase, QText, QMarkdown, escape_markdown
        if not isinstance(key, str):
            raise TypeError('Translation key must be str')
        selected_language = self._current_language() if language is None else language
        handler = fallback_handler or LanguageFallbackHandler.auto()
        # Lookup exactly follows native framework-first / plugin-second fallback order.
        try:
            formatter = translation_utils.translate_from_dict(self.translations.get(key, {}), selected_language, fallback_handler=handler)
        except KeyError:
            formatter = translation_utils.translate_from_dict((self._plugin_translations() or {}).get(key, {}), selected_language,
                                                              fallback_handler=handler, default=None)
        missing_translation = formatter is None
        if formatter is None:
            if not allow_failure:
                raise KeyError('Translation key not found: {}'.format(key))
            self.logger.error('Error translating key {} to {}'.format(key, selected_language))
            formatter = key
        formatter = formatter.strip('\n\r')
        resolved = {}
        keyboard = None
        has_text = False
        has_markdown = False
        for value in (*args, *kwargs.values()):
            if id(value) in resolved:
                continue
            if isinstance(value, QTextBase):
                evaluated = self.evaluate(value, language=selected_language)
                if not isinstance(evaluated, (QText, QMarkdown)):
                    raise TypeError('Translation parameters require QText or QMarkdown')
                has_text = True
                has_markdown |= isinstance(evaluated, QMarkdown)
                value_keyboard = evaluated.get_keyboard()
                if value_keyboard is not None:
                    if keyboard is not None:
                        raise ValueError('Translation parameters contain multiple keyboards')
                    keyboard = value_keyboard
                resolved[id(value)] = evaluated
            elif isinstance(value, (str, int, float, bool)) or value is None:
                resolved[id(value)] = value
            else:
                raise TypeError('Unsupported QQ translation parameter')

        def convert(value):
            value = resolved[id(value)]
            if isinstance(value, QTextBase):
                text = value.to_plain_text()
                return escape_markdown(text) if has_markdown and not isinstance(value, QMarkdown) else text
            if has_markdown and isinstance(value, str):
                return escape_markdown(value)
            return value

        try:
            formatted = formatter if missing_translation else formatter.format(*(convert(value) for value in args), **{name: convert(value) for name, value in kwargs.items()})
        except Exception as error:
            raise ValueError('Failed to format QQ translation {}'.format(key)) from error
        if has_markdown:
            return QMarkdown(formatted, keyboard=copy.deepcopy(keyboard))
        if has_text:
            return QText(formatted, keyboard=copy.deepcopy(keyboard))
        return formatted

    def rtr(self, key, *args, **kwargs):
        from botcraft.translation.translation_text import QQTranslationText
        return QQTranslationText(self, key, *args, **kwargs)

    def evaluate(self, message, language=None):
        from botcraft.message.qtext.text import QTextBase
        if isinstance(message, str):
            return message
        if not isinstance(message, QTextBase):
            raise TypeError('QQ messages must be str or QTextBase')
        selected = self._current_language() if language is None else language
        if hasattr(message, '_evaluate_translation'):
            return message._evaluate_translation(self, selected)
        return message.copy()
