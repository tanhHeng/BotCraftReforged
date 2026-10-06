"""QQ synchronous executor: native queue, sentinel, futures and thread loop."""
from __future__ import annotations
from typing import TYPE_CHECKING, Callable, TypeVar
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
    from mcdreforged.plugin.type.plugin import AbstractPlugin

T = TypeVar('T')
import threading
from concurrent.futures import Future
from mcdreforged.executor.task_executor_sync import SyncTaskExecutor
from mcdreforged.executor.task_executor_common import TaskExecutorBase, TaskDoneFuture
from mcdreforged.executor.task_executor_queue import TaskQueue, TaskQueueItem, TaskPriority
from botcraft.utils.future_utils import observe_future, complete_future


class TaskExecutor(SyncTaskExecutor):
    def __init__(self: Self, runtime: Runtime) -> None:
        """Initialize the native synchronous queue without binding an MCDR host.
        
        :param runtime: Runtime providing the standalone logger.
        :return: No return value.
        """
        # TaskExecutorBase is the native common initializer; SyncTaskExecutor's
        # initializer is intentionally skipped because it binds a real MCDR host.
        self.runtime = runtime
        TaskExecutorBase.__init__(self, runtime.logger)
        self._SyncTaskExecutor__task_queue = TaskQueue()
        self._SyncTaskExecutor__running_plugin = None
        self._SyncTaskExecutor__active_futures = set()
        self._pending_lock = threading.RLock()
        self._SyncTaskExecutor__soft_stop_sentinel = TaskQueueItem(lambda: None, TaskPriority.SENTINEL, None, Future())
        self.set_name('TaskExecutor')

    def submit(self: Self, func: Callable[[], T], *, priority: TaskPriority = TaskPriority.REGULAR, raise_if_full: bool = False, plugin: AbstractPlugin | None = None) -> Future[T]:
        """Queue a callable and return its thread-aware completion future.
        
        :param func: Callable to execute on the synchronous executor thread.
        :param priority: Native queue priority for the submitted task.
        :param raise_if_full: Whether queue saturation should raise instead of blocking.
        :param plugin: Optional plugin owning the submitted task.
        :return: Thread-aware future carrying the callable result.
        """
        future = TaskDoneFuture(self.get_thread())
        observe_future(future, self.logger, 'sync task')
        if not self.should_keep_looping():
            future.cancel()
            return future
        item = TaskQueueItem(func, priority, plugin, future)
        self._SyncTaskExecutor__task_queue.put(item, block=not raise_if_full)
        return future

    def should_keep_looping(self: Self) -> bool:
        """Report whether the native executor loop should continue.
        
        :return: Result of the operation.
        """
        # Runtime stop requests are coordinated by Runtime's bounded join; soft_stop
        # inserts the native sentinel and therefore does not abandon queued work.
        return super(TaskExecutorBase, self).should_keep_looping()

    def get_running_plugin(self: Self) -> AbstractPlugin | None:
        """Return the plugin owning the currently executing synchronous task.
        
        :return: Result of the operation.
        """
        return self._SyncTaskExecutor__running_plugin

    def soft_stop(self: Self) -> None:
        """Queue the native sentinel so already queued tasks can finish.
        
        :return: No return value.
        """
        self._SyncTaskExecutor__task_queue.put(self._SyncTaskExecutor__soft_stop_sentinel)

    def tick(self: Self) -> None:
        """Execute the next queued task and preserve its completion or cancellation result.
        
        :return: No return value.
        """
        task = self._SyncTaskExecutor__task_queue.get()
        if task is self._SyncTaskExecutor__soft_stop_sentinel:
            TaskExecutorBase.stop(self)
            return
        self._SyncTaskExecutor__running_plugin = task.plugin
        with self._pending_lock:
            self._SyncTaskExecutor__active_futures.add(task.future)
        try:
            if task.future.cancelled():
                return
            result = task.func()
        except BaseException as error:
            complete_future(task.future, self.logger, 'sync task', error=error)
        else:
            complete_future(task.future, self.logger, 'sync task', result=result)
        finally:
            self._SyncTaskExecutor__running_plugin = None
            with self._pending_lock:
                self._SyncTaskExecutor__active_futures.discard(task.future)

    def finish_pending(self: Self, error: BaseException | None = None) -> None:
        """Cancel queued work and cancel or fail outstanding active futures.
        
        :param error: Shutdown failure for active futures, or None to cancel them.
        :return: No return value.
        """
        for task in self._SyncTaskExecutor__task_queue.drain_all_tasks():
            task.future.cancel()
        with self._pending_lock:
            active = tuple(self._SyncTaskExecutor__active_futures)
        for future in active:
            if error is None:
                future.cancel()
            else:
                complete_future(future, self.logger, 'sync shutdown', error=error)

    def finalize_shutdown(self: Self, error: BaseException | None = None) -> None:
        """Finish pending futures and request sentinel-based shutdown.
        
        :param error: Shutdown failure for active futures, or None to cancel them.
        :return: No return value.
        """
        self.finish_pending(error)
        self.soft_stop()
