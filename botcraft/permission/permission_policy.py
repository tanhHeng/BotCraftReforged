"""Default permission policies; explicit grants are resolved by the manager first."""
from typing_extensions import Self
from botcraft.message.user import User
from abc import ABC, abstractmethod
from enum import Enum


class PermissionPolicy(ABC):
    @abstractmethod
    def default_permission(self: Self, user: User) -> int:
        """Resolve a default permission for a QQ user after explicit grants are exhausted.
        
        :param user: QQ user and optional group role to evaluate.
        :return: Default numeric permission level.
        """
        raise NotImplementedError


class NativePermissionPolicy(PermissionPolicy):
    def default_permission(self: Self, user: User) -> int:
        """Return the native guest default without consulting QQ member roles.
        
        :param user: QQ user and optional group role to evaluate.
        :return: Guest permission level zero.
        """
        return 0


class RolePermissionPolicy(PermissionPolicy):
    def default_permission(self: Self, user: User) -> int:
        """Resolve the group member role into the default QQ permission level.
        
        :param user: QQ user and optional group role to evaluate.
        :return: Guest, administrator or owner level based on the supported group role.
        """
        scene = user.scene.value if isinstance(user.scene, Enum) else user.scene
        if scene != 'group':
            return 0
        role = user.member_role
        if isinstance(role, Enum):
            role = role.value
        return {'member': 0, 'admin': 2, 'owner': 4}.get(role, 0)


class MixedPermissionPolicy(RolePermissionPolicy):
    pass


POLICIES = {'native': NativePermissionPolicy(), 'role': RolePermissionPolicy(), 'mixed': MixedPermissionPolicy()}
