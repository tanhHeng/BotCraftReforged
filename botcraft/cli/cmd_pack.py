"""Reuse MCDR 2.14.4's pack implementation with a private filename binding.

The upstream function has no metadata-path parameter. A separate globals mapping
changes that one dependency for this callable only: the native module, constants,
and every other caller remain untouched. Ignore traversal, Metadata, resources,
requirements, archive naming and shebang handling all remain native.
"""
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

from mcdreforged.cli import cmd_pack as native_pack
from mcdreforged.cli.cmd_pack import PackArgs, read_ignore_file
from mcdreforged.plugin.meta.metadata import Metadata
import pathspec

from botcraft.constants import plugin_constant


class _InputRelativeIgnore:
    def __init__(self, spec, root):
        self.spec = spec
        self.root = root.resolve()

    def match_file(self, path):
        candidate = Path(path)
        relative = candidate.resolve().relative_to(self.root).as_posix()
        if candidate.is_dir():
            relative += '/'
        return self.spec.match_file(relative)


def _bind_native_packer(input_dir: Path):
    def from_lines(lines):
        return _InputRelativeIgnore(pathspec.GitIgnoreSpec.from_lines(lines), input_dir)

    def load_ignore(path, writeln):
        spec = read_ignore_file(path, writeln)
        return _InputRelativeIgnore(spec if spec is not None else pathspec.GitIgnoreSpec.from_lines([]), input_dir)

    original = native_pack.make_packed_plugin
    bindings = dict(original.__globals__, plugin_constant=plugin_constant,
                    pathspec=SimpleNamespace(GitIgnoreSpec=SimpleNamespace(from_lines=from_lines)),
                    read_ignore_file=load_ignore)
    bound = FunctionType(original.__code__, bindings, original.__name__, original.__defaults__, original.__closure__)
    bound.__kwdefaults__ = original.__kwdefaults__.copy() if original.__kwdefaults__ else None
    return bound


def make_packed_plugin(args: PackArgs, *, quiet: bool = False) -> None:
    # Native mkdir is non-recursive; a deployment output may have missing parents.
    if not Path(args.input).is_dir():
        raise NotADirectoryError(args.input)
    if not (Path(args.input) / plugin_constant.PLUGIN_META_FILE).is_file():
        raise FileNotFoundError(str(Path(args.input) / plugin_constant.PLUGIN_META_FILE))
    metadata_path = Path(args.input) / plugin_constant.PLUGIN_META_FILE
    with metadata_path.open(encoding='utf8') as stream:
        Metadata(json.load(stream))
    Path(args.output).mkdir(parents=True, exist_ok=True)
    _bind_native_packer(Path(args.input))(args, quiet=quiet)
