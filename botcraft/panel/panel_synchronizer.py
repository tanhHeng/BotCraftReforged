"""Help-driven global group/c2c panels with coalesced, evidence-aware reconciliation."""
import asyncio
from collections.abc import Sequence
from concurrent.futures import Future
from dataclasses import dataclass, replace
from enum import Enum
import json
import os
from pathlib import Path
from threading import RLock
import time
from typing import TYPE_CHECKING, TypeAlias
from typing_extensions import Self

from mcdreforged.utils.translation_utils import translate_from_dict
from botcraft.network.exception import NetworkError, ResultUnknownError
from botcraft.utils.future_utils import report_error
from botcraft.message.user import Scene
from botcraft.translation.translation_text import QQTranslationText

if TYPE_CHECKING:
    from botcraft.runtime import Runtime

PanelItem: TypeAlias = tuple[str, str, bool]


class PanelState(str, Enum):
    PENDING = 'pending'
    SYNCING = 'syncing'
    ACTIVE = 'active'
    DEFERRED = 'deferred'
    FAILED = 'failed'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class PanelStatus:
    scope: str
    state: PanelState = PanelState.PENDING
    panel_id: str | None = None
    desired_version: int = 0
    confirmed_version: int = 0
    undisplayed_prefixes: tuple[str, ...] = ()
    err_code: int | None = None
    code: int | None = None
    http_code: int | None = None
    trace_id: str | None = None
    reason: str | None = None
    next_sync_at: float | None = None


class PanelSynchronizer:
    SCOPES = ('group', 'c2c')

    def __init__(self: Self, runtime: 'Runtime', path: str | Path = 'config/botcraft/panels.json') -> None:
        """Initialize help-driven global group and C2C panel reconciliation.
        
        :param runtime: Runtime providing help metadata, language and the panel API client.
        :param path: File storing reconciliation records.
        :return: Initialize panel state without performing remote operations.
        """
        self.runtime = runtime
        self.path = Path(path)
        self._lock = RLock()
        self._capture_lock = RLock()
        self._status = {scope: PanelStatus(scope) for scope in self.SCOPES}
        self._desired = {scope: () for scope in self.SCOPES}
        self._confirmed = {scope: None for scope in self.SCOPES}
        self._invalid = {}
        self._retry_at = {}
        self._worker = None
        self._closed = False
        self._rebuild_started = False
        self._initialized = False
        self._delay_notice = None

    def get_status(self: Self, scope: str | Scene) -> PanelStatus:
        """Read an immutable snapshot of one conversation panel's status.
        
        :param scope: Group or C2C conversation scope.
        :return: Current desired and confirmed versions, state and error details.
        """
        scope = getattr(scope, 'value', scope)
        with self._lock:
            if scope not in self._status:
                raise ValueError('Only group and c2c panels are managed')
            return self._status[scope]

    @staticmethod
    def _field(text: str, name: str, maximum: int) -> str:
        if not isinstance(text, str) or not text or len(text) > maximum:
            raise ValueError(f'panel {name} must contain 1..{maximum} characters')
        if any(ord(char) < 32 or ord(char) == 127 for char in text):
            raise ValueError(f'panel {name} contains control characters')
        return text

    def _capture(self: Self) -> None:
        with self._capture_lock:
            self._capture_locked()

    def _capture_locked(self):
        records = tuple(self.runtime.plugin_manager.registry_storage.panel_help_messages)
        language = self.runtime.get_language()
        for scope in self.SCOPES:
            items = {}
            error = None
            try:
                for record in records:
                    if scope not in record.scope:
                        continue
                    name = self._field(record.prefix, 'name', 14)
                    desc = translate_from_dict(record.message, language) if isinstance(record.message, dict) else record.message
                    desc = self._field(desc, 'description', 30)
                    if not isinstance(record.only_admin, bool):
                        raise ValueError('panel only_admin must be bool')
                    item = (name, desc, record.only_admin)
                    if name in items and items[name] != item:
                        raise ValueError(f'conflicting help metadata for {name!r} in {scope}')
                    items.setdefault(name, item)
            except (ValueError, TypeError, KeyError) as caught:
                error = caught
            all_items = tuple(items.values())
            desired = all_items[:20]
            discarded = tuple(item[0] for item in all_items[20:])
            with self._lock:
                old = self._status[scope]
                changed = (desired != self._desired[scope] or discarded != old.undisplayed_prefixes or
                           str(error) != str(self._invalid.get(scope)))
                if changed:
                    self._desired[scope] = desired
                    self._status[scope] = replace(old, desired_version=old.desired_version + 1,
                                                  undisplayed_prefixes=discarded)
                    if discarded:
                        self.runtime.logger.warning('Panel %s omits prefixes beyond 20: %s', scope, ', '.join(discarded))
                if error is None:
                    self._invalid.pop(scope, None)
                else:
                    self._invalid[scope] = error
                    if changed:
                        report_error(error, self.runtime.logger, f'panel {scope} metadata')
                    if old.state != PanelState.UNKNOWN:
                        self._status[scope] = replace(self._status[scope], state=PanelState.FAILED,
                                                      reason=str(error), next_sync_at=None)
                if changed and error is None and old.state != PanelState.UNKNOWN:
                    self._status[scope] = replace(self._status[scope], state=PanelState.PENDING,
                                                  reason=None, err_code=None, code=None, http_code=None,
                                                  trace_id=None, next_sync_at=None)
                    self._retry_at.pop(scope, None)

    @staticmethod
    def _payload(items: Sequence[PanelItem]) -> list[dict[str, str | bool]]:
        return [{'type': 'command', 'name': name, 'desc': desc, 'only_admin': admin}
                for name, desc, admin in items]

    def _failure(self: Self, scope: str, error: Exception) -> None:
        with self._lock:
            status = self._status[scope]
            unknown = isinstance(error, ResultUnknownError)
            self._status[scope] = replace(status, state=PanelState.UNKNOWN if unknown else PanelState.FAILED,
                                          err_code=getattr(error, 'err_code', None), code=getattr(error, 'code', None),
                                          http_code=getattr(error, 'http_code', None), trace_id=getattr(error, 'trace_id', None),
                                          reason=str(error), next_sync_at=None)
        self._persist()

    def _persist(self: Self) -> None:
        with self._lock:
            data = {'appid': self.runtime.get_config().appid, 'scopes': {
                scope: {'panel_id': status.panel_id, 'state': status.state.value,
                        'desired_version': status.desired_version, 'confirmed_version': status.confirmed_version,
                        'trace_id': status.trace_id, 'err_code': status.err_code}
                for scope, status in self._status.items()}}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + '.tmp')
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
            os.replace(temporary, self.path)
        except OSError as error:
            self.runtime.logger.warning('Cannot persist panel reconciliation records: %s', type(error).__name__)

    async def rebuild(self: Self) -> None:
        """Rebuild both global panels from current registered help metadata.
        
        :return: Replace remote startup panels and record confirmed versions; failures propagate.
        """
        if self._rebuild_started or self._closed:
            raise RuntimeError('Panel startup rebuild may run only once')
        self._rebuild_started = True
        self._capture()
        if self._invalid:
            scope, error = next(iter(self._invalid.items()))
            raise ValueError(f'{scope} panel metadata invalid: {error}')
        api = self.runtime.api_client
        # Complete both listings before mutating their pagination ordering.
        remote = {}
        for scope in self.SCOPES:
            try:
                remote[scope] = await api.list_panels(scope)
            except Exception as error:
                self._failure(scope, error)
                raise
        for scope in self.SCOPES:
            with self._lock:
                self._status[scope] = replace(self._status[scope], state=PanelState.SYNCING)
            try:
                for record in remote[scope]:
                    await api.delete_panel(record['panel_id'])
            except Exception as error:
                self._failure(scope, error)
                raise
        for scope in self.SCOPES:
            with self._lock:
                desired = self._desired[scope]
                version = self._status[scope].desired_version
            try:
                result = await api.create_panel(scope, self._payload(desired))
            except Exception as error:
                self._failure(scope, error)
                raise
            with self._lock:
                self._confirmed[scope] = desired
                status = self._status[scope]
                self._status[scope] = replace(status, panel_id=result['panel_id'], confirmed_version=version,
                                              state=PanelState.ACTIVE if version == status.desired_version else PanelState.PENDING)
            self._persist()
        self._initialized = True

    def schedule_sync(self: Self) -> None:
        """Capture current help and schedule coalesced panel synchronization.
        
        :return: Start reconciliation after initialization unless the synchronizer is closed.
        """
        if self._closed:
            return
        self._capture()
        with self._lock:
            if not self._initialized:
                return
            for scope, status in self._status.items():
                if status.state == PanelState.FAILED and scope not in self._invalid:
                    self._status[scope] = replace(status, state=PanelState.PENDING)
            self._ensure_worker()

    def _ensure_worker(self: Self) -> None:
        if self._closed or (self._worker is not None and not self._worker.done()):
            return
        self._worker = self.runtime.network_loop.submit(self._sync(), operation='panel synchronization')
        self._worker.add_done_callback(self._worker_done)

    def _worker_done(self: Self, future: Future[None]) -> None:
        with self._lock:
            if self._worker is not future:
                return
            self._worker = None
            pending = any(scope not in self._invalid and status.state not in (PanelState.UNKNOWN, PanelState.FAILED)
                          and status.desired_version != status.confirmed_version
                          for scope, status in self._status.items())
            if pending and not self._closed:
                self._ensure_worker()

    async def _sync(self: Self) -> None:
        api = self.runtime.api_client
        while not self._closed:
            with self._lock:
                pending = [scope for scope in self.SCOPES if scope not in self._invalid and
                           self._status[scope].state not in (PanelState.UNKNOWN, PanelState.FAILED) and
                           (self._status[scope].desired_version != self._status[scope].confirmed_version)]
            if not pending:
                return
            now = time.monotonic()
            wait = max(api.panel_write_delay(), min(max(0, self._retry_at.get(scope, 0) - now) for scope in pending))
            if wait > 0:
                next_at = time.time() + wait
                with self._lock:
                    for scope in pending:
                        self._status[scope] = replace(self._status[scope], state=PanelState.DEFERRED, next_sync_at=next_at)
                notice = (tuple(pending), 'write quota/retry')
                if notice != self._delay_notice:
                    self.runtime.logger.warning('Panel synchronization deferred: scopes=%s reason=write quota/retry next_sync_at=%s', ','.join(pending), next_at)
                    self._delay_notice = notice
                await asyncio.sleep(min(wait, 1))
                continue
            self._delay_notice = None
            scope = next(scope for scope in pending if self._retry_at.get(scope, 0) <= now)
            with self._lock:
                status = self._status[scope]
                desired = self._desired[scope]
                version = status.desired_version
                if desired == self._confirmed[scope]:
                    self._status[scope] = replace(status, state=PanelState.ACTIVE, confirmed_version=version,
                                                  next_sync_at=None, reason=None)
                    continue
                self._status[scope] = replace(status, state=PanelState.SYNCING, next_sync_at=None)
            try:
                await api.modify_panel(status.panel_id, self._payload(desired))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._failure(scope, error)
                report_error(error, self.runtime.logger, f'panel {scope} synchronization')
                if isinstance(error, NetworkError) and error.retryable:
                    delay = max(6, error.retry_after or 0)
                    self._retry_at[scope] = time.monotonic() + delay
                    with self._lock:
                        self._status[scope] = replace(self._status[scope], state=PanelState.DEFERRED,
                                                      next_sync_at=time.time() + delay)
                continue
            with self._lock:
                self._confirmed[scope] = desired
                current = self._status[scope]
                if current.state != PanelState.UNKNOWN:
                    state = PanelState.FAILED if scope in self._invalid else (
                        PanelState.ACTIVE if version == current.desired_version else PanelState.PENDING)
                    self._status[scope] = replace(current, confirmed_version=version, state=state,
                                                  reason=str(self._invalid[scope]) if scope in self._invalid else None,
                                                  err_code=None, code=None, http_code=None,
                                                  trace_id=None, next_sync_at=None)
            self._persist()

    async def close(self: Self) -> None:
        """Persist panel state and wait briefly for in-flight synchronization.
        
        :return: Stop scheduling work without blindly deleting remote panels.
        """
        self._closed = True
        self._persist()
        # No blind remote cleanup on process exit. In-flight HTTP keeps its real outcome.
        if self._worker is not None and not self._worker.done():
            try:
                await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(self._worker)), timeout=10)
            except (asyncio.TimeoutError, NetworkError):
                pass
