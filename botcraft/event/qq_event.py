from typing import TYPE_CHECKING, Any
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
import copy


class QQEvent:
    """A platform dispatch envelope and independent, editable JSON view."""

    def __init__(self: Self, runtime: "Runtime", payload: dict[str, Any]) -> None:
        """Create independent editable views of a platform event envelope and its data.
        
        :param runtime: The runtime that received this event.
        :param payload: Platform JSON dispatch envelope; copied rather than retained by reference.
        :return: The method returns no value.
        """
        if not isinstance(payload, dict):
            raise TypeError('QQ event envelope must be a dict')
        self._runtime = runtime
        self.raw_payload = copy.deepcopy(payload)
        self.event_type = self.raw_payload.get('t')
        self.event_id = self.raw_payload.get('id')
        self.sequence = self.raw_payload.get('s')
        self.data = copy.deepcopy(self.raw_payload.get('d'))
        self.model_parse_failed = False
        self.parse_error = None
