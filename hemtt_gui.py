import os
import sys
import time
import queue
import threading
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import scrolledtext

from config_store import load_config, save_config, get_config_path
from command_runner import CommandRunner, build_command

APP_TITLE = "HEMTT GUI"


class HemttGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(800, 500)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # State
        self.output_queue: "queue.Queue[str]" = queue.Queue()
        self.runner: CommandRunner | None = None
        self.running: bool = False
        self.start_time: float = 0.0
        self.current_command: list[str] | None = None

        # Load config
        self.config_data = load_config()

        # Build UI
        self._build_ui()
        self._load_config_into_ui()
        self._poll_output_queue()

    def _build_ui(self):
        # Top frame for paths
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        # HEMTT executable path
        hemtt_label = ttk.Label(top, text="HEMTT executable:")
        hemtt_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.hemtt_var = tk.StringVar()
        hemtt_entry = ttk.Entry(top, textvariable=self.hemtt_var)
        hemtt_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)
        hemtt_browse = ttk.Button(top, text="Browse…", command=self._browse_hemtt)
        hemtt_browse.grid(row=0, column=2, padx=(8, 0), pady=4)

        # Project directory
        proj_label = ttk.Label(top, text="Project directory:")
        proj_label.grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.proj_var = tk.StringVar()
        proj_entry = ttk.Entry(top, textvariable=self.proj_var)
        proj_entry.grid(row=1, column=1, sticky=tk.EW, pady=4)
        proj_browse = ttk.Button(top, text="Browse…", command=self._browse_project)
        proj_browse.grid(row=1, column=2, padx=(8, 0), pady=4)

        top.columnconfigure(1, weight=1)

        # Buttons frame
        btns = ttk.Frame(self, padding=(8, 0))
        btns.pack(fill=tk.X, pady=(4, 0))

        self.btn_build = ttk.Button(btns, text="hemtt build", command=self._run_build)
        self.btn_release = ttk.Button(btns, text="hemtt release", command=self._run_release)
        self.btn_ln_sort = ttk.Button(btns, text="hemtt ln sort", command=self._run_ln_sort)
        self.btn_cancel = ttk.Button(btns, text="Cancel", command=self._cancel_run)
        self.btn_cancel.state(["disabled"])  # disabled by default

        self.btn_build.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_release.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_ln_sort.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_cancel.pack(side=tk.LEFT)

        # Custom command
        custom = ttk.Frame(self, padding=8)
        custom.pack(fill=tk.X)
        ttk.Label(custom, text="Custom args (after 'hemtt'):").pack(side=tk.LEFT)
        self.custom_var = tk.StringVar()
        self.custom_entry = ttk.Entry(custom, textvariable=self.custom_var)
        self.custom_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.btn_custom = ttk.Button(custom, text="Run", command=self._run_custom)
        self.btn_custom.pack(side=tk.LEFT)

        # Output area
        out_frame = ttk.Frame(self, padding=8)
        out_frame.pack(fill=tk.BOTH, expand=True)
        self.output = scrolledtext.ScrolledText(out_frame, height=20, wrap=tk.WORD, state=tk.DISABLED)
        self.output.pack(fill=tk.BOTH, expand=True)

        # Status bar
        status = ttk.Frame(self, padding=(8, 4))
        status.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(status, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)
        self.elapsed_var = tk.StringVar(value="")
        self.elapsed_label = ttk.Label(status, textvariable=self.elapsed_var)
        self.elapsed_label.pack(side=tk.RIGHT)

    def _load_config_into_ui(self):
        hemtt_path = self.config_data.get("hemtt_path") or "hemtt"
        proj_dir = self.config_data.get("project_dir") or os.getcwd()
        self.hemtt_var.set(hemtt_path)
        self.proj_var.set(proj_dir)

    def _browse_hemtt(self):
        initial = self.hemtt_var.get() or os.getcwd()
        path = filedialog.askopenfilename(title="Select HEMTT executable", initialdir=os.path.dirname(initial),
                                          filetypes=[("Executable", "*"), ("All files", "*.*")])
        if path:
            self.hemtt_var.set(path)
            self._persist_config()

    def _browse_project(self):
        initial = self.proj_var.get() or os.getcwd()
        path = filedialog.askdirectory(title="Select project directory", initialdir=initial)
        if path:
            self.proj_var.set(path)
            self._persist_config()

    def _persist_config(self):
        save_config({
            "hemtt_path": self.hemtt_var.get().strip() or "hemtt",
            "project_dir": self.proj_var.get().strip() or os.getcwd(),
        })

    def _append_output(self, text: str):
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _enqueue_output(self, text: str):
        self.output_queue.put(text)

    def _poll_output_queue(self):
        try:
            while True:
                text = self.output_queue.get_nowait()
                self._append_output(text)
        except queue.Empty:
            pass
        if self.running and self.start_time:
            elapsed = time.time() - self.start_time
            self.elapsed_var.set(f"Elapsed: {elapsed:0.1f}s")
        else:
            self.elapsed_var.set("")
        self.after(100, self._poll_output_queue)

    def _set_running(self, running: bool, command_str: str | None = None):
        self.running = running
        widgets = [self.btn_build, self.btn_release, self.btn_ln_sort, self.btn_custom, self.custom_entry]
        for w in widgets:
            if running:
                w.state(["disabled"])  # type: ignore[attr-defined]
            else:
                w.state(["!disabled"])  # type: ignore[attr-defined]
        if running:
            self.btn_cancel.state(["!disabled"])  # type: ignore[attr-defined]
            self.status_var.set(f"Running: {command_str}")
            self.start_time = time.time()
        else:
            self.btn_cancel.state(["disabled"])  # type: ignore[attr-defined]
            self.status_var.set("Ready")
            self.start_time = 0.0

    def _validated_paths(self) -> tuple[str, str] | None:
        hemtt = self.hemtt_var.get().strip() or "hemtt"
        proj = self.proj_var.get().strip() or os.getcwd()

        if not os.path.isdir(proj):
            messagebox.showerror(APP_TITLE, f"Project directory not found:\n{proj}")
            return None

        # If hemtt is not an explicit path, allow PATH resolution
        if os.path.sep in hemtt or (os.path.altsep and os.path.altsep in hemtt):
            if not os.path.isfile(hemtt):
                messagebox.showerror(APP_TITLE, f"HEMTT executable not found:\n{hemtt}")
                return None
        else:
            resolved = shutil.which(hemtt)
            if resolved is None:
                # Still allow to try, but warn user
                if not messagebox.askyesno(APP_TITLE, "'hemtt' not found in PATH. Continue anyway?"):
                    return None
        return hemtt, proj

    def _run(self, args: list[str]):
        validated = self._validated_paths()
        if not validated:
            return
        hemtt, proj = validated

        # Clear output and persist config
        self.output.configure(state=tk.NORMAL)
        self.output.delete(1.0, tk.END)
        self.output.configure(state=tk.DISABLED)
        self._persist_config()

        cmd = build_command(hemtt, args)
        self.current_command = cmd
        self._set_running(True, " ".join(cmd))

        self.runner = CommandRunner(
            command=cmd,
            cwd=proj,
            on_output=self._enqueue_output,
            on_exit=self._on_command_exit,
        )
        self.runner.start()

    def _on_command_exit(self, returncode: int):
        self._enqueue_output(f"\n[Process exited with code {returncode}]\n")
        self._set_running(False)
        self.runner = None

    def _cancel_run(self):
        if self.runner:
            self.runner.cancel()
            self._enqueue_output("\n[Cancellation requested]\n")

    # Button handlers
    def _run_build(self):
        self._run(["build"]) 

    def _run_release(self):
        self._run(["release"]) 

    def _run_ln_sort(self):
        # The user requested 'hemtt ln sort'
        self._run(["ln", "sort"]) 

    def _run_custom(self):
        extra = self.custom_var.get().strip()
        if not extra:
            messagebox.showinfo(APP_TITLE, "Enter custom arguments, e.g. 'validate' or 'package --dry-run'")
            return
        args = [a for a in extra.split(" ") if a]
        self._run(args)

    def on_close(self):
        if self.runner and self.runner.is_running:
            if not messagebox.askyesno(APP_TITLE, "A command is still running. Exit anyway?"):
                return
        self._persist_config()
        self.destroy()


def main():
    app = HemttGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
