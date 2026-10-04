"""QQ async executor retaining native AsyncTaskExecutor loop and task ownership."""
from __future__ import annotations
import asyncio
import threading
from concurrent.futures import Future
from mcdreforged.executor.task_executor_async import AsyncTaskExecutor as NativeAsyncTaskExecutor
from mcdreforged.executor.task_executor_common import TaskExecutorBase, TaskDoneFuture
from botcraft.utils.future_utils import observe_future, complete_future

class AsyncTaskExecutor(NativeAsyncTaskExecutor):
    def __init__(self, runtime):
        self.runtime = runtime
        TaskExecutorBase.__init__(self, runtime.logger)
        self._AsyncTaskExecutor__start_ok_event = threading.Event()
        self._AsyncTaskExecutor__stop_flag = False
        self._AsyncTaskExecutor__event_loop = None
        self._AsyncTaskExecutor__stop_event = None
        self._AsyncTaskExecutor__submitted_tasks = None
        self._task_futures = {}
        self._future_lock = threading.RLock()
        self._delivered_futures = set()
        self.set_name('AsyncTaskExecutor')

    def get_event_loop(self):
        return self._AsyncTaskExecutor__event_loop

    def get_running_plugin(self):
        loop = self._AsyncTaskExecutor__event_loop
        task = asyncio.current_task(loop) if loop is not None else None
        return getattr(task, '_mcdr_running_plugin', None) if task else None

    def submit(self, coro, *, plugin=None):
        future = TaskDoneFuture(self.get_thread())
        observe_future(future, self.logger, 'async task')
        with self._future_lock:
            self._delivered_futures.add(future)
        future.add_done_callback(self._discard_future)
        if self._AsyncTaskExecutor__stop_flag:
            if hasattr(coro, 'close'): coro.close()
            future.cancel()
            return future
        def task_done_callback(task):
            if task.cancelled(): future.cancel()
            else:
                error = task.exception()
                complete_future(future, self.logger, 'async task', error=error, result=None if error else task.result())
            self._task_futures.pop(task, None)
        def create_task():
            if self._AsyncTaskExecutor__stop_flag:
                if hasattr(coro, 'close'): coro.close()
                future.cancel(); return
            task = self._AsyncTaskExecutor__event_loop.create_task(coro)
            self._task_futures[task] = future
            task.add_done_callback(task_done_callback)
            setattr(task, '_mcdr_running_plugin', plugin)
            self._AsyncTaskExecutor__submitted_tasks.put_nowait(task)
        self.call_soon_threadsafe(create_task)
        return future

    def call_soon_threadsafe(self, func):
        self._AsyncTaskExecutor__event_loop.call_soon_threadsafe(func)

    def start(self):
        TaskExecutorBase.start(self)
        self._AsyncTaskExecutor__start_ok_event.wait()
        return self.get_thread()

    def stop(self):
        if self._AsyncTaskExecutor__stop_flag: return
        self._AsyncTaskExecutor__stop_flag = True
        loop = self._AsyncTaskExecutor__event_loop
        event = self._AsyncTaskExecutor__stop_event
        if loop is not None and event is not None: loop.call_soon_threadsafe(event.set)

    def loop(self):
        asyncio.run(self.__async_loop())

    async def __async_loop(self):
        self._AsyncTaskExecutor__event_loop = asyncio.get_event_loop()
        self._AsyncTaskExecutor__stop_event = asyncio.Event()
        self._AsyncTaskExecutor__submitted_tasks = asyncio.Queue()
        self._AsyncTaskExecutor__start_ok_event.set()
        sentinel = object()
        async def task_awaiter():
            while True:
                task = await self._AsyncTaskExecutor__submitted_tasks.get()
                if task is sentinel: break
                try: await task
                except asyncio.CancelledError: pass
                except Exception: self.logger.exception('async task await error')
        task_awaiter_task = asyncio.create_task(task_awaiter())
        await self._AsyncTaskExecutor__stop_event.wait()
        self._AsyncTaskExecutor__submitted_tasks.put_nowait(sentinel)
        await task_awaiter_task

    def _discard_future(self, future):
        with self._future_lock:
            self._delivered_futures.discard(future)

    def finish_pending(self, error=None):
        with self._future_lock:
            pending = tuple(self._delivered_futures)
        for future in pending:
            if error is None:
                future.cancel()
            else:
                complete_future(future, self.logger, 'async shutdown', error=error)
        loop = self._AsyncTaskExecutor__event_loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(lambda: [task.cancel() for task in tuple(self._task_futures)])

    def finalize_shutdown(self, error=None):
        self.finish_pending(error); self.stop()
