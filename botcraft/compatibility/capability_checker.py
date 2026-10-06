"""Version-keyed checks of the installed BotCraft runtime, never user plugins."""
from botcraft.logging.logger import Logger
import json
import os
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from mcdreforged.utils.file_utils import safe_write

from botcraft.constants.core_constant import VERSION


_REPORT_PREFIX = 'BOTCRAFT_CAPABILITY_REPORT='
_CACHE_PATH = Path('config/botcraft/capabilities.json')


class CapabilityCheckError(RuntimeError):
    """The installed runtime cannot provide a required local capability."""


def check_capabilities(logger: Logger, force: bool = False) -> None:
    """Run packaged probes in an isolated subprocess or reuse matching versions.
    
    Only successful, fully cleaned reports are cached by BotCraft and MCDR versions.
    
    :param logger: Runtime logger receiving subprocess diagnostics.
    :param force: Ignore the version cache and run the probes again.
    :return: No value is returned.
    """
    versions = {'botcraft': VERSION, 'mcdr': version('mcdreforged')}
    cache_path = _CACHE_PATH.absolute()
    if not force:
        try:
            cached = json.loads(cache_path.read_text(encoding='utf8'))
        except (OSError, ValueError, UnicodeError):
            pass
        else:
            if isinstance(cached, dict) and cached == versions:
                return

    # A failed forced check must not leave a previous success reusable.
    try:
        cache_path.unlink(missing_ok=True)
    except OSError as error:
        logger.warning('Cannot remove the old capability cache; this check will not reuse it: %s', error)

    logger.info('Checking local BotCraft capabilities (BotCraft %s, MCDR %s)', versions['botcraft'], versions['mcdr'])
    env = os.environ.copy()
    # Works both from a checkout and an installed wheel. Use the package root,
    # not the caller's cwd or any tests directory, in the isolated process.
    package_root = str(Path(__file__).resolve().parents[2])
    env['PYTHONPATH'] = package_root + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    try:
        with TemporaryDirectory(prefix='botcraft-capabilities-') as directory:
            completed = subprocess.run(
                [sys.executable, '-m', 'botcraft.compatibility.probes'],
                cwd=directory, env=env, capture_output=True, text=True,
                encoding='utf8', errors='replace', timeout=180,
            )
            reports = [line[len(_REPORT_PREFIX):] for line in completed.stdout.splitlines() if line.startswith(_REPORT_PREFIX)]
            try:
                report = json.loads(reports[-1]) if reports else None
            except ValueError:
                report = None
            if (completed.returncode != 0 or not isinstance(report, dict)
                    or report.get('ok') is not True or report.get('stage') != 'cleaned'):
                stage = report.get('stage', 'subprocess') if isinstance(report, dict) else 'subprocess'
                detail = report.get('error', 'No complete probe report') if isinstance(report, dict) else 'No complete probe report'
                diagnostics = report.get('traceback', '') if isinstance(report, dict) else completed.stdout + '\n' + completed.stderr
                logger.error('Capability check failed at %s (BotCraft %s, MCDR %s): %s\n%s',
                             stage, versions['botcraft'], versions['mcdr'], detail, diagnostics)
                raise CapabilityCheckError('Capability check failed at {}: {}'.format(stage, detail))
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.error('Capability check subprocess failed (BotCraft %s, MCDR %s): %s', versions['botcraft'], versions['mcdr'], error)
        raise CapabilityCheckError('Capability check subprocess failed: {}'.format(error)) from error

    # Both child runtime cleanup and parent temporary-directory cleanup precede
    # the checkpoint. A read-only working directory does not negate a pass.
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with safe_write(cache_path, encoding='utf8') as stream:
            json.dump(versions, stream, ensure_ascii=False, sort_keys=True)
            stream.write('\n')
    except OSError as error:
        logger.warning('Capabilities passed, but the success cache could not be written: %s', error)
    logger.info('Local BotCraft capabilities passed; QQ platform/network acceptance is not covered')
