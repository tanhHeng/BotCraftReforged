"""Single-shard QQ Gateway; every reconnect identifies a fresh session."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, NoReturn
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
import asyncio
from enum import Enum
import json
import math
import platform
import random
import time
from urllib.parse import urlsplit

import aiohttp
from botcraft.utils.future_utils import report_error
from botcraft.logging.logger import log_raw_response
from .exception import ErrorCategory, GatewayError, NetworkError, PlatformError


class GatewayState(str, Enum):
    CREATED = 'created'
    CONNECTING = 'connecting'
    IDENTIFYING = 'identifying'
    READY = 'ready'
    OFFLINE = 'offline'
    STOPPING = 'stopping'
    STOPPED = 'stopped'
    FAILED = 'failed'


_FATAL_CLOSE = {4001, 4002, 4010, 4011, 4012, 4013, 4014, 4914, 4915}


class GatewayClient:
    READY_TIMEOUT = 60

    def __init__(self: Self, runtime: Runtime) -> None:
        """Initialize a single-shard QQ gateway with fresh-session reconnect state.
        
        :param runtime: Runtime providing the API client, network loop and event dispatcher.
        :return: No return value.
        """
        self.runtime = runtime
        self.state = GatewayState.CREATED
        self._ws = None
        self._runner = None
        self._first_ready = None
        self._closing = False
        self._sequence = None
        self._ack_pending = False
        self._gateway_url = None
        self._last_identify = 0.0
        self._last_discovery = float('-inf')
        self._intents = runtime.get_config().gateway.intent_mask
        self._config_reconnect = False

    def is_ready(self: Self) -> bool:
        """Report whether the gateway is ready and not closing.
        
        :return: True only while the gateway is ready and not closing.
        """
        return self.state == GatewayState.READY and not self._closing

    async def apply_config(self: Self) -> None:
        """Apply changed intents and disconnect so the next session identifies afresh.
        
        :return: No return value.
        """
        intents = self.runtime.get_config().gateway.intent_mask
        if intents == self._intents:
            return
        self._intents = intents
        if self.state in (GatewayState.CREATED, GatewayState.STOPPING, GatewayState.STOPPED, GatewayState.FAILED):
            return
        self._config_reconnect = True
        self.state = GatewayState.OFFLINE
        if self._ws is not None:
            await self._ws.close(code=1000)

    async def start(self: Self) -> None:
        """Start the gateway runner and wait for its first READY within the configured deadline.
        
        :return: No return value.
        """
        if self.state != GatewayState.CREATED:
            raise RuntimeError('Gateway may be started only once')
        self._first_ready = asyncio.get_running_loop().create_future()
        self.state = GatewayState.CONNECTING
        self._runner = self.runtime.network_loop.submit(self._run(), operation='QQ gateway')
        try:
            await asyncio.wait_for(asyncio.shield(self._first_ready), timeout=self.READY_TIMEOUT)
        except asyncio.TimeoutError:
            await self.close()
            raise GatewayError('first READY deadline exceeded (60 seconds)') from None

    async def close(self: Self) -> None:
        """Close the gateway and wait a bounded time for the runner to finish.
        
        :return: No return value.
        """
        if self.state == GatewayState.STOPPED:
            return
        failed = self.state == GatewayState.FAILED
        self._closing = True
        stop_timed_out = False
        if not failed:
            self.state = GatewayState.STOPPING
        if self._ws is not None:
            await self._ws.close(code=1000)
        if self._runner is not None:
            # The runner checks closing between bounded connection attempts/backoff.
            try:
                await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(self._runner)), timeout=10)
            except asyncio.TimeoutError as error:
                stop_timed_out = True
                report_error(error, self.runtime.logger, 'QQ gateway stop timed out; background tasks may still be shutting down')
            except NetworkError:
                pass
        if self._first_ready is not None and not self._first_ready.done():
            self._first_ready.cancel()
        if not failed:
            self.state = GatewayState.STOPPED
        if not stop_timed_out:
            self.runtime.logger.info('QQ gateway stopped' if self._runner is not None else 'QQ gateway closed (not started)')

    def _fatal(self: Self, error: BaseException) -> None:
        self.state = GatewayState.FAILED
        report_error(error, self.runtime.logger, 'Unrecoverable QQ gateway failure')
        if not self._first_ready.done():
            self._first_ready.set_exception(error)

    async def _run(self: Self) -> None:
        attempts = 0
        try:
            while not self._closing:
                self.state = GatewayState.CONNECTING
                try:
                    if self._gateway_url is None:
                        delay = self._last_discovery + 30 - time.monotonic()
                        if delay > 0:
                            await asyncio.sleep(delay)
                        if self._closing:
                            return
                        self._last_discovery = time.monotonic()
                        self._gateway_url = await self.runtime.api_client.get_gateway()
                        self.runtime.logger.info('QQ gateway URL acquired')
                    parsed = urlsplit(self._gateway_url)
                    if parsed.scheme not in ('wss', 'ws') or not parsed.netloc:
                        raise GatewayError('invalid gateway URL')
                    token = await self.runtime.api_client.token_provider.get_token()
                    await self._connection(token)
                    attempts = 0
                except GatewayError as error:
                    if not error.recoverable:
                        self._fatal(error)
                        raise
                    if not self._closing and not self._config_reconnect:
                        report_error(error, self.runtime.logger, 'QQ gateway disconnected')
                except PlatformError as error:
                    if not error.retryable:
                        self._fatal(error)
                        raise
                    report_error(error, self.runtime.logger, 'QQ gateway connection')
                except NetworkError as error:
                    report_error(error, self.runtime.logger, 'QQ gateway connection')
                except aiohttp.WSServerHandshakeError as error:
                    failure = GatewayError('gateway HTTP handshake rejected', http_code=error.status,
                                           recoverable=error.status == 429 or error.status >= 500)
                    if not failure.recoverable:
                        self._fatal(failure)
                        raise failure from None
                    report_error(failure, self.runtime.logger, 'QQ gateway connection')
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as error:
                    report_error(NetworkError('gateway ' + type(error).__name__), self.runtime.logger, 'QQ gateway connection')
                if self._closing:
                    break
                self.state = GatewayState.OFFLINE
                attempts += 1
                delay = min(60, 5 * 2 ** min(attempts - 1, 4)) + random.uniform(0, 1)
                self.runtime.logger.info('QQ gateway offline; reconnecting in %.2f seconds (attempt %s, intents changed=%s)',
                                         delay, attempts, self._config_reconnect)
                deadline = time.monotonic() + delay
                while not self._closing and time.monotonic() < deadline:
                    await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))
        except asyncio.CancelledError:
            if not self._closing:
                self._fatal(GatewayError('gateway task cancelled'))
            raise
        except Exception as error:
            if self.state != GatewayState.FAILED:
                self._fatal(error)
            raise
        finally:
            if self.state != GatewayState.FAILED:
                self.state = GatewayState.STOPPED if self._closing else GatewayState.OFFLINE

    async def _connection(self: Self, token: str) -> None:
        session = self.runtime.api_client._session
        timeout = self.runtime.get_config().http.timeout
        async with session.ws_connect(self._gateway_url, timeout=timeout, autoping=True,
                                      max_msg_size=8 * 1024 * 1024) as ws:
            self._ws = ws
            self._sequence = None
            self._ack_pending = False
            heartbeat_task = None
            receive_task = None
            try:
                hello = await asyncio.wait_for(ws.receive(), timeout=timeout)
                if hello.type != aiohttp.WSMsgType.TEXT:
                    self._raise_close(ws, hello)
                log_raw_response(self.runtime, 'Gateway', hello.data)
                payload = self._decode(hello.data)
                if payload.get('op') != 10 or not isinstance(payload.get('d'), dict):
                    raise GatewayError('expected Hello opcode')
                interval = payload['d'].get('heartbeat_interval')
                if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
                    raise GatewayError('invalid heartbeat interval')
                interval /= 1000
                self.runtime.logger.info('QQ gateway connected (heartbeat interval=%.2f seconds)', interval)
                # IDENTIFY cannot be a tight loop even when the server closes immediately.
                delay = self._last_identify + 5 - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                if self._closing:
                    return
                self.state = GatewayState.IDENTIFYING
                intents = self._intents
                self._config_reconnect = False
                await ws.send_json({'op': 2, 'd': {'token': 'QQBot ' + token, 'intents': intents,
                                    'shard': [0, 1], 'properties': {'$os': platform.system(),
                                    '$browser': 'BotCraft', '$device': 'BotCraft'}}})
                self._last_identify = time.monotonic()
                heartbeat_task = asyncio.create_task(self._heartbeats(ws, interval), name='QQ heartbeat')
                while not self._closing:
                    receive_task = asyncio.create_task(ws.receive())
                    done, _ = await asyncio.wait((receive_task, heartbeat_task), return_when=asyncio.FIRST_COMPLETED)
                    if heartbeat_task in done:
                        await heartbeat_task
                    message = await receive_task
                    receive_task = None
                    if message.type != aiohttp.WSMsgType.TEXT:
                        self._raise_close(ws, message)
                    log_raw_response(self.runtime, 'Gateway', message.data)
                    payload = self._decode(message.data)
                    if 's' in payload:
                        self._sequence = payload['s']
                    opcode = payload.get('op')
                    if opcode == 11:
                        self._ack_pending = False
                    elif opcode == 1:
                        if not self._ack_pending:
                            await ws.send_json({'op': 1, 'd': self._sequence})
                            self._ack_pending = True
                    elif opcode == 7:
                        raise GatewayError('gateway requested reconnect', recoverable=True)
                    elif opcode == 9:
                        error = GatewayError('Identify rejected (Invalid Session)', category=ErrorCategory.INVALID_REQUEST)
                        report_error(error, self.runtime.logger, 'QQ gateway authentication failed: unrecoverable Invalid Session/op9')
                        raise error
                    elif opcode == 0:
                        if payload.get('t') == 'READY':
                            ready_data = payload.get('d')
                            user = ready_data.get('user') if isinstance(ready_data, dict) else None
                            self.runtime.bot_user_id = user.get('id') if isinstance(user, dict) else None
                            self.state = GatewayState.READY
                            self.runtime.logger.info('QQ gateway authenticated, READY (intent mask=%s)', intents)
                            if not self._first_ready.done():
                                self._first_ready.set_result(None)
                        self.runtime.event_dispatcher.submit_payload(payload)
                    else:
                        raise GatewayError('unexpected gateway opcode', category=ErrorCategory.INVALID_REQUEST)
            finally:
                self._ws = None
                if self.state == GatewayState.READY:
                    self.state = GatewayState.OFFLINE
                tasks = [task for task in (heartbeat_task, receive_task) if task is not None]
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _decode(text: str) -> dict[str, Any]:
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            raise GatewayError('invalid gateway JSON') from None
        if not isinstance(payload, dict) or isinstance(payload.get('op'), bool) or not isinstance(payload.get('op'), int):
            raise GatewayError('invalid gateway envelope')
        return payload

    def _raise_close(self: Self, ws: aiohttp.ClientWebSocketResponse, message: aiohttp.WSMessage) -> NoReturn:
        code = message.data if message.type == aiohttp.WSMsgType.CLOSE else ws.close_code
        if self._closing:
            raise GatewayError('gateway closed for shutdown', recoverable=True)
        if code in _FATAL_CLOSE:
            error = GatewayError(f'non-recoverable gateway close code {code}', close_code=code)
            if code == 4014:
                report_error(error, self.runtime.logger, 'QQ gateway authentication failed: unauthorized intents (close code=4014)')
            raise error
        raise GatewayError(f'gateway connection closed (code {code})', close_code=code, recoverable=True)

    async def _heartbeats(self: Self, ws: aiohttp.ClientWebSocketResponse, interval: float) -> None:
        while not self._closing:
            await asyncio.sleep(interval)
            if self._ack_pending:
                raise GatewayError('heartbeat ACK missed', recoverable=True)
            await ws.send_json({'op': 1, 'd': self._sequence})
            self._ack_pending = True
