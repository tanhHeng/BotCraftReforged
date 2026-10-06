from __future__ import annotations

import inspect
from asyncio import AbstractEventLoop
from concurrent.futures import Future
from enum import Enum
from os import PathLike
from typing import Any, Callable, Coroutine, IO, Iterable, Mapping, NoReturn, TYPE_CHECKING, TypeVar
from typing_extensions import Self

from mcdreforged.command.builder.nodes.basic import Literal
from mcdreforged.permission.permission_level import PermissionLevelItem
from mcdreforged.plugin.operation_result import PluginResultType
from mcdreforged.plugin.plugin_event import EventListener, LiteralEvent, PluginEvent
from mcdreforged.preference.preference_manager import PreferenceItem
from mcdreforged.translation.language_fallback_handler import LanguageFallbackHandler
from botcraft.command.command_source import ConsoleSource, QQCommandSource
from botcraft.event.qq_event import QQEvent
from botcraft.event.qq_interaction import QQInteraction
from botcraft.logging.logger import Logger
from botcraft.message.message_received import QQMessageReceived
from botcraft.message.message_receipt import QQMessageReceipt
from botcraft.message.qtext.text import QMarkdown, QText, QTextBase
from botcraft.message.user import Group, Scene, User
from botcraft.network.gateway_client import GatewayState
from botcraft.panel.panel_synchronizer import PanelStatus
from botcraft.plugin.meta.metadata import Metadata
from botcraft.translation.translation_manager import TranslationOption, TranslationParameter
from botcraft.translation.translation_text import QQTranslationText
from botcraft.utils.exception import UnsupportedOperationError, RuntimeNotReadyError
from botcraft.utils.future_utils import observe_future

if TYPE_CHECKING:
    from botcraft.plugin.plugin_manager import PluginManager
    from botcraft.plugin.si.plugin_server_interface import QQPluginServerInterface
    from botcraft.plugin.si.server_interface import QQServerInterface
    from botcraft.plugin.type.plugin import Plugin
    from botcraft.runtime import Runtime

_Result = TypeVar('_Result')


class ServerInterfaceMixin:
    _instance = None

    def __init__(self: Self, runtime: Runtime) -> None:
        """Bind the interface to its QQ runtime.
        
        :param runtime: Runtime that owns this interface and all submitted operations.
        :return: No value is returned.
        """
        self._runtime = runtime
        self._tr = runtime.create_internal_translator('server_interface').tr

    @classmethod
    def get_instance(cls: type[Self]) -> QQServerInterface | None:
        """Get the currently active basic QQ interface, if any.
        
        :return: The active interface, or None when the optional lookup has no matching context.
        """
        return ServerInterfaceMixin._instance

    @classmethod
    def si_opt(cls: type[Self]) -> QQServerInterface | None:
        """Get the active QQ interface without requiring a running runtime.
        
        :return: The active interface, or None when the optional lookup has no matching context.
        """
        return cls.get_instance()

    @classmethod
    def si(cls: type[Self]) -> QQServerInterface:
        """Get the active QQ interface or raise when BotCraft is not running.
        
        :return: The interface for the required active context.
        """
        instance = cls.si_opt()
        if instance is None:
            raise RuntimeError('BotCraft is not running')
        return instance

    @classmethod
    def psi_opt(cls: type[Self]) -> QQPluginServerInterface | None:
        """Get the interface for the current plugin context, if present.
        
        :return: The active interface, or None when the optional lookup has no matching context.
        """
        instance = cls.si_opt()
        if instance is None:
            return None
        plugin = instance._runtime.plugin_manager.get_plugin_in_current_context()
        return plugin.server_interface if plugin is not None else None

    @classmethod
    def psi(cls: type[Self]) -> QQPluginServerInterface:
        """Get the current plugin interface or raise when no plugin context exists.
        
        :return: The interface for the required active context.
        """
        instance = cls.psi_opt()
        if instance is None:
            raise RuntimeError('No current QQ plugin context')
        return instance

    @property
    def _plugin_manager(self: Self) -> PluginManager:
        return self._runtime.plugin_manager

    @property
    def logger(self: Self) -> Logger:
        """Get the logger associated with the bound or currently active plugin.
        
        :return: The plugin logger, or the runtime logger outside a plugin context.
        """
        from botcraft.logging.logger import plugin_logger
        plugin = getattr(self, '_plugin', None) or self._plugin_manager.get_plugin_in_current_context()
        return plugin_logger(self._runtime.logger, plugin.get_id()) if plugin is not None else self._runtime.logger

    def _create_plugin_logger(self: Self, plugin_id: str) -> Logger:
        from botcraft.logging.logger import plugin_logger
        return plugin_logger(self._runtime.logger, plugin_id)

    def _reset_on_load(self: Self) -> None:
        # Logger access is uncached; the plugin record remains the same bound object.
        return None

    def as_basic_server_interface(self: Self) -> QQServerInterface:
        """Get the runtime-wide basic QQ interface.
        
        :return: The basic interface owned by this runtime.
        """
        return self._runtime.server_interface

    def as_plugin_server_interface(self: Self) -> QQPluginServerInterface | None:
        """Get this bound plugin interface or the current plugin-context interface.
        
        :return: A plugin interface, or None outside a bound/current plugin context.
        """
        return self if hasattr(self, '_plugin') else self.psi_opt()

    def _registration_plugin(self: Self) -> Plugin:
        if self._runtime.is_stopping():
            raise RuntimeNotReadyError('Runtime does not accept new registrations')
        plugin = getattr(self, '_plugin', None) or self._plugin_manager.get_plugin_in_current_context()
        if plugin is None:
            raise RuntimeError('Registration requires a plugin record')
        plugin._check_state()
        return plugin

    def register_command(self: Self, root_node: Literal, *, allow_duplicates: bool = False, scope: Iterable[Scene | str] = ('group', 'c2c')) -> None:
        """Register a command root for the bound or current plugin.
        
        :param root_node: Native command-builder root to register.
        :param allow_duplicates: Whether existing command roots may share the same literal.
        :param scope: Scenes where the command is available; group and c2c are supported.
        :return: No value is returned.
        """
        self._registration_plugin().plugin_registry.register_command(root_node, allow_duplicates=allow_duplicates, scope=scope)

    def register_event_listener(self: Self, event: PluginEvent | str, callback: Callable[..., object], priority: int | None = None) -> None:
        """Register a QQ or custom event callback for the bound or current plugin.
        
        :param event: Event object or event ID to listen for.
        :param callback: Callback invoked with the plugin interface and the event arguments.
        :param priority: Listener priority; None selects the native priority of 1000.
        :return: No value is returned.
        """
        from botcraft.plugin.plugin_event import normalize_event_id
        plugin = self._registration_plugin()
        if not isinstance(event, (str, PluginEvent)):
            raise TypeError('Expected event ID or PluginEvent')
        event_id = normalize_event_id(event if isinstance(event, str) else event.id)
        listener = EventListener(plugin, callback, 1000 if priority is None else priority)
        plugin.plugin_registry.register_event_listener(event_id, listener)

    def register_translation(self: Self, language: str, mapping: dict[str, Any]) -> None:
        """Register nested translation entries for a language.
        
        :param language: Language identifier for these entries.
        :param mapping: Nested translation mapping with string leaves and open JSON values.
        :return: No value is returned.
        """
        self._registration_plugin().plugin_registry.register_translation(language, mapping)

    def register_help_message(self: Self, prefix: str, message: str | dict[str, str] | QQTranslationText, permission: int = 0, *, scope: Iterable[Scene | str] = ('group', 'c2c'), only_admin: bool = False) -> None:
        """Register help text and a QQ panel entry for the bound or current plugin.
        
        :param prefix: Command prefix displayed in help and panels.
        :param message: Plain text, language-to-text mapping, or delayed translation. Ordinary help resolves the querying source's preferred language; panels resolve the current configuration language when synchronized.
        :param permission: Minimum permission level for ordinary help visibility.
        :param scope: Supported scenes in which this help entry applies.
        :param only_admin: Whether the panel entry is restricted to administrators.
        :return: No value is returned.
        """
        from botcraft.plugin.plugin_registry import HelpMessage
        plugin = self._registration_plugin()
        plugin.plugin_registry.register_help_message(HelpMessage(plugin, prefix, message, permission, scope=scope, only_admin=only_admin))

    def get_self_metadata(self: Self) -> Metadata:
        """Get metadata for the bound plugin or the current plugin context.
        
        :return: The plugin metadata; missing plugin context raises RuntimeError.
        """
        plugin = getattr(self, '_plugin', None) or self._plugin_manager.get_plugin_in_current_context()
        if plugin is None:
            raise RuntimeError('No bound plugin record')
        return plugin.get_metadata()

    def get_data_folder(self: Self) -> str:
        """Create and get the configuration folder for this bound plugin.
        
        :return: The relative configuration-folder path; an unbound interface raises RuntimeError.
        """
        from pathlib import Path
        plugin = getattr(self, '_plugin', None)
        if plugin is None:
            raise RuntimeError('No bound plugin record')
        path = Path('config') / plugin.get_id()
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def tell(self: Self, user: User, message: str | QTextBase, *, refer_msg: QQMessageReceived | QQMessageReceipt | None = None, return_future: bool = False) -> Future[QQMessageReceipt] | None:
        """Send a message to a QQ user, mentioning them in a group.
        
        :param user: User to send to; group delivery mentions this user.
        :param message: Plain or QQ rich text, including delayed translations evaluated before submission.
        :param refer_msg: Optional received message or receipt from the same conversation, using its reference index. This is a quoted reference, not a passive msg_id or event_id.
        :param return_future: Whether to return the submitted concurrent future; False hides the future without waiting.
        :return: A concurrent future resolving to the sent-message receipt when requested, otherwise None.
        """
        from botcraft.message.user import User
        if not isinstance(user, User):
            raise TypeError('tell requires User')
        future = self._runtime.sender.send(user, message, refer_msg=refer_msg, mention=True)
        return future if return_future else None

    def say(self: Self, target: User | Group, message: str | QTextBase, *, refer_msg: QQMessageReceived | QQMessageReceipt | None = None, return_future: bool = False) -> Future[QQMessageReceipt] | None:
        """Send an active message to a QQ user or group.
        
        :param target: User or group that determines the destination route.
        :param message: Plain or QQ rich text, including delayed translations evaluated before submission.
        :param refer_msg: Optional received message or receipt from the same conversation, using its reference index. This is a quoted reference, not a passive msg_id or event_id.
        :param return_future: Whether to return the submitted concurrent future; False hides the future without waiting.
        :return: A concurrent future resolving to the sent-message receipt when requested, otherwise None.
        """
        future = self._runtime.sender.send(target, message, refer_msg=refer_msg)
        return future if return_future else None

    def broadcast(self: Self, target: User | Group, message: str | QTextBase, *, refer_msg: QQMessageReceived | QQMessageReceipt | None = None, return_future: bool = False) -> Future[QQMessageReceipt] | None:
        """Send an active message and log its submission.
        
        :param target: User or group that determines the destination route.
        :param message: Plain or QQ rich text, including delayed translations evaluated before submission.
        :param refer_msg: Optional received message or receipt from the same conversation, using its reference index. This is a quoted reference, not a passive msg_id or event_id.
        :param return_future: Whether to return the submitted concurrent future; False hides the future without waiting.
        :return: A concurrent future resolving to the sent-message receipt when requested, otherwise None.
        """
        future = self._runtime.sender.send(target, message, refer_msg=refer_msg)
        self.logger.info('broadcast submitted: %s', message if isinstance(message, str) else type(message).__name__)
        return future if return_future else None

    def reply(self: Self, source: QQCommandSource, message: str | QTextBase, *, refer_msg: QQMessageReceived | QQMessageReceipt | None = None, return_future: bool = False) -> Future[QQMessageReceipt] | None:
        """Reply passively to a received QQ command using its original message association.
        
        :param source: Original QQ command source from this runtime. Its received message supplies the passive msg_id; the source's preferred language is used.
        :param message: Plain or QQ rich text, including delayed translations evaluated before submission.
        :param refer_msg: Optional received message or receipt from the same conversation, using its reference index. This is a quoted reference, not a passive msg_id or event_id.
        :param return_future: Whether to return the submitted concurrent future; False hides the future without waiting.
        :return: A concurrent future resolving to the sent-message receipt when requested, otherwise None.
        """
        from botcraft.command.command_source import QQCommandSource
        if not isinstance(source, QQCommandSource) or source._runtime is not self._runtime:
            raise TypeError('reply requires a real QQ source from this Runtime')
        with source.preferred_language_context():
            future = self._runtime.sender.reply(source, message, refer_msg=refer_msg)
        return future if return_future else None

    def reply_event(self: Self, event: QQEvent, message: str | QTextBase, *, refer_msg: QQMessageReceived | QQMessageReceipt | None = None, return_future: bool = False) -> Future[QQMessageReceipt] | None:
        """Reply passively to a supported QQ relationship event.
        
        :param event: Original GROUP_ADD_ROBOT or GROUP_MSG_RECEIVE event whose event_id supplies the passive association.
        :param message: Plain or QQ rich text, including delayed translations evaluated before submission.
        :param refer_msg: Optional received message or receipt from the same conversation, using its reference index. This is a quoted reference, not a passive msg_id or event_id.
        :param return_future: Whether to return the submitted concurrent future; False hides the future without waiting.
        :return: A concurrent future resolving to the sent-message receipt when requested, otherwise None.
        """
        future = self._runtime.sender.reply_event(event, message, refer_msg=refer_msg)
        return future if return_future else None

    def delete_message(self: Self, message: QQMessageReceived | QQMessageReceipt, *, return_future: bool = False) -> Future[None] | None:
        """Delete a received or sent QQ message.
        
        :param message: Received message or sent receipt containing its conversation route and message ID.
        :param return_future: Whether to return the submitted concurrent future; False hides the future without waiting.
        :return: A concurrent future resolving to None when requested, otherwise None.
        """
        future = self._runtime.sender.delete_message(message)
        return future if return_future else None

    def delete_message_with_id(self: Self, target: User | Group, id: str, *, return_future: bool = False) -> Future[None] | None:
        """Delete a QQ message by route and message ID.
        
        :param target: User or group identifying the conversation.
        :param id: Message ID to delete, not a quoted-reference index.
        :param return_future: Whether to return the submitted concurrent future; False hides the future without waiting.
        :return: A concurrent future resolving to None when requested, otherwise None.
        """
        future = self._runtime.sender.delete_message_with_id(target, id)
        return future if return_future else None

    def respond_interaction(self: Self, event: QQInteraction, code: int | Enum) -> Future[None]:
        """Submit an acknowledgement for a QQ interaction.
        
        :param event: Original interaction to acknowledge.
        :param code: Integer response code from 0 through 5, or an enum with such an integer value.
        :return: A concurrent future resolving to None after the acknowledgement succeeds.
        """
        return self._runtime.sender.respond_interaction(event, code)

    def execute_command(self: Self, command: str, source: QQCommandSource) -> None:
        """Execute a registered QQ command with its actual received-message source.
        
        :param command: Command line to traverse.
        :param source: QQ source owned by this runtime; fabricated or console sources are not accepted.
        :return: No value is returned; command errors are handled by command traversal.
        """
        return self._runtime.command_manager.execute_command(command, source)

    def get_plugin_command_source(self: Self) -> NoReturn:
        """Reject plugin command-source requests, which have no supported QQ equivalent.
        
        :raises UnsupportedOperationError: A real received QQ message is required to create a command source.
        """
        raise UnsupportedOperationError('Plugin command sources are not supported')

    def schedule_task(self: Self, callable_: Callable[[], _Result] | Coroutine[Any, Any, _Result], *, block: bool = False, timeout: float | None = None) -> Future[_Result]:
        """Submit a callable or coroutine to the appropriate plugin-task executor.
        
        :param callable_: Zero-argument synchronous callable or already-created coroutine.
        :param block: Whether to wait for completion before returning the same future.
        :param timeout: Timeout in seconds for blocking waits; None waits without a timeout.
        :return: A concurrent future carrying the callable or coroutine result, also when block is True.
        """
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

    def get_event_loop(self: Self) -> AbstractEventLoop | None:
        """Get the asynchronous plugin-task executor's event loop.
        
        :return: The executor loop, or None before its initialization.
        """
        return self._runtime.async_task_executor.get_event_loop()

    def exit(self: Self) -> bool:
        """Request an orderly shutdown of this runtime.
        
        :return: True when the shutdown request is accepted, False after a stopped or failed runtime.
        """
        return self._runtime.exit()

    def is_ready(self: Self) -> bool:
        """Check whether the runtime and QQ gateway are ready.
        
        :return: Whether both services currently satisfy readiness.
        """
        return self._runtime.is_ready()

    def get_connection_state(self: Self) -> GatewayState:
        """Get the QQ gateway connection state.
        
        :return: The current gateway state.
        """
        return self._runtime.gateway.state

    def get_panel_status(self: Self, scope: Scene | str) -> PanelStatus:
        """Get the synchronization status for a QQ panel scope.
        
        :param scope: Panel scene, either group or c2c.
        :return: An immutable snapshot of the requested panel status.
        """
        return self._runtime.panel_synchronizer.get_status(scope)

    def get_permission_level(self: Self, obj: User | QQCommandSource | ConsoleSource) -> int:
        """Resolve the subject's current QQ permission level.
        
        :param obj: User or real QQ source identifying the permission subject; console sources are accepted for read-only lookup.
        :return: The effective numeric PermissionLevel value.
        """
        return self._runtime.permission_manager.get_permission(obj)

    def set_permission_level(self: Self, obj: User | QQCommandSource, level: str | int | PermissionLevelItem, *, global_scope: bool = False) -> None:
        """Set a persisted QQ permission for a verified user identity.
        
        :param obj: User or real QQ source identifying the subject.
        :param level: Permission-level name, integer, or native PermissionLevelItem.
        :param global_scope: Whether to update the identity globally instead of in its current conversation.
        :return: No value is returned.
        """
        return self._runtime.permission_manager.set_permission(obj, level, global_scope=global_scope)

    def remove_permission(self: Self, obj: User | QQCommandSource, *, global_scope: bool = False) -> None:
        """Remove a persisted QQ permission for a verified user identity.
        
        :param obj: User or real QQ source identifying the subject.
        :param global_scope: Whether to remove global rather than conversation-scoped permissions.
        :return: No value is returned.
        """
        return self._runtime.permission_manager.remove_permission(obj, global_scope=global_scope)

    def is_super_admin(self: Self, obj: User | QQCommandSource | ConsoleSource) -> bool:
        """Check whether the subject has configured super-administrator status.
        
        :param obj: User or real QQ source identifying the permission subject; console sources are accepted for read-only lookup.
        :return: Whether the user is a configured super administrator; console sources return True.
        """
        return self._runtime.permission_manager.is_super_admin(obj)

    def get_preference(self: Self, obj: User | QQCommandSource | ConsoleSource, **kwargs: bool) -> PreferenceItem:
        """Get a copy of the subject's preference, falling back to configuration defaults.
        
        :param obj: User or BotCraft command source whose preference is requested.
        :param kwargs: Native boolean options auto_add and strict_type_check; no other options are supported.
        :return: The current preference copy.
        """
        return self._runtime.preference_manager.get_preference(obj, **kwargs)

    def set_preference(self: Self, obj: User | QQCommandSource | ConsoleSource, preference: PreferenceItem) -> None:
        """Validate and persist a QQ subject's preferences.
        
        :param obj: User or BotCraft command source identifying the preference owner.
        :param preference: Native PreferenceItem with a known language or None.
        :return: No value is returned.
        """
        return self._runtime.preference_manager.set_preference(obj, preference)

    def get_default_preference(self: Self) -> PreferenceItem:
        """Create the default preference from the current runtime language.
        
        :return: A new default PreferenceItem.
        """
        return self._runtime.preference_manager.get_default_preference()

    def tr(self: Self, key: str, *args: TranslationParameter, **kwargs: TranslationParameter | LanguageFallbackHandler) -> str | QText | QMarkdown:
        """Translate and format text immediately in the selected language.
        
        :param key: Translation key to resolve.
        :param args: Positional formatting values, including QQ text and delayed translated parameters.
        :param kwargs: Named formatting values and language, allow_failure, or fallback_handler translation options.
        :return: Plain text or concrete QQ text/Markdown according to the translated parameters.
        """
        return self._runtime.translation_manager.tr(key, *args, **kwargs)

    def rtr(self, key, *args, **kwargs):
        return self._runtime.translation_manager.rtr(key, *args, **kwargs)

    def get_botcraft_language(self: Self) -> str:
        """Get the configured BotCraft language.
        
        :return: The current configuration language identifier.
        """
        return self._runtime.get_language()

    def get_botcraft_config(self: Self) -> dict[str, Any]:
        """Get a serialized snapshot of the BotCraft configuration.
        
        :return: A detached dictionary of configuration values.
        """
        return self._runtime.get_config().serialize()

    def modify_botcraft_config(self: Self, changes: Mapping[str, Any]) -> None:
        """Apply, save, and propagate BotCraft configuration changes.
        
        :param changes: Dotted configuration paths mapped to their new JSON-compatible values.
        :return: No value is returned.
        """
        self._runtime.config_manager.set_values(changes)
        self._runtime.config_manager.save()
        self._runtime.on_config_changed(log=False)

    def reload_botcraft_config_file(self: Self, *, log: bool = False) -> bool:
        """Reload BotCraft configuration from disk and notify its services.
        
        :param log: Whether configuration-change notification logs its updated state.
        :return: Whether the configuration storage reported a missing file.
        """
        return self._runtime.load_config(log=log)

    def get_plugin_list(self: Self) -> list[str]:
        """List the IDs of loaded regular QQ plugins.
        
        :return: Plugin IDs in the manager's current iteration order.
        """
        return [p.get_id() for p in self._plugin_manager.get_regular_plugins()]



    def get_plugin_metadata(self: Self, plugin_id: str) -> Metadata | None:
        """Get metadata for a loaded QQ plugin.
        
        :param plugin_id: ID of the plugin to look up.
        :return: The plugin metadata, or None if no plugin with that ID exists.
        """
        plugin = self._plugin_manager.get_plugin_from_id(plugin_id)
        return plugin.get_metadata() if plugin else None

    def _plugin_operation_thread_check(self: Self) -> None:
        if self.is_on_async_executor_thread():
            raise RuntimeError('Schedule plugin operations on the synchronous executor')
        if self._runtime.is_stopping():
            raise RuntimeNotReadyError('Runtime is stopping')

    def load_plugin(self: Self, file_path: str | PathLike[str]) -> bool:
        """Submit a QQ plugin load operation.
        
        :param file_path: Path to the plugin file or directory.
        :return: The immediate completed-operation success status; False when the operation is still pending.
        """
        from pathlib import Path
        from mcdreforged.plugin.operation_result import PluginResultType
        self._plugin_operation_thread_check()
        future = self._plugin_manager.load_plugin(Path(file_path))
        return future.result().get_if_success(PluginResultType.LOAD) if future.done() else False

    def _operate_plugin(self: Self, plugin_id: str, method: str, result_type: PluginResultType) -> bool | None:
        self._plugin_operation_thread_check()
        plugin = self._plugin_manager.get_regular_plugin_from_id(plugin_id)
        if plugin is None:
            return None
        future = getattr(self._plugin_manager, method)(plugin)
        return future.result().get_if_success(result_type) if future.done() else None

    def unload_plugin(self: Self, plugin_id: str) -> bool | None:
        """Submit a QQ plugin unload operation.
        
        :param plugin_id: ID of the loaded regular plugin to operate on.
        :return: Success status if already complete, or None when pending or the plugin ID is absent.
        """
        from mcdreforged.plugin.operation_result import PluginResultType
        return self._operate_plugin(plugin_id, 'unload_plugin', PluginResultType.UNLOAD)

    def reload_plugin(self: Self, plugin_id: str) -> bool | None:
        """Submit a QQ plugin reload operation.
        
        :param plugin_id: ID of the loaded regular plugin to operate on.
        :return: Success status if already complete, or None when pending or the plugin ID is absent.
        """
        from mcdreforged.plugin.operation_result import PluginResultType
        return self._operate_plugin(plugin_id, 'reload_plugin', PluginResultType.RELOAD)

    def enable_plugin(self: Self, file_path: str | PathLike[str]) -> bool:
        """Submit a QQ plugin enable operation.
        
        :param file_path: Path to the plugin file or directory.
        :return: The immediate completed-operation success status; False when the operation is still pending.
        """
        from pathlib import Path
        from mcdreforged.plugin.operation_result import PluginResultType
        self._plugin_operation_thread_check()
        future = self._plugin_manager.enable_plugin(Path(file_path))
        return future.result().get_if_success(PluginResultType.LOAD) if future.done() else False

    def disable_plugin(self: Self, plugin_id: str) -> bool | None:
        """Submit a QQ plugin disable operation.
        
        :param plugin_id: ID of the loaded regular plugin to operate on.
        :return: Success status if already complete, or None when pending or the plugin ID is absent.
        """
        from mcdreforged.plugin.operation_result import PluginResultType
        return self._operate_plugin(plugin_id, 'disable_plugin', PluginResultType.UNLOAD)

    def refresh_all_plugins(self: Self) -> None:
        """Refresh all regular QQ plugins through the manager.
        
        :return: No value is returned.
        """
        self._plugin_operation_thread_check()
        self._plugin_manager.refresh_all_plugins()

    def refresh_changed_plugins(self: Self) -> None:
        """Refresh only QQ plugins whose files have changed.
        
        :return: No value is returned.
        """
        self._plugin_operation_thread_check()
        self._plugin_manager.refresh_changed_plugins()

    def reload_permission_file(self: Self) -> None:
        """Reload persisted permissions without accepting a missing file.
        
        :return: No value is returned.
        """
        return self._runtime.permission_manager.load_permission_file(allowed_missing_file=False)

    def reload_preference_file(self: Self) -> None:
        """Reload preferences using the native malformed-file recovery policy.
        
        :return: No value is returned.
        """
        return self._runtime.preference_manager.load_preferences()

    def is_on_executor_thread(self: Self) -> bool:
        """Check whether the caller runs on the synchronous plugin-task executor.
        
        :return: Whether the current thread is the requested executor thread.
        """
        return self._runtime.sync_task_executor.is_on_thread()

    def is_on_async_executor_thread(self: Self) -> bool:
        """Check whether the caller runs on the asynchronous plugin-task executor.
        
        :return: Whether the current thread is the requested executor thread.
        """
        return self._runtime.async_task_executor.is_on_thread()

    def has_translation(self: Self, translation_key: str, *, language: str | None = None, no_auto_fallback: bool = False) -> bool:
        """Check whether a translation resolves under the selected fallback policy.
        
        :param translation_key: Translation key to look up.
        :param language: Explicit language, or None for the active language context.
        :param no_auto_fallback: Whether to disable automatic language fallback.
        :return: False if translation lookup raises KeyError, otherwise True.
        """
        from mcdreforged.translation.language_fallback_handler import LanguageFallbackHandler
        try:
            self._runtime.translation_manager.tr(translation_key, language=language, allow_failure=False,
                fallback_handler=LanguageFallbackHandler.none() if no_auto_fallback else LanguageFallbackHandler.auto())
        except KeyError:
            return False
        return True

    def open_bundled_file(self: Self, relative_file_path: str) -> IO[bytes]:
        """Open a file bundled with this bound directory or packed plugin.
        
        :param relative_file_path: Path relative to the plugin bundle; non-bundled interfaces raise FileNotFoundError.
        :return: An open binary file object that the caller must close.
        """
        from mcdreforged.plugin.type.multi_file_plugin import MultiFilePlugin
        plugin = getattr(self, '_plugin', None)
        if not isinstance(plugin, MultiFilePlugin):
            raise FileNotFoundError('Bundled files require a directory or packed plugin')
        return plugin.open_file(relative_file_path)

    def dispatch_event(self: Self, event: PluginEvent | str, args: tuple[object, ...] = (), *, on_executor_thread: bool = True) -> None:
        """Dispatch a custom plugin event; built-in QQ/framework events are rejected.
        
        :param event: Custom event object or event ID.
        :param args: Arguments passed after each listener's plugin interface.
        :param on_executor_thread: Whether to submit a new executor task instead of invoking listeners directly.
        :return: No value is returned.
        """
        if not isinstance(event, (str, PluginEvent)):
            raise TypeError('Expected custom event')
        event_id = event if isinstance(event, str) else event.id
        from botcraft.plugin.plugin_event import PluginEvents
        if event_id.lower().startswith('botcraft.') or PluginEvents.is_known_event(event_id) or event_id.upper() == event_id:
            raise UnsupportedOperationError('Cannot manually dispatch built-in events')
        policy = self._plugin_manager.DispatchEventPolicy.always_new_task if on_executor_thread else self._plugin_manager.DispatchEventPolicy.directly_invoke
        self._plugin_manager.dispatch_event(LiteralEvent(event_id), args, dispatch_policy=policy)

    def _unsupported(self: Self, *args: object, **kwargs: object) -> NoReturn:
        """Reject a Minecraft/MCDR host operation without a QQ equivalent.
        
        :param args: Positional arguments of the requested unsupported host operation.
        :param kwargs: Keyword arguments of the requested unsupported host operation.
        :raises UnsupportedOperationError: No supported QQ operation is performed.
        """
        raise UnsupportedOperationError('Minecraft/MCDR host operation has no QQ equivalent')

    start = stop = kill = restart = execute = execute_async = _unsupported
    get_pid = get_server_pid = get_server_information = get_server_version = _unsupported
    is_server_running = is_server_startup = is_server_rcon_ready = _unsupported
    rcon_query = connect_rcon = disconnect_rcon = register_server_handler = register_info_filter = _unsupported
    get_mcdr_config = modify_mcdr_config = reload_config_file = get_mcdr_language = _unsupported
    wait_until_stop = wait_for_start = stop_exit = set_exit_after_stop_flag = _unsupported
    is_rcon_running = get_server_pid_all = _unsupported
