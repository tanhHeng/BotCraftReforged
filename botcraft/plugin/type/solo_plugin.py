from __future__ import annotations
from typing import TYPE_CHECKING
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.plugin.plugin_manager import PluginManager
from pathlib import Path
from mcdreforged.plugin.type.solo_plugin import SoloPlugin as NativeSoloPlugin
from botcraft.plugin._native import bind_native
from botcraft.plugin.meta.metadata import Metadata
from .regular_plugin import RegularPlugin


class SoloPlugin(RegularPlugin, NativeSoloPlugin):
    """Native solo import/metadata flow, independent QQ plugin record."""
    def __init__(self: Self, plugin_manager: PluginManager, file_path: str | Path) -> None:
        """Initialize a plugin record for its native file format.
        
        :param plugin_manager: Manager owning the record.
        :param file_path: Plugin file to load.
        :return: No value is returned.
        """
        super().__init__(plugin_manager, file_path)
        self.module_name = f'BOTCRAFT_SOLO_PLUGIN@{self.plugin_path}'

    _on_load = bind_native(NativeSoloPlugin._on_load, globals={'Metadata': Metadata})
