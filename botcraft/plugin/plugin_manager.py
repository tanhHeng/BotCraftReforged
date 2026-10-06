"""QQ adapter for MCDR's plugin manager, retaining its dependency/batch algorithms."""
from __future__ import annotations
from typing import Any, Callable, TYPE_CHECKING, TypeVar
from types import FunctionType
from typing_extensions import Self, TypedDict, Unpack
from mcdreforged.plugin.plugin_event import PluginEvent, EventListener

if TYPE_CHECKING:
    from botcraft.runtime import Runtime

_OperationValue = TypeVar("_OperationValue")


import functools
import queue
import threading
from concurrent.futures import Future
from contextvars import ContextVar
from pathlib import Path

from mcdreforged.plugin.plugin_manager import PluginManager as NativePluginManager
from mcdreforged.plugin.operation_result import PluginOperationResult
from mcdreforged.plugin.meta.dependency_walker import DependencyWalker as NativeDependencyWalker
from mcdreforged.plugin.type.common import PluginState
from mcdreforged.plugin.type.regular_plugin import RegularPlugin
from mcdreforged.plugin.exception import RequirementCheckFailure
from mcdreforged.utils.exception import SelfJoinError
from botcraft.utils.future_utils import observe_future, complete_future
from . import plugin_factory
from .plugin_event import PluginEvents, normalize_event_id
from .plugin_registry import PluginRegistryStorage
from ._native import bind_native
class _ManipulationOptions(TypedDict, total=False):
    load: list[Path] | None
    unload: list[RegularPlugin] | None
    reload: list[RegularPlugin] | None
    enable: list[Path] | None
    disable: list[RegularPlugin] | None
    try_load_indirect_unloaded: bool
    entered_callback: Callable[[], Any] | None


class DependencyWalker(NativeDependencyWalker):
    __init__ = bind_native(NativeDependencyWalker.__init__, runtime=True)


def _native_method(name: str) -> FunctionType:
    return bind_native(getattr(NativePluginManager, name), globals={
        'plugin_factory': plugin_factory,
        'MCDRPluginEvents': PluginEvents,
        'DependencyWalker': DependencyWalker,
    })


class PluginManager(NativePluginManager):
    def __init__(self: Self, runtime: Runtime) -> None:
        """Initialize native plugin collections and BotCraft operation scheduling.
        
        :param runtime: Runtime providing executors, configuration and logging.
        :return: No value is returned.
        """
        self.runtime = runtime
        self.logger = runtime.logger
        self.plugin_directories = []
        self._PluginManager__tr = runtime.create_internal_translator('plugin_manager').tr
        self._PluginManager__plugins = {}
        self._PluginManager__plugin_file_paths = {}
        self.registry_storage = PluginRegistryStorage(self)
        self._PluginManager__current_plugin = ContextVar('botcraft_current_plugin', default=None)
        self._PluginManager__mani_lock = threading.RLock()
        self._PluginManager__mani_thread = None
        self._PluginManager__mani_queue = queue.Queue()
        self._operation_futures = set()
        self._operation_lock = threading.RLock()
        runtime.add_config_changed_callback(self._PluginManager__on_mcdr_config_loaded)

    # Native collection, dependent selection, unload/reload and finalization algorithms.
    _PluginManager__collect_possible_plugin_file_paths = _native_method('_PluginManager__collect_possible_plugin_file_paths')
    _PluginManager__collect_regular_plugins_with_dependents = _native_method('_PluginManager__collect_regular_plugins_with_dependents')
    _PluginManager__unload_plugin = _native_method('_PluginManager__unload_plugin')
    _PluginManager__finalize_plugin_manipulation = _native_method('_PluginManager__finalize_plugin_manipulation')
    _native_manipulate_plugins = _native_method('manipulate_plugins')

    def manipulate_plugins(self: Self, **kwargs: Unpack[_ManipulationOptions]) -> Future[PluginOperationResult]:
        """Run a native batch of plugin state transitions.
        
        :param kwargs: Native load, unload, reload, enable and disable lists, indirect-loading flag and entry callback.
        :return: Future completed with the native batch operation result.
        """
        return observe_future(self._native_manipulate_plugins(**kwargs), self.logger, 'plugin operation')

    def _PluginManager__load_plugin(self: Self, file_path: Path) -> RegularPlugin | None:
        plugin = plugin_factory.create_regular_plugin(self, file_path)
        try:
            plugin.load()
        except Exception:
            self.logger.exception('Failed to load plugin at %s', file_path)
            try:
                if plugin.in_states({PluginState.LOADING, PluginState.LOADED, PluginState.READY}):
                    plugin.unload()
                if plugin.in_states({PluginState.UNLOADING}):
                    plugin.remove()
            except Exception:
                self.logger.exception('Failed plugin cleanup at %s', file_path)
            return None
        existing = self.get_plugin_from_id(plugin.get_id())
        if existing is not None:
            self.logger.error('Duplicate plugin id %s at %s; existing %s', plugin.get_id(), file_path, existing)
            plugin.unload()
            plugin.remove()
            return None
        self._PluginManager__add_plugin(plugin)
        self.logger.info('Loaded plugin %s', plugin)
        return plugin

    def _PluginManager__update_registry(self: Self) -> None:
        self.registry_storage.clear()
        for plugin in self.get_all_plugins():
            self.registry_storage.collect(plugin, plugin.plugin_registry)
        self.registry_storage.arrange()
        command_manager = getattr(self.runtime, 'command_manager', None)
        if command_manager is not None:
            with command_manager.start_command_register() as exporter:
                self.registry_storage.export_commands(exporter)
        self.runtime.on_registry_changed()

    def register_builtin_plugins(self: Self) -> None:
        """Load and register the BotCraft and Python built-in plugins.
        
        :return: No value is returned.
        """
        from .type.builtin_plugin import CorePlugin, PythonPlugin
        for plugin in (CorePlugin(self), PythonPlugin(self)):
            self._PluginManager__add_plugin(plugin)
            plugin.set_state(PluginState.LOADED)
            with self.with_plugin_context(plugin):
                plugin.load()
            plugin.set_state(PluginState.READY)
        self._PluginManager__sort_plugins_by_id()
        self._PluginManager__update_registry()

    def load_all_plugins(self: Self) -> Future[PluginOperationResult]:
        """Refresh all enabled plugins using native dependency ordering.
        
        :return: Future completed with the refresh operation result.
        """
        return self.refresh_all_plugins()

    def _track_operation(self: Self, future: Future[_OperationValue]) -> Future[_OperationValue]:
        with self._operation_lock:
            self._operation_futures.add(future)
        def discard(done: Future[_OperationValue]) -> None:
            """Remove a completed operation from shutdown tracking.
            
            :param done: Future whose operation has completed.
            :return: No value is returned.
            """
            with self._operation_lock:
                self._operation_futures.discard(done)
        future.add_done_callback(discard)
        return observe_future(future, self.logger, 'plugin operation')

    def _PluginManager__run_manipulation(self: Self, action: Callable[[], PluginOperationResult], *, wait_if_async: bool = True) -> Future[PluginOperationResult]:
        if self.runtime.async_task_executor.is_on_thread():
            raise RuntimeError('Plugin manipulation is not allowed on the async executor')
        executor = self.runtime.sync_task_executor
        if not executor.is_on_thread():
            result_future = self._track_operation(Future())
            def func() -> None:
                """Schedule a plugin operation on the synchronous executor.
                
                :return: No value is returned.
                """
                inner = self._PluginManager__run_manipulation(action)
                def done(future: Future[PluginOperationResult]) -> None:
                    """Complete the caller-facing future from a plugin operation.
                    
                    :param future: Completed inner plugin operation.
                    :return: No value is returned.
                    """
                    if future.cancelled():
                        result_future.cancel()
                    else:
                        error = future.exception()
                        complete_future(result_future, self.logger, 'plugin operation', error=error, result=None if error else future.result())
                inner.add_done_callback(done)
            scheduled = executor.submit(func)
            def submission_done(future: Future[None]) -> None:
                """Propagate scheduling cancellation and errors to the operation.
                
                :param future: Completed synchronous executor submission.
                :return: No value is returned.
                """
                if future.cancelled():
                    result_future.cancel()
                elif future.exception() is not None:
                    complete_future(result_future, self.logger, 'plugin operation', error=future.exception())
            scheduled.add_done_callback(submission_done)
            if wait_if_async:
                scheduled.result()
            return result_future
        with self._PluginManager__mani_lock:
            future = self._track_operation(Future())
            self._PluginManager__mani_queue.put((action, future))
            if self._PluginManager__mani_thread is not threading.current_thread():
                self._PluginManager__mani_thread = threading.current_thread()
                try:
                    while True:
                        try:
                            queued_action, queued_future = self._PluginManager__mani_queue.get_nowait()
                        except queue.Empty:
                            break
                        try:
                            result = queued_action()
                        except BaseException as error:
                            complete_future(queued_future, self.logger, 'plugin operation', error=error)
                        else:
                            complete_future(queued_future, self.logger, 'plugin operation', result=result)
                finally:
                    self._PluginManager__mani_thread = None
            return future

    def finish_pending(self: Self, error: BaseException | None = None) -> None:
        """Cancel or fail outstanding plugin operations during shutdown.
        
        :param error: Failure to assign to pending operations, or None to cancel them.
        :return: No value is returned.
        """
        with self._operation_lock:
            pending = tuple(self._operation_futures)
        for future in pending:
            if not future.done():
                if error is None:
                    future.cancel()
                else:
                    complete_future(future, self.logger, 'plugin shutdown', error=error)

    def dispatch_event(self: Self, event: PluginEvent | str, args: tuple[Any, ...], *, dispatch_policy: NativePluginManager.DispatchEventPolicy = NativePluginManager.DispatchEventPolicy.always_new_task, block: bool = False, exclude_legacy: bool = False) -> None:
        """Dispatch plugin listeners with native ordering and executor policy.
        
        :param event: Event object or canonicalizable identifier.
        :param args: Open positional arguments supplied to plugin callbacks.
        :param dispatch_policy: Native executor scheduling policy.
        :param block: Wait for all dispatched listeners to finish.
        :param exclude_legacy: Skip listeners already delivered through a legacy callback path.
        :return: No value is returned.
        """
        executor = self.runtime.sync_task_executor
        on_thread = executor.is_on_thread()
        submit = dispatch_policy == self.DispatchEventPolicy.always_new_task or dispatch_policy == self.DispatchEventPolicy.ensure_on_thread and not on_thread
        if block and submit and on_thread:
            raise SelfJoinError()
        direct, queued = [], []
        event_id = normalize_event_id(event)
        for listener in tuple(self.registry_storage.get_event_listeners(event_id)):
            if exclude_legacy and self.registry_storage.is_legacy_listener(listener, event_id):
                continue
            func = functools.partial(self.trigger_listener, listener, args)
            if submit:
                queued.append(executor.submit(func, plugin=listener.plugin))
            else:
                direct.append(func())
        if block:
            direct.extend(future.result() for future in queued)
            for future in direct:
                future.result()

    def trigger_listener(self: Self, listener: EventListener, args: tuple[Any, ...]) -> Future[None]:
        """Invoke a ready plugin listener in its owning plugin context.
        
        :param listener: Native listener containing its plugin and callback.
        :param args: Open positional arguments supplied to the plugin callback.
        :return: Future completed after invocation, skipped invocation, or callback failure.
        """
        if not listener.plugin.in_states({PluginState.READY}):
            future = Future()
            future.set_result(None)
            return observe_future(future, self.logger, 'plugin listener skipped')
        if listener.is_async():
            return self.runtime.async_task_executor.submit(self._trigger_listener_async(listener, args), plugin=listener.plugin)
        future = Future()
        observe_future(future, self.logger, 'plugin listener')
        try:
            with self.with_plugin_context(listener.plugin):
                listener.callback(listener.plugin.server_interface, *args)
        except BaseException as error:
            complete_future(future, self.logger, 'plugin listener', error=error)
        else:
            complete_future(future, self.logger, 'plugin listener', result=None)
        return future

    async def _trigger_listener_async(self: Self, listener: EventListener, args: tuple[Any, ...]) -> None:
        if not listener.plugin.in_states({PluginState.READY}):
            return
        with self.with_plugin_context(listener.plugin):
            await listener.callback(listener.plugin.server_interface, *args)
