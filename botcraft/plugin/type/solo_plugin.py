from mcdreforged.plugin.type.solo_plugin import SoloPlugin as NativeSoloPlugin
from botcraft.plugin._native import bind_native
from botcraft.plugin.meta.metadata import Metadata
from .regular_plugin import RegularPlugin


class SoloPlugin(RegularPlugin, NativeSoloPlugin):
    """Native solo import/metadata flow, independent QQ plugin record."""
    def __init__(self, plugin_manager, file_path):
        super().__init__(plugin_manager, file_path)
        self.module_name = f'BOTCRAFT_SOLO_PLUGIN@{self.plugin_path}'

    _on_load = bind_native(NativeSoloPlugin._on_load, globals={'Metadata': Metadata})
