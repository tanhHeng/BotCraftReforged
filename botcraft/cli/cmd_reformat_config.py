"""Validate first, then use the native default-template merge and YAML writer."""
from pathlib import Path

from mcdreforged.utils.yaml_data_storage import YamlDataStorage
from ruamel.yaml import YAML

from botcraft.bootstrap import read_validated_config
from botcraft.config import load_resource_yaml


def reformat_config(input_path: str, output_path=None, *, quiet: bool = False) -> None:
    data, _ = read_validated_config(input_path)
    formatted = load_resource_yaml('resources/default_config.yml')
    YamlDataStorage.merge_dict(data, formatted)
    destination = Path(output_path if output_path is not None else input_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    yaml = YAML()
    yaml.width = 1048576
    with destination.open('w', encoding='utf8') as stream:
        yaml.dump(formatted, stream)
    if not quiet:
        print('Reformatted configuration {!r} to {!r}'.format(input_path, str(destination)))
