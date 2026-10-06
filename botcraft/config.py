"""Host-independent QQ configuration, reusing MCDR's YAML merge and save logic."""
import logging
from os import PathLike
from typing import Any, Mapping
from typing_extensions import Self
import math
import threading
from importlib.resources import files
from typing import Dict, List

from ruamel.yaml import YAML

from mcdreforged.logging.debug_option import DebugOption
from mcdreforged.mcdr_config import MCDReforgedConfigManager
from mcdreforged.utils.lazy_item import LazyItem
from mcdreforged.utils.serializer import Serializable
from mcdreforged.utils.yaml_data_storage import YamlDataStorage


class GatewayConfig(Serializable):
    intents: List[str] = ['GROUP_AND_C2C_EVENT', 'INTERACTION']

    @property
    def intent_mask(self: Self) -> int:
        """Combine configured QQ gateway intent names into a protocol bitmask.
        
        :return: Result of the operation.
        """
        bits = {'GROUP_AND_C2C_EVENT': 1 << 25, 'INTERACTION': 1 << 26, 'MESSAGE_AUDIT': 1 << 27}
        mask = 0
        for name in self.intents:
            mask |= bits[name]
        return mask

    def on_deserialization(self: Self) -> None:
        """Reject unsupported gateway intent names after deserialization.
        
        :return: No return value.
        """
        if any(name not in {'GROUP_AND_C2C_EVENT', 'INTERACTION', 'MESSAGE_AUDIT'} for name in self.intents):
            raise ValueError('Unknown QQ gateway intent name')


class HttpConfig(Serializable):
    timeout: float = 10.0

    def on_deserialization(self: Self) -> None:
        """Require a finite positive HTTP timeout after deserialization.
        
        :return: No return value.
        """
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('http.timeout must be finite and positive')


class PermissionConfig(Serializable):
    mode: str = 'mixed'
    super_admins: List[str] = []

    def on_deserialization(self: Self) -> None:
        """Validate the permission policy and super-administrator identities.
        
        :return: No return value.
        """
        if self.mode not in {'native', 'role', 'mixed'}:
            raise ValueError('Unknown permission mode')
        if any(not identity for identity in self.super_admins):
            raise ValueError('Super administrator identities must be nonempty')


class Config(Serializable):
    appid: str = ''
    secret: str = ''
    language: str = 'zh_cn'
    plugin_directories: List[str] = ['plugins']
    log_received_messages: bool = True
    advanced_console: bool = True
    disable_console_thread: bool = False
    disable_console_color: bool = False
    debug: Dict[str, bool] = {**{option.name.lower(): False for option in DebugOption}, 'raw_response': False}
    gateway: GatewayConfig = GatewayConfig.get_default()
    http: HttpConfig = HttpConfig.get_default()
    permission: PermissionConfig = PermissionConfig.get_default()

    def is_debug_on(self: Self) -> bool:
        """Report whether any standalone debug option is enabled.
        
        :return: Result of the operation.
        """
        return any(self.debug.values())

    def __repr__(self: Self) -> str:
        return 'Config(language={!r}, secret=<redacted>)'.format(self.language)

    def on_deserialization(self: Self) -> None:
        """Require nonempty language and plugin directory settings.
        
        :return: No return value.
        """
        if not self.language or any(not path for path in self.plugin_directories):
            raise ValueError('Language and plugin paths must be nonempty')


def load_resource_yaml(resource_path: str) -> dict[str, Any]:
    """Load a bundled YAML resource from the BotCraft package.
    
    :param resource_path: Package-relative YAML template path.
    :return: Parsed YAML template mapping.
    """
    return YAML().load(files('botcraft').joinpath(resource_path).read_text(encoding='utf8'))


class ResourceStorageMixin:
    """Replace only the native package-bound lazy resource provider (MCDR 2.14.4)."""
    def __init__(self: Self, logger: logging.Logger, path: str | PathLike[str], resource_path: str) -> None:
        """Bind native YAML storage to a BotCraft resource template.
        
        :param logger: Logger used for storage diagnostics.
        :param path: Configuration file path.
        :param resource_path: Package-relative YAML template path.
        :return: No return value.
        """
        super().__init__(logger, str(path), resource_path)
        self._YamlDataStorage__default_data = LazyItem(lambda: load_resource_yaml(resource_path))


class ConfigStorage(ResourceStorageMixin, YamlDataStorage):
    pass


class ConfigManager(MCDReforgedConfigManager):
    DEFAULT_CONFIG_RESOURCE_PATH = 'resources/default_config.yml'
    IMMUTABLE_FIELDS = ('appid', 'secret', 'advanced_console', 'disable_console_thread')

    def __init__(self: Self, logger: logging.Logger, path: str | PathLike[str]) -> None:
        """Create native-backed storage and a default standalone configuration.
        
        :param logger: Logger used for storage diagnostics.
        :param path: Configuration file path.
        :return: No return value.
        """
        self.logger = logger
        self.path = str(path)
        self._MCDReforgedConfigManager__storage = self._new_storage()
        self._MCDReforgedConfigManager__config = Config.get_default()
        self._MCDReforgedConfigManager__config_lock = threading.Lock()

    def _new_storage(self: Self) -> ConfigStorage:
        return ConfigStorage(self.logger, self.path, self.DEFAULT_CONFIG_RESOURCE_PATH)

    def _deserialize(self: Self, data: dict[str, Any], **kwargs: Any) -> Config:
        if not isinstance(data, dict):
            raise ValueError('BotCraft configuration must be a mapping')
        if any(key in data and not isinstance(data[key], dict) for key in ('gateway', 'http', 'permission', 'debug')):
            raise ValueError('Nested configuration sections must be mappings')
        unknown = [False]
        if isinstance(data, dict) and isinstance(data.get('debug'), dict):
            known = {option.name.lower() for option in DebugOption} | {'raw_response'}
            if any(name not in known for name in data['debug']):
                unknown[0] = True
                data = dict(data, debug={name: value for name, value in data['debug'].items() if name in known})
        if isinstance(data, dict) and isinstance(data.get('http'), dict) and type(data['http'].get('timeout')) is bool:
            raise ValueError('http.timeout must be a number, not bool')
        def redundant(*_: object) -> None:
            unknown[0] = True
        try:
            result = Config.deserialize(data, redundancy_callback=redundant, **kwargs)
        except Exception:
            # Native exceptions may embed raw data. Never propagate credentials or unknown values.
            raise ValueError('Invalid BotCraft configuration: check field types and QQ constraints') from None
        if unknown[0]:
            self.logger.warning('Unknown BotCraft configuration fields were ignored')
        return result

    def validate(self: Self, data: dict[str, Any]) -> Config:
        """Validate supplied fields using native defaults without changing state or disk.
        
        :param data: Supplied configuration mapping, including open YAML field values.
        :return: Validated standalone configuration with native defaults.
        """
        return self._deserialize(data)

    def load(self: Self, allowed_missing_file: bool = False, *, initial: bool = True) -> bool:
        """Validate and atomically load configuration, repairing missing options when allowed.
        
        :param allowed_missing_file: Whether a missing configuration file may be initialized.
        :param initial: Whether this is startup loading, permitting immutable startup fields and repair saves.
        :return: Whether native storage found missing configuration options.
        """
        candidate_storage = self._new_storage()
        try:
            if candidate_storage.file_presents():
                with open(self.path, encoding='utf8') as stream:
                    raw = YAML(typ='safe').load(stream)
                if not isinstance(raw, dict):
                    raise ValueError()
                for key in ('gateway', 'http', 'permission', 'debug'):
                    if key in raw and not isinstance(raw[key], dict):
                        raise ValueError()
                # Validate supplied fields before native missing-option repair can replace malformed mappings.
                self._deserialize(raw)
            missing = candidate_storage.read_config(allowed_missing_file, save_on_missing=False)
            candidate = self._deserialize(candidate_storage.to_dict())
        except FileNotFoundError:
            raise
        except Exception:
            raise ValueError('Invalid BotCraft configuration: check field types and QQ constraints') from None
        with self._MCDReforgedConfigManager__config_lock:
            current = self.get_config()
            if not initial and any(getattr(candidate, field) != getattr(current, field) for field in self.IMMUTABLE_FIELDS):
                raise ValueError('Configuration changes to credentials or console startup settings require a new process')
            self._MCDReforgedConfigManager__storage = candidate_storage
            self._MCDReforgedConfigManager__config = candidate
        if missing and initial:
            self.save()
        return missing

    def save_default(self: Self) -> None:
        """Write the bundled default configuration through native storage.
        
        :return: No return value.
        """
        self._MCDReforgedConfigManager__storage.save_default()

    def set_values(self: Self, changes: Mapping[str | tuple[str, ...], Any]) -> None:
        """Validate and atomically apply selected mutable configuration fields.
        
        :param changes: Mapping of dotted or tuple field paths to replacement configuration values.
        :return: No return value.
        """
        with self._MCDReforgedConfigManager__config_lock:
            candidate = self.get_config().serialize()
            for path, value in changes.items():
                keys = tuple(path.split('.')) if isinstance(path, str) else tuple(path)
                if not keys or any(not isinstance(key, str) or key.startswith('_') for key in keys):
                    raise ValueError('Invalid configuration field path')
                obj = candidate
                for key in keys[:-1]:
                    if not isinstance(obj, dict) or key not in obj:
                        raise KeyError('Unknown configuration field')
                    obj = obj[key]
                if not isinstance(obj, dict) or keys[-1] not in obj:
                    raise KeyError('Unknown configuration field')
                obj[keys[-1]] = value
            validated = self._deserialize(candidate)
            current = self.get_config()
            if any(getattr(validated, field) != getattr(current, field) for field in self.IMMUTABLE_FIELDS):
                raise ValueError('Configuration changes to credentials or console startup settings require a new process')
            self._MCDReforgedConfigManager__config = validated
