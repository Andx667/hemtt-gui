from __future__ import annotations
import os
import subprocess
import threading
from typing import Callable, Optional


def build_command(hemtt_executable: str, args: list[str]) -> list[str]:
    """
    Build the full command list to pass to subprocess.
    On Windows, ensure .exe can be invoked via PATH or absolute path.
    """
    cmd = [hemtt_executable]
    cmd.extend(args)
    return cmd


class CommandRunner:
    def __init__(
        self,
        command: list[str],
        cwd: Optional[str] = None,
        on_output: Optional[Callable[[str], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None,
        env: Optional[dict[str, str]] = None,
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.on_output = on_output or (lambda _text: None)
        self.on_exit = on_exit or (lambda _code: None)
        self.env = env

        self.process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._cancel_requested = False
        self.is_running = False

    def start(self):
        if self.is_running:
            return
        self._cancel_requested = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel_requested = True
        if self.process and self.is_running:
            try:
                self.process.terminate()
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    def _run(self):
        self.is_running = True
        try:
            # Use universal_newlines/text True for str output
            self.process = subprocess.Popen(
                self.command,
                cwd=self.cwd or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=self.env,
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                if line is None:
                    break
                self.on_output(line)
                if self._cancel_requested:
                    break
            # Ensure process completed
            returncode = self.process.wait()
            self.on_exit(returncode)
        except FileNotFoundError as e:
            self.on_output(f"Error: {e}\n")
            self.on_exit(127)
        except Exception as e:
            self.on_output(f"Unexpected error: {e}\n")
            self.on_exit(1)
        finally:
            self.is_running = False
