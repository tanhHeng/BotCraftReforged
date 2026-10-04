"""Native copy/save/reset preference behavior with QQ-only identity keys."""
from pathlib import Path

from mcdreforged.preference.preference_manager import PreferenceManager as NativePreferenceManager, PreferenceItem, InvalidPreferenceSource

CONSOLE_ALIAS = '#@BotCraft_Console@#'
PREFERENCE_FILE_PATH = Path('config/botcraft/preferences.json')


class PreferenceManager(NativePreferenceManager):
    def __init__(self, runtime):
        self.runtime = runtime
        self.logger = runtime.logger
        self.preferences = {}
        self._PreferenceManager__store_file_path = PREFERENCE_FILE_PATH

    @classmethod
    def _PreferenceManager__get_name(cls, obj, *, strict_type_check=False):
        from botcraft.message.user import User
        from botcraft.command.command_source import QQCommandSource, ConsoleSource
        if isinstance(obj, ConsoleSource):
            return CONSOLE_ALIAS
        if isinstance(obj, QQCommandSource):
            obj = obj.user
        if isinstance(obj, User):
            try:
                return obj.require_identity()
            except ValueError:
                if strict_type_check:
                    raise InvalidPreferenceSource('Preference subject has no real QQ user identity') from None
                return None
        raise InvalidPreferenceSource('Preference subject must be User or a BotCraft command source')

    def get_default_preference(self):
        return PreferenceItem(language=self.runtime.get_language())

    def get_console_preference(self):
        pref = self.preferences.get(CONSOLE_ALIAS)
        return self.get_default_preference() if pref is None else pref.copy()

    def set_console_preference(self, pref):
        self._validate_preference(pref)
        self.preferences[CONSOLE_ALIAS] = pref.copy()
        self._PreferenceManager__save_preferences()

    def set_preference(self, obj, pref):
        self._PreferenceManager__get_name(obj, strict_type_check=True)
        self._validate_preference(pref)
        super().set_preference(obj, pref)

    def _validate_preference(self, pref):
        if not isinstance(pref, PreferenceItem):
            raise TypeError('Preference must be a native PreferenceItem')
        language = getattr(pref, 'language', None)
        if language is not None and language not in self.runtime.translation_manager.available_languages:
            raise ValueError('Unknown preference language')

    def get_preferred_language(self, obj):
        return self.get_preference(obj).language or self.runtime.get_language()

    def load_preferences(self):
        # The upstream path intentionally empties and rewrites malformed JSON.
        self.logger.warning('Preference loading follows native recovery: malformed files are emptied and saved; back up preferences to avoid data loss')
        super().load_preferences()
