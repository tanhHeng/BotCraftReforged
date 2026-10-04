"""Process entrypoint; imports no runtime services until a start is requested."""
import sys


def entrypoint() -> None:
    from botcraft.cli.cli_entry import cli_dispatch
    try:
        status = cli_dispatch()
    except KeyboardInterrupt:
        status = 130
    except Exception as error:
        # Configuration deserialization sanitizes credentials before raising.
        print('BotCraft: {}'.format(error), file=sys.stderr)
        status = 1
    raise SystemExit(status)
