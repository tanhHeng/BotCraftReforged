"""Observe framework futures without changing their result or cancellation semantics."""
from concurrent.futures import Future, InvalidStateError
from threading import RLock
from weakref import WeakSet

_lock = RLock()
_observed = WeakSet()


def report_error(error, logger, operation='task'):
    """Report shared request exceptions once, but report independent requests separately."""
    with _lock:
        if getattr(error, '_botcraft_reported', False):
            return
        error._botcraft_reported = True
    logger.warning('%s: %s', operation, error)


def observe_future(future: Future, logger, operation: str = 'task') -> Future:
    with _lock:
        if future in _observed:
            return future
        _observed.add(future)

    def report(done):
        if done.cancelled():
            logger.warning('%s: cancellation', operation)
        else:
            error = done.exception()
            if error is not None:
                report_error(error, logger, operation)
    future.add_done_callback(report)
    return future


def complete_future(future: Future, logger, operation: str, *, result=None, error=None):
    """Report late errors without overwriting completed or cancelled futures."""
    try:
        if error is None:
            future.set_result(result)
        else:
            future.set_exception(error)
    except InvalidStateError:
        if error is not None:
            report_error(error, logger, operation + ': late failure')
