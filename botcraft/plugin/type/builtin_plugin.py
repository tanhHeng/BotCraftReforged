from __future__ import annotations
from typing import TYPE_CHECKING
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.plugin.plugin_manager import PluginManager
from typing import Any
from mcdreforged.plugin.type.builtin_plugin import BuiltinPlugin as NativeBuiltinPlugin
from mcdreforged.plugin.builtin.python_plugin import PythonPlugin as NativePythonPlugin, METADATA
from botcraft.constants.core_constant import VERSION
from botcraft.plugin.meta.metadata import Metadata
from .plugin import Plugin


class BuiltinPlugin(Plugin, NativeBuiltinPlugin):
    def __init__(self: Self, plugin_manager: PluginManager, metadata_dict: dict[str, Any]) -> None:
        """Initialize a built-in plugin from native metadata fields.
        
        :param plugin_manager: Manager owning the record.
        :param metadata_dict: Metadata fields with open JSON-compatible values.
        :return: No value is returned.
        """
        Plugin.__init__(self, plugin_manager)
        self._BuiltinPlugin__metadata = Metadata(metadata_dict, plugin=self)


class CorePlugin(BuiltinPlugin):
    def __init__(self: Self, plugin_manager: PluginManager) -> None:
        """Initialize the BotCraft administration plugin.
        
        :param plugin_manager: Manager owning the record.
        :return: No value is returned.
        """
        super().__init__(plugin_manager, {'id': 'botcraft', 'version': VERSION, 'name': 'BotCraft', 'dependencies': {'python': '*'}})

    def load(self: Self) -> None:
        """Register the BotCraft administration commands.
        
        :return: No value is returned.
        """
        from botcraft.plugin.builtin.botcraft import register
        self.runtime.builtin_command_root = register(self.server_interface)


class PythonPlugin(BuiltinPlugin, NativePythonPlugin):
    def __init__(self: Self, plugin_manager: PluginManager) -> None:
        """Initialize the native Python runtime plugin record.
        
        :param plugin_manager: Manager owning the record.
        :return: No value is returned.
        """
        BuiltinPlugin.__init__(self, plugin_manager, METADATA)

    def load(self: Self) -> None:
        """Log the available Python runtime plugin.
        
        :return: No value is returned.
        """
        self.runtime.logger.info('Python runtime: %s', self.get_meta_name())
