"""Native logging and rotation with an independent name, QQ redaction and color formatting."""
import json
import logging
import re
from threading import RLock
from colorlog import ColoredFormatter
from mcdreforged.logging.logger import MCDReforgedLogger
from mcdreforged.logging.formatter import PluginIdAwareFormatter, NoColorFormatter


class Logger(MCDReforgedLogger):
    DEFAULT_NAME = 'BotCraft'
    CONSOLE_FORMATTER = PluginIdAwareFormatter(
        ColoredFormatter,
        '[%(name)s] [%(asctime)s] [%(threadName)s/%(log_color)s%(levelname)s%(reset)s] [%(plugin_id)s]: %(message)s',
        datefmt='%H:%M:%S', log_colors=MCDReforgedLogger.LOG_COLORS,
    )
    PLAIN_CONSOLE_FORMATTER = PluginIdAwareFormatter(
        NoColorFormatter,
        '[%(name)s] [%(asctime)s] [%(threadName)s/%(levelname)s] [%(plugin_id)s]: %(message)s',
        datefmt='%H:%M:%S',
    )

    def setLevel(self, level):
        super().setLevel(level)
        # Directly constructed native loggers are absent from logging.manager's cache sweep.
        self._cache.clear()

    def set_console_color(self, enabled):
        self.console_handler.setFormatter(self.CONSOLE_FORMATTER if enabled else self.PLAIN_CONSOLE_FORMATTER)

    def set_debug_options(self, debug_options):
        super().set_debug_options({key: value for key, value in debug_options.items() if key != 'raw_response'})


class SecretFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.secrets = set()
        self._lock = RLock()

    def add(self, value):
        if value:
            with self._lock:
                self.secrets.add(str(value))

    def _sanitize(self, text):
        with self._lock:
            secrets = sorted(self.secrets, key=len, reverse=True)
        for secret in secrets:
            text = text.replace(secret, '<redacted>')
        text = re.sub(r'(?i)((?:access_token|auth_token|clientSecret|secret|authorization)[\"\']?\s*[=:]\s*[\"\']?)[^\s,;\"\'\]}]+', r'\1<redacted>', text)
        text = re.sub(r'(?i)(QQBot\s+|Bearer\s+)[^\s,;\"\']+', r'\1<redacted>', text)
        return text

    def sanitize_response(self, body):
        if isinstance(body, bytes):
            body = body.decode('utf8', errors='replace')
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            data = body

        def redact(value):
            if isinstance(value, dict):
                return {key: '<redacted>' if key.lower() in {
                    'access_token', 'auth_token', 'token', 'clientsecret', 'client_secret',
                    'secret', 'authorization', 'session_id',
                } else redact(item) for key, item in value.items()}
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, str):
                if value.startswith(('ws://', 'wss://')):
                    return '<redacted>'
                return self._sanitize(value)
            return value

        rendered = json.dumps(redact(data), ensure_ascii=False, separators=(',', ':'))
        return rendered.translate({code: repr(chr(code))[1:-1] for code in (*range(127, 160), 0x2028, 0x2029)})

    def filter(self, record):
        record.msg, record.args = self._sanitize(record.getMessage()), ()
        if record.exc_info:
            record.exc_text = self._sanitize(logging.Formatter().formatException(record.exc_info))
        return True


def log_raw_response(runtime, origin, body, *, operation=None, http_code=None):
    if not runtime.get_config().debug.get('raw_response', False):
        return
    rendered = runtime.logger.secret_filter.sanitize_response(body)
    if http_code is None:
        runtime.logger.debug('Raw response [%s] %s', origin, rendered)
    else:
        runtime.logger.debug('Raw response [%s] [%s] [http_code:%s] %s', origin, operation, http_code, rendered)


def create_logger(name='BotCraft', *, log_directory=None, debug=False):
    logger = Logger()
    logger.name = name
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.secret_filter = SecretFilter()
    logger.console_handler.addFilter(logger.secret_filter)
    if log_directory is not None:
        from pathlib import Path
        logger.set_file(str(Path(log_directory) / 'botcraft.log'))
        logger.file_handler.addFilter(logger.secret_filter)
    return logger


def plugin_logger(logger, plugin_id):
    child = Logger(plugin_id)
    child.setLevel(logger.level)
    child.removeHandler(child.console_handler)
    child.console_handler = logger.console_handler
    for handler in logger.handlers:
        child.addHandler(handler)
    child.secret_filter = logger.secret_filter
    return child
