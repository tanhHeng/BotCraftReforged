"""Native prompt-toolkit UI with standalone console completion and shutdown."""
from __future__ import annotations
from typing import TYPE_CHECKING, TextIO
from typing_extensions import Self

if TYPE_CHECKING:
    from botcraft.runtime import Runtime
    from botcraft.command.command_manager import CommandManager
import queue
import sys
import threading
from prompt_toolkit.utils import is_dumb_terminal

from mcdreforged.command.builder.nodes.basic import CommandSuggestions
from mcdreforged.executor.background_thread_executor import BackgroundThreadExecutor
from mcdreforged.executor.console_handler import (
    CachedSuggestionProvider as NativeSuggestionProvider,
    MCDRPromptSession as NativePromptSession,
    MCDRStdoutProxy,
)
from mcdreforged.logging.stream_handler import SyncStdoutStreamHandler

from botcraft.plugin._native import bind_native


class ConsoleSuggestionProvider(NativeSuggestionProvider):
    """Serialize native completion calls without retaining stale plugin data."""

    def __init__(self: Self, command_manager: CommandManager) -> None:
        """Create a completion provider serialized against concurrent suggestion requests.
        
        :param command_manager: Command manager supplying console completion.
        :return: No return value.
        """
        self.command_manager = command_manager
        self._calc_lock = threading.Lock()

    def suggest(self: Self, input_: str) -> CommandSuggestions:
        """Return current console command suggestions without retaining stale plugin data.
        
        :param input_: Console input text for completion.
        :return: Result of the operation.
        """
        if not self._calc_lock.acquire(blocking=False):
            return CommandSuggestions()
        try:
            return self.command_manager.suggest_console(input_)
        finally:
            self._calc_lock.release()


class ConsolePromptSession(NativePromptSession):
    # Keep native completion menus, argument hints and dynamic menu height.
    __init__ = bind_native(
        NativePromptSession.__init__, runtime=True,
        globals={'CachedSuggestionProvider': ConsoleSuggestionProvider},
    )


class PromptToolkitWrapper:
    def __init__(self: Self, console_handler: ConsoleHandler) -> None:
        """Initialize advanced-console state and wakeable basic-input queues.
        
        :param console_handler: Console executor owning the prompt and logger.
        :return: No return value.
        """
        self.console_handler = console_handler
        self.prompt_session = None
        self.stdout_proxy = None
        self.pt_enabled = False
        self._stopped = threading.Event()
        self._state_lock = threading.Lock()
        self._real_stdout = None
        self._real_stderr = None
        self._basic_input = queue.Queue()
        self._basic_requests = queue.Queue()
        self._basic_reader = None

    def start_kits(self: Self) -> None:
        """Enable the native advanced console when the terminal supports it.
        
        :return: No return value.
        """
        with self._state_lock:
            if self._stopped.is_set():
                return
            if is_dumb_terminal():
                self.console_handler.logger.warning('Advanced console is unavailable for a dumb terminal; using basic input')
                return
            try:
                self.prompt_session = ConsolePromptSession(self.console_handler)
                self.stdout_proxy = MCDRStdoutProxy()
            except Exception:
                if self.prompt_session is not None:
                    self.prompt_session.app.input.close()
                    self.prompt_session = None
                self.console_handler.logger.exception('Failed to enable advanced console, switch back to basic input')
                return
            self._real_stdout, self._real_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = self.stdout_proxy
            SyncStdoutStreamHandler.update_stdout(sys.stdout)
            self.pt_enabled = True

    def _exit_prompt(self: Self) -> None:
        session = self.prompt_session
        if session is not None:
            future = session.app.future
            if future is not None and not future.done():
                session.app.exit(exception=EOFError)

    def _before_prompt(self: Self) -> None:
        # Application.future exists here. This covers stop before run/pre_run.
        if self._stopped.is_set():
            self._exit_prompt()

    def stop_kits(self: Self) -> None:
        """Wake blocked console input and request exit from an active prompt.
        
        :return: No return value.
        """
        self._stopped.set()
        self._basic_input.put(EOFError())
        self._basic_requests.put(False)
        with self._state_lock:
            session = self.prompt_session
            loop = session.app.loop if session is not None else None
            if loop is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(self._exit_prompt)
                except RuntimeError:
                    # A completed prompt may close its loop concurrently.
                    pass

    def close(self: Self) -> None:
        """Restore standard streams and release console resources after input returns.
        
        :return: No return value.
        """
        # Run after prompt returns so proxy flushing cannot strand an active UI.
        with self._state_lock:
            if self.pt_enabled:
                self.pt_enabled = False
                sys.stdout, sys.stderr = self._real_stdout, self._real_stderr
                SyncStdoutStreamHandler.update_stdout(sys.stdout)
                self.stdout_proxy.flush()
                self.stdout_proxy.close()
                self.stdout_proxy = None
            if self.prompt_session is not None:
                self.prompt_session.app.input.close()
                self.prompt_session = None

    def _read_basic(self: Self, stream: TextIO) -> None:
        # Blocking stdin has no portable cancellation. Only this daemon can
        # remain blocked; the Console executor itself waits on a wakeable queue.
        while self._basic_requests.get():
            if self._stopped.is_set():
                return
            try:
                line = stream.readline()
            except Exception as error:
                self._basic_input.put(error)
                return
            self._basic_input.put(line if line else EOFError())
            if not line:
                return

    def get_input(self: Self) -> list[str]:
        """Read console lines using the advanced prompt or wakeable basic-input queue.
        
        :return: Entered lines; EOF or input errors are raised to the console executor.
        """
        if self._stopped.is_set():
            raise EOFError
        if self.pt_enabled:
            input_ = self.prompt_session.prompt('> ', pre_run=self._before_prompt)
            return (input_ or '').splitlines()
        if self._basic_reader is None:
            self._basic_reader = threading.Thread(
                target=self._read_basic, args=(sys.stdin,),
                name='ConsoleStdin', daemon=True,
            )
            self._basic_reader.start()
        self._basic_requests.put(True)
        line = self._basic_input.get()
        if isinstance(line, Exception):
            raise line
        return [line.rstrip('\r\n')]


class ConsoleHandler(BackgroundThreadExecutor):
    def __init__(self: Self, runtime: Runtime) -> None:
        """Create the standalone console background executor.
        
        :param runtime: Runtime receiving entered console commands.
        :return: No return value.
        """
        super().__init__(runtime.logger)
        self.runtime = runtime
        self.set_name('Console')
        self.console_kit = PromptToolkitWrapper(self)

    def loop(self: Self) -> None:
        """Serve console input and close prompt resources when the loop ends.
        
        :return: No return value.
        """
        try:
            if self.runtime.config.advanced_console:
                self.console_kit.start_kits()
            super().loop()
        finally:
            self.console_kit.stop_kits()
            self.console_kit.close()

    def tick(self: Self) -> None:
        """Read console lines and submit nonempty commands to the runtime.
        
        :return: No return value.
        """
        try:
            for text in self.console_kit.get_input():
                if not self.should_keep_looping() or self.runtime.is_stopping():
                    return
                if text.strip():
                    self.runtime.execute_console(text)
        except (EOFError, KeyboardInterrupt):
            if not self.runtime.is_stopping():
                self.runtime.exit()
            self.stop()
        except Exception:
            if not self.runtime.is_stopping():
                self.logger.exception('Error reading console input')
                self.runtime.exit()
            self.stop()

    def stop(self: Self) -> None:
        """Stop the background loop and wake pending console input.
        
        :return: No return value.
        """
        super().stop()
        self.console_kit.stop_kits()
