import threading
from mcdreforged.executor.background_thread_executor import BackgroundThreadExecutor


class ConsoleHandler(BackgroundThreadExecutor):
    def __init__(self, runtime):
        super().__init__(runtime.logger)
        self.runtime = runtime
        self.set_name('Console')
        self._session = None

    def loop(self):
        if self.runtime.config.advanced_console:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.patch_stdout import patch_stdout
            self._session = PromptSession()
            with patch_stdout():
                super().loop()
        else:
            super().loop()

    def tick(self):
        try:
            text = self._session.prompt('botcraft> ') if self._session is not None else input()
        except (EOFError, KeyboardInterrupt):
            self.runtime.exit()
            self.stop()
            return
        if text.strip():
            self.runtime.execute_console(text)

    def stop(self):
        super().stop()
        if self._session is not None and self._session.app.is_running:
            self._session.app.exit()
