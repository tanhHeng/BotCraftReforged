from typing import Any
from typing_extensions import Self
from botcraft.message.user import Scene
import copy
from typing import Optional

from botcraft.utils.serializer import QQSerializable


class MessageExtInfo(QQSerializable):
    """Optional platform reference index associated with a sent message."""
    ref_idx: Optional[str] = None


class QQMessageReceiptData(QQSerializable):
    """Serializable response fields for a successful message send."""
    id: Optional[str] = None
    timestamp: Optional[str] = None
    ext_info: Optional[MessageExtInfo] = None


class QQMessageReceipt:
    """Independent raw and parsed send response views with the submitted route."""
    def __init__(self: Self, raw_response: dict[str, Any], scene: Scene | str, conversation: str) -> None:
        """Snapshot the platform response and submitted routing facts after a successful send.
        
        :param raw_response: Platform JSON response; independently copied for raw and parsed views.
        :param scene: The submitted group or c2c scene.
        :param conversation: The non-empty submitted conversation OpenID.
        :return: The method returns no value.
        """
        if not isinstance(raw_response, dict):
            raise TypeError('Message receipt response must be a dict')
        if scene not in ('group', 'c2c'):
            raise ValueError('Unsupported message receipt scene')
        if not isinstance(conversation, str) or not conversation:
            raise ValueError('Receipt requires its submitted conversation OpenID')
        self.raw_response = copy.deepcopy(raw_response)
        self.receipt_data = QQMessageReceiptData.deserialize(copy.deepcopy(raw_response))
        self.scene = scene
        self.conversation = conversation
