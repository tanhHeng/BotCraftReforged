from typing_extensions import Self
from typing import Optional

from botcraft.utils.serializer import QQSerializable, QQStrEnum


class Scene(QQStrEnum):
    """Supported QQ message conversation scenes."""
    GROUP = 'group'
    C2C = 'c2c'


class MemberRole(QQStrEnum):
    """Official member role codes."""
    MEMBER = 'member'
    ADMIN = 'admin'
    OWNER = 'owner'


class User(QQSerializable):
    """Serializable user facts and routing identifiers for a QQ conversation."""
    id: Optional[str] = None
    username: Optional[str] = None
    bot: Optional[bool] = None
    union_openid: Optional[str] = None
    union_user_account: Optional[str] = None
    user_openid: Optional[str] = None
    member_openid: Optional[str] = None
    member_role: Optional[str] = None
    scene: Optional[str] = None
    group_openid: Optional[str] = None
    _enum_fields = {'member_role': MemberRole, 'scene': Scene}

    def require_identity(self: Self) -> str:
        """Require a real, non-empty official user identity.
        
        :return: The official user ID; an invalid or absent ID raises ValueError.
        """
        if not isinstance(self.id, str) or not self.id:
            raise ValueError('User requires a real, non-empty official id')
        return self.id

    def route(self: Self) -> tuple[str, str]:
        """Resolve the supported conversation route from the stored scene and OpenIDs.
        
        :return: The group or c2c scene and its conversation OpenID; incomplete routing facts raise ValueError.
        """
        scene = self.scene
        if scene is None and isinstance(self.user_openid, str) and self.user_openid:
            scene = Scene.C2C
        if scene == Scene.GROUP:
            conversation = self.group_openid
        elif scene == Scene.C2C:
            conversation = self.user_openid
        else:
            raise ValueError('User has no supported QQ conversation scene')
        if not isinstance(conversation, str) or not conversation:
            raise ValueError('User is missing its conversation OpenID')
        return str(scene.value if isinstance(scene, Scene) else scene), conversation


class MentionedUser(User):
    """Mentioned user facts, including whether the mention targets this bot."""
    is_you: Optional[bool] = None


class Group(QQSerializable):
    """A group target identified by its official conversation OpenID."""
    group_openid: Optional[str] = None

    def __init__(self: Self, group_openid: str | None = None) -> None:
        """Create a group target using its conversation OpenID.
        
        :param group_openid: The optional official group OpenID; route requires it to be non-empty.
        :return: The method returns no value.
        """
        super().__init__(group_openid=group_openid)

    def route(self: Self) -> tuple[str, str]:
        """Require a usable official group conversation route.
        
        :return: The group scene and non-empty group OpenID.
        """
        if not isinstance(self.group_openid, str) or not self.group_openid:
            raise ValueError('Group requires a non-empty group_openid')
        return 'group', self.group_openid
