"""Internal typed QQ OpenAPI client. No generic public request escape hatch."""
import asyncio
from collections import deque
import json as json_module
import math
import time
from types import SimpleNamespace
from urllib.parse import quote

import aiohttp
from botcraft.logging.logger import log_raw_response

from .access_token_provider import AccessTokenProvider
from .exception import ErrorCategory, NetworkError, PlatformError, ResultUnknownError, sanitize


# Categories derive from the documented public and per-interface numeric tables.
_AUTH = {11241, 11243}
_PERMISSION = {11282, 11253, 11254, 11264, 11265, 304004, 304036, 304064,
               40034101, 40034105, 40034127, 40054002, 40054003, 40054004,
               40054013, 40062003, 630003}
_TRANSIENT = {11281, 11252, 11263, 11242, 40030009, 630004, 630005, 50065001,
              50055001, 50055002, 50055006, 40054006}
_RATE = {20028, 40034100}
_INVALID = {11251, 11261, 11262, 11275, 12002, 22006, 304061, 304062, 304080,
            304103, 305007, 306009, 340069, 50059, 630001, 630007, 630008,
            40030001, 40030006, 40030008, 40030011, 40030012, 40030013, 40030015,
            40030016, 40030018, 40030020, 40030021, 40034005, 40034006, 40034008,
            40034009, 40034010, 40034011, 40034024, 40034025, 40034026, 40034027,
            40034029, 40034106, 40034108, 40034109, 40034124, 40034128, 40054005,
            40054007, 40054010, 40054018, 40061001, 40061002, 40064004}


def _category(status, code, credential):
    if credential:
        if code == 100001:
            return ErrorCategory.RATE_LIMIT
        if code in (100007, 100016, 10004):
            return ErrorCategory.AUTHENTICATION
    if status == 401 or code in _AUTH:
        return ErrorCategory.AUTHENTICATION
    if status == 403 or code in _PERMISSION:
        return ErrorCategory.PERMISSION
    if status == 429 or code in _RATE:
        return ErrorCategory.RATE_LIMIT
    if status >= 500 or code in _TRANSIENT:
        return ErrorCategory.TRANSIENT
    if 400 <= status < 500 or code in _INVALID:
        return ErrorCategory.INVALID_REQUEST
    return ErrorCategory.PLATFORM


def _id(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a non-empty string')
    return quote(value, safe='')


def _scene(scene):
    scene = getattr(scene, 'value', scene)
    if scene not in ('group', 'c2c'):
        raise ValueError('Only group and c2c are supported')
    return scene


class ApiClient:
    BASE_URL = 'https://api.bot.qq.com'

    def __init__(self, runtime):
        self.runtime = runtime
        self._session = None
        self._closed = False
        self._base_url = self.BASE_URL
        self.token_provider = AccessTokenProvider(runtime, self._request)
        self._panel_writes = deque()
        self._panel_queries = deque()
        self._panel_write_lock = asyncio.Lock()
        self._panel_query_lock = asyncio.Lock()

    async def start(self):
        if self._session is not None or self._closed:
            raise RuntimeError('ApiClient may be started only once')
        trace = aiohttp.TraceConfig()

        async def headers_sent(session, context, params):
            if context.trace_request_ctx is not None:
                context.trace_request_ctx.sent = True

        trace.on_request_headers_sent.append(headers_sent)
        self._session = aiohttp.ClientSession(trace_configs=[trace])
        await self.token_provider.get_token()

    async def close(self):
        self._closed = True
        await self.token_provider.close()
        if self._session is not None:
            await self._session.close()

    async def _request(self, method, path, *, json=None, params=None, credential=False,
                       operation, allow_empty=False, required=(), validate=None):
        if self._session is None or self._closed:
            raise RuntimeError('ApiClient is not open')
        token = None if credential else await self.token_provider.get_token()
        secrets = self.token_provider.secrets
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        if token is not None:
            headers['Authorization'] = 'QQBot ' + token
        config = self.runtime.get_config()
        timeout = aiohttp.ClientTimeout(total=config.http.timeout)
        context = SimpleNamespace(sent=False)
        status = None
        trace_id = None
        modifying = method != 'GET'
        try:
            async with self._session.request(method, self._base_url + path, json=json, params=params,
                                             headers=headers, timeout=timeout, allow_redirects=False,
                                             trace_request_ctx=context) as response:
                status = response.status
                trace_id = response.headers.get('X-Tps-trace-ID')
                trace_id = sanitize(trace_id, secrets) if trace_id else None
                raw = await response.read()
                log_raw_response(self.runtime, 'HTTP', raw, operation=operation, http_code=status)
                try:
                    data = json_module.loads(raw) if raw else {}
                except (ValueError, UnicodeError):
                    evidence = {'http_code': status, 'trace_id': sanitize(trace_id, secrets) if trace_id else None}
                    cls = ResultUnknownError if modifying and 200 <= status < 300 else PlatformError
                    raise cls('response is not valid JSON', **evidence) from None
                if not isinstance(data, dict):
                    cls = ResultUnknownError if modifying and 200 <= status < 300 else PlatformError
                    raise cls('response is not a JSON object', http_code=status, trace_id=trace_id)
                key = 'code' if credential else 'err_code'
                code = data.get(key)
                if code is not None and (isinstance(code, bool) or not isinstance(code, int)):
                    cls = ResultUnknownError if modifying and 200 <= status < 300 else PlatformError
                    raise cls('invalid business error code', http_code=status, trace_id=trace_id)
                evidence = {'http_code': status, key: code,
                            'message': sanitize(data['message'], secrets) if 'message' in data else None,
                            'trace_id': sanitize(data.get('trace_id', trace_id), secrets) if data.get('trace_id', trace_id) else None}
                retry_after = response.headers.get('Retry-After')
                try:
                    delay = float(retry_after) if retry_after else None
                    evidence['retry_after'] = max(0, delay) if delay is not None and math.isfinite(delay) else None
                except ValueError:
                    pass
                if code in (304023, 304024):
                    raise ResultUnknownError(operation + ' awaiting platform audit', **evidence)
                if code not in (None, 0) or not 200 <= status < 300:
                    category = _category(status, code, credential)
                    if category == ErrorCategory.AUTHENTICATION and token is not None:
                        self.token_provider.invalidate(token)
                    raise PlatformError(operation + ' rejected', category=category, **evidence)
                # Interface success data confirms a creation/update independently
                # of status; audit business codes above never count as completion.
                if status in (201, 202) and not required and validate is None:
                    raise ResultUnknownError(operation + ' accepted asynchronously, outcome unconfirmed', **evidence)
                if not raw and not allow_empty:
                    cls = ResultUnknownError if modifying else PlatformError
                    raise cls('missing response body', **evidence)
                for field in required:
                    if not isinstance(data.get(field), str) or not data[field]:
                        cls = ResultUnknownError if modifying else PlatformError
                        raise cls('missing response field ' + field, **evidence)
                if validate is not None:
                    reason = validate(data)
                    if reason is not None:
                        cls = ResultUnknownError if modifying else PlatformError
                        raise cls(reason, **evidence)
                return data
        except (PlatformError, ResultUnknownError):
            raise
        except asyncio.CancelledError:
            if modifying and context.sent:
                raise ResultUnknownError(operation + ' interrupted after request headers were sent',
                                         http_code=status, trace_id=trace_id) from None
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as error:
            cls = ResultUnknownError if modifying and context.sent else NetworkError
            # No URL/header/response dump: aiohttp exceptions may retain authorization.
            reason = sanitize(f'{operation}: {type(error).__name__}', secrets)
            raise cls(reason, http_code=status, trace_id=trace_id) from None

    async def get_gateway(self):
        data = await self._request('GET', '/gateway', operation='gateway discovery', required=('url',))
        return data['url']

    async def send_message(self, scene, conversation, payload):
        kind = 'groups' if _scene(scene) == 'group' else 'users'
        return await self._request('POST', f'/v2/{kind}/{_id(conversation, "conversation")}/messages',
                                   json=payload, operation='send message', required=('id',))

    async def delete_message(self, scene, conversation, id):
        kind = 'groups' if _scene(scene) == 'group' else 'users'
        await self._request('DELETE', f'/v2/{kind}/{_id(conversation, "conversation")}/messages/{_id(id, "message id")}',
                            operation='delete message', allow_empty=True)

    async def respond_interaction(self, id, code):
        await self._request('PUT', f'/interactions/{_id(id, "interaction id")}', json={'code': code},
                            operation='respond interaction', allow_empty=True)

    @staticmethod
    def _delay(history, limit):
        now = time.monotonic()
        while history and history[0] <= now - 60:
            history.popleft()
        return max(0, history[0] + 60 - now) if len(history) >= limit else 0

    def panel_write_delay(self):
        return self._delay(self._panel_writes, 10)

    async def _panel_slot(self, write):
        lock = self._panel_write_lock if write else self._panel_query_lock
        history = self._panel_writes if write else self._panel_queries
        limit = 10 if write else 30
        async with lock:
            delay = self._delay(history, limit)
            if delay:
                await asyncio.sleep(delay)
            history.append(time.monotonic())  # Failures consume exactly the same slot.

    @staticmethod
    def _validate_panel_page(data, scope):
        if not isinstance(data.get('records'), list):
            return 'invalid panel records'
        for record in data['records']:
            if not isinstance(record, dict) or record.get('scope') != scope or not isinstance(record.get('panel_id'), str) or not record['panel_id']:
                return 'invalid panel record or wrong scope'
        # QQ may omit next_cursor when is_end explicitly marks the final page.
        next_cursor = data.get('next_cursor', '' if data.get('is_end') is True else None)
        if not isinstance(next_cursor, str) or not isinstance(data.get('is_end'), bool):
            return 'invalid panel pagination metadata'

    @staticmethod
    def _validate_panel_version(data):
        version = data.get('version')
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            return 'invalid panel version response'

    async def list_panels(self, scope):
        scope = _scene(scope)
        records = []
        cursor = ''
        seen = set()
        while True:
            await self._panel_slot(False)
            data = await self._request('GET', '/v2/panels', params={'scope': scope, 'limit': 50, 'cursor': cursor},
                                       operation='list ' + scope + ' panels',
                                       validate=lambda data: self._validate_panel_page(data, scope) or (
                                           'repeated panel pagination cursor' if data.get('next_cursor') in seen else None))
            page = data.get('records')
            for record in page:
                records.append(record)
            next_cursor = data.get('next_cursor')
            if data.get('is_end') is True or next_cursor == '':
                return records
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen:
                raise PlatformError('invalid or repeated panel pagination cursor', category=ErrorCategory.INVALID_REQUEST)
            seen.add(next_cursor)
            cursor = next_cursor

    async def create_panel(self, scope, items):
        await self._panel_slot(True)
        return await self._request('POST', '/v2/panels',
                                   json={'scope': _scene(scope), 'target_type': 'all',
                                         'panel': {'items': items, 'remark': 'BotCraft'}},
                                   operation='create ' + scope + ' panel', required=('panel_id',))

    async def modify_panel(self, panel_id, items):
        await self._panel_slot(True)
        return await self._request('PUT', '/v2/panels/' + _id(panel_id, 'panel id'),
                                   json={'panel': {'items': items, 'remark': 'BotCraft'}},
                                   operation='modify panel', validate=self._validate_panel_version)

    async def delete_panel(self, panel_id):
        await self._panel_slot(True)
        await self._request('DELETE', '/v2/panels/' + _id(panel_id, 'panel id'),
                            operation='delete panel', allow_empty=True)
