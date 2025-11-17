import os
import queue
import shutil
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, scrolledtext, ttk

from command_runner import CommandRunner, build_command
from config_store import load_config, save_config

APP_TITLE = "GUI 4 HEMTT"


class HemttGUI(tk.Tk):
    """Tkinter-based GUI wrapper around the HEMTT CLI.

    Provides buttons for common commands, live process output, and user
    preferences such as dark mode and verbosity toggles.
    """

    def __init__(self):
        """Initialize the main application window and state."""
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(800, 500)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # State
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.runner: CommandRunner | None = None
        self.running: bool = False
        self.start_time: float = 0.0
        self.dark_mode: bool = False

        # Load config
        self.config_data = load_config()

        # Build UI
        self._build_ui()
        self._load_config_into_ui()
        self._poll_output_queue()

    def _build_ui(self):
        """Create and lay out all UI widgets."""
        # Winget install/update frame (top-most)
        winget_frame = ttk.Frame(self, padding=(8, 8))
        winget_frame.pack(fill=tk.X)
        self.btn_install_hemtt = ttk.Button(
            winget_frame,
            text="Install HEMTT (winget)",
            command=self._install_hemtt,
        )
        self.btn_update_hemtt = ttk.Button(
            winget_frame,
            text="Update HEMTT (winget)",
            command=self._update_hemtt,
        )
        self.btn_install_hemtt.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_update_hemtt.pack(side=tk.LEFT)
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

        # Arma 3 executable path
        arma3_label = ttk.Label(top, text="Arma 3 executable:")
        arma3_label.grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.arma3_var = tk.StringVar()
        arma3_entry = ttk.Entry(top, textvariable=self.arma3_var)
        arma3_entry.grid(row=2, column=1, sticky=tk.EW, pady=4)
        arma3_browse = ttk.Button(top, text="Browse…", command=self._browse_arma3)
        arma3_browse.grid(row=2, column=2, padx=(8, 0), pady=4)

        top.columnconfigure(1, weight=1)

        # Buttons frame - First row
        btns = ttk.Frame(self, padding=(8, 0))
        btns.pack(fill=tk.X, pady=(4, 0))

        self.btn_check = ttk.Button(btns, text="hemtt check", command=self._run_check)
        self.btn_dev = ttk.Button(btns, text="hemtt dev", command=self._run_dev)
        self.btn_launch = ttk.Button(btns, text="hemtt launch", command=self._run_launch)
        self.btn_build = ttk.Button(btns, text="hemtt build", command=self._run_build)
        self.btn_release = ttk.Button(btns, text="hemtt release", command=self._run_release)
        self.btn_cancel = ttk.Button(btns, text="Cancel", command=self._cancel_run)
        self.btn_cancel.state(["disabled"])  # disabled by default

        self.btn_check.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_dev.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_launch.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_build.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_release.pack(side=tk.LEFT, padx=(0, 8))

        # Separator before cancel button
        ttk.Separator(btns, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self.btn_cancel.pack(side=tk.LEFT)

        # Buttons frame - Second row
        btns2 = ttk.Frame(self, padding=(8, 4))
        btns2.pack(fill=tk.X)

        self.btn_ln_sort = ttk.Button(btns2, text="hemtt ln sort", command=self._run_ln_sort)
        self.btn_ln_coverage = ttk.Button(
            btns2, text="hemtt ln coverage", command=self._run_ln_coverage
        )
        self.btn_utils_fnl = ttk.Button(btns2, text="hemtt utils fnl", command=self._run_utils_fnl)
        # Add an info icon using a Unicode info symbol for clarity
        self.btn_book = ttk.Button(btns2, text="hemtt book ℹ", command=self._open_book)

        self.btn_ln_sort.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_ln_coverage.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_utils_fnl.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_book.pack(side=tk.LEFT)

        # Options frame - General options (all commands)
        general_frame = ttk.LabelFrame(self, text="General Options (All Commands)", padding=(8, 8))
        general_frame.pack(fill=tk.X, padx=8, pady=(4, 0))

        general_row = ttk.Frame(general_frame)
        general_row.pack(fill=tk.X, pady=2)
        self.verbose_var = tk.BooleanVar(value=False)
        self.verbose_check = ttk.Checkbutton(
            general_row, text="Verbose (-v)", variable=self.verbose_var
        )
        self.verbose_check.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(general_row, text="Threads (-t):").pack(side=tk.LEFT, padx=(8, 4))
        self.threads_var = tk.StringVar()
        threads_spinbox = ttk.Spinbox(
            general_row, from_=1, to=32, textvariable=self.threads_var, width=5
        )
        threads_spinbox.pack(side=tk.LEFT)

        # Check command options
        check_frame = ttk.LabelFrame(self, text="Check Options", padding=(8, 8))
        check_frame.pack(fill=tk.X, padx=8, pady=(4, 0))

        check_row = ttk.Frame(check_frame)
        check_row.pack(fill=tk.X, pady=2)
        self.pedantic_var = tk.BooleanVar(value=False)
        self.pedantic_check = ttk.Checkbutton(
            check_row, text="Pedantic (-p)", variable=self.pedantic_var
        )
        self.pedantic_check.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(check_row, text="Lints (-L):").pack(side=tk.LEFT, padx=(8, 4))
        self.lints_var = tk.StringVar()
        lints_entry = ttk.Entry(check_row, textvariable=self.lints_var, width=30)
        lints_entry.pack(side=tk.LEFT)
        ttk.Label(check_row, text="(comma-separated)").pack(side=tk.LEFT, padx=(4, 0))

        # Dev/Build/Launch options
        build_frame = ttk.LabelFrame(self, text="Dev/Build/Launch Options", padding=(8, 8))
        build_frame.pack(fill=tk.X, padx=8, pady=(4, 0))

        # Row 1 - Binarization and RAP options
        build_row1 = ttk.Frame(build_frame)
        build_row1.pack(fill=tk.X, pady=2)
        self.binarize_var = tk.BooleanVar(value=False)
        self.binarize_check = ttk.Checkbutton(
            build_row1, text="Binarize (-b)", variable=self.binarize_var
        )
        self.binarize_check.pack(side=tk.LEFT, padx=(0, 8))
        self.no_rap_var = tk.BooleanVar(value=False)
        self.no_rap_check = ttk.Checkbutton(
            build_row1, text="No Rap (--no-rap)", variable=self.no_rap_var
        )
        self.no_rap_check.pack(side=tk.LEFT, padx=(0, 8))
        self.all_optionals_var = tk.BooleanVar(value=False)
        self.all_optionals_check = ttk.Checkbutton(
            build_row1, text="All Optionals (-O)", variable=self.all_optionals_var
        )
        self.all_optionals_check.pack(side=tk.LEFT)

        # Row 2 - Optional addons and Just
        build_row2 = ttk.Frame(build_frame)
        build_row2.pack(fill=tk.X, pady=2)
        ttk.Label(build_row2, text="Optional addons (-o):").pack(side=tk.LEFT, padx=(0, 4))
        self.optional_addons_var = tk.StringVar()
        optional_entry = ttk.Entry(build_row2, textvariable=self.optional_addons_var, width=20)
        optional_entry.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(build_row2, text="Just (--just):").pack(side=tk.LEFT, padx=(0, 4))
        self.just_var = tk.StringVar()
        just_entry = ttk.Entry(build_row2, textvariable=self.just_var, width=20)
        just_entry.pack(side=tk.LEFT)
        ttk.Label(build_row2, text="(comma-separated)").pack(side=tk.LEFT, padx=(4, 0))

        # Release options
        release_frame = ttk.LabelFrame(self, text="Release Options", padding=(8, 8))
        release_frame.pack(fill=tk.X, padx=8, pady=(4, 0))

        release_row = ttk.Frame(release_frame)
        release_row.pack(fill=tk.X, pady=2)
        self.no_bin_var = tk.BooleanVar(value=False)
        self.no_bin_check = ttk.Checkbutton(
            release_row, text="No Binarize (--no-bin)", variable=self.no_bin_var
        )
        self.no_bin_check.pack(side=tk.LEFT, padx=(0, 8))
        self.no_sign_var = tk.BooleanVar(value=False)
        self.no_sign_check = ttk.Checkbutton(
            release_row, text="No Sign (--no-sign)", variable=self.no_sign_var
        )
        self.no_sign_check.pack(side=tk.LEFT, padx=(0, 8))
        self.no_archive_var = tk.BooleanVar(value=False)
        self.no_archive_check = ttk.Checkbutton(
            release_row, text="No Archive (--no-archive)", variable=self.no_archive_var
        )
        self.no_archive_check.pack(side=tk.LEFT)

        # Utility buttons frame
        util_btns = ttk.Frame(self, padding=(8, 4))
        util_btns.pack(fill=tk.X)

        # Dark mode toggle
        self.btn_dark_mode = ttk.Button(
            util_btns, text="Toggle Dark Mode", command=self._toggle_dark_mode
        )
        self.btn_dark_mode.pack(side=tk.LEFT, padx=(0, 8))

        # Export log button
        self.btn_export_log = ttk.Button(util_btns, text="Export Log", command=self._export_log)
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
        self.output = scrolledtext.ScrolledText(
            out_frame,
            height=20,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10),
            borderwidth=0,
            relief=tk.FLAT,
        )
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
        """Setup light and dark mode color schemes and apply initial theme."""
        self.style = ttk.Style()

        # Try to use a theme that supports better customization
        # 'clam' theme works well on all platforms and allows better color control
        available_themes = self.style.theme_names()
        if "clam" in available_themes:
            self.style.theme_use("clam")

        self.light_theme = {
            "bg": "#f0f0f0",
            "fg": "black",
            "entry_bg": "white",
            "entry_fg": "black",
            "text_bg": "#f5f5f5",
            "text_fg": "#333333",
            "error": "#cc0000",
            "warning": "#ff8c00",
            "info": "#0066cc",
            "button_bg": "#e1e1e1",
            "button_fg": "black",
        }
        self.dark_theme = {
            "bg": "#2d2d2d",
            "fg": "#d4d4d4",
            "entry_bg": "#3c3c3c",
            "entry_fg": "#d4d4d4",
            "text_bg": "#0c0c0c",
            "text_fg": "#cccccc",
            "error": "#ff5555",
            "warning": "#ffff55",
            "info": "#55ffff",
            "button_bg": "#3c3c3c",
            "button_fg": "#d4d4d4",
        }
        # Load dark mode preference from config
        self.dark_mode = self.config_data.get("dark_mode", False)
        if self.dark_mode:
            self._apply_dark_mode()
        else:
            self._apply_light_mode()

    def _load_config_into_ui(self):
        """Populate the UI from the persisted configuration file."""
        hemtt_path = self.config_data.get("hemtt_path") or "hemtt"
        proj_dir = self.config_data.get("project_dir") or os.getcwd()
        arma3_path = self.config_data.get("arma3_executable") or ""
        self.hemtt_var.set(hemtt_path)
        self.proj_var.set(proj_dir)
        self.arma3_var.set(arma3_path)
        # Load option toggles
        self.verbose_var.set(bool(self.config_data.get("verbose", False)))
        self.pedantic_var.set(bool(self.config_data.get("pedantic", False)))

    def _browse_hemtt(self):
        """Open a file dialog to select the HEMTT executable and persist path."""
        initial = self.hemtt_var.get() or os.getcwd()
        path = filedialog.askopenfilename(
            title="Select HEMTT executable",
            initialdir=os.path.dirname(initial),
            filetypes=[("Executable", "*"), ("All files", "*.*")],
        )
        if path:
            self.hemtt_var.set(path)
            self._persist_config()

    def _browse_project(self):
        """Open a folder dialog to select the project directory and persist it."""
        initial = self.proj_var.get() or os.getcwd()
        path = filedialog.askdirectory(title="Select project directory", initialdir=initial)
        if path:
            self.proj_var.set(path)
            self._persist_config()

    def _browse_arma3(self):
        """Open a file dialog to select the Arma 3 executable and persist path."""
        initial = self.arma3_var.get()
        initialdir = (
            os.path.dirname(initial) if initial and os.path.isfile(initial) else os.getcwd()
        )
        path = filedialog.askopenfilename(
            title="Select Arma 3 executable",
            initialdir=initialdir,
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.arma3_var.set(path)
            self._persist_config()

    def _persist_config(self):
        """Write current UI settings and preferences to the config file."""
        save_config(
            {
                "hemtt_path": self.hemtt_var.get().strip() or "hemtt",
                "project_dir": self.proj_var.get().strip() or os.getcwd(),
                "arma3_executable": self.arma3_var.get().strip(),
                "dark_mode": self.dark_mode,
                "verbose": bool(self.verbose_var.get()),
                "pedantic": bool(self.pedantic_var.get()),
            }
        )

    def _toggle_dark_mode(self):
        """Toggle between light and dark mode and persist preference."""
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self._apply_dark_mode()
        else:
            self._apply_light_mode()
        self._persist_config()

    def _apply_dark_mode(self):
        """Apply dark mode colors to the entire GUI and text tags."""
        theme = self.dark_theme

        # Configure main window
        self.configure(bg=theme["bg"])

        # Configure ttk styles for frames and labels
        self.style.configure("TFrame", background=theme["bg"])
        self.style.configure("TLabelframe", background=theme["bg"], foreground=theme["fg"])
        self.style.configure("TLabelframe.Label", background=theme["bg"], foreground=theme["fg"])
        self.style.configure("TLabel", background=theme["bg"], foreground=theme["fg"])

        # Configure buttons with dark colors
        self.style.configure(
            "TButton",
            background=theme["button_bg"],
            foreground=theme["button_fg"],
            bordercolor=theme["bg"],
            lightcolor=theme["button_bg"],
            darkcolor=theme["bg"],
        )
        self.style.map(
            "TButton",
            background=[("active", "#4a4a4a"), ("pressed", "#505050")],
            foreground=[("active", theme["fg"]), ("pressed", theme["fg"])],
        )

        # Configure checkbuttons
        self.style.configure("TCheckbutton", background=theme["bg"], foreground=theme["fg"])
        self.style.map(
            "TCheckbutton",
            background=[("", theme["bg"])],
            foreground=[("", theme["fg"])],
        )

        # Configure entry fields
        self.style.configure(
            "TEntry",
            fieldbackground=theme["entry_bg"],
            foreground=theme["entry_fg"],
            bordercolor=theme["bg"],
            lightcolor=theme["entry_bg"],
            darkcolor=theme["bg"],
        )

        # Configure spinbox
        self.style.configure(
            "TSpinbox",
            fieldbackground=theme["entry_bg"],
            foreground=theme["entry_fg"],
            bordercolor=theme["bg"],
            arrowcolor=theme["fg"],
        )

        # Configure output text widget
        self.output.configure(
            bg=theme["text_bg"], fg=theme["text_fg"], insertbackground=theme["text_fg"]
        )
        self.output.tag_config("error", foreground=theme["error"])
        self.output.tag_config("warning", foreground=theme["warning"])
        self.output.tag_config("info", foreground=theme["info"])

    def _apply_light_mode(self):
        """Apply light mode colors to the entire GUI and text tags."""
        theme = self.light_theme

        # Configure main window
        self.configure(bg=theme["bg"])

        # Configure ttk styles for frames and labels
        self.style.configure("TFrame", background=theme["bg"])
        self.style.configure("TLabelframe", background=theme["bg"], foreground=theme["fg"])
        self.style.configure("TLabelframe.Label", background=theme["bg"], foreground=theme["fg"])
        self.style.configure("TLabel", background=theme["bg"], foreground=theme["fg"])

        # Configure buttons
        self.style.configure(
            "TButton",
            background=theme["button_bg"],
            foreground=theme["button_fg"],
        )
        self.style.map(
            "TButton",
            background=[("active", "#d0d0d0"), ("pressed", "#c0c0c0")],
        )

        # Configure checkbuttons
        self.style.configure("TCheckbutton", background=theme["bg"], foreground=theme["fg"])
        self.style.map(
            "TCheckbutton",
            background=[("", theme["bg"])],
            foreground=[("", theme["fg"])],
        )

        # Configure entry fields
        self.style.configure(
            "TEntry",
            fieldbackground=theme["entry_bg"],
            foreground=theme["entry_fg"],
        )

        # Configure spinbox
        self.style.configure(
            "TSpinbox",
            fieldbackground=theme["entry_bg"],
            foreground=theme["entry_fg"],
        )

        # Configure output text widget
        self.output.configure(
            bg=theme["text_bg"], fg=theme["text_fg"], insertbackground=theme["text_fg"]
        )
        self.output.tag_config("error", foreground=self.light_theme["error"])
        self.output.tag_config("warning", foreground=self.light_theme["warning"])
        self.output.tag_config("info", foreground=self.light_theme["info"])

    def _export_log(self):
        """Export the current contents of the output pane to a UTF-8 text file."""
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
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )

        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(output_text)
                messagebox.showinfo(APP_TITLE, f"Log exported successfully to:\n{filepath}")
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Failed to export log:\n{e}")

    def _append_output(self, text: str):
        """Append a line to the output widget with basic severity highlighting.

        The method classifies lines as error/warning/info based on simple
        keyword matching and applies a text tag to colorize them.
        """
        self.output.configure(state=tk.NORMAL)

        # Detect log level and apply appropriate color tag
        tag = None
        text_lower = text.lower()

        # Check for error patterns
        if any(
            pattern in text_lower for pattern in ["error", "err:", "fatal", "failed", "failure"]
        ):
            tag = "error"
        # Check for warning patterns
        elif any(pattern in text_lower for pattern in ["warning", "warn:", "caution"]):
            tag = "warning"
        # Check for info patterns
        elif any(pattern in text_lower for pattern in ["info", "information", "note:", "hint:"]):
            tag = "info"

        # Insert text with appropriate tag
        if tag:
            self.output.insert(tk.END, text, tag)
        else:
            self.output.insert(tk.END, text)

        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _enqueue_output(self, text: str):
        """Queue text from the background runner for UI-thread insertion."""
        self.output_queue.put(text)

    def _poll_output_queue(self):
        """Drain the output queue periodically and update elapsed time."""
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
        """Enable/disable widgets and update status based on run state."""
        self.running = running
        widgets = [
            self.btn_build,
            self.btn_release,
            self.btn_check,
            self.btn_dev,
            self.btn_launch,
            self.btn_utils_fnl,
            self.btn_ln_sort,
            self.btn_ln_coverage,
            self.btn_install_hemtt,
            self.btn_update_hemtt,
            self.btn_custom,
            self.custom_entry,
            self.verbose_check,
            self.pedantic_check,
            self.binarize_check,
            self.no_rap_check,
            self.all_optionals_check,
            self.no_bin_check,
            self.no_sign_check,
            self.no_archive_check,
        ]
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
        """Validate and resolve the HEMTT executable and project directory.

        Returns a tuple of (hemtt_path, project_dir) when valid, or None if
        validation fails and the user cancels.
        """
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
                if not messagebox.askyesno(
                    APP_TITLE, "'hemtt' not found in PATH. Continue anyway?"
                ):
                    return None
        return hemtt, proj

    def _run(
        self, args: list[str], command_type: str = "other"
    ):
        """Start running a HEMTT command with optional flags.

        Parameters
        ----------
        args: list[str]
            Arguments after the 'hemtt' executable (e.g., ["build"]).
        command_type: str
            Type of command: "check", "dev", "build", "launch", "release", or "other".
        """
        validated = self._validated_paths()
        if not validated:
            return
        hemtt, proj = validated

        # Clear output and persist config
        self.output.configure(state=tk.NORMAL)
        self.output.delete(1.0, tk.END)
        self.output.configure(state=tk.DISABLED)
        self._persist_config()

        # Start building command arguments
        full_args = args.copy()

        # Add global options (all commands support these)
        if self.verbose_var.get():
            full_args.append("-v")

        threads = self.threads_var.get().strip()
        if threads:
            full_args.extend(["-t", threads])

        # Add command-specific options
        if command_type == "check":
            # Check-specific options
            if self.pedantic_var.get():
                full_args.append("-p")

            lints = self.lints_var.get().strip()
            if lints:
                for lint in lints.split(","):
                    lint = lint.strip()
                    if lint:
                        full_args.extend(["-L", lint])

        elif command_type in ["dev", "build", "launch"]:
            # Dev/Build/Launch options
            if self.binarize_var.get():
                full_args.append("-b")
            if self.no_rap_var.get():
                full_args.append("--no-rap")
            if self.all_optionals_var.get():
                full_args.append("-O")

            # Add optional addons
            optionals = self.optional_addons_var.get().strip()
            if optionals:
                for opt in optionals.split(","):
                    opt = opt.strip()
                    if opt:
                        full_args.extend(["-o", opt])

            # Add just option (dev and build support this)
            if command_type in ["dev", "build"]:
                just = self.just_var.get().strip()
                if just:
                    for j in just.split(","):
                        j = j.strip()
                        if j:
                            full_args.extend(["--just", j])

        elif command_type == "release":
            # Release-specific options
            if self.no_bin_var.get():
                full_args.append("--no-bin")
            if self.no_rap_var.get():
                full_args.append("--no-rap")
            if self.no_sign_var.get():
                full_args.append("--no-sign")
            if self.no_archive_var.get():
                full_args.append("--no-archive")

        cmd = build_command(hemtt, full_args)
        self._set_running(True, " ".join(cmd))

        self.runner = CommandRunner(
            command=cmd,
            cwd=proj,
            on_output=self._enqueue_output,
            on_exit=self._on_command_exit,
        )
        self.runner.start()

    def _on_command_exit(self, returncode: int):
        """Handle process termination and update UI state."""
        self._enqueue_output(f"\n[Process exited with code {returncode}]\n")
        self._set_running(False)
        self.runner = None

    def _cancel_run(self):
        """Request cancellation of the running process, if any."""
        if self.runner:
            self.runner.cancel()
            self._enqueue_output("\n[Cancellation requested]\n")

    # Button handlers
    def _run_build(self):
        """Run 'hemtt build'."""
        self._run(["build"], command_type="build")

    def _run_release(self):
        """Run 'hemtt release'."""
        self._run(["release"], command_type="release")

    def _run_check(self):
        """Run 'hemtt check'."""
        self._run(["check"], command_type="check")

    def _run_dev(self):
        """Run 'hemtt dev'."""
        self._run(["dev"], command_type="dev")

    def _run_utils_fnl(self):
        """Run 'hemtt utils fnl'."""
        self._run(["utils", "fnl"], command_type="other")

    def _run_ln_sort(self):
        """Run 'hemtt ln sort'."""
        self._run(["ln", "sort"], command_type="other")

    def _run_ln_coverage(self):
        """Run 'hemtt ln coverage'."""
        self._run(["ln", "coverage"], command_type="other")

    def _run_custom(self):
        """Run a custom argument list typed by the user after 'hemtt'."""
        extra = self.custom_var.get().strip()
        if not extra:
            messagebox.showinfo(APP_TITLE, "Enter custom arguments, e.g. 'validate'")
            return
        args = [a for a in extra.split(" ") if a]
        self._run(args, command_type="other")

    def _install_hemtt(self):
        """Install HEMTT via winget (BrettMayson.HEMTT)."""
        self._run_winget(["install", "--id", "BrettMayson.HEMTT", "-e"], label="winget install")

    def _update_hemtt(self):
        """Update/upgrade HEMTT via winget (BrettMayson.HEMTT)."""
        self._run_winget(["upgrade", "--id", "BrettMayson.HEMTT", "-e"], label="winget upgrade")

    def _run_winget(self, winget_args: list[str], label: str):
        """Run a winget command and stream output to the console.

        Parameters
        ----------
        winget_args: list[str]
            Arguments after 'winget'. Example: ['install', '--id', 'BrettMayson.HEMTT', '-e']
        label: str
            Short label for status bar.
        """
        # Clear output
        self.output.configure(state=tk.NORMAL)
        self.output.delete(1.0, tk.END)
        self.output.configure(state=tk.DISABLED)

        cmd = ["winget"] + winget_args
        self._set_running(True, " ".join(cmd))

        self.runner = CommandRunner(
            command=cmd,
            cwd=os.getcwd(),
            on_output=self._enqueue_output,
            on_exit=self._on_command_exit,
        )
        self.runner.start()

    def _run_launch(self):
        """Open launch dialog and run hemtt launch with selected options."""
        arma3_exec = self.arma3_var.get().strip()
        dialog = LaunchDialog(self, arma3_exec)
        self.wait_window(dialog)
        if dialog.result:
            args = ["launch"] + dialog.result
            self._run(args, command_type="launch")

    def _open_book(self):
        """Open the HEMTT documentation in the default web browser."""
        try:
            webbrowser.open("https://hemtt.dev")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Failed to open browser:\n{e}")

    def on_close(self):
        """Prompt on close if a command is running, then persist and exit."""
        if self.runner and self.runner.is_running:
            if not messagebox.askyesno(APP_TITLE, "A command is still running. Exit anyway?"):
                return
        self._persist_config()
        self.destroy()


class LaunchDialog(tk.Toplevel):
    """Dialog for configuring hemtt launch options."""

    def __init__(self, parent, default_arma3_exec=""):
        super().__init__(parent)
        self.title("HEMTT Launch Configuration")
        self.resizable(False, False)
        self.result = None

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # Profile configuration
        profile_frame = ttk.LabelFrame(self, text="Launch Profile", padding=10)
        profile_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(profile_frame, text="Profile name:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.profile_var = tk.StringVar(value="default")
        profile_entry = ttk.Entry(profile_frame, textvariable=self.profile_var, width=30)
        profile_entry.grid(row=0, column=1, sticky=tk.EW, pady=2, padx=(5, 0))
        ttk.Label(
            profile_frame, text="(leave 'default' for default profile)", font=("TkDefaultFont", 8)
        ).grid(row=1, column=1, sticky=tk.W, pady=(0, 5), padx=(5, 0))

        profile_frame.columnconfigure(1, weight=1)

        # Launch options
        options_frame = ttk.LabelFrame(self, text="Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        self.quick_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame, text="Quick launch (-Q, skip build)", variable=self.quick_var
        ).pack(anchor=tk.W, pady=2)

        self.no_filepatching_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="Disable file patching (-F)",
            variable=self.no_filepatching_var,
        ).pack(anchor=tk.W, pady=2)

        self.binarize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame, text="Binarize files (-b)", variable=self.binarize_var
        ).pack(anchor=tk.W, pady=2)

        self.all_optionals_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="Include all optionals (-O)",
            variable=self.all_optionals_var,
        ).pack(anchor=tk.W, pady=2)

        self.no_rap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="No RAP (--no-rap)",
            variable=self.no_rap_var,
        ).pack(anchor=tk.W, pady=2)

        # Executable
        exec_frame = ttk.Frame(options_frame)
        exec_frame.pack(fill=tk.X, pady=5)
        ttk.Label(exec_frame, text="Executable (-e):").pack(side=tk.LEFT)
        self.executable_var = tk.StringVar(value=default_arma3_exec)
        exec_entry = ttk.Entry(exec_frame, textvariable=self.executable_var, width=20)
        exec_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(
            exec_frame, text="(optional, e.g. arma3profiling_x64)", font=("TkDefaultFont", 8)
        ).pack(side=tk.LEFT)

        # Instances
        inst_frame = ttk.Frame(options_frame)
        inst_frame.pack(fill=tk.X, pady=2)
        ttk.Label(inst_frame, text="Instances (-i):").pack(side=tk.LEFT)
        self.instances_var = tk.StringVar(value="1")
        inst_spinbox = ttk.Spinbox(
            inst_frame, from_=1, to=10, textvariable=self.instances_var, width=5
        )
        inst_spinbox.pack(side=tk.LEFT, padx=5)
        ttk.Label(
            inst_frame, text="(number of game instances to launch)", font=("TkDefaultFont", 8)
        ).pack(side=tk.LEFT)

        # Optional addons
        optional_frame = ttk.Frame(options_frame)
        optional_frame.pack(fill=tk.X, pady=5)
        ttk.Label(optional_frame, text="Optional addons (-o):").pack(side=tk.LEFT)
        self.optional_var = tk.StringVar()
        optional_entry = ttk.Entry(optional_frame, textvariable=self.optional_var, width=30)
        optional_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(
            optional_frame, text="(comma-separated, e.g. compat,extra)", font=("TkDefaultFont", 8)
        ).pack(side=tk.LEFT)

        # Additional arguments
        extra_frame = ttk.LabelFrame(self, text="Additional Arguments", padding=10)
        extra_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(extra_frame, text="Extra args (after --):").pack(anchor=tk.W)
        self.extra_args_var = tk.StringVar()
        extra_entry = ttk.Entry(extra_frame, textvariable=self.extra_args_var)
        extra_entry.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(
            extra_frame,
            text="Example: -world=empty -window",
            font=("TkDefaultFont", 8),
        ).pack(anchor=tk.W, pady=(2, 0))

        # Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Launch", command=self._on_launch).pack(
            side=tk.RIGHT, padx=(5, 0)
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT)

        # Center dialog on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _on_launch(self):
        """Build command arguments and close dialog."""
        args = []

        # Add profile if not default
        profile = self.profile_var.get().strip()
        if profile and profile != "default":
            args.append(profile)

        # Add options using correct short flags where available
        if self.quick_var.get():
            args.append("-Q")
        if self.no_filepatching_var.get():
            args.append("-F")
        if self.binarize_var.get():
            args.append("-b")
        if self.all_optionals_var.get():
            args.append("-O")
        if self.no_rap_var.get():
            args.append("--no-rap")

        # Add executable
        executable = self.executable_var.get().strip()
        if executable:
            args.extend(["-e", executable])

        # Add instances
        instances = self.instances_var.get().strip()
        if instances and instances != "1":
            args.extend(["-i", instances])

        # Add optional addons
        optionals = self.optional_var.get().strip()
        if optionals:
            for opt in optionals.split(","):
                opt = opt.strip()
                if opt:
                    args.extend(["-o", opt])

        # Add extra arguments (passthrough after --)
        extra = self.extra_args_var.get().strip()
        if extra:
            args.append("--")
            args.extend(extra.split())

        self.result = args
        self.destroy()

    def _on_cancel(self):
        """Close dialog without launching."""
        self.result = None
        self.destroy()


def main():
    """Entrypoint to start the Tkinter application."""
    app = HemttGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
