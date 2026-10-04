"""QQBot access-token acquisition and expiry-aware shared refresh."""
import asyncio
import math
import time
from botcraft.utils.future_utils import report_error


class AccessTokenProvider:
    TOKEN_PATH = '/app/getAppAccessToken'

    def __init__(self, runtime, request):
        self.runtime = runtime
        self._request = request
        self._token = None
        self._expires_at = 0.0
        self._refresh_task = None
        self._timer = None
        self._closed = False
        self._secrets = set()

    @property
    def secrets(self):
        return tuple(self._secrets) + (self.runtime.get_config().secret,)

    def invalidate(self, token):
        if token == self._token:
            self._expires_at = 0.0

    async def get_token(self):
        if self._closed:
            raise RuntimeError('Access token provider is closed')
        if self._token and time.monotonic() < self._expires_at - 60:
            return self._token
        if self._refresh_task is None:
            self._refresh_task = asyncio.create_task(self._refresh(), name='QQ token refresh')
            self._refresh_task.add_done_callback(self._finish_refresh)
        return await asyncio.shield(self._refresh_task)

    def _finish_refresh(self, task):
        if self._refresh_task is task:
            self._refresh_task = None
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                report_error(error, self.runtime.logger, 'access token refresh')

    @staticmethod
    def _validate_response(data):
        token = data.get('access_token')
        try:
            raw = data.get('expires_in')
            expires = float(raw) if not isinstance(raw, bool) else 0
        except (ValueError, TypeError, OverflowError):
            expires = 0
        if not isinstance(token, str) or not token or not math.isfinite(expires) or expires <= 0:
            return 'invalid access-token response'

    async def _refresh(self):
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

    def _scheduled_refresh(self):
        if self._closed:
            return
        self.runtime.network_loop.submit(self.get_token(), operation='access token refresh')

    async def close(self):
        self._closed = True
        if self._timer is not None:
            self._timer.cancel()
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            await asyncio.gather(self._refresh_task, return_exceptions=True)
        self._token = None
        self._secrets.clear()
