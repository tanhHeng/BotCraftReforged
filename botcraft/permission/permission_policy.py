"""Default permission policies; explicit grants are resolved by the manager first."""
from abc import ABC, abstractmethod
from enum import Enum


class PermissionPolicy(ABC):
    @abstractmethod
    def default_permission(self, user):
        raise NotImplementedError


class NativePermissionPolicy(PermissionPolicy):
    def default_permission(self, user):
        return 0


class RolePermissionPolicy(PermissionPolicy):
    def default_permission(self, user):
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
