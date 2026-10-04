from botcraft.bootstrap import generate_default
from botcraft.runtime_args import RuntimeArgs


def generate_default_stuffs(*, config_file_path: str, permission_file_path: str, quiet: bool = False) -> None:
    generate_default(RuntimeArgs(
        generate_default_only=True, config_file_path=config_file_path, permission_file_path=permission_file_path))
    if not quiet:
        print('Generated default configuration {!r} and permissions {!r}'.format(config_file_path, permission_file_path))
