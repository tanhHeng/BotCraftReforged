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


def rtr(key, *args, **kwargs):
    from botcraft.plugin.si.server_interface import QQServerInterface
    return QQServerInterface.si().rtr(key, *args, **kwargs)
