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
        self.dark_mode: bool = False

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

        # Buttons frame - First row
        btns = ttk.Frame(self, padding=(8, 0))
        btns.pack(fill=tk.X, pady=(4, 0))

        self.btn_check = ttk.Button(btns, text="hemtt check", command=self._run_check)
        self.btn_dev = ttk.Button(btns, text="hemtt dev", command=self._run_dev)
        self.btn_build = ttk.Button(btns, text="hemtt build", command=self._run_build)
        self.btn_release = ttk.Button(btns, text="hemtt release", command=self._run_release)
        self.btn_cancel = ttk.Button(btns, text="Cancel", command=self._cancel_run)
        self.btn_cancel.state(["disabled"])  # disabled by default

        self.btn_check.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_dev.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_build.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_release.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_cancel.pack(side=tk.LEFT)

        # Buttons frame - Second row
        btns2 = ttk.Frame(self, padding=(8, 4))
        btns2.pack(fill=tk.X)

        self.btn_ln_sort = ttk.Button(btns2, text="hemtt ln sort", command=self._run_ln_sort)
        self.btn_utils_fnl = ttk.Button(btns2, text="hemtt utils fnl", command=self._run_utils_fnl)

        self.btn_ln_sort.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_utils_fnl.pack(side=tk.LEFT)

        # Options frame
        opts = ttk.Frame(self, padding=(8, 8))
        opts.pack(fill=tk.X)
        ttk.Label(opts, text="Options:").pack(side=tk.LEFT, padx=(0, 8))
        self.verbose_var = tk.BooleanVar(value=False)
        self.verbose_check = ttk.Checkbutton(opts, text="Verbose (-v)", variable=self.verbose_var)
        self.verbose_check.pack(side=tk.LEFT, padx=(0, 8))
        self.pedantic_var = tk.BooleanVar(value=False)
        self.pedantic_check = ttk.Checkbutton(opts, text="Pedantic (-p)", variable=self.pedantic_var)
        self.pedantic_check.pack(side=tk.LEFT, padx=(0, 16))
        
        # Dark mode toggle
        self.btn_dark_mode = ttk.Button(opts, text="Toggle Dark Mode", command=self._toggle_dark_mode)
        self.btn_dark_mode.pack(side=tk.LEFT, padx=(0, 8))
        
        # Export log button
        self.btn_export_log = ttk.Button(opts, text="Export Log", command=self._export_log)
        self.btn_export_log.pack(side=tk.LEFT)

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
        
        # Configure color tags for different log levels (light mode)
        self.output.tag_config("error", foreground="red")
        self.output.tag_config("warning", foreground="orange")
        self.output.tag_config("info", foreground="blue")
        
        # Store initial colors for theme switching
        self._setup_themes()

        # Status bar
        status = ttk.Frame(self, padding=(8, 4))
        status.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(status, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)
        self.elapsed_var = tk.StringVar(value="")
        self.elapsed_label = ttk.Label(status, textvariable=self.elapsed_var)
        self.elapsed_label.pack(side=tk.RIGHT)

    def _setup_themes(self):
        """Setup light and dark mode color schemes."""
        self.light_theme = {
            "bg": "white",
            "fg": "black",
            "error": "red",
            "warning": "orange",
            "info": "blue"
        }
        self.dark_theme = {
            "bg": "#1e1e1e",
            "fg": "#d4d4d4",
            "error": "#f48771",
            "warning": "#dcdcaa",
            "info": "#4fc1ff"
        }
        # Load dark mode preference from config
        self.dark_mode = self.config_data.get("dark_mode", False)
        if self.dark_mode:
            self._apply_dark_mode()

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
            "dark_mode": self.dark_mode,
        })
    
    def _toggle_dark_mode(self):
        """Toggle between light and dark mode."""
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self._apply_dark_mode()
        else:
            self._apply_light_mode()
        self._persist_config()
    
    def _apply_dark_mode(self):
        """Apply dark mode colors."""
        self.output.configure(
            bg=self.dark_theme["bg"],
            fg=self.dark_theme["fg"],
            insertbackground=self.dark_theme["fg"]
        )
        self.output.tag_config("error", foreground=self.dark_theme["error"])
        self.output.tag_config("warning", foreground=self.dark_theme["warning"])
        self.output.tag_config("info", foreground=self.dark_theme["info"])
    
    def _apply_light_mode(self):
        """Apply light mode colors."""
        self.output.configure(
            bg=self.light_theme["bg"],
            fg=self.light_theme["fg"],
            insertbackground=self.light_theme["fg"]
        )
        self.output.tag_config("error", foreground=self.light_theme["error"])
        self.output.tag_config("warning", foreground=self.light_theme["warning"])
        self.output.tag_config("info", foreground=self.light_theme["info"])
    
    def _export_log(self):
        """Export the output log to a text file."""
        # Get the output text
        output_text = self.output.get(1.0, tk.END)
        
        if not output_text.strip():
            messagebox.showinfo(APP_TITLE, "No log content to export.")
            return
        
        # Ask user for save location
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        default_filename = f"hemtt_log_{timestamp}.txt"
        
        filepath = filedialog.asksaveasfilename(
            title="Export Log",
            defaultextension=".txt",
            initialfile=default_filename,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(output_text)
                messagebox.showinfo(APP_TITLE, f"Log exported successfully to:\n{filepath}")
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Failed to export log:\n{e}")

    def _append_output(self, text: str):
        self.output.configure(state=tk.NORMAL)
        
        # Detect log level and apply appropriate color tag
        tag = None
        text_lower = text.lower()
        
        # Check for error patterns
        if any(pattern in text_lower for pattern in ['error', 'err:', 'fatal', 'failed', 'failure']):
            tag = "error"
        # Check for warning patterns
        elif any(pattern in text_lower for pattern in ['warning', 'warn:', 'caution']):
            tag = "warning"
        # Check for info patterns
        elif any(pattern in text_lower for pattern in ['info', 'information', 'note:', 'hint:']):
            tag = "info"
        
        # Insert text with appropriate tag
        if tag:
            self.output.insert(tk.END, text, tag)
        else:
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
        widgets = [self.btn_build, self.btn_release, self.btn_check, self.btn_dev, self.btn_utils_fnl, self.btn_ln_sort, self.btn_custom, self.custom_entry, self.verbose_check, self.pedantic_check]
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

        # Add verbose and pedantic flags if enabled
        full_args = args.copy()
        if self.verbose_var.get():
            full_args.append("-v")
        if self.pedantic_var.get():
            full_args.append("-p")

        cmd = build_command(hemtt, full_args)
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

    def _run_check(self):
        self._run(["check"]) 

    def _run_dev(self):
        self._run(["dev"]) 

    def _run_utils_fnl(self):
        self._run(["utils", "fnl"]) 

    def _run_ln_sort(self):
        self._run(["ln", "sort"]) 

    def _run_custom(self):
        extra = self.custom_var.get().strip()
        if not extra:
            messagebox.showinfo(APP_TITLE, "Enter custom arguments, e.g. 'validate'")
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
