import inspect
from mcdreforged.plugin.plugin_event import EventListener, LiteralEvent, PluginEvent
from botcraft.utils.exception import UnsupportedOperationError, RuntimeNotReadyError
from botcraft.utils.future_utils import observe_future


class ServerInterfaceMixin:
    _instance = None

    def __init__(self, runtime):
        self._runtime = runtime
        self._tr = runtime.create_internal_translator('server_interface').tr

    @classmethod
    def get_instance(cls):
        return ServerInterfaceMixin._instance

    @classmethod
    def si_opt(cls):
        return cls.get_instance()

    @classmethod
    def si(cls):
        instance = cls.si_opt()
        if instance is None:
            raise RuntimeError('BotCraft is not running')
        return instance

    @classmethod
    def psi_opt(cls):
        instance = cls.si_opt()
        if instance is None:
            return None
        plugin = instance._runtime.plugin_manager.get_plugin_in_current_context()
        return plugin.server_interface if plugin is not None else None

    @classmethod
    def psi(cls):
        instance = cls.psi_opt()
        if instance is None:
            raise RuntimeError('No current QQ plugin context')
        return instance

    @property
    def _plugin_manager(self):
        return self._runtime.plugin_manager

    @property
    def logger(self):
        from botcraft.logging.logger import plugin_logger
        plugin = getattr(self, '_plugin', None) or self._plugin_manager.get_plugin_in_current_context()
        return plugin_logger(self._runtime.logger, plugin.get_id()) if plugin is not None else self._runtime.logger

    def _create_plugin_logger(self, plugin_id):
        from botcraft.logging.logger import plugin_logger
        return plugin_logger(self._runtime.logger, plugin_id)

    def _reset_on_load(self):
        # Logger access is uncached; the plugin record remains the same bound object.
        return None

    def as_basic_server_interface(self):
        return self._runtime.server_interface

    def as_plugin_server_interface(self):
        return self if hasattr(self, '_plugin') else self.psi_opt()

    def _registration_plugin(self):
        if self._runtime.is_stopping():
            raise RuntimeNotReadyError('Runtime does not accept new registrations')
        plugin = getattr(self, '_plugin', None) or self._plugin_manager.get_plugin_in_current_context()
        if plugin is None:
            raise RuntimeError('Registration requires a plugin record')
        plugin._check_state()
        return plugin

    def register_command(self, root_node, *, allow_duplicates=False, scope=('group', 'c2c')):
        self._registration_plugin().plugin_registry.register_command(root_node, allow_duplicates=allow_duplicates, scope=scope)

    def register_event_listener(self, event, callback, priority=None):
        from botcraft.plugin.plugin_event import normalize_event_id
        plugin = self._registration_plugin()
        if not isinstance(event, (str, PluginEvent)):
            raise TypeError('Expected event ID or PluginEvent')
        event_id = normalize_event_id(event if isinstance(event, str) else event.id)
        listener = EventListener(plugin, callback, 1000 if priority is None else priority)
        plugin.plugin_registry.register_event_listener(event_id, listener)

    def register_translation(self, language, mapping):
        self._registration_plugin().plugin_registry.register_translation(language, mapping)

    def register_help_message(self, prefix, message, permission=0, *, scope=('group', 'c2c'), only_admin=False):
        from botcraft.plugin.plugin_registry import HelpMessage
        plugin = self._registration_plugin()
        plugin.plugin_registry.register_help_message(HelpMessage(plugin, prefix, message, permission, scope=scope, only_admin=only_admin))

    def get_self_metadata(self):
        plugin = getattr(self, '_plugin', None) or self._plugin_manager.get_plugin_in_current_context()
        if plugin is None:
            raise RuntimeError('No bound plugin record')
        return plugin.get_metadata()

    def get_data_folder(self):
        from pathlib import Path
        plugin = getattr(self, '_plugin', None)
        if plugin is None:
            raise RuntimeError('No bound plugin record')
        path = Path('config') / plugin.get_id()
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def tell(self, user, message, *, refer_msg=None, return_future=False):
        from botcraft.message.user import User
        if not isinstance(user, User):
            raise TypeError('tell requires User')
        future = self._runtime.sender.send(user, message, refer_msg=refer_msg, mention=True)
        return future if return_future else None

    def say(self, target, message, *, refer_msg=None, return_future=False):
        future = self._runtime.sender.send(target, message, refer_msg=refer_msg)
        return future if return_future else None

    def broadcast(self, target, message, *, refer_msg=None, return_future=False):
        future = self._runtime.sender.send(target, message, refer_msg=refer_msg)
        self.logger.info('broadcast submitted: %s', message if isinstance(message, str) else type(message).__name__)
        return future if return_future else None

    def reply(self, source, message, *, refer_msg=None, return_future=False):
        from botcraft.command.command_source import QQCommandSource
        if not isinstance(source, QQCommandSource) or source._runtime is not self._runtime:
            raise TypeError('reply requires a real QQ source from this Runtime')
        with source.preferred_language_context():
            future = self._runtime.sender.reply(source, message, refer_msg=refer_msg)
        return future if return_future else None

    def reply_event(self, event, message, *, refer_msg=None, return_future=False):
        future = self._runtime.sender.reply_event(event, message, refer_msg=refer_msg)
        return future if return_future else None

    def delete_message(self, message, *, return_future=False):
        future = self._runtime.sender.delete_message(message)
        return future if return_future else None

    def delete_message_with_id(self, target, id, *, return_future=False):
        future = self._runtime.sender.delete_message_with_id(target, id)
        return future if return_future else None

    def respond_interaction(self, event, code):
        return self._runtime.sender.respond_interaction(event, code)

    def execute_command(self, command, source):
        return self._runtime.command_manager.execute_command(command, source)

    def get_plugin_command_source(self):
        raise UnsupportedOperationError('Plugin command sources are not supported')

    def schedule_task(self, callable_, *, block=False, timeout=None):
        if self._runtime.is_stopping():
            raise RuntimeNotReadyError('Runtime does not accept new tasks')
        if inspect.iscoroutine(callable_):
            future = self._runtime.async_task_executor.submit(callable_)
        elif callable(callable_):
            future = self._runtime.sync_task_executor.submit(callable_)
        else:
            raise TypeError('Expected callable or coroutine')
        observe_future(future, self.logger, 'schedule_task')
        if block:
            future.result(timeout=timeout)
        return future

    def get_event_loop(self):
        return self._runtime.async_task_executor.get_event_loop()

    def exit(self):
        return self._runtime.exit()

    def is_ready(self):
        return self._runtime.is_ready()

    def get_connection_state(self):
        return self._runtime.gateway.state

    def get_panel_status(self, scope):
        return self._runtime.panel_synchronizer.get_status(scope)

    def get_permission_level(self, obj):
        return self._runtime.permission_manager.get_permission(obj)

    def set_permission_level(self, obj, level, *, global_scope=False):
        return self._runtime.permission_manager.set_permission(obj, level, global_scope=global_scope)

    def remove_permission(self, obj, *, global_scope=False):
        return self._runtime.permission_manager.remove_permission(obj, global_scope=global_scope)

    def is_super_admin(self, obj):
        return self._runtime.permission_manager.is_super_admin(obj)

    def get_preference(self, obj, **kwargs):
        return self._runtime.preference_manager.get_preference(obj, **kwargs)

    def set_preference(self, obj, preference):
        return self._runtime.preference_manager.set_preference(obj, preference)

    def get_default_preference(self):
        return self._runtime.preference_manager.get_default_preference()

    def tr(self, key, *args, **kwargs):
        return self._runtime.translation_manager.tr(key, *args, **kwargs)

    def rtr(self, key, *args, **kwargs):
        return self._runtime.translation_manager.rtr(key, *args, **kwargs)

    def get_botcraft_language(self):
        return self._runtime.get_language()

    def get_botcraft_config(self):
        return self._runtime.get_config().serialize()

    def modify_botcraft_config(self, changes):
        self._runtime.config_manager.set_values(changes)
        self._runtime.config_manager.save()
        self._runtime.on_config_changed(log=False)

    def reload_botcraft_config_file(self, *, log=False):
        return self._runtime.load_config(log=log)

    def get_plugin_list(self):
        return [p.get_id() for p in self._plugin_manager.get_regular_plugins()]

    def get_plugin_metadata(self, plugin_id):
        plugin = self._plugin_manager.get_plugin_from_id(plugin_id)
        return plugin.get_metadata() if plugin else None

    def _plugin_operation_thread_check(self):
        if self.is_on_async_executor_thread():
            raise RuntimeError('Schedule plugin operations on the synchronous executor')
        if self._runtime.is_stopping():
            raise RuntimeNotReadyError('Runtime is stopping')

    def load_plugin(self, file_path):
        from pathlib import Path
        from mcdreforged.plugin.operation_result import PluginResultType
        self._plugin_operation_thread_check()
        future = self._plugin_manager.load_plugin(Path(file_path))
        return future.result().get_if_success(PluginResultType.LOAD) if future.done() else False

    def _operate_plugin(self, plugin_id, method, result_type):
        self._plugin_operation_thread_check()
        plugin = self._plugin_manager.get_regular_plugin_from_id(plugin_id)
        if plugin is None:
            return None
        future = getattr(self._plugin_manager, method)(plugin)
        return future.result().get_if_success(result_type) if future.done() else None

    def unload_plugin(self, plugin_id):
        from mcdreforged.plugin.operation_result import PluginResultType
        return self._operate_plugin(plugin_id, 'unload_plugin', PluginResultType.UNLOAD)

    def reload_plugin(self, plugin_id):
        from mcdreforged.plugin.operation_result import PluginResultType
        return self._operate_plugin(plugin_id, 'reload_plugin', PluginResultType.RELOAD)

    def enable_plugin(self, file_path):
        from pathlib import Path
        from mcdreforged.plugin.operation_result import PluginResultType
        self._plugin_operation_thread_check()
        future = self._plugin_manager.enable_plugin(Path(file_path))
        return future.result().get_if_success(PluginResultType.LOAD) if future.done() else False

    def disable_plugin(self, plugin_id):
        from mcdreforged.plugin.operation_result import PluginResultType
        return self._operate_plugin(plugin_id, 'disable_plugin', PluginResultType.UNLOAD)

    def refresh_all_plugins(self):
        self._plugin_operation_thread_check()
        self._plugin_manager.refresh_all_plugins()

    def refresh_changed_plugins(self):
        self._plugin_operation_thread_check()
        self._plugin_manager.refresh_changed_plugins()

    def reload_permission_file(self):
        return self._runtime.permission_manager.load_permission_file(allowed_missing_file=False)

    def reload_preference_file(self):
        return self._runtime.preference_manager.load_preferences()

    def is_on_executor_thread(self):
        return self._runtime.sync_task_executor.is_on_thread()

    def is_on_async_executor_thread(self):
        return self._runtime.async_task_executor.is_on_thread()

    def has_translation(self, translation_key, *, language=None, no_auto_fallback=False):
        from mcdreforged.translation.language_fallback_handler import LanguageFallbackHandler
        try:
            self._runtime.translation_manager.tr(translation_key, language=language, allow_failure=False,
                fallback_handler=LanguageFallbackHandler.none() if no_auto_fallback else LanguageFallbackHandler.auto())
        except KeyError:
            return False
        return True

    def open_bundled_file(self, relative_file_path):
        from mcdreforged.plugin.type.multi_file_plugin import MultiFilePlugin
        plugin = getattr(self, '_plugin', None)
        if not isinstance(plugin, MultiFilePlugin):
            raise FileNotFoundError('Bundled files require a directory or packed plugin')
        return plugin.open_file(relative_file_path)

    def dispatch_event(self, event, args=(), *, on_executor_thread=True):
        if not isinstance(event, (str, PluginEvent)):
            raise TypeError('Expected custom event')
        event_id = event if isinstance(event, str) else event.id
        from botcraft.plugin.plugin_event import PluginEvents
        if event_id.lower().startswith('botcraft.') or PluginEvents.is_known_event(event_id) or event_id.upper() == event_id:
            raise UnsupportedOperationError('Cannot manually dispatch built-in events')
        policy = self._plugin_manager.DispatchEventPolicy.always_new_task if on_executor_thread else self._plugin_manager.DispatchEventPolicy.directly_invoke
        self._plugin_manager.dispatch_event(LiteralEvent(event_id), args, dispatch_policy=policy)

    def _unsupported(self, *args, **kwargs):
        raise UnsupportedOperationError('Minecraft/MCDR host operation has no QQ equivalent')

    start = stop = kill = restart = execute = execute_async = _unsupported
    get_pid = get_server_pid = get_server_information = get_server_version = _unsupported
    is_server_running = is_server_startup = is_server_rcon_ready = _unsupported
    rcon_query = connect_rcon = disconnect_rcon = register_server_handler = register_info_filter = _unsupported
    get_mcdr_config = modify_mcdr_config = reload_config_file = get_mcdr_language = _unsupported
    wait_until_stop = wait_for_start = stop_exit = set_exit_after_stop_flag = _unsupported
    is_rcon_running = get_server_pid_all = _unsupported
