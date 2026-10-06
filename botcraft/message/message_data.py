from enum import Enum
from typing import Any, Dict, List, Optional

from botcraft.message.user import User
from botcraft.utils.serializer import QQSerializable, QQStrEnum


class MessageType(int, Enum):
    """Official QQ message kind codes."""
    TEXT = 0
    ARK = 3
    PARALLEL = 101
    CHAT_HISTORY = 102
    REFERENCE = 103


class MessageSceneSource(QQStrEnum):
    """Official source codes for message scene metadata."""
    DEFAULT = 'default'


class AttachmentContentType(QQStrEnum):
    """Official attachment content-type codes."""
    VOICE = 'voice'
    JPEG = 'image/jpeg'
    PNG = 'image/png'
    GIF = 'image/gif'
    VIDEO = 'video/mp4'
    FILE = 'file'


class ARKType(QQStrEnum):
    """Official ARK card kind codes."""
    TUWEN = 'tuwen'
    FEED = 'feed'
    MINIAPP = 'miniapp'
    MAP = 'map'
    CONTACT_CARD = 'contact_card'
    VIDEO_SHARE = 'video_share'
    MUSIC_TOGETHER = 'music_together'
    PICTURE = 'picture'


class MessageScene(QQSerializable):
    """Serializable optional message source and context extensions."""
    source: Optional[str] = None
    ext: Optional[List[str]] = None
    _enum_fields = {'source': MessageSceneSource}


class MessageAttachment(QQSerializable):
    """Serializable attachment URL, dimensions, size and voice transcription facts."""
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
    """Serializable ARK card metadata with open JSON fields."""
    prompt: Optional[str] = None
    ark_type: Optional[str] = None
    ark_name: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    _enum_fields = {'ark_type': ARKType}


class MsgElement(QQSerializable):
    """Serializable nested message element, including forwarded history elements."""
    msg_idx: Optional[str] = None
    author: Optional[User] = None
    message_type: Optional[int] = None
    content: Optional[str] = None
    attachments: Optional[List[MessageAttachment]] = None
    ark_data: Optional[ARKData] = None
    msg_elements: Optional[List['MsgElement']] = None
    _enum_fields = {'message_type': MessageType}


class QQMessageReceivedData(QQSerializable):
    """Serializable received message fields; raw routing facts remain on QQMessageReceived."""
    # Official message ID used for passive replies and deletion.
    id: Optional[str] = None
    # Parsed author facts; scene routing is supplied by the received event wrapper.
    author: Optional[User] = None
    # Optional literal platform content.
    content: Optional[str] = None
    # Official group conversation OpenID, absent for private messages.
    group_openid: Optional[str] = None
    # Original platform timestamp string.
    timestamp: Optional[str] = None
    # Platform integer kind; recognized values are exposed as MessageType members.
    message_type: Optional[int] = None
    # Optional source and reference-index context extensions.
    message_scene: Optional[MessageScene] = None
    # Optional parsed attachment descriptors.
    attachments: Optional[List[MessageAttachment]] = None
    # Optional parsed mentioned users; scene routing is supplied by the event wrapper.
    mentions: Optional[List[User]] = None
    # Optional parsed ARK card content.
    ark_data: Optional[ARKData] = None
    # Optional nested message elements such as forwarded history.
    msg_elements: Optional[List[MsgElement]] = None
    _enum_fields = {'message_type': MessageType}
