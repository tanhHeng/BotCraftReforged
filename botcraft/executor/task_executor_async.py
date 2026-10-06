"""QQ async executor retaining native AsyncTaskExecutor loop and task ownership."""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, Coroutine, TypeVar
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
    from mcdreforged.plugin.type.plugin import AbstractPlugin

T = TypeVar('T')
import asyncio
import threading
from concurrent.futures import Future
from mcdreforged.executor.task_executor_async import AsyncTaskExecutor as NativeAsyncTaskExecutor
from mcdreforged.executor.task_executor_common import TaskExecutorBase, TaskDoneFuture
from botcraft.utils.future_utils import observe_future, complete_future

class AsyncTaskExecutor(NativeAsyncTaskExecutor):
    def __init__(self: Self, runtime: Runtime) -> None:
        """Initialize the standalone native asynchronous executor state.
        
        :param runtime: Runtime providing the standalone logger.
        :return: No return value.
        """
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

    def get_event_loop(self: Self) -> asyncio.AbstractEventLoop | None:
        """Return the executor loop, or None before initialization.
        
        :return: Result of the operation.
        """
        return self._AsyncTaskExecutor__event_loop

    def get_running_plugin(self: Self) -> AbstractPlugin | None:
        """Return the plugin owning the current asynchronous task.
        
        :return: Result of the operation.
        """
        loop = self._AsyncTaskExecutor__event_loop
        task = asyncio.current_task(loop) if loop is not None else None
        return getattr(task, '_mcdr_running_plugin', None) if task else None

    def submit(self: Self, coro: Coroutine[Any, Any, T], *, plugin: AbstractPlugin | None = None) -> Future[T]:
        """Submit a plugin coroutine and expose its completion through a native future.
        
        :param coro: Coroutine whose result is delivered through the completion future.
        :param plugin: Optional plugin owning the submitted coroutine.
        :return: Thread-aware future carrying the coroutine result.
        """
        future = TaskDoneFuture(self.get_thread())
        observe_future(future, self.logger, 'async task')
        with self._future_lock:
            self._delivered_futures.add(future)
        future.add_done_callback(self._discard_future)
        if self._AsyncTaskExecutor__stop_flag:
            if hasattr(coro, 'close'): coro.close()
            future.cancel()
            return future
        def task_done_callback(task: asyncio.Task[T]) -> None:
            if task.cancelled(): future.cancel()
            else:
                error = task.exception()
                complete_future(future, self.logger, 'async task', error=error, result=None if error else task.result())
            self._task_futures.pop(task, None)
        def create_task() -> None:
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

    def call_soon_threadsafe(self: Self, func: Callable[[], object]) -> None:
        """Schedule a callback on the asynchronous executor loop.
        
        :param func: Callback invoked without arguments on the executor loop.
        :return: No return value.
        """
        self._AsyncTaskExecutor__event_loop.call_soon_threadsafe(func)

    def start(self: Self) -> threading.Thread:
        """Start the executor thread and wait until its event loop is initialized.
        
        :return: Started executor thread.
        """
        TaskExecutorBase.start(self)
        self._AsyncTaskExecutor__start_ok_event.wait()
        return self.get_thread()

    def stop(self: Self) -> None:
        """Request asynchronous shutdown without waiting for the executor thread.
        
        :return: No return value.
        """
        if self._AsyncTaskExecutor__stop_flag: return
        self._AsyncTaskExecutor__stop_flag = True
        loop = self._AsyncTaskExecutor__event_loop
        event = self._AsyncTaskExecutor__stop_event
        if loop is not None and event is not None: loop.call_soon_threadsafe(event.set)

    def loop(self: Self) -> None:
        """Run the executor-owned asynchronous loop.
        
        :return: No return value.
        """
        asyncio.run(self.__async_loop())

    async def __async_loop(self: Self) -> None:
        self._AsyncTaskExecutor__event_loop = asyncio.get_event_loop()
        self._AsyncTaskExecutor__stop_event = asyncio.Event()
        self._AsyncTaskExecutor__submitted_tasks = asyncio.Queue()
        self._AsyncTaskExecutor__start_ok_event.set()
        sentinel = object()
        async def task_awaiter() -> None:
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

    def _discard_future(self: Self, future: Future[Any]) -> None:
        with self._future_lock:
            self._delivered_futures.discard(future)

    def finish_pending(self: Self, error: BaseException | None = None) -> None:
        """Cancel or fail delivered futures and request cancellation of submitted tasks.
        
        :param error: Shutdown failure for pending futures, or None to cancel them.
        :return: No return value.
        """
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

    def finalize_shutdown(self: Self, error: BaseException | None = None) -> None:
        """Finish pending futures and request asynchronous shutdown.
        
        :param error: Shutdown failure for pending futures, or None to cancel them.
        :return: No return value.
        """
        self.finish_pending(error); self.stop()
