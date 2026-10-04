"""QQ identity adaptation of native permission lists and highest-level lookup."""
import threading
from urllib.parse import quote, unquote

from ruamel.yaml import YAML
from mcdreforged.permission.permission_level import PermissionLevel, PermissionLevelItem
from mcdreforged.permission.permission_manager import PermissionManager as NativePermissionManager, PermissionStorage as NativePermissionStorage

from botcraft.config import ResourceStorageMixin
from botcraft.permission.permission_policy import POLICIES


def subject_user(subject):
    from botcraft.message.user import User
    from botcraft.command.command_source import QQCommandSource
    if isinstance(subject, User):
        return subject
    if isinstance(subject, QQCommandSource):
        return subject.user
    raise TypeError('Permission subject must be a User or QQCommandSource')


def encode_identity(user, *, global_scope=False):
    identity = user.require_identity()
    if global_scope:
        return 'global:' + quote(identity, safe='')
    scene, conversation = user.route()
    return ':'.join((scene, quote(conversation, safe=''), quote(identity, safe='')))


def validate_key(key):
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
    def __init__(self, runtime, path):
        self.runtime = runtime
        self.path = str(path)
        self.storage = self._new_storage()
        self._lock = threading.RLock()
        self._PermissionManager__tr = runtime.create_internal_translator('permission_manager').tr

    def _new_storage(self):
        return PermissionStorage(self.runtime.logger, self.path, 'resources/default_permission.yml')

    @staticmethod
    def encode_key(subject, *, global_scope=False):
        if type(global_scope) is not bool:
            raise TypeError('global_scope must be bool')
        return encode_identity(subject_user(subject), global_scope=global_scope)

    def load_permission_file(self, *, allowed_missing_file=False):
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
    def _validate_storage(data, *, partial=False):
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

    def is_super_admin(self, subject):
        from botcraft.command.command_source import ConsoleSource
        if isinstance(subject, ConsoleSource):
            return True
        user = subject_user(subject)
        return user.require_identity() in self.runtime.get_config().permission.super_admins

    def get_permission(self, subject):
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

    def _operation_user(self, subject, *, global_scope):
        user = subject_user(subject)
        user.require_identity()
        if not global_scope:
            scene, conversation = user.route()
            if scene == 'c2c':
                known = self.runtime.users.get_user(user.id)
                if known is None or known.route() != (scene, conversation):
                    raise ValueError('C2C permissions require a known User with its verified private route')
        return user

    def set_permission(self, subject, value, *, global_scope=False):
        if type(global_scope) is not bool:
            raise TypeError('global_scope must be bool')
        key = encode_identity(self._operation_user(subject, global_scope=global_scope), global_scope=global_scope)
        self.set_permission_level(key, self._level(value))

    def remove_permission(self, subject, *, global_scope=False):
        if type(global_scope) is not bool:
            raise TypeError('global_scope must be bool')
        self.remove_player(encode_identity(self._operation_user(subject, global_scope=global_scope), global_scope=global_scope))

    @staticmethod
    def _level(value):
        if isinstance(value, PermissionLevelItem):
            if PermissionLevel.from_value(value.level) != value:
                raise ValueError('Invalid permission level item')
            return value
        if type(value) is bool:
            raise TypeError('Permission level must not be bool')
        return PermissionLevel.from_value(value)

    # These native mutation methods touch mcdr_server for logging; replace only that
    # coupling, retaining native list storage, highest-level lookup and safe YAML writes.
    def add_player(self, player, level_name=None):
        validate_key(player)
        level = self._level(self.get_default_permission_level() if level_name is None else level_name)
        with self._lock:
            self.get_permission_group_list(level.level).append(player)
            self.storage.save()
        self.runtime.logger.mdebug('Added QQ identity {} with permission {}'.format(player, level.name))
        return level.level

    def remove_player(self, player):
        validate_key(player)
        with self._lock:
            while (level := self.get_player_permission_level(player, auto_add=False)) is not None:
                self.get_permission_group_list(level).remove(player)
            self.storage.save()
        self.runtime.logger.mdebug('Removed QQ permission identity {}'.format(player))

    def set_permission_level(self, player, new_level):
        validate_key(player)
        level = self._level(new_level)
        with self._lock:
            self.remove_player(player)
            self.add_player(player, level.name)
        self.runtime.logger.info(self._PermissionManager__tr('set_permission_level.done', player, level.name))

    def set_default_permission_level(self, level):
        level = self._level(level)
        with self._lock:
            self.storage['default_level'] = level.name
            self.storage.save()
        self.runtime.logger.info(self._PermissionManager__tr('set_default_permission_level.done', level.name))
