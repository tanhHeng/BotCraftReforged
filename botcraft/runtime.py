"""Standalone QQ runtime using reusable MCDR code without an MCDR host."""
from __future__ import annotations
from concurrent.futures import Future
from typing import TYPE_CHECKING, Callable, Protocol
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.config import Config
    from botcraft.logging.logger import Logger
    from botcraft.message.qtext.text import QText, QMarkdown
    from botcraft.plugin.si.server_interface import QQServerInterface
    from botcraft.translation.translation_manager import TranslationParameter, TranslationOption


import asyncio
import logging
import threading
import time
from functools import partial
from botcraft.runtime_args import RuntimeArgs
from botcraft.state import RuntimeState
from botcraft.logging.logger import create_logger
from botcraft.utils.future_utils import observe_future, report_error


class _InternalTranslator(Protocol):
    def tr(self: Self, key: str, *args: object, **kwargs: object) -> str | QText | QMarkdown:
        """Translate a native manager key using adapted scalar values.
        
        :param key: Translation key beneath the native manager namespace.
        :param args: Positional values adapted to scalar text when necessary.
        :param kwargs: Named formatting values adapted to scalar text when necessary.
        :return: Immediately evaluated translation with QQ text formatting preserved.
        """
        ...


class Runtime:
    def __init__(self: Self, args: RuntimeArgs | None = None, logger: Logger | None = None) -> None:
        """Create a fresh runtime with optional deployment arguments and logger.
        
        :param args: Deployment action and selected configuration paths, or defaults when omitted.
        :param logger: Standalone logger, or a newly created default logger.
        :return: No return value.
        """
        self.args = args or RuntimeArgs()
        self.logger = logger or create_logger()
        self.state = RuntimeState.CREATED
        self._exit_requested = threading.Event()
        self._stop_lock = threading.RLock()
        self._config_callbacks = []
        self._initialized = False
        self._local_started = False
        self._network_started = False
        self._was_ready = False
        self._callbacks_ready = False
        self.builtin_command_root = None

    def get_config(self: Self) -> Config:
        """Return the active standalone configuration.
        
        :return: Result of the operation.
        """
        return self.config_manager.get_config()

    @property
    def config(self: Self) -> Config:
        """Expose the active standalone configuration.
        
        :return: Result of the operation.
        """
        return self.get_config()

    def get_language(self: Self) -> str:
        """Return the configured translation language.
        
        :return: Result of the operation.
        """
        return self.translation_manager.language

    def get_server_interface(self: Self) -> QQServerInterface:
        """Return the plugin-facing QQ server interface.
        
        :return: Result of the operation.
        """
        return self.server_interface

    def add_config_changed_callback(self: Self, callback: Callable[[Config, bool], None]) -> None:
        """Register a configuration callback and invoke it immediately once callbacks are ready.
        
        :param callback: Callback receiving the active configuration and logging flag.
        :return: No return value.
        """
        self._config_callbacks.append(callback)
        if self._callbacks_ready:
            callback(self.config, False)

    def create_internal_translator(self: Self, prefix: str) -> _InternalTranslator:
        """Create a native-key translator that converts nonscalar formatting values to text.
        
        :param prefix: Native manager translation namespace beneath mcdreforged.
        :return: Result of the operation.
        """
        class Translator:
            def __init__(inner: Self, runtime: Runtime) -> None:
                inner.runtime = runtime

            def tr(inner: Self, key: str, *args: object, **kwargs: object) -> str | QText | QMarkdown:
                scalar = (str, int, float, bool, type(None))
                def adapt(value: object) -> str | int | float | bool | None:
                    return value if isinstance(value, scalar) else str(value)
                args = tuple(adapt(value) for value in args)
                kwargs = {name: adapt(value) for name, value in kwargs.items()}
                return inner.runtime.translate('mcdreforged.' + prefix + '.' + key, *args, **kwargs)
        return Translator(self)

    def translate(self: Self, key: str, *args: TranslationParameter, **kwargs: TranslationOption) -> str | QText | QMarkdown:
        """Translate a key immediately, honoring native language and failure option aliases.
        
        :param key: Translation key.
        :param args: Positional translation formatting values.
        :param kwargs: Named formatting values and supported translation options.
        :return: Result of the operation.
        """
        if '_mcdr_tr_language' in kwargs:
            kwargs['language'] = kwargs.pop('_mcdr_tr_language')
        if '_mcdr_tr_allow_failure' in kwargs:
            kwargs['allow_failure'] = kwargs.pop('_mcdr_tr_allow_failure')
        return self.translation_manager.tr(key, *args, **kwargs)

    def is_stopping(self: Self) -> bool:
        """Report whether shutdown has started or the runtime has failed.
        
        :return: Result of the operation.
        """
        return self.state in (RuntimeState.STOPPING, RuntimeState.STOPPED, RuntimeState.FAILED)

    def is_ready(self: Self) -> bool:
        """Report whether the runtime and QQ gateway are both ready.
        
        :return: Result of the operation.
        """
        return self.state is RuntimeState.READY and self.gateway.is_ready()

    def exit(self: Self) -> bool:
        """Request orderly shutdown without waiting for executor threads.
        
        :return: True when shutdown was requested; False after a terminal state.
        """
        if self.state in (RuntimeState.STOPPED, RuntimeState.FAILED):
            return False
        self._exit_requested.set()
        return True

    def initialize_local(self: Self) -> None:
        """Initialize local managers and services without starting network connections.
        
        :return: No return value.
        """
        if self._initialized:
            return
        from botcraft.config import ConfigManager
        from botcraft.translation.translation_manager import TranslationManager
        from botcraft.permission.permission_manager import PermissionManager
        from botcraft.preference.preference_manager import PreferenceManager
        from botcraft.preference.known_users import KnownUserStore
        from botcraft.plugin.si.server_interface import QQServerInterface
        from botcraft.plugin.plugin_manager import PluginManager
        from botcraft.command.command_manager import CommandManager
        from botcraft.executor.task_executor_sync import TaskExecutor
        from botcraft.executor.task_executor_async import AsyncTaskExecutor
        from botcraft.network.network_loop import NetworkLoop
        from botcraft.network.api_client import ApiClient
        from botcraft.network.gateway_client import GatewayClient
        from botcraft.message.message_sender import MessageSender
        from botcraft.panel.panel_synchronizer import PanelSynchronizer
        from botcraft.event.event_dispatcher import EventDispatcher
        if not hasattr(self, 'config_manager'):
            self.config_manager = ConfigManager(self.logger, self.args.config_file_path)
            self.config_manager.load(allowed_missing_file=False)
        self.logger.secret_filter.add(self.config.secret)
        self.translation_manager = TranslationManager(self)
        self.translation_manager.load_translations()
        self.translation_manager.set_language(self.config.language)
        self.permission_manager = PermissionManager(self, self.args.permission_file_path)
        self.permission_manager.load_permission_file(allowed_missing_file=False)
        self.preference_manager = PreferenceManager(self)
        self.preference_manager.load_preferences()
        self.users = KnownUserStore(self)
        self.users.load()
        self.server_interface = QQServerInterface(self)
        self.plugin_manager = PluginManager(self)
        self.command_manager = CommandManager(self)
        self.sync_task_executor = TaskExecutor(self)
        self.async_task_executor = AsyncTaskExecutor(self)
        self.network_loop = NetworkLoop(self)
        self.api_client = ApiClient(self)
        self.gateway = GatewayClient(self)
        self.sender = MessageSender(self)
        self.panel_synchronizer = PanelSynchronizer(self)
        self.event_dispatcher = EventDispatcher(self)
        self._initialized = True
        self._callbacks_ready = True
        self.on_config_changed(log=False)

    def on_config_changed(self: Self, *, log: bool = False) -> None:
        """Apply active configuration to local services and schedule network updates.
        
        :param log: Whether configuration callbacks should log applied settings.
        :return: No return value.
        """
        self.logger.setLevel(logging.DEBUG if self.config.is_debug_on() else logging.INFO)
        self.logger.set_debug_options(self.config.debug)
        self.logger.set_console_color(not self.config.disable_console_color)
        self.translation_manager.set_language(self.config.language)
        for callback in self._config_callbacks:
            callback(self.config, log)
        if self._network_started:
            self.network_loop.submit(self._apply_network_config(), operation='configuration apply')
        self.on_registry_changed()

    async def _apply_network_config(self: Self) -> None:
        await self.gateway.apply_config()

    def load_config(self: Self, *, log: bool = False) -> bool:
        """Reload configuration and notify registered services of the change.
        
        :param log: Whether configuration callbacks should log applied settings.
        :return: Whether the configuration file needed missing-option repair.
        """
        result = self.config_manager.load(allowed_missing_file=False, initial=False)
        self.on_config_changed(log=log)
        return result

    def on_registry_changed(self: Self) -> None:
        """Schedule panel synchronization after command registry changes.
        
        :return: No return value.
        """
        if self._network_started and not self.is_stopping():
            self.panel_synchronizer.schedule_sync()

    def start_local(self: Self) -> None:
        """Start local executors and load plugins.
        
        :return: No return value.
        """
        if self._local_started or self.is_stopping():
            raise RuntimeError('Runtime cannot be started twice')
        self.initialize_local()
        self.state = RuntimeState.STARTING
        from botcraft.plugin.si.qq_server_interface_mixin import ServerInterfaceMixin
        if ServerInterfaceMixin._instance is not None:
            raise RuntimeError('Only one Runtime may run in this process')
        ServerInterfaceMixin._instance = self.server_interface
        self.sync_task_executor.start()
        self.async_task_executor.start()
        self._local_started = True
        self.state = RuntimeState.PLUGIN_LOADING
        self.plugin_manager.register_builtin_plugins()
        self.plugin_manager.load_all_plugins().result()

    def start(self: Self) -> None:
        """Start the complete runtime and wait for initial QQ gateway readiness.
        
        :return: No return value.
        """
        if self.state is not RuntimeState.CREATED:
            raise RuntimeError('Runtime start requires a fresh instance')
        try:
            from botcraft.bootstrap import prepare_environment
            from botcraft.config import ConfigManager
            prepare_environment(self.args)
            if self.logger.file_handler is None:
                self.logger.set_file('logs/botcraft.log')
                self.logger.file_handler.addFilter(self.logger.secret_filter)
            self.config_manager = ConfigManager(self.logger, self.args.config_file_path)
            self.config_manager.load(allowed_missing_file=False)
            self.logger.secret_filter.add(self.config.secret)
            if not self.config.appid or not self.config.secret:
                raise ValueError('Configure appid and secret first; never share credentials in chat or logs')
            from botcraft.compatibility.capability_checker import check_capabilities
            check_capabilities(self.logger, force=self.args.check_capabilities)
            self.start_local()
            self.network_loop.start()
            self._network_started = True
            self.network_loop.submit(self.api_client.start(), operation='HTTP start').result()
            self.state = RuntimeState.PANEL_REBUILDING
            self.network_loop.submit(self.panel_synchronizer.rebuild(), operation='panel startup').result()
            self.state = RuntimeState.CONNECTING
            self.network_loop.submit(self.gateway.start(), operation='gateway start').result()
            self.state = RuntimeState.READY
            self._was_ready = True
            from botcraft.plugin.plugin_event import PluginEvents
            self.plugin_manager.dispatch_event(PluginEvents.BOTCRAFT_START, ())
            self.logger.info('BotCraft READY')
        except BaseException:
            self.state = RuntimeState.FAILED
            self.stop(interrupted=True)
            raise

    def run(self: Self) -> None:
        """Run the selected deployment action or serve until shutdown is requested.
        
        :return: No return value.
        """
        if self.args.generate_default_only:
            from botcraft.bootstrap import generate_default
            generate_default(self.args)
            return
        if self.args.initialize_environment:
            from botcraft.bootstrap import initialize_environment
            initialize_environment(self.args)
            return
        try:
            self.start()
            from botcraft.executor.console_handler import ConsoleHandler
            self.console_handler = ConsoleHandler(self)
            if not self.config.disable_console_thread:
                self.console_handler.start()
            while not self._exit_requested.wait(0.2):
                if self.gateway.state.name == 'FAILED':
                    raise RuntimeError('Gateway entered an unrecoverable state')
        except KeyboardInterrupt:
            self.exit()
            self.stop(interrupted=True)
        finally:
            self.stop()

    def execute_console(self: Self, command: str) -> Future[None]:
        """Submit a console command to the synchronous executor.
        
        :param command: Console command text to execute.
        :return: Future completing when console command execution finishes.
        """
        from botcraft.command.command_source import ConsoleSource
        if self.is_stopping():
            raise RuntimeError('Runtime is stopping')
        return observe_future(self.sync_task_executor.submit(lambda: self.command_manager.execute_console(command, ConsoleSource(self))), self.logger, 'console command')

    def stop(self: Self, *, interrupted: bool = False) -> None:
        """Stop local and network services with bounded shutdown waits.
        
        :param interrupted: Whether to use the shorter interrupted-shutdown deadline.
        :return: No return value.
        """
        with self._stop_lock:
            if self._local_started and (self.sync_task_executor.is_on_thread() or self.async_task_executor.is_on_thread()):
                raise RuntimeError('Use server.exit() from plugin executor threads; stop() cannot wait for itself')
            if self.state is RuntimeState.STOPPED:
                return
            failed = self.state is RuntimeState.FAILED
            self.state = RuntimeState.STOPPING
            self._exit_requested.set()
            if hasattr(self, 'console_handler'):
                self.console_handler.stop()
                console_thread = self.console_handler.get_thread()
                if console_thread is not None and not self.console_handler.is_on_thread():
                    self.console_handler.join(timeout=5)
                    if console_thread.is_alive():
                        self.logger.warning('Console executor did not stop within five seconds')
            if hasattr(self, 'sender'):
                self.sender.close()
            deadline = time.monotonic() + (10 if interrupted else 600)
            if self._local_started:
                from botcraft.plugin.plugin_event import PluginEvents
                if self._was_ready:
                    self.plugin_manager.dispatch_event(PluginEvents.BOTCRAFT_STOP, ())
                for plugin in list(self.plugin_manager.get_regular_plugins()):
                    try:
                        completion = self.sync_task_executor.submit(partial(self.plugin_manager.unload_plugin, plugin))
                        operation = completion.result(timeout=max(0, deadline - time.monotonic()))
                        operation.result(timeout=max(0, deadline - time.monotonic()))
                    except TimeoutError as error:
                        report_error(error, self.logger, 'plugin shutdown deadline')
                        break
                self.sync_task_executor.soft_stop()
                for elapsed in range(10 if interrupted else 600):
                    remaining = max(0, deadline - time.monotonic())
                    if remaining == 0:
                        break
                    self.sync_task_executor.join(timeout=min(1, remaining))
                    if not self.sync_task_executor.get_thread().is_alive():
                        break
                    if elapsed + 1 in (10, 30, 60, 120, 300, 600):
                        self.logger.warning('Synchronous executor still alive after %s seconds', elapsed + 1)
                        stack = self.sync_task_executor.get_thread_stack()
                        if stack is not None:
                            for line in stack.format():
                                self.logger.warning('%s', line)
                if self.sync_task_executor.get_thread().is_alive():
                    error = TimeoutError('Synchronous shutdown deadline exceeded; running threads were not killed')
                    self.sync_task_executor.finish_pending(error)
                    self.plugin_manager.finish_pending(error)
                    report_error(error, self.logger, 'Runtime shutdown')
                self.async_task_executor.stop()
                self.async_task_executor.join(timeout=max(0, deadline - time.monotonic()))
                if self.async_task_executor.get_thread().is_alive():
                    self.async_task_executor.finish_pending(TimeoutError('Async shutdown deadline exceeded'))
                    self.logger.warning('Async executor exceeded shutdown deadline')
                self._local_started = False
            if self._network_started:
                try:
                    self.network_loop.submit(self._close_network(), operation='network stop').result(timeout=self.config.http.timeout + 15)
                except Exception as error:
                    report_error(error, self.logger, 'network stop')
                finally:
                    self.network_loop.stop()
                    self._network_started = False
            from botcraft.plugin.si.qq_server_interface_mixin import ServerInterfaceMixin
            if ServerInterfaceMixin._instance is getattr(self, 'server_interface', None):
                ServerInterfaceMixin._instance = None
            self.state = RuntimeState.FAILED if failed else RuntimeState.STOPPED

    async def _close_network(self: Self) -> None:
        await self.gateway.close()
        await self.panel_synchronizer.close()
        await self.api_client.close()
