from mcdreforged.plugin.type.directory_plugin import DirectoryPlugin as NativeDirectoryPlugin
from .multi_file_plugin import MultiFilePlugin


class DirectoryPlugin(MultiFilePlugin, NativeDirectoryPlugin):
    """Native directory methods with metadata paths adapted by MultiFilePlugin."""
