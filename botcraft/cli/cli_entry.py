"""CLI argument parsing, shared by installed console scripts and python -m."""
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from typing import Optional, Sequence

from botcraft.runtime_args import RuntimeArgs


def cli_dispatch(argv: Optional[Sequence[str]] = None) -> int:
    """Parse and dispatch a standalone BotCraft deployment, packaging or runtime command.
    
    :param argv: Command-line arguments, or the process arguments when omitted.
    :return: Zero after successful command dispatch; parser and command failures raise.
    """
    parser = ArgumentParser(prog='botcraft', description='BotCraft QQ bot framework',
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('-V', '--version', action='store_true', help='Print version and exit')
    subparsers = parser.add_subparsers(dest='command', title='Commands')

    def config_paths(subparser: ArgumentParser) -> None:
        subparser.add_argument('--config', default='config.yml', metavar='CONFIG_FILE',
                               help='Path to the BotCraft configuration file')
        subparser.add_argument('--permission', default='permissions.yml', metavar='PERMISSION_FILE',
                               help='Path to the permission file')

    for name, help_text in (
        ('init', 'Create missing deployment files and directories (never connect to QQ)'),
        ('gen-default', 'Overwrite the selected configuration and permission files with defaults'),
    ):
        subparser = subparsers.add_parser(name, help=help_text,
                                         formatter_class=ArgumentDefaultsHelpFormatter)
        config_paths(subparser)

    subparsers.add_parser('version', help='Print BotCraft version')
    start = subparsers.add_parser('start', help='Start the QQ runtime',
                                 formatter_class=ArgumentDefaultsHelpFormatter)
    config_paths(start)
    start.add_argument('--auto-init', action='store_true', help='Create missing deployment files before starting')
    start.add_argument('--check-capabilities', action='store_true', help='Force isolated local capability checks')

    pack = subparsers.add_parser('pack', help='Pack a directory plugin using native MCDR archive conventions',
                                formatter_class=ArgumentDefaultsHelpFormatter)
    pack.add_argument('-i', '--input', default='.', help='Plugin input directory')
    pack.add_argument('-o', '--output', default='.', help='Output directory')
    pack.add_argument('-n', '--name', help='Archive name (supports {id} and {version})')
    pack.add_argument('--ignore-patterns', nargs='+', default=[], metavar='IGNORE_PATTERN',
                      help='Gitignore-style patterns overriding --ignore-file')
    pack.add_argument('--ignore-file', default='.gitignore', help='UTF-8 ignore file relative to input directory')
    pack.add_argument('--shebang', help='Interpreter line, for example /usr/bin/env python3')

    reformat = subparsers.add_parser('reformat-config', help='Validate and reformat configuration without starting QQ')
    reformat.add_argument('-i', '--input', required=True, help='Input configuration file')
    reformat.add_argument('-o', '--output', help='Output configuration file (defaults to input)')

    args = parser.parse_args(argv)
    if args.version or args.command == 'version':
        from botcraft.cli.cmd_version import show_version
        show_version()
    elif args.command == 'gen-default':
        from botcraft.cli.cmd_gendefault import generate_default_stuffs
        generate_default_stuffs(config_file_path=args.config, permission_file_path=args.permission)
    elif args.command == 'init':
        from botcraft.cli.cmd_init import initialize_environment
        initialize_environment(config_file_path=args.config, permission_file_path=args.permission)
    elif args.command == 'pack':
        from botcraft.cli.cmd_pack import make_packed_plugin
        make_packed_plugin(args)
    elif args.command == 'reformat-config':
        from botcraft.cli.cmd_reformat_config import reformat_config
        reformat_config(args.input, args.output)
    else:
        from botcraft.cli.cmd_start import run_botcraft
        runtime_args = RuntimeArgs() if args.command is None else RuntimeArgs(
            auto_init=args.auto_init, config_file_path=args.config,
            permission_file_path=args.permission, check_capabilities=args.check_capabilities)
        run_botcraft(runtime_args)
    return 0
