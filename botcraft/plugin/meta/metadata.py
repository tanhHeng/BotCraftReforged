"""Native metadata parsing with QQ-owned logging and language selection."""
from typing_extensions import Self
from mcdreforged.plugin.meta.metadata import Metadata as NativeMetadata
from mcdreforged.utils import translation_utils
from botcraft.plugin._native import bind_native


class Metadata(NativeMetadata):
    __init__ = bind_native(NativeMetadata.__init__, runtime=True)

    def get_description(self: Self, lang: str | None = None) -> str | None:
        """Select a plugin description using the runtime language fallback.
        
        :param lang: Preferred language, or None to use the active runtime language.
        :return: Localized description, or None when no matching description exists.
        """
        if isinstance(self.description, str):
            return self.description
        if lang is None:
            from botcraft.plugin.si.server_interface import QQServerInterface
            interface = QQServerInterface.si_opt()
            lang = interface._runtime.get_language() if interface is not None else 'zh_cn'
        return translation_utils.translate_from_dict(self.description, lang, default=None)
