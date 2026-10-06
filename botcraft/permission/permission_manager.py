"""QQ identity adaptation of native permission lists and highest-level lookup."""
from __future__ import annotations
from os import PathLike
from typing import TYPE_CHECKING, Any
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
    from botcraft.message.user import User
    from botcraft.command.command_source import QQCommandSource, ConsoleSource
import threading
from urllib.parse import quote, unquote

from ruamel.yaml import YAML
from mcdreforged.permission.permission_level import PermissionLevel, PermissionLevelItem
from mcdreforged.permission.permission_manager import PermissionManager as NativePermissionManager, PermissionStorage as NativePermissionStorage

from botcraft.config import ResourceStorageMixin
from botcraft.permission.permission_policy import POLICIES


def subject_user(subject: User | QQCommandSource) -> User:
    """Extract a QQ user from a user instance or QQ command source.
    
    :param subject: QQ user or command source whose identity or authority is evaluated.
    :return: Result of the operation.
    """
    from botcraft.message.user import User
    from botcraft.command.command_source import QQCommandSource
    if isinstance(subject, User):
        return subject
    if isinstance(subject, QQCommandSource):
        return subject.user
    raise TypeError('Permission subject must be a User or QQCommandSource')


def encode_identity(user: User, *, global_scope: bool = False) -> str:
    """Encode a real QQ identity into a global or conversation-scoped permission key.
    
    :param user: QQ user containing a real identity and supported route.
    :param global_scope: Whether the grant applies across conversations instead of the current route.
    :return: Result of the operation.
    """
    identity = user.require_identity()
    if global_scope:
        return 'global:' + quote(identity, safe='')
    scene, conversation = user.route()
    return ':'.join((scene, quote(conversation, safe=''), quote(identity, safe='')))


def validate_key(key: str) -> str:
    """Validate the canonical encoding of a supported scoped permission key.
    
    :param key: Canonical global or group/c2c permission identity key.
    :return: The unchanged canonical permission key.
    """
    if not isinstance(key, str):
        raise ValueError('Permission identity key must be a string')
    parts = key.split(':')
    if not ((len(parts) == 2 and parts[0] == 'global') or (len(parts) == 3 and parts[0] in {'group', 'c2c'})):
        raise ValueError('Invalid scoped permission identity key')
    if any(not value or quote(unquote(value), safe='') != value for value in parts[1:]):
        raise ValueError('Invalid encoded permission identity')
    return key


class PermissionStorage(ResourceStorageMixin, NativePermissionStorage):
    pass


class PermissionManager(NativePermissionManager):
    def __init__(self: Self, runtime: Runtime, path: str | PathLike[str]) -> None:
        """Initialize QQ permission storage with native list semantics.
        
        :param runtime: Runtime providing configuration, known users and logging.
        :param path: Permission YAML file path.
        :return: No return value.
        """
        self.runtime = runtime
        self.path = str(path)
        self.storage = self._new_storage()
        self._lock = threading.RLock()
        self._PermissionManager__tr = runtime.create_internal_translator('permission_manager').tr

    def _new_storage(self: Self) -> PermissionStorage:
        return PermissionStorage(self.runtime.logger, self.path, 'resources/default_permission.yml')

    @staticmethod
    def encode_key(subject: User | QQCommandSource, *, global_scope: bool = False) -> str:
        """Encode a supported permission subject with the requested scope.
        
        :param subject: QQ user or command source whose identity or authority is evaluated.
        :param global_scope: Whether the grant applies across conversations instead of the current route.
        :return: Result of the operation.
        """
        if type(global_scope) is not bool:
            raise TypeError('global_scope must be bool')
        return encode_identity(subject_user(subject), global_scope=global_scope)

    def load_permission_file(self: Self, *, allowed_missing_file: bool = False) -> None:
        """Validate and load permission storage, saving missing native defaults when needed.
        
        :param allowed_missing_file: Whether a missing permission file may be initialized.
        :return: No return value.
        """
        candidate = self._new_storage()
        if candidate.file_presents():
            with open(self.path, encoding='utf8') as stream:
                supplied = YAML(typ='safe').load(stream)
            if not isinstance(supplied, dict):
                raise ValueError('Permission file must be a mapping')
            self._validate_storage(supplied, partial=True)
        missing = candidate.read_config(allowed_missing_file, save_on_missing=False)
        self._validate_storage(candidate.to_dict())
        with self._lock:
            self.storage = candidate
            if missing:
                self.storage.save()

    @staticmethod
    def _validate_storage(data: dict[str, Any], *, partial: bool = False) -> None:
        if 'default_level' in data or not partial:
            PermissionLevel.from_value(data['default_level'])
        for name in PermissionLevel.NAMES:
            if name not in data and partial:
                continue
            entries = data[name]
            if entries is not None:
                if not isinstance(entries, list):
                    raise ValueError('Permission levels must contain lists or null')
                for key in entries:
                    validate_key(key)

    def is_super_admin(self: Self, subject: User | QQCommandSource | ConsoleSource) -> bool:
        """Recognize console authority or configured global super-administrator identities.
        
        :param subject: QQ user or command source whose identity or authority is evaluated.
        :return: Result of the operation.
        """
        from botcraft.command.command_source import ConsoleSource
        if isinstance(subject, ConsoleSource):
            return True
        user = subject_user(subject)
        return user.require_identity() in self.runtime.get_config().permission.super_admins

    def get_permission(self: Self, subject: User | QQCommandSource | ConsoleSource) -> int:
        """Resolve console authority, super administrators, explicit grants and default policy.
        
        :param subject: QQ user or command source whose identity or authority is evaluated.
        :return: Effective numeric permission level after precedence resolution.
        """
        from botcraft.command.command_source import ConsoleSource
        if isinstance(subject, ConsoleSource):
            return PermissionLevel.CONSOLE_LEVEL
        user = subject_user(subject)
        session_key = encode_identity(user)
        with self._lock:
            if self.is_super_admin(user):
                return PermissionLevel.OWNER
            explicit = self.get_player_permission_level(session_key, auto_add=False)
            if explicit is not None:
                return explicit
            global_level = self.get_player_permission_level(encode_identity(user, global_scope=True), auto_add=False)
            if global_level is not None:
                return global_level
            return POLICIES[self.runtime.get_config().permission.mode].default_permission(user)

    def _operation_user(self: Self, subject: User | QQCommandSource, *, global_scope: bool) -> User:
        user = subject_user(subject)
        user.require_identity()
        if not global_scope:
            scene, conversation = user.route()
            if scene == 'c2c':
                known = self.runtime.users.get_user(user.id)
                if known is None or known.route() != (scene, conversation):
                    raise ValueError('C2C permissions require a known User with its verified private route')
        return user

    def set_permission(self: Self, subject: User | QQCommandSource, value: int | str | PermissionLevelItem, *, global_scope: bool = False) -> None:
        """Persist a validated explicit permission grant for a QQ subject.
        
        :param subject: QQ user or command source whose identity or authority is evaluated.
        :param value: Native numeric level, level name or PermissionLevelItem.
        :param global_scope: Whether the grant applies across conversations instead of the current route.
        :return: No return value.
        """
        if type(global_scope) is not bool:
            raise TypeError('global_scope must be bool')
        key = encode_identity(self._operation_user(subject, global_scope=global_scope), global_scope=global_scope)
        self.set_permission_level(key, self._level(value))

    def remove_permission(self: Self, subject: User | QQCommandSource, *, global_scope: bool = False) -> None:
        """Remove an explicit QQ subject permission in the selected scope.
        
        :param subject: QQ user or command source whose identity or authority is evaluated.
        :param global_scope: Whether the grant applies across conversations instead of the current route.
        :return: No return value.
        """
        if type(global_scope) is not bool:
            raise TypeError('global_scope must be bool')
        self.remove_player(encode_identity(self._operation_user(subject, global_scope=global_scope), global_scope=global_scope))

    @staticmethod
    def _level(value: int | str | PermissionLevelItem) -> PermissionLevelItem:
        if isinstance(value, PermissionLevelItem):
            if PermissionLevel.from_value(value.level) != value:
                raise ValueError('Invalid permission level item')
            return value
        if type(value) is bool:
            raise TypeError('Permission level must not be bool')
        return PermissionLevel.from_value(value)

    # These native mutation methods touch mcdr_server for logging; replace only that
    # coupling, retaining native list storage, highest-level lookup and safe YAML writes.
    def add_player(self: Self, player: str, level_name: int | str | PermissionLevelItem | None = None) -> int:
        """Append a validated identity to the native permission level list and save it.
        
        :param player: Canonical encoded QQ permission identity.
        :param level_name: Requested native level, or the stored default when omitted.
        :return: Numeric level of the appended permission grant.
        """
        validate_key(player)
        level = self._level(self.get_default_permission_level() if level_name is None else level_name)
        with self._lock:
            self.get_permission_group_list(level.level).append(player)
            self.storage.save()
        self.runtime.logger.mdebug('Added QQ identity {} with permission {}'.format(player, level.name))
        return level.level

    def remove_player(self: Self, player: str) -> None:
        """Remove all native permission entries for a validated identity and save.
        
        :param player: Canonical encoded QQ permission identity.
        :return: No return value.
        """
        validate_key(player)
        with self._lock:
            while (level := self.get_player_permission_level(player, auto_add=False)) is not None:
                self.get_permission_group_list(level).remove(player)
            self.storage.save()
        self.runtime.logger.mdebug('Removed QQ permission identity {}'.format(player))

    def set_permission_level(self: Self, player: str, new_level: int | str | PermissionLevelItem) -> None:
        """Replace native permission entries for a validated identity.
        
        :param player: Canonical encoded QQ permission identity.
        :param new_level: Replacement native numeric level, name or level item.
        :return: No return value.
        """
        validate_key(player)
        level = self._level(new_level)
        with self._lock:
            self.remove_player(player)
            self.add_player(player, level.name)
        self.runtime.logger.info(self._PermissionManager__tr('set_permission_level.done', player, level.name))

    def set_default_permission_level(self: Self, level: int | str | PermissionLevelItem) -> None:
        """Set and save the default native permission level.
        
        :param level: Native numeric level, name or level item to use as the default.
        :return: No return value.
        """
        level = self._level(level)
        with self._lock:
            self.storage['default_level'] = level.name
            self.storage.save()
        self.runtime.logger.info(self._PermissionManager__tr('set_default_permission_level.done', level.name))
