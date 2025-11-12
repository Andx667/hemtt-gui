from __future__ import annotations
import os
import re
import subprocess
import threading
from typing import Callable, Optional


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


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
            # Prepare environment to disable color output from HEMTT
            run_env = self.env.copy() if self.env else os.environ.copy()
            # Force NO_COLOR to disable ANSI color codes
            run_env['NO_COLOR'] = '1'
            # Also set other common env vars that disable colors
            run_env['TERM'] = 'dumb'
            
            # Use universal_newlines/text True for str output with UTF-8 encoding
            self.process = subprocess.Popen(
                self.command,
                cwd=self.cwd or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace',
                env=run_env,
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                if line is None:
                    break
                # Strip ANSI escape codes before sending to output
                clean_line = strip_ansi_codes(line)
                self.on_output(clean_line)
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
