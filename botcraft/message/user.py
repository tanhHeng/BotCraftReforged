from typing import Optional

from botcraft.utils.serializer import QQSerializable, QQStrEnum


class Scene(QQStrEnum):
    GROUP = 'group'
    C2C = 'c2c'


class MemberRole(QQStrEnum):
    MEMBER = 'member'
    ADMIN = 'admin'
    OWNER = 'owner'


class User(QQSerializable):
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

    def require_identity(self) -> str:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError('User requires a real, non-empty official id')
        return self.id

    def route(self):
        # An explicit private target need not invent a User.id or scene.
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


class Group(QQSerializable):
    group_openid: Optional[str] = None

    def __init__(self, group_openid=None):
        super().__init__(group_openid=group_openid)

    def route(self):
        if not isinstance(self.group_openid, str) or not self.group_openid:
            raise ValueError('Group requires a non-empty group_openid')
        return 'group', self.group_openid
