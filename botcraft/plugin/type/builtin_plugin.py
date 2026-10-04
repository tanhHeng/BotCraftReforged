from mcdreforged.plugin.type.builtin_plugin import BuiltinPlugin as NativeBuiltinPlugin
from mcdreforged.plugin.builtin.python_plugin import PythonPlugin as NativePythonPlugin, METADATA
from botcraft.constants.core_constant import VERSION
from botcraft.plugin.meta.metadata import Metadata
from .plugin import Plugin


class BuiltinPlugin(Plugin, NativeBuiltinPlugin):
    def __init__(self, plugin_manager, metadata_dict):
        Plugin.__init__(self, plugin_manager)
        self._BuiltinPlugin__metadata = Metadata(metadata_dict, plugin=self)


class CorePlugin(BuiltinPlugin):
    def __init__(self, plugin_manager):
        super().__init__(plugin_manager, {'id': 'botcraft', 'version': VERSION, 'name': 'BotCraft', 'dependencies': {'python': '*'}})

    def load(self):
        from botcraft.plugin.builtin.botcraft import register
        self.runtime.builtin_command_root = register(self.server_interface)


class PythonPlugin(BuiltinPlugin, NativePythonPlugin):
    def __init__(self, plugin_manager):
        BuiltinPlugin.__init__(self, plugin_manager, METADATA)

    def load(self):
        self.runtime.logger.info('Python runtime: %s', self.get_meta_name())
