"""AbstractPlugin adapter: ownership and host-bound registration/event paths."""
from mcdreforged.plugin.type.plugin import AbstractPlugin
from mcdreforged.plugin.type.common import PluginState
from mcdreforged.plugin.plugin_event import EventListener
from botcraft.plugin.plugin_event import normalize_event_id
from botcraft.plugin.plugin_registry import PluginRegistry
from botcraft.utils.exception import UnsupportedOperationError


class Plugin(AbstractPlugin):
    def __init__(self, plugin_manager):
        # Do not call AbstractPlugin.__init__: it requires a real MCDR host.
        self.plugin_manager = plugin_manager
        self.runtime = plugin_manager.runtime
        self.state = PluginState.UNINITIALIZED
        self.plugin_registry = PluginRegistry(self, plugin_manager.registry_storage)
        from botcraft.plugin.si.plugin_server_interface import QQPluginServerInterface
        self.server_interface = QQPluginServerInterface(self.runtime, self)

    @property
    def logger(self):
        return self.runtime.logger

    def _check_state(self):
        self.assert_state({PluginState.LOADED, PluginState.READY}, 'Only loaded or ready plugins may register')


    def register_event_listener(self, event, listener):
        self._check_state()
        self.plugin_registry.register_event_listener(normalize_event_id(event), listener)

    def register_command(self, node, *, allow_duplicates=False, scope=('group', 'c2c')):
        self._check_state()
        self.plugin_registry.register_command(node, allow_duplicates, scope)

    def register_help_message(self, help_message):
        self._check_state()
        self.plugin_registry.register_help_message(help_message)

    def register_translation(self, language, mapping):
        self._check_state()
        self.plugin_registry.register_translation(language, mapping)

    def register_server_handler(self, *_args, **_kwargs):
        raise UnsupportedOperationError('QQ plugins cannot register server handlers')

    def register_info_filter(self, *_args, **_kwargs):
        raise UnsupportedOperationError('QQ plugins cannot register info filters')

    def get_plugin_command_source(self):
        raise UnsupportedOperationError('QQ plugins have no plugin command source')

    def receive_event(self, event, args):
        self.assert_state({PluginState.READY})
        for listener in self.plugin_registry.get_event_listeners(normalize_event_id(event)):
            try:
                self.plugin_manager.trigger_listener(listener, args).result()
            except Exception:
                self.runtime.logger.exception('Direct listener triggering failed: plugin %s, event %s, listener %s', self, event, listener)


