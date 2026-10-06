from __future__ import annotations
from typing import TYPE_CHECKING
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.plugin.plugin_manager import PluginManager
from pathlib import Path
from mcdreforged.plugin.type.packed_plugin import PackedPlugin as NativePackedPlugin
from botcraft.plugin._native import bind_native
from .multi_file_plugin import MultiFilePlugin


class PackedPlugin(MultiFilePlugin, NativePackedPlugin):
    """Native archive cache, SHA256, resources and zip-import cleanup."""
    def __init__(self: Self, plugin_manager: PluginManager, file_path: str | Path) -> None:
        """Initialize a plugin record for its native file format.
        
        :param plugin_manager: Manager owning the record.
        :param file_path: Plugin file to load.
        :return: No value is returned.
        """
        super().__init__(plugin_manager, file_path)
        self._PackedPlugin__zip_file_cache = None
        self._PackedPlugin__file_sha256 = None


# Native super() closures must advance through the QQ adapter rather than
# bypassing it into the host-bound native MultiFilePlugin._on_unload.
PackedPlugin._reset = bind_native(NativePackedPlugin._reset, owner=PackedPlugin)
PackedPlugin._on_unload = bind_native(NativePackedPlugin._on_unload, runtime=True, owner=PackedPlugin)
PackedPlugin._load_entry_instance = bind_native(NativePackedPlugin._load_entry_instance, owner=PackedPlugin)
