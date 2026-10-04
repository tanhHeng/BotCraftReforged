from pathlib import Path
from mcdreforged.constants import plugin_constant
from .type.solo_plugin import SoloPlugin
from .type.directory_plugin import DirectoryPlugin
from .type.packed_plugin import PackedPlugin

PLUGIN_META_FILE = 'botcraft.plugin.json'

def _class(path, allow_disabled=False):
    path = Path(path)
    if path.is_file():
        name = path.name[:-len(plugin_constant.DISABLED_PLUGIN_FILE_SUFFIX)] if allow_disabled and path.name.endswith(plugin_constant.DISABLED_PLUGIN_FILE_SUFFIX) else path.name
        if name.endswith(plugin_constant.SOLO_PLUGIN_FILE_SUFFIX): return SoloPlugin
        if any(name.endswith(suffix) for suffix in plugin_constant.PACKED_PLUGIN_FILE_SUFFIXES): return PackedPlugin
    elif path.is_dir() and (allow_disabled or not path.name.endswith(plugin_constant.DISABLED_PLUGIN_FILE_SUFFIX)):
        if (path / PLUGIN_META_FILE).is_file() and not (path / '__init__.py').is_file(): return DirectoryPlugin
    return None

def is_plugin(path): return _class(path, False) is not None

def is_disabled_plugin(path): return _class(path, False) is None and _class(path, True) is not None

def create_regular_plugin(plugin_manager, path):
    cls = _class(path, False)
    if cls is None: raise TypeError(f'Trying to create a regular plugin with invalid path {path}')
    return cls(plugin_manager, Path(path))

