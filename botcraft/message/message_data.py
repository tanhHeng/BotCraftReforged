from enum import Enum
from typing import Any, Dict, List, Optional

from botcraft.message.user import User
from botcraft.utils.serializer import QQSerializable, QQStrEnum


class MessageType(int, Enum):
    TEXT = 0
    ARK = 3
    PARALLEL = 101
    CHAT_HISTORY = 102
    REFERENCE = 103


class MessageSceneSource(QQStrEnum):
    DEFAULT = 'default'


class AttachmentContentType(QQStrEnum):
    VOICE = 'voice'
    JPEG = 'image/jpeg'
    PNG = 'image/png'
    GIF = 'image/gif'
    VIDEO = 'video/mp4'
    FILE = 'file'


class ARKType(QQStrEnum):
    TUWEN = 'tuwen'
    FEED = 'feed'
    MINIAPP = 'miniapp'
    MAP = 'map'
    CONTACT_CARD = 'contact_card'
    VIDEO_SHARE = 'video_share'
    MUSIC_TOGETHER = 'music_together'
    PICTURE = 'picture'


class MessageScene(QQSerializable):
    source: Optional[str] = None
    ext: Optional[List[str]] = None
    _enum_fields = {'source': MessageSceneSource}


class MessageAttachment(QQSerializable):
    url: Optional[str] = None
    filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size: Optional[int] = None
    content_type: Optional[str] = None
    voice_wav_url: Optional[str] = None
    asr_refer_text: Optional[str] = None
    _enum_fields = {'content_type': AttachmentContentType}


class ARKData(QQSerializable):
    prompt: Optional[str] = None
    ark_type: Optional[str] = None
    ark_name: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    _enum_fields = {'ark_type': ARKType}


class MsgElement(QQSerializable):
    msg_idx: Optional[str] = None
    author: Optional[User] = None
    message_type: Optional[int] = None
    content: Optional[str] = None
    attachments: Optional[List[MessageAttachment]] = None
    ark_data: Optional[ARKData] = None
    msg_elements: Optional[List['MsgElement']] = None
    _enum_fields = {'message_type': MessageType}


class QQMessageReceivedData(QQSerializable):
    id: Optional[str] = None
    author: Optional[User] = None
    content: Optional[str] = None
    group_openid: Optional[str] = None
    timestamp: Optional[str] = None
    message_type: Optional[int] = None
    message_scene: Optional[MessageScene] = None
    attachments: Optional[List[MessageAttachment]] = None
    mentions: Optional[List[User]] = None
    ark_data: Optional[ARKData] = None
    msg_elements: Optional[List[MsgElement]] = None
    _enum_fields = {'message_type': MessageType}
