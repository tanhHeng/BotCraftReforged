from mcdreforged.plugin.si.server_interface import ServerInterface
from botcraft.plugin.si.qq_server_interface_mixin import ServerInterfaceMixin


class QQServerInterface(ServerInterfaceMixin, ServerInterface):
    """QQ implementation of the MCDR interface contract without MCDR host initialization."""
