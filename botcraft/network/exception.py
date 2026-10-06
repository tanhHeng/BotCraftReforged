"""Failure evidence at the QQ transport boundary; never infer from message text."""
from typing import Iterable, TypedDict
from typing_extensions import Self, Unpack


class _FailureEvidence(TypedDict, total=False):
    category: 'ErrorCategory'
    http_code: int | None
    err_code: int | None
    code: int | None
    message: str | None
    trace_id: str | None
    retry_after: float | None
from enum import Enum
import re
from botcraft.utils.exception import RuntimeNotReadyError


class ErrorCategory(str, Enum):
    AUTHENTICATION = 'authentication'
    PERMISSION = 'permission'
    RATE_LIMIT = 'rate_limit'
    INVALID_REQUEST = 'invalid_request'
    TRANSIENT = 'transient'
    PLATFORM = 'platform'
    NETWORK = 'network'
    UNKNOWN = 'result_unknown'


def sanitize(value: object, secrets: Iterable[str] = ()) -> str:
    """Render protocol evidence while redacting supplied and recognizable credentials.
    
    :param value: Protocol evidence to render as sanitized text.
    :param secrets: Known credentials to remove from evidence.
    :return: Result of the operation.
    """
    text = str(value)
    for secret in sorted((str(s) for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)(QQBot\s+|Bearer\s+|Bot\s+)[^\s,;"\']+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:access_token|clientSecret|secret|authorization)\s*[=:]\s*)[^\s,;]+', r'\1[REDACTED]', text)
    return text


class NetworkError(RuntimeError):
    """An operation known not to have completed."""
    def __init__(self: Self, reason: str, *, category: ErrorCategory = ErrorCategory.NETWORK, http_code: int | None = None,
                 err_code: int | None = None, code: int | None = None, message: str | None = None, trace_id: str | None = None, retry_after: float | None = None) -> None:
        """Record failure evidence for an operation known not to have completed.
        
        :param reason: Sanitized human-readable failure reason.
        :param category: Evidence-based failure category.
        :param http_code: HTTP response status, when available.
        :param err_code: QQ OpenAPI business error code, when available.
        :param code: Credential endpoint business error code, when available.
        :param message: Sanitized platform error message.
        :param trace_id: Sanitized platform trace identifier.
        :param retry_after: Platform retry delay in seconds, when available.
        :return: No return value.
        """
        self.reason = reason
        self.category = category
        self.http_code = http_code
        self.err_code = err_code
        self.code = code
        self.message = message
        self.trace_id = trace_id
        self.retry_after = retry_after
        super().__init__(self.__str__())

    @property
    def retryable(self: Self) -> bool:
        """Report whether the evidence category allows a consumer to consider retrying.
        
        :return: True for network, transient and rate-limit categories.
        """
        return self.category in (ErrorCategory.NETWORK, ErrorCategory.TRANSIENT, ErrorCategory.RATE_LIMIT)

    def __str__(self: Self) -> str:
        fields = [self.category.value, str(self.reason)]
        for name in ('http_code', 'err_code', 'code', 'message', 'trace_id'):
            value = getattr(self, name)
            if value is not None:
                fields.append(f'{name}={value}')
        return '; '.join(fields)


class PlatformError(NetworkError):
    """A definite rejection supported by HTTP or documented business evidence."""


class ResultUnknownError(NetworkError):
    """The platform may have applied this operation. Never replay automatically."""
    def __init__(self: Self, reason: str, **evidence: Unpack[_FailureEvidence]) -> None:
        """Record an uncertain platform outcome that must not be automatically replayed.
        
        :param reason: Sanitized human-readable failure reason.
        :param evidence: Typed optional HTTP and business failure evidence.
        :return: No return value.
        """
        evidence['category'] = ErrorCategory.UNKNOWN
        super().__init__(reason, **evidence)

    @property
    def retryable(self: Self) -> bool:
        """Always reject automatic retry for an uncertain platform outcome.
        
        :return: False for every uncertain platform outcome.
        """
        return False


class GatewayError(NetworkError):
    def __init__(self: Self, reason: str, *, close_code: int | None = None, recoverable: bool = False, **evidence: Unpack[_FailureEvidence]) -> None:
        """Record gateway failure evidence and reconnect recoverability.
        
        :param reason: Sanitized human-readable failure reason.
        :param close_code: Websocket close code, when available.
        :param recoverable: Whether this gateway failure permits establishing a new session.
        :param evidence: Typed optional HTTP and business failure evidence.
        :return: No return value.
        """
        self.close_code = close_code
        self.recoverable = recoverable
        super().__init__(reason, **evidence)


class NotReadyError(RuntimeNotReadyError):
    """Synchronous rejection: the runtime is not accepting QQ operations."""
