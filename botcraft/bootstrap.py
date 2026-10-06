"""Prepare local deployment files without creating a Runtime or opening a connection."""
from typing import Any
from botcraft.config import Config
import logging
from importlib.resources import files
from pathlib import Path

from ruamel.yaml import YAML

from botcraft.runtime_args import RuntimeArgs


def _write_template(path: str, resource: str, *, overwrite: bool) -> bool:
    destination = Path(path)
    if not overwrite and destination.exists():
        if not destination.is_file():
            raise IsADirectoryError(str(destination))
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    template = files('botcraft').joinpath('resources', resource).read_text(encoding='utf8')
    with destination.open('w' if overwrite else 'x', encoding='utf8', newline='\n') as stream:
        stream.write(template)
    return True


def generate_default(args: RuntimeArgs) -> None:
    """Explicitly replace selected configuration and permission files with bundled defaults.
    
    :param args: Deployment paths and initialization options.
    :return: No return value.
    """
    _write_template(args.config_file_path, 'default_config.yml', overwrite=True)
    _write_template(args.permission_file_path, 'default_permission.yml', overwrite=True)


def read_validated_config(path: str, *, logger: logging.Logger | None = None) -> tuple[dict[str, Any], Config]:
    """Read and validate configuration without repair or disk writes.
    
    :param path: Configuration YAML file to read.
    :param logger: Validation logger, or a bootstrap logger when omitted.
    :return: Original YAML mapping and the validated configuration.
    """
    from botcraft.config import ConfigManager
    with open(path, encoding='utf8') as stream:
        try:
            data = YAML(typ='safe').load(stream)
        except Exception:
            raise ValueError('Invalid BotCraft configuration YAML') from None
    manager = ConfigManager(logger or logging.getLogger('BotCraft.bootstrap'), path)
    config = manager.validate(data)
    return data, config


def initialize_environment(args: RuntimeArgs) -> None:
    """Create missing deployment files and configured plugin, data and log directories.
    
    :param args: Deployment paths and initialization options.
    :return: No return value.
    """
    _write_template(args.config_file_path, 'default_config.yml', overwrite=False)
    _write_template(args.permission_file_path, 'default_permission.yml', overwrite=False)
    _, config = read_validated_config(args.config_file_path)
    for path in (*config.plugin_directories, 'config/botcraft', 'logs'):
        Path(path).mkdir(parents=True, exist_ok=True)


def prepare_environment(args: RuntimeArgs) -> None:
    """Require deployment files unless automatic initialization was selected.
    
    :param args: Deployment paths and initialization options.
    :return: No return value.
    """
    if args.auto_init:
        initialize_environment(args)
    for label, path in (('configuration', args.config_file_path), ('permission', args.permission_file_path)):
        if not Path(path).is_file():
            raise FileNotFoundError(
                'Missing {} file {!r}; run botcraft init or select start --auto-init'.format(label, path)
            )
