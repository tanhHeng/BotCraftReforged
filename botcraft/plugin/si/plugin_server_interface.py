from __future__ import annotations

from typing import TYPE_CHECKING
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.plugin.type.plugin import Plugin
    from botcraft.runtime import Runtime

from mcdreforged.plugin.si.plugin_server_interface import PluginServerInterface
from botcraft.plugin.si.qq_server_interface_mixin import ServerInterfaceMixin


class QQPluginServerInterface(ServerInterfaceMixin, PluginServerInterface):
    def __init__(self: Self, runtime: Runtime, plugin: Plugin) -> None:
        """Bind a QQ server interface to a plugin record.
        
        :param runtime: Runtime providing QQ services for this plugin.
        :param plugin: Plugin record used for registrations, metadata, and logging.
        :return: No value is returned.
        """
        ServerInterfaceMixin.__init__(self, runtime)
        self._plugin = plugin
