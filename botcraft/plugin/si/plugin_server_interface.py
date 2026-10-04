from mcdreforged.plugin.si.plugin_server_interface import PluginServerInterface
from botcraft.plugin.si.qq_server_interface_mixin import ServerInterfaceMixin


class QQPluginServerInterface(ServerInterfaceMixin, PluginServerInterface):
    def __init__(self, runtime, plugin):
        ServerInterfaceMixin.__init__(self, runtime)
        self._plugin = plugin
