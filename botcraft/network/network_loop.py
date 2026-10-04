"""Dedicated protocol loop, deliberately separate from plugin executors."""
import asyncio
from concurrent.futures import Future
from threading import Event, RLock, Thread, current_thread

from botcraft.utils.future_utils import complete_future, observe_future
from .exception import NetworkError, ResultUnknownError


class NetworkLoop:
    def __init__(self, runtime):
        self.runtime = runtime
        self.logger = runtime.logger
        self._loop = None
        self._thread = None
        self._ready = Event()
        self._lock = RLock()
        self._accepting = False
        self._stopped = False
        self._pending = {}

    def start(self):
        with self._lock:
            if self._thread is not None or self._stopped:
                raise RuntimeError('NetworkLoop may be started only once')
            self._thread = Thread(target=self._run, name='Network', daemon=True)
            self._thread.start()
        self._ready.wait()
        if not self._accepting:
            raise RuntimeError('Network loop failed to start')

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
            self._accepting = True
            self._ready.set()
        try:
            loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            with self._lock:
                self._stopped = True
                self._accepting = False
                pending = tuple(self._pending.items())
                self._pending.clear()
            for future, (operation, _) in pending:
                if not future.done():
                    complete_future(future, self.logger, operation,
                                    error=ResultUnknownError('network loop stopped before operation completed'))

    def submit(self, coroutine, operation='network operation'):
        if not asyncio.iscoroutine(coroutine):
            raise TypeError('NetworkLoop.submit requires a coroutine')
        future = Future()
        observe_future(future, self.logger, operation)
        future.add_done_callback(self._cancel_submission)
        with self._lock:
            if not self._accepting:
                coroutine.close()
                raise RuntimeError('Network loop is not accepting operations')
            self._pending[future] = (operation, None)
            self._loop.call_soon_threadsafe(self._begin, future, coroutine, operation)
        return future

    def _cancel_submission(self, future):
        if not future.cancelled():
            return
        with self._lock:
            pending = self._pending.get(future)
            if pending is None or pending[1] is None or self._stopped:
                return
            self._loop.call_soon_threadsafe(pending[1].cancel)

    def _begin(self, future, coroutine, operation):
        if future.cancelled():
            coroutine.close()
            with self._lock:
                self._pending.pop(future, None)
            return
        started = False

        async def execute():
            nonlocal started
            started = True
            try:
                result = await coroutine
            except asyncio.CancelledError:
                future.cancel()
            except BaseException as error:
                complete_future(future, self.logger, operation, error=error)
            else:
                complete_future(future, self.logger, operation, result=result)
            finally:
                with self._lock:
                    self._pending.pop(future, None)

        task = self._loop.create_task(execute(), name=operation)
        with self._lock:
            if future in self._pending:
                self._pending[future] = (operation, task)
            cancelled = future.cancelled()

        def release_unstarted(done):
            if not started:
                coroutine.close()
                with self._lock:
                    self._pending.pop(future, None)
                future.cancel()

        task.add_done_callback(release_unstarted)
        if cancelled:
            task.cancel()

    def stop(self, timeout=10):
        if self._thread is current_thread():
            raise RuntimeError('NetworkLoop.stop cannot join its own thread')
        with self._lock:
            if self._stopped or self._thread is None:
                self._stopped = True
                return
            self._accepting = False
            loop = self._loop

        async def shutdown():
            current = asyncio.current_task()
            tasks = [task for task in asyncio.all_tasks() if task is not current]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            loop.call_soon(loop.stop)

        observe_future(asyncio.run_coroutine_threadsafe(shutdown(), loop), self.logger, 'network shutdown')
        self._thread.join(timeout)
        if self._thread.is_alive():
            with self._lock:
                pending = tuple(self._pending.items())
            for future, (operation, _) in pending:
                if not future.done():
                    complete_future(future, self.logger, operation,
                                    error=ResultUnknownError('network shutdown deadline exceeded'))
            self.logger.warning('Network thread did not stop before its deadline')

    def is_on_thread(self):
        return current_thread() is self._thread
