"""QQBot access-token acquisition and expiry-aware shared refresh."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
import asyncio
import math
import time
from botcraft.utils.future_utils import report_error


class AccessTokenProvider:
    TOKEN_PATH = '/app/getAppAccessToken'

    def __init__(self: Self, runtime: Runtime, request: Callable[..., Awaitable[dict[str, Any]]]) -> None:
        """Create an expiry-aware provider sharing token refresh across requests.
        
        :param runtime: Runtime supplying application credentials and protocol services.
        :param request: Internal HTTP request coroutine callable returning a JSON response mapping.
        :return: No return value.
        """
        self.runtime = runtime
        self._request = request
        self._token = None
        self._expires_at = 0.0
        self._refresh_task = None
        self._timer = None
        self._closed = False
        self._secrets = set()

    @property
    def secrets(self: Self) -> tuple[str, ...]:
        """Return known access tokens and the application secret for redaction.
        
        :return: Credentials that must be redacted from protocol evidence.
        """
        return tuple(self._secrets) + (self.runtime.get_config().secret,)

    def invalidate(self: Self, token: str) -> None:
        """Expire the cached token only if it matches the rejected credential.
        
        :param token: Rejected token to invalidate if still current.
        :return: No return value.
        """
        if token == self._token:
            self._expires_at = 0.0

    async def get_token(self: Self) -> str:
        """Return a valid access token, sharing any necessary refresh operation.
        
        :return: Unexpired QQ access token.
        """
        if self._closed:
            raise RuntimeError('Access token provider is closed')
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token
        if self._refresh_task is None:
            self._refresh_task = asyncio.create_task(self._refresh(), name='QQ token refresh')
            self._refresh_task.add_done_callback(self._finish_refresh)
        return await asyncio.shield(self._refresh_task)

    def _finish_refresh(self: Self, task: asyncio.Task[str]) -> None:
        if self._refresh_task is task:
            self._refresh_task = None
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                report_error(error, self.runtime.logger, 'access token refresh')

    @staticmethod
    def _validate_response(data: dict[str, Any]) -> str | None:
        token = data.get('access_token')
        try:
            raw = data.get('expires_in')
            expires = float(raw) if not isinstance(raw, bool) else 0
        except (ValueError, TypeError, OverflowError):
            expires = 0
        if not isinstance(token, str) or not token or not math.isfinite(expires) or expires <= 0:
            return 'invalid access-token response'

    async def _refresh(self: Self) -> str:
        config = self.runtime.get_config()
        data = await self._request('POST', self.TOKEN_PATH,
                                   json={'appId': config.appid, 'clientSecret': config.secret},
                                   credential=True, operation='access token', validate=self._validate_response)
        token = data.get('access_token')
        self._token = token
        self._secrets.add(token)
        self.runtime.logger.secret_filter.add(token)
        expires = float(data['expires_in'])
        self._expires_at = time.monotonic() + expires
        if self._timer is not None:
            self._timer.cancel()
        self._timer = asyncio.get_running_loop().call_later(max(1, expires - 60), self._scheduled_refresh)
        self.runtime.logger.info('QQ access token refreshed (expires in %.2f seconds)', expires)
        return token

    def _scheduled_refresh(self: Self) -> None:
        if self._closed:
            return
        self.runtime.network_loop.submit(self.get_token(), operation='access token refresh')

    async def close(self: Self) -> None:
        """Cancel scheduled refresh work and discard cached credentials.
        
        :return: No return value.
        """
        self._closed = True
        if self._timer is not None:
            self._timer.cancel()
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            await asyncio.gather(self._refresh_task, return_exceptions=True)
        self._token = None
        self._secrets.clear()
