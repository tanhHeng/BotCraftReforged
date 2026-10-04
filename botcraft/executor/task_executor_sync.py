"""QQ synchronous executor: native queue, sentinel, futures and thread loop."""
from __future__ import annotations
import threading
from concurrent.futures import Future
from mcdreforged.executor.task_executor_sync import SyncTaskExecutor
from mcdreforged.executor.task_executor_common import TaskExecutorBase, TaskDoneFuture
from mcdreforged.executor.task_executor_queue import TaskQueue, TaskQueueItem, TaskPriority
from botcraft.utils.future_utils import observe_future, complete_future


class TaskExecutor(SyncTaskExecutor):
    def __init__(self, runtime):
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

    def submit(self, func, *, priority=TaskPriority.REGULAR, raise_if_full=False, plugin=None):
        future = TaskDoneFuture(self.get_thread())
        observe_future(future, self.logger, 'sync task')
        if not self.should_keep_looping():
            future.cancel()
            return future
        item = TaskQueueItem(func, priority, plugin, future)
        self._SyncTaskExecutor__task_queue.put(item, block=not raise_if_full)
        return future

    def should_keep_looping(self):
        # Runtime stop requests are coordinated by Runtime's bounded join; soft_stop
        # inserts the native sentinel and therefore does not abandon queued work.
        return super(TaskExecutorBase, self).should_keep_looping()

    def get_running_plugin(self):
        return self._SyncTaskExecutor__running_plugin

    def soft_stop(self):
        self._SyncTaskExecutor__task_queue.put(self._SyncTaskExecutor__soft_stop_sentinel)

    def tick(self):
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

    def finish_pending(self, error=None):
        for task in self._SyncTaskExecutor__task_queue.drain_all_tasks():
            task.future.cancel()
        with self._pending_lock:
            active = tuple(self._SyncTaskExecutor__active_futures)
        for future in active:
            if error is None:
                future.cancel()
            else:
                complete_future(future, self.logger, 'sync shutdown', error=error)

    def finalize_shutdown(self, error=None):
        self.finish_pending(error)
        self.soft_stop()
