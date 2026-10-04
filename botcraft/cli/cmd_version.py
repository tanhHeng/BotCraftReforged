from botcraft.constants.core_constant import VERSION


def show_version(*, quiet: bool = False) -> None:
    print(VERSION if quiet else 'BotCraft {}'.format(VERSION))
