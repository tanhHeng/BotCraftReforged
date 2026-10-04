import copy
from typing import Optional

from botcraft.utils.serializer import QQSerializable


class MessageExtInfo(QQSerializable):
    ref_idx: Optional[str] = None


class QQMessageReceiptData(QQSerializable):
    id: Optional[str] = None
    timestamp: Optional[str] = None
    ext_info: Optional[MessageExtInfo] = None


class QQMessageReceipt:
    def __init__(self, raw_response, scene, conversation):
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
