class UnsupportedOperationError(RuntimeError):
    """The MCDR operation has no supported QQ equivalent."""


class RuntimeNotReadyError(RuntimeError):
    """The runtime or gateway is not accepting new operations."""


class PassiveReplyExpiredError(ValueError):
    """The passive reply reference exceeds the framework's ten-minute retention period."""
