"""Public translation helpers use only the standalone BotCraft interface."""
from botcraft.message.qtext.text import QText, QMarkdown
from botcraft.translation.translation_manager import TranslationParameter, TranslationOption
from botcraft.translation.translation_text import QQTranslationText


def tr(key: str, *args: TranslationParameter, **kwargs: TranslationOption) -> str | QText | QMarkdown:
    """Immediately translate through the standalone server interface.
    
    :param key: Translation resource key.
    :param args: Positional scalar or QQ text formatting values.
    :param kwargs: Named formatting values and language, allow_failure or fallback_handler options.
    :return: Formatted translation in the selected language.
    """
    from botcraft.plugin.si.server_interface import QQServerInterface
    return QQServerInterface.si().tr(key, *args, **kwargs)


def rtr(key: str, *args: TranslationParameter, markdown: bool = False,
        **kwargs: TranslationOption) -> QQTranslationText:
    """Create runtime-bound text translated when it is evaluated.
    
    :param key: Translation resource key; no lookup occurs during this call.
    :param args: Positional formatting values, including nested delayed translations.
    :param markdown: Preserve Markdown template markup and escape ordinary formatting values.
    :param kwargs: Named formatting values and native translation options.
    :return: Delayed text evaluated in the eventual sending language.
    """
    from botcraft.plugin.si.server_interface import QQServerInterface
    return QQServerInterface.si().rtr(key, *args, markdown=markdown, **kwargs)
