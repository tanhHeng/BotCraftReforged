"""Persistent C2C users; real identity and conversation OpenID remain distinct."""
from __future__ import annotations
from os import PathLike
from typing import TYPE_CHECKING
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
    from botcraft.message.user import User, Scene
import copy
import json
import threading
from pathlib import Path

from mcdreforged.utils import file_utils


class KnownUserStore:
    def __init__(self: Self, runtime: Runtime, path: str | PathLike[str] = 'config/botcraft/users.json') -> None:
        """Create thread-safe storage for verified C2C user snapshots.
        
        :param runtime: Runtime owning this persistent known-user store.
        :param path: Known-user JSON storage path.
        :return: No return value.
        """
        self.runtime = runtime
        self.path = Path(path)
        self._users = {}
        self._lock = threading.RLock()

    def load(self: Self) -> None:
        """Load validated C2C identities, preserving malformed files instead of replacing them.
        
        :return: No return value.
        """
        from botcraft.message.user import User
        if not self.path.is_file():
            with self._lock:
                self._users = {}
                self._save()
            return
        try:
            with self.path.open(encoding='utf8') as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError()
            candidate = {}
            for key, value in data.items():
                user = User.deserialize(value)
                identity = user.require_identity()
                scene, _ = user.route()
                if scene != 'c2c' or key != 'c2c:' + identity:
                    raise ValueError()
                candidate[key] = user
        except Exception:
            # Unlike native preferences, no data-loss policy is authorized here.
            raise ValueError('Known C2C user file is malformed; preserved without replacement') from None
        with self._lock:
            self._users = candidate

    def _save(self: Self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with file_utils.safe_write(self.path, encoding='utf8') as stream:
            json.dump({key: user.serialize() for key, user in self._users.items()}, stream, indent=4, ensure_ascii=False)

    def record(self: Self, user: User) -> bool:
        """Persist a changed C2C user snapshot without conflating identity and route OpenIDs.
        
        :param user: QQ user snapshot; non-C2C users are ignored.
        :return: True when a changed snapshot was successfully persisted; False otherwise.
        """
        from botcraft.message.user import User
        if not isinstance(user, User):
            raise TypeError('Known users must be User instances')
        scene, _ = user.route()
        if scene != 'c2c':
            return False
        identity = user.require_identity()
        snapshot = copy.deepcopy(user)
        key = 'c2c:' + identity
        with self._lock:
            old = self._users.get(key)
            if old is not None and old.serialize() == snapshot.serialize():
                return False
            candidate = dict(self._users)
            candidate[key] = snapshot
            previous = self._users
            self._users = candidate
            try:
                self._save()
            except Exception:
                self._users = previous
                raise
        return True

    def get_user(self: Self, identity: str, *, scene: str | Scene = 'c2c') -> User | None:
        """Return an independent verified C2C user snapshot by its real identity.
        
        :param identity: Real nonempty QQ User.id, not a conversation OpenID.
        :param scene: Lookup scene, which must be c2c.
        :return: Copied known user, or None when the identity has not been recorded.
        """
        if scene != 'c2c':
            raise ValueError('Known user store contains only verified C2C identities')
        if not isinstance(identity, str) or not identity:
            raise ValueError('Known user lookup requires a real User.id')
        with self._lock:
            user = self._users.get('c2c:' + identity)
            return copy.deepcopy(user) if user is not None else None

    def get_users(self: Self) -> list[User]:
        """Return independent snapshots of every known C2C user.
        
        :return: Copied verified C2C users.
        """
        with self._lock:
            return [copy.deepcopy(user) for user in self._users.values()]
