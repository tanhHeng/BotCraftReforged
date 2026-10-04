"""Failure evidence at the QQ transport boundary; never infer from message text."""
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


def sanitize(value, secrets=()):
    text = str(value)
    for secret in sorted((str(s) for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)(QQBot\s+|Bearer\s+|Bot\s+)[^\s,;"\']+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:access_token|clientSecret|secret|authorization)\s*[=:]\s*)[^\s,;]+', r'\1[REDACTED]', text)
    return text


class NetworkError(RuntimeError):
    """An operation known not to have completed."""
    def __init__(self, reason, *, category=ErrorCategory.NETWORK, http_code=None,
                 err_code=None, code=None, message=None, trace_id=None, retry_after=None):
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
    def retryable(self):
        return self.category in (ErrorCategory.NETWORK, ErrorCategory.TRANSIENT, ErrorCategory.RATE_LIMIT)

    def __str__(self):
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
    def __init__(self, reason, **evidence):
        evidence['category'] = ErrorCategory.UNKNOWN
        super().__init__(reason, **evidence)

    @property
    def retryable(self):
        return False


class GatewayError(NetworkError):
    def __init__(self, reason, *, close_code=None, recoverable=False, **evidence):
        self.close_code = close_code
        self.recoverable = recoverable
        super().__init__(reason, **evidence)


class NotReadyError(RuntimeNotReadyError):
    """Synchronous rejection: the runtime is not accepting QQ operations."""
