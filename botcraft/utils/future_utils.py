"""Observe framework futures without changing their result or cancellation semantics."""
from __future__ import annotations
import logging
from typing import TypeVar

T = TypeVar('T')
from concurrent.futures import Future, InvalidStateError
from threading import RLock
from weakref import WeakSet

_lock = RLock()
_observed = WeakSet()


def report_error(error: BaseException, logger: logging.Logger, operation: str = 'task') -> None:
    """Report a shared exception once while keeping independent request failures distinct.
    
    :param error: Failure to report or deliver to the future.
    :param logger: Logger receiving failure diagnostics.
    :param operation: Human-readable operation label.
    :return: No return value.
    """
    with _lock:
        if getattr(error, '_botcraft_reported', False):
            return
        error._botcraft_reported = True
    logger.warning('%s: %s', operation, error)


def observe_future(future: Future[T], logger: logging.Logger, operation: str = 'task') -> Future[T]:
    """Observe completion errors without changing future results or cancellation.
    
    :param future: Future whose result and cancellation state are preserved.
    :param logger: Logger receiving failure diagnostics.
    :param operation: Human-readable operation label.
    :return: The same future, with completion diagnostics attached.
    """
    with _lock:
        if future in _observed:
            return future
        _observed.add(future)

    def report(done: Future[T]) -> None:
        if done.cancelled():
            logger.warning('%s: cancellation', operation)
        else:
            error = done.exception()
            if error is not None:
                report_error(error, logger, operation)
    future.add_done_callback(report)
    return future


def complete_future(future: Future[T], logger: logging.Logger, operation: str, *, result: T | None = None, error: BaseException | None = None) -> None:
    """Complete a future, reporting late errors without overwriting finished futures.
    
    :param future: Future whose result and cancellation state are preserved.
    :param logger: Logger receiving failure diagnostics.
    :param operation: Human-readable operation label.
    :param result: Successful result to deliver when no error is supplied.
    :param error: Failure to report or deliver to the future.
    :return: No return value.
    """
    try:
        if error is None:
            future.set_result(result)
        else:
            future.set_exception(error)
    except InvalidStateError:
        if error is not None:
            report_error(error, logger, operation + ': late failure')
