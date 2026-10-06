"""Native multi-file requirements/resources/import mechanisms, QQ coupling only."""
from typing_extensions import Self
import sys
from mcdreforged.plugin.type.multi_file_plugin import MultiFilePlugin as NativeMultiFilePlugin
from botcraft.constants import plugin_constant
from botcraft.plugin._native import bind_native
from botcraft.plugin.meta.metadata import Metadata
from .regular_plugin import RegularPlugin


class MultiFilePlugin(RegularPlugin, NativeMultiFilePlugin):
    _load_structure = bind_native(NativeMultiFilePlugin._on_load, runtime=True, globals={'plugin_constant': plugin_constant, 'Metadata': Metadata})
    _import_entrypoint_module = bind_native(NativeMultiFilePlugin._import_entrypoint_module, runtime=True)
    _MultiFilePlugin__check_requirements = bind_native(NativeMultiFilePlugin._MultiFilePlugin__check_requirements, runtime=True)
    _MultiFilePlugin__register_default_translation = bind_native(NativeMultiFilePlugin._MultiFilePlugin__register_default_translation, runtime=True)

    def _on_load(self: Self) -> None:
        self._load_structure()
        # Import failure participates in native load/reload failure isolation,
        # instead of the native ready hook swallowing it and reporting READY.
        sys.path.append(self._module_search_path)
        self._load_entry_instance()

    def _on_ready(self: Self) -> None:
        self._register_default_listeners()
        self._MultiFilePlugin__register_default_translation()

    def _on_unload(self: Self) -> None:
        RegularPlugin._on_unload(self)
        try:
            sys.path.remove(self._module_search_path)
        except ValueError:
            self.runtime.logger.debug('Plugin search path already removed: %s', self._module_search_path)
