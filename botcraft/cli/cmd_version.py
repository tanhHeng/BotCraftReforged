from botcraft.constants.core_constant import VERSION


def show_version(*, quiet: bool = False) -> None:
    """Print the standalone BotCraft version.
    
    :param quiet: Whether to print only the version without the product name.
    :return: No return value.
    """
    print(VERSION if quiet else 'BotCraft {}'.format(VERSION))
