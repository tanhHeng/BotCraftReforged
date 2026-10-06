from pathlib import Path

from botcraft.bootstrap import initialize_environment as bootstrap_initialize
from botcraft.runtime_args import RuntimeArgs


def initialize_environment(*, config_file_path: str, permission_file_path: str, quiet: bool = False) -> None:
    """Create missing deployment files and directories without connecting to QQ.
    
    :param config_file_path: Selected configuration YAML path.
    :param permission_file_path: Selected permission YAML path.
    :param quiet: Whether to suppress initialization status output.
    :return: No return value.
    """
    bootstrap_initialize(RuntimeArgs(
        initialize_environment=True, config_file_path=config_file_path, permission_file_path=permission_file_path))
    if not quiet:
        print('Initialized BotCraft environment in {}'.format(Path.cwd()))
        print('Existing files were preserved. Configure appid and secret before starting.')
