from typing import TYPE_CHECKING, Any
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
from enum import Enum
from typing import List, Optional

from botcraft.event.qq_event import QQEvent
from botcraft.utils.serializer import QQSerializable, QQStrEnum


class InteractionType(int, Enum):
    """Official QQ interaction kind codes."""
    INLINE_KEYBOARD = 11
    CALLBACK_COMMAND = 12
    MESSAGE_FEEDBACK = 13
    CLEAR_SESSION = 14
    IN_OUT_STORY = 15
    SWITCH_MODEL = 16
    USER_AUTHORIZE = 18
    GROUP_AUTHORIZE = 19
    GROUP_AUTHORIZE_STATUS = 20


class InteractionScene(QQStrEnum):
    """Conversation scene codes reported by QQ interactions."""
    C2C = 'c2c'
    GROUP = 'group'
    GUILD = 'guild'


class InteractionChatType(int, Enum):
    """Official numeric conversation type codes."""
    GUILD = 0
    GROUP = 1
    C2C = 2


class FeedbackOption(QQStrEnum):
    """Official positive and negative message feedback options."""
    LIKE = 'LIKE'
    UNLIKE = 'UNLIKE'


class InteractionAction(QQStrEnum):
    """Official story entry and exit action codes."""
    ENTER_STORY = 'ENTER_STORY'
    QUIT_STORY = 'QUIT_STORY'


class AuthorizeScene(QQStrEnum):
    """Official user authorization UI scene codes."""
    SETTING = 'setting'
    DIALOG = 'dialog'


class AuthorizeScope(QQStrEnum):
    """Official push authorization scope codes."""
    C2C_PUSH = 'c2c_push'
    GROUP_PUSH = 'group_push'


class InteractionMessageScene(QQSerializable):
    """Serializable optional context extensions for an interaction message."""
    ext: Optional[List[str]] = None


class AuthorizeData(QQSerializable):
    """Serializable authorization scene and requested scope."""
    opt_scene: Optional[str] = None
    scope: Optional[str] = None
    _enum_fields = {'opt_scene': AuthorizeScene, 'scope': AuthorizeScope}


class InteractionResolved(QQSerializable):
    """Serializable resolved button, message, feedback and authorization facts."""
    button_data: Optional[str] = None
    button_id: Optional[str] = None
    user_id: Optional[str] = None
    feature_id: Optional[str] = None
    message_id: Optional[str] = None
    feedback_opt: Optional[str] = None
    checked: Optional[int] = None
    action: Optional[str] = None
    message_scene: Optional[InteractionMessageScene] = None
    authorize_data: Optional[AuthorizeData] = None
    _enum_fields = {'feedback_opt': FeedbackOption, 'action': InteractionAction}


class InteractionData(QQSerializable):
    """Serializable interaction kind and its resolved details."""
    type: Optional[int] = None
    resolved: Optional[InteractionResolved] = None
    _enum_fields = {'type': InteractionType}


class QQInteractionData(QQSerializable):
    """Serializable outer interaction identifiers, routing and data fields."""
    id: Optional[str] = None
    type: Optional[int] = None
    scene: Optional[str] = None
    chat_type: Optional[int] = None
    timestamp: Optional[str] = None
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    user_openid: Optional[str] = None
    group_openid: Optional[str] = None
    group_member_openid: Optional[str] = None
    data: Optional[InteractionData] = None
    version: Optional[int] = None
    application_id: Optional[str] = None
    _enum_fields = {'type': InteractionType, 'scene': InteractionScene, 'chat_type': InteractionChatType}


class QQInteraction(QQEvent):
    """A received QQ interaction with independent raw facts and parsed model."""
    def __init__(self: Self, runtime: "Runtime", payload: dict[str, Any], model: QQInteractionData) -> None:
        """Create an interaction event with raw platform facts and parsed interaction data.
        
        :param runtime: Runtime receiving and responding to this interaction.
        :param payload: Original platform JSON dispatch envelope, copied by the base event.
        :param model: Parsed interaction data; must be a QQInteractionData instance.
        :return: The method returns no value.
        """
        if not isinstance(model, QQInteractionData):
            raise TypeError('model must be QQInteractionData')
        super().__init__(runtime, payload)
        self.interaction_data = model
        self.interaction_id = self.raw_payload['d'].get('id')
