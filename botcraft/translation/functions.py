"""Public translation helpers use only the standalone BotCraft interface."""
def tr(key, *args, **kwargs):
    from botcraft.plugin.si.server_interface import QQServerInterface
    return QQServerInterface.si().tr(key, *args, **kwargs)


def rtr(key, *args, **kwargs):
    from botcraft.plugin.si.server_interface import QQServerInterface
    return QQServerInterface.si().rtr(key, *args, **kwargs)
