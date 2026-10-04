"""QQ protocol enum values at the native Serializable field boundary.

Nested objects, containers, defaults and Optional remain MCDR's responsibility.
Scalar annotations deliberately keep native exact-type checking, including rejecting
bool for an integer field. Scalar Enum subclasses serialize as protocol values in
MCDR's existing primitive branch; unknown values remain unchanged.
"""
from enum import Enum
import copy
from typing import ClassVar, Dict, Type

from mcdreforged.utils.serializer import Serializable


class QQStrEnum(str, Enum):
    def __str__(self):
        # MCDR serializes scalar subclasses with str(obj), not obj.value.
        return self.value


def protocol_enum(enum: Type[Enum], value):
    if value is None or isinstance(value, enum):
        return value
    scalar = type(next(iter(enum)).value)
    if type(value) is not scalar:
        raise TypeError('{} requires {}, got {}'.format(enum.__name__, scalar.__name__, type(value).__name__))
    try:
        return enum(value)
    except ValueError:
        return value


class QQSerializable(Serializable):
    _enum_fields: ClassVar[Dict[str, Type[Enum]]] = {}

    def __setattr__(self, name, value):
        enum = self._enum_fields.get(name)
        if enum is not None:
            value = protocol_enum(enum, value)
        super().__setattr__(name, value)

    def copy(self, *, deep=True):
        # Native deep copy round-trips enums through their member names; QQ
        # scalar enums intentionally encode values instead. Copy the model
        # without conversion, preserving scalar enums and nested mutable data.
        return copy.deepcopy(self) if deep else copy.copy(self)
