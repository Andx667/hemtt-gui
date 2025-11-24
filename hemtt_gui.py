import os
import queue
import shutil
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    HAS_DND = True
except ImportError:
    HAS_DND = False
    TkinterDnD = None  # type: ignore

from command_runner import CommandRunner, build_command
from config_store import load_config, save_config

APP_TITLE = "GUI 4 HEMTT"


class HemttGUI(TkinterDnD.Tk if HAS_DND else tk.Tk):  # type: ignore
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
        self._setup_main_window_dnd()
        self._poll_output_queue()

    def _setup_main_window_dnd(self):
        """Setup drag and drop for project folder on main window."""
        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)  # type: ignore
                self.dnd_bind("<<Drop>>", self._on_main_window_drop)  # type: ignore
            except Exception:
                pass

    def _on_main_window_drop(self, event):
        """Handle folder drops on main window to set project directory."""
        files = self.tk.splitlist(event.data)
        if files:
            path = files[0].strip("{}").strip()
            # Check if it's a directory
            if os.path.isdir(path):
                self.proj_var.set(path)
                self._persist_config()
            else:
                # If file was dropped, use its parent directory
                parent_dir = os.path.dirname(path)
                if os.path.isdir(parent_dir):
                    self.proj_var.set(parent_dir)
                    self._persist_config()

    def _create_tooltip(self, widget, text):
        """Create a tooltip for a widget."""

        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
            label = tk.Label(
                tooltip,
                text=text,
                background="#ffffe0",
                relief=tk.SOLID,
                borderwidth=1,
                font=("TkDefaultFont", 9),
                padx=5,
                pady=3,
            )
            label.pack()
            widget._tooltip = tooltip

        def on_leave(event):
            if hasattr(widget, "_tooltip"):
                widget._tooltip.destroy()
                del widget._tooltip

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _build_ui(self):
        """Create and lay out all UI widgets."""
        # Winget install/update frame (top-most)
        winget_frame = ttk.Frame(self, padding=(8, 8))
        winget_frame.pack(fill=tk.X)
        self.btn_install_hemtt = ttk.Button(
            winget_frame,
            text="Install HEMTT (winget) ⓘ",
            command=self._install_hemtt,
        )
        self._create_tooltip(
            self.btn_install_hemtt,
            "Install HEMTT via Windows Package Manager\nRequires winget to be installed",
        )

        self.btn_update_hemtt = ttk.Button(
            winget_frame,
            text="Update HEMTT (winget) ⓘ",
            command=self._update_hemtt,
        )
        self._create_tooltip(
            self.btn_update_hemtt, "Update HEMTT to latest version\nUses Windows Package Manager"
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

        # Separator with title for main commands
        main_separator_frame = ttk.Frame(self, padding=(8, 8, 8, 0))
        main_separator_frame.pack(fill=tk.X)
        ttk.Label(
            main_separator_frame, text="Main Commands", font=("TkDefaultFont", 9, "bold")
        ).pack(anchor=tk.W)
        ttk.Separator(main_separator_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(2, 0))

        # Buttons frame - First row
        btns = ttk.Frame(self, padding=(8, 0))
        btns.pack(fill=tk.X, pady=(4, 0))

        self.btn_check = ttk.Button(btns, text="hemtt check ⓘ", command=self._run_check)
        self._create_tooltip(
            self.btn_check, "Check project for errors\nQuick validation without building files"
        )

        self.btn_dev = ttk.Button(btns, text="hemtt dev ⓘ", command=self._run_dev)
        self._create_tooltip(
            self.btn_dev, "Build for development\nCreates symlinks for file-patching"
        )

        self.btn_launch = ttk.Button(btns, text="hemtt launch ⓘ", command=self._run_launch)
        self._create_tooltip(
            self.btn_launch, "Build and launch Arma 3\nAutomatically loads mods and dependencies"
        )

        self.btn_build = ttk.Button(btns, text="hemtt build ⓘ", command=self._run_build)
        self._create_tooltip(
            self.btn_build, "Build for local testing\nBinarizes files for final testing"
        )

        self.btn_release = ttk.Button(btns, text="hemtt release ⓘ", command=self._run_release)
        self._create_tooltip(
            self.btn_release, "Build for release\nCreates signed PBOs and archives"
        )

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

        # Separator with title for helper commands
        separator_frame = ttk.Frame(self, padding=(8, 8, 8, 0))
        separator_frame.pack(fill=tk.X)
        ttk.Label(separator_frame, text="Helper Commands", font=("TkDefaultFont", 9, "bold")).pack(
            anchor=tk.W
        )
        ttk.Separator(separator_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(2, 0))

        # Buttons frame - Second row
        btns2 = ttk.Frame(self, padding=(8, 4))
        btns2.pack(fill=tk.X)

        self.btn_ln_sort = ttk.Button(btns2, text="hemtt ln sort ⓘ", command=self._run_ln_sort)
        self._create_tooltip(
            self.btn_ln_sort, "Sort stringtable entries\nOrganizes localization keys alphabetically"
        )

        self.btn_ln_coverage = ttk.Button(
            btns2, text="hemtt ln coverage ⓘ", command=self._run_ln_coverage
        )
        self._create_tooltip(
            self.btn_ln_coverage, "Check stringtable coverage\nFinds missing translations"
        )

        self.btn_utils_fnl = ttk.Button(
            btns2, text="hemtt utils fnl ⓘ", command=self._run_utils_fnl
        )
        self._create_tooltip(
            self.btn_utils_fnl,
            "Insert final newline into files if missing\nEnsures files end with newline (POSIX standard)",
        )

        self.btn_utils_bom = ttk.Button(
            btns2, text="hemtt utils bom ⓘ", command=self._run_utils_bom
        )
        self._create_tooltip(
            self.btn_utils_bom,
            "Remove UTF-8 BOM markers from files\nFixes parsing issues caused by Byte Order Marks",
        )

        self.btn_book = ttk.Button(btns2, text="hemtt book ⓘ", command=self._open_book)
        self._create_tooltip(
            self.btn_book, "Open HEMTT documentation\nOpens hemtt.dev in your browser"
        )

        self.btn_ln_sort.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_ln_coverage.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_utils_fnl.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_utils_bom.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_book.pack(side=tk.LEFT)

        # Third row for PAA/PBO utility buttons
        btns3 = ttk.Frame(self, padding=(8, 4))
        btns3.pack(fill=tk.X)

        self.btn_paa_convert = ttk.Button(
            btns3, text="hemtt paa convert ⓘ", command=self._run_paa_convert
        )
        self._create_tooltip(
            self.btn_paa_convert,
            "Convert image to/from PAA format\nSupports PNG, JPEG, BMP, etc.",
        )

        self.btn_paa_inspect = ttk.Button(
            btns3, text="hemtt paa inspect ⓘ", command=self._run_paa_inspect
        )
        self._create_tooltip(
            self.btn_paa_inspect,
            "Inspect a PAA file\nShows PAA properties in various formats",
        )

        self.btn_pbo_inspect = ttk.Button(
            btns3, text="hemtt pbo inspect ⓘ", command=self._run_pbo_inspect
        )
        self._create_tooltip(
            self.btn_pbo_inspect,
            "Inspect a PBO file\nShows PBO properties and contents in various formats",
        )

        self.btn_pbo_unpack = ttk.Button(
            btns3, text="hemtt pbo unpack ⓘ", command=self._run_pbo_unpack
        )
        self._create_tooltip(
            self.btn_pbo_unpack,
            "Unpack a PBO file\nExtracts PBO contents with optional derapification",
        )

        self.btn_paa_convert.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_paa_inspect.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_pbo_inspect.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_pbo_unpack.pack(side=tk.LEFT)

        # Separator with title for utility buttons
        util_separator_frame = ttk.Frame(self, padding=(8, 8, 8, 0))
        util_separator_frame.pack(fill=tk.X)
        ttk.Label(util_separator_frame, text="Utilities", font=("TkDefaultFont", 9, "bold")).pack(
            anchor=tk.W
        )
        ttk.Separator(util_separator_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(2, 0))

        # Utility buttons frame
        util_btns = ttk.Frame(self, padding=(8, 4))
        util_btns.pack(fill=tk.X)

        # Dark mode toggle
        self.btn_dark_mode = ttk.Button(
            util_btns, text="Toggle Dark Mode", command=self._toggle_dark_mode
        )
        self.btn_dark_mode.pack(side=tk.LEFT, padx=(0, 8))

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

        # Configure radiobuttons
        self.style.configure("TRadiobutton", background=theme["bg"], foreground=theme["fg"])
        self.style.map(
            "TRadiobutton",
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
            foreground=[("active", theme["button_fg"]), ("pressed", theme["button_fg"])],
        )

        # Configure checkbuttons
        self.style.configure("TCheckbutton", background=theme["bg"], foreground=theme["fg"])
        self.style.map(
            "TCheckbutton",
            background=[("", theme["bg"])],
            foreground=[("", theme["fg"])],
        )

        # Configure radiobuttons
        self.style.configure("TRadiobutton", background=theme["bg"], foreground=theme["fg"])
        self.style.map(
            "TRadiobutton",
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

    def _run(self, args: list[str], command_type: str = "other", cwd: str | None = None):
        """Start running a HEMTT command with arguments from dialogs.

        Parameters
        ----------
        args: list[str]
            Full arguments after the 'hemtt' executable, including all flags.
        command_type: str
            Type of command for tracking purposes.
        cwd: str | None
            Optional working directory. If None, uses project directory.
        """
        validated = self._validated_paths()
        if not validated:
            return
        hemtt, proj = validated

        # Use provided cwd or default to project directory
        working_dir = cwd if cwd is not None else proj

        # Clear output and persist config
        self.output.configure(state=tk.NORMAL)
        self.output.delete(1.0, tk.END)
        self.output.configure(state=tk.DISABLED)
        self._persist_config()

        cmd = build_command(hemtt, args)
        self._set_running(True, " ".join(cmd))

        self.runner = CommandRunner(
            command=cmd,
            cwd=working_dir,
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
        """Open build dialog and run hemtt build with selected options."""
        dialog = BuildDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            args = ["build"] + dialog.result
            self._run(args, command_type="build")

    def _run_release(self):
        """Open release dialog and run hemtt release with selected options."""
        dialog = ReleaseDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            args = ["release"] + dialog.result
            self._run(args, command_type="release")

    def _run_check(self):
        """Open check dialog and run hemtt check with selected options."""
        dialog = CheckDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            args = ["check"] + dialog.result
            self._run(args, command_type="check")

    def _run_dev(self):
        """Open dev dialog and run hemtt dev with selected options."""
        dialog = DevDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            args = ["dev"] + dialog.result
            self._run(args, command_type="dev")

    def _run_utils_fnl(self):
        """Run 'hemtt utils fnl'."""
        self._run(["utils", "fnl"], command_type="other")

    def _run_utils_bom(self):
        """Run 'hemtt utils bom'."""
        self._run(["utils", "bom"], command_type="other")

    def _run_ln_sort(self):
        """Run 'hemtt ln sort'."""
        self._run(["ln", "sort"], command_type="other")

    def _run_ln_coverage(self):
        """Run 'hemtt ln coverage'."""
        self._run(["ln", "coverage"], command_type="other")

    def _run_paa_convert(self):
        """Open PAA convert dialog and run hemtt utils paa convert with selected files."""
        dialog = PaaConvertDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            args = ["utils", "paa", "convert"] + dialog.result
            # Get the directory of the source file to use as working directory
            src_file = dialog.result[0] if dialog.result else None
            if src_file and os.path.isfile(src_file):
                src_dir = os.path.dirname(os.path.abspath(src_file))
                self._run(args, command_type="other", cwd=src_dir)
            else:
                self._run(args, command_type="other")

    def _run_paa_inspect(self):
        """Open PAA inspect dialog and run hemtt utils paa inspect with selected options."""
        dialog = PaaInspectDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            args = ["utils", "paa", "inspect"] + dialog.result
            # Get the directory of the PAA file to use as working directory
            paa_file = dialog.result[0] if dialog.result else None
            if paa_file and os.path.isfile(paa_file):
                paa_dir = os.path.dirname(os.path.abspath(paa_file))
                self._run(args, command_type="other", cwd=paa_dir)
            else:
                self._run(args, command_type="other")

    def _run_pbo_inspect(self):
        """Open PBO inspect dialog and run hemtt utils pbo inspect with selected options."""
        dialog = PboInspectDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            args = ["utils", "pbo", "inspect"] + dialog.result
            # Get the directory of the PBO file to use as working directory
            pbo_file = dialog.result[0] if dialog.result else None
            if pbo_file and os.path.isfile(pbo_file):
                pbo_dir = os.path.dirname(os.path.abspath(pbo_file))
                self._run(args, command_type="other", cwd=pbo_dir)
            else:
                self._run(args, command_type="other")

    def _run_pbo_unpack(self):
        """Open PBO unpack dialog and run hemtt utils pbo unpack with selected options."""
        dialog = PboUnpackDialog(self)
        self.wait_window(dialog)
        if dialog.result is not None:
            args = ["utils", "pbo", "unpack"] + dialog.result
            # Get the directory of the PBO file to use as working directory
            pbo_file = dialog.result[0] if dialog.result else None
            if pbo_file and os.path.isfile(pbo_file):
                pbo_dir = os.path.dirname(os.path.abspath(pbo_file))
                self._run(args, command_type="other", cwd=pbo_dir)
            else:
                self._run(args, command_type="other")

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
        if dialog.result is not None:
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


class BaseCommandDialog(tk.Toplevel):
    """Base class for HEMTT command configuration dialogs."""

    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        self.parent = parent

        self.transient(parent)
        self.grab_set()

        # Apply dark mode if parent is in dark mode
        if parent.dark_mode:
            self.configure(bg=parent.dark_theme["bg"])

    def _center_on_parent(self):
        """Center the dialog on the parent window."""
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - self.winfo_width()) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_global_options_frame(self) -> ttk.LabelFrame:
        """Create the standard global options frame with verbosity and threads."""
        global_frame = ttk.LabelFrame(self, text="Global Options", padding=10)
        global_frame.pack(fill=tk.X, padx=10, pady=5)

        # Verbosity level
        verbose_frame = ttk.Frame(global_frame)
        verbose_frame.pack(fill=tk.X, pady=2)
        verbose_label = ttk.Label(verbose_frame, text="Verbosity:")
        verbose_label.pack(side=tk.LEFT)
        self.parent._create_tooltip(
            verbose_label, "None: Normal output\n-v: Debug output\n-vv: Trace output"
        )

        self.verbose_var = tk.StringVar(value="none")
        ttk.Radiobutton(verbose_frame, text="None", variable=self.verbose_var, value="none").pack(
            side=tk.LEFT, padx=5
        )
        ttk.Radiobutton(
            verbose_frame, text="-v (Debug)", variable=self.verbose_var, value="v"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(
            verbose_frame, text="-vv (Trace)", variable=self.verbose_var, value="vv"
        ).pack(side=tk.LEFT, padx=5)

        # Threads
        threads_frame = ttk.Frame(global_frame)
        threads_frame.pack(fill=tk.X, pady=2)
        ttk.Label(threads_frame, text="Threads (-t):").pack(side=tk.LEFT)
        self.threads_var = tk.StringVar()
        ttk.Spinbox(threads_frame, from_=1, to=32, textvariable=self.threads_var, width=5).pack(
            side=tk.LEFT, padx=5
        )

        return global_frame

    def _create_button_frame(self, on_run_callback, on_cancel_callback):
        """Create the standard button frame with Run and Cancel buttons."""
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Run", command=on_run_callback).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=on_cancel_callback).pack(side=tk.RIGHT)

    def _add_verbosity_to_args(self, args: list[str]):
        """Add verbosity flags to args based on verbose_var."""
        verbose = self.verbose_var.get()
        if verbose == "v":
            args.append("-v")
        elif verbose == "vv":
            args.extend(["-v", "-v"])

    def _add_threads_to_args(self, args: list[str]):
        """Add threads flag to args if specified."""
        threads = self.threads_var.get().strip()
        if threads:
            args.extend(["-t", threads])

    def _on_cancel(self):
        """Cancel the dialog without setting result."""
        self.result = None
        self.destroy()


class CheckDialog(BaseCommandDialog):
    """Dialog for configuring hemtt check options."""

    def __init__(self, parent):
        super().__init__(parent, "HEMTT Check Configuration")

        # Check options
        options_frame = ttk.LabelFrame(self, text="Check Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        self.pedantic_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Pedantic (-p)", variable=self.pedantic_var).pack(
            anchor=tk.W, pady=2
        )

        # Lints
        lints_frame = ttk.Frame(options_frame)
        lints_frame.pack(fill=tk.X, pady=5)
        ttk.Label(lints_frame, text="Lints (-L):").pack(side=tk.LEFT)
        self.lints_var = tk.StringVar()
        lints_entry = ttk.Entry(lints_frame, textvariable=self.lints_var, width=30)
        lints_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(lints_frame, text="(comma-separated)", font=("TkDefaultFont", 8)).pack(
            side=tk.LEFT
        )

        # Global options
        self._create_global_options_frame()

        # Buttons
        self._create_button_frame(self._on_run, self._on_cancel)

        self._center_on_parent()

    def _on_run(self):
        args = ["check"]

        if self.pedantic_var.get():
            args.append("-p")

        lints = self.lints_var.get().strip()
        if lints:
            for lint in lints.split(","):
                lint = lint.strip()
                if lint:
                    args.extend(["-L", lint])

        self._add_verbosity_to_args(args)
        self._add_threads_to_args(args)

        self.result = args[1:]  # Remove "check" since it's added by caller
        self.destroy()


class DevDialog(BaseCommandDialog):
    """Dialog for configuring hemtt dev options."""

    def __init__(self, parent):
        super().__init__(parent, "HEMTT Dev Configuration")

        # Dev options
        options_frame = ttk.LabelFrame(self, text="Dev Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        self.binarize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Binarize (-b)", variable=self.binarize_var).pack(
            anchor=tk.W, pady=2
        )

        self.no_rap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="No RAP (--no-rap)", variable=self.no_rap_var).pack(
            anchor=tk.W, pady=2
        )

        self.all_optionals_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame, text="All Optionals (-O)", variable=self.all_optionals_var
        ).pack(anchor=tk.W, pady=2)

        # Optional addons
        optional_frame = ttk.Frame(options_frame)
        optional_frame.pack(fill=tk.X, pady=5)
        ttk.Label(optional_frame, text="Optional addons (-o):").pack(side=tk.LEFT)
        self.optional_var = tk.StringVar()
        ttk.Entry(optional_frame, textvariable=self.optional_var, width=30).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Label(optional_frame, text="(comma-separated)", font=("TkDefaultFont", 8)).pack(
            side=tk.LEFT
        )

        # Just
        just_frame = ttk.Frame(options_frame)
        just_frame.pack(fill=tk.X, pady=5)
        ttk.Label(just_frame, text="Just (--just):").pack(side=tk.LEFT)
        self.just_var = tk.StringVar()
        ttk.Entry(just_frame, textvariable=self.just_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Label(just_frame, text="(comma-separated)", font=("TkDefaultFont", 8)).pack(
            side=tk.LEFT
        )

        # Global options
        self._create_global_options_frame()

        # Buttons
        self._create_button_frame(self._on_run, self._on_cancel)

        self._center_on_parent()

    def _on_run(self):
        args = ["dev"]

        if self.binarize_var.get():
            args.append("-b")
        if self.no_rap_var.get():
            args.append("--no-rap")
        if self.all_optionals_var.get():
            args.append("-O")

        optionals = self.optional_var.get().strip()
        if optionals:
            for opt in optionals.split(","):
                opt = opt.strip()
                if opt:
                    args.extend(["-o", opt])

        just = self.just_var.get().strip()
        if just:
            for j in just.split(","):
                j = j.strip()
                if j:
                    args.extend(["--just", j])

        self._add_verbosity_to_args(args)
        self._add_threads_to_args(args)

        self.result = args[1:]  # Remove "dev" since it's added by caller
        self.destroy()


class PaaConvertDialog(tk.Toplevel):
    """Dialog for configuring hemtt utils paa convert options."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("HEMTT PAA Convert")
        self.resizable(False, False)
        self.result = None
        self.parent = parent

        self.transient(parent)
        self.grab_set()

        # Apply dark mode if parent is in dark mode
        if parent.dark_mode:
            self.configure(bg=parent.dark_theme["bg"])

        # Source file selection
        src_frame = ttk.LabelFrame(self, text="Source File (PAA or Image)", padding=10)
        src_frame.pack(fill=tk.X, padx=10, pady=5)

        self.src_var = tk.StringVar()
        src_entry_frame = ttk.Frame(src_frame)
        src_entry_frame.pack(fill=tk.X)
        ttk.Entry(src_entry_frame, textvariable=self.src_var, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(src_entry_frame, text="Browse...", command=self._browse_src).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # Destination file selection
        dest_frame = ttk.LabelFrame(self, text="Destination File (PAA or Image)", padding=10)
        dest_frame.pack(fill=tk.X, padx=10, pady=5)

        self.dest_var = tk.StringVar()
        dest_entry_frame = ttk.Frame(dest_frame)
        dest_entry_frame.pack(fill=tk.X)
        ttk.Entry(dest_entry_frame, textvariable=self.dest_var, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(dest_entry_frame, text="Browse...", command=self._browse_dest).pack(
            side=tk.LEFT, padx=(5, 0)
        )
        ttk.Label(
            dest_frame,
            text="Supports: PNG, JPEG, BMP, PAA (detected by extension)",
            font=("TkDefaultFont", 8),
        ).pack(anchor=tk.W, pady=(5, 0))

        # Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Convert", command=self._on_convert).pack(
            side=tk.RIGHT, padx=(5, 0)
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT)

        self._center_on_parent()
        self._setup_dnd()

    def _setup_dnd(self):
        """Setup drag and drop for image/PAA files."""
        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)  # type: ignore
                self.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore
            except Exception:
                pass

    def _on_drop(self, event):
        """Handle file drops."""
        files = self.tk.splitlist(event.data)
        if files:
            file_path = files[0].strip("{}").strip()
            # Set as source if empty, otherwise destination
            if not self.src_var.get():
                self.src_var.set(file_path)
            elif not self.dest_var.get():
                self.dest_var.set(file_path)

    def _browse_src(self):
        """Open file dialog to select source file."""
        filename = filedialog.askopenfilename(
            parent=self,
            title="Select source file",
            filetypes=[
                ("PAA files", "*.paa"),
                ("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.tga"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.src_var.set(filename)

    def _browse_dest(self):
        """Open file dialog to select destination file."""
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Select destination file",
            filetypes=[
                ("PAA files", "*.paa"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg;*.jpeg"),
                ("BMP files", "*.bmp"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.dest_var.set(filename)

    def _center_on_parent(self):
        """Center the dialog on the parent window."""
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - self.winfo_width()) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _on_convert(self):
        """Validate inputs and build command arguments."""
        src_file = self.src_var.get().strip()
        dest_file = self.dest_var.get().strip()

        if not src_file:
            messagebox.showerror("Error", "Please select a source file", parent=self)
            return
        if not dest_file:
            messagebox.showerror("Error", "Please select a destination file", parent=self)
            return

        self.result = [src_file, dest_file]
        self.destroy()

    def _on_cancel(self):
        """Cancel the dialog without setting result."""
        self.result = None
        self.destroy()


class PaaInspectDialog(tk.Toplevel):
    """Dialog for configuring hemtt utils paa inspect options."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("HEMTT PAA Inspect")
        self.resizable(False, False)
        self.result = None
        self.parent = parent

        self.transient(parent)
        self.grab_set()

        # Apply dark mode if parent is in dark mode
        if parent.dark_mode:
            self.configure(bg=parent.dark_theme["bg"])

        # PAA file selection
        paa_frame = ttk.LabelFrame(self, text="PAA File", padding=10)
        paa_frame.pack(fill=tk.X, padx=10, pady=5)

        self.paa_var = tk.StringVar()
        paa_entry_frame = ttk.Frame(paa_frame)
        paa_entry_frame.pack(fill=tk.X)
        ttk.Entry(paa_entry_frame, textvariable=self.paa_var, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(paa_entry_frame, text="Browse...", command=self._browse_paa).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # Format selection
        format_frame = ttk.LabelFrame(self, text="Output Format", padding=10)
        format_frame.pack(fill=tk.X, padx=10, pady=5)

        self.format_var = tk.StringVar(value="ascii")
        format_options = [
            ("ASCII Table (default)", "ascii"),
            ("JSON (compact)", "json"),
            ("Pretty JSON", "pretty-json"),
            ("Markdown Table", "markdown"),
        ]
        
        for text, value in format_options:
            ttk.Radiobutton(
                format_frame, text=text, variable=self.format_var, value=value
            ).pack(anchor=tk.W, pady=2)

        # Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Inspect", command=self._on_inspect).pack(
            side=tk.RIGHT, padx=(5, 0)
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT)

        self._center_on_parent()
        self._setup_paa_dnd()

    def _setup_paa_dnd(self):
        """Setup drag and drop for PAA files."""
        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)  # type: ignore
                self.dnd_bind("<<Drop>>", self._on_paa_drop)  # type: ignore
            except Exception:
                pass

    def _on_paa_drop(self, event):
        """Handle PAA file drops."""
        files = self.tk.splitlist(event.data)
        if files:
            file_path = files[0].strip("{}").strip()
            if file_path.lower().endswith(".paa"):
                self.paa_var.set(file_path)
            else:
                messagebox.showwarning("Invalid File", "Please drop a .paa file", parent=self)

    def _browse_paa(self):
        """Open file dialog to select a PAA file."""
        filename = filedialog.askopenfilename(
            parent=self,
            title="Select PAA file",
            filetypes=[("PAA files", "*.paa"), ("All files", "*.*")],
        )
        if filename:
            self.paa_var.set(filename)

    def _center_on_parent(self):
        """Center the dialog on the parent window."""
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - self.winfo_width()) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _on_inspect(self):
        """Validate inputs and build command arguments."""
        paa_file = self.paa_var.get().strip()
        if not paa_file:
            messagebox.showerror("Error", "Please select a PAA file", parent=self)
            return

        args = [paa_file]

        # Add format option if not default
        format_choice = self.format_var.get()
        if format_choice != "ascii":
            args.extend(["--format", format_choice])

        self.result = args
        self.destroy()

    def _on_cancel(self):
        """Cancel the dialog without setting result."""
        self.result = None
        self.destroy()


class PboInspectDialog(tk.Toplevel):
    """Dialog for configuring hemtt utils pbo inspect options."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("HEMTT PBO Inspect")
        self.resizable(False, False)
        self.result = None
        self.parent = parent

        self.transient(parent)
        self.grab_set()

        # Apply dark mode if parent is in dark mode
        if parent.dark_mode:
            self.configure(bg=parent.dark_theme["bg"])

        # PBO file selection
        pbo_frame = ttk.LabelFrame(self, text="PBO File", padding=10)
        pbo_frame.pack(fill=tk.X, padx=10, pady=5)

        self.pbo_var = tk.StringVar()
        pbo_entry_frame = ttk.Frame(pbo_frame)
        pbo_entry_frame.pack(fill=tk.X)
        ttk.Entry(pbo_entry_frame, textvariable=self.pbo_var, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(pbo_entry_frame, text="Browse...", command=self._browse_pbo).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # Format selection
        format_frame = ttk.LabelFrame(self, text="Output Format", padding=10)
        format_frame.pack(fill=tk.X, padx=10, pady=5)

        self.format_var = tk.StringVar(value="ascii")
        format_options = [
            ("ASCII Table (default)", "ascii"),
            ("JSON (compact)", "json"),
            ("Pretty JSON", "pretty-json"),
            ("Markdown Table", "markdown"),
        ]

        for text, value in format_options:
            ttk.Radiobutton(format_frame, text=text, variable=self.format_var, value=value).pack(
                anchor=tk.W, pady=2
            )

        # Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Inspect", command=self._on_inspect).pack(
            side=tk.RIGHT, padx=(5, 0)
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT)

        self._center_on_parent()
        self._setup_pbo_dnd()

    def _setup_pbo_dnd(self):
        """Setup drag and drop for PBO files."""
        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)  # type: ignore
                self.dnd_bind("<<Drop>>", self._on_pbo_drop)  # type: ignore
            except Exception:
                pass

    def _on_pbo_drop(self, event):
        """Handle PBO file drops."""
        files = self.tk.splitlist(event.data)
        if files:
            file_path = files[0].strip("{}").strip()
            if file_path.lower().endswith(".pbo"):
                self.pbo_var.set(file_path)
            else:
                messagebox.showwarning("Invalid File", "Please drop a .pbo file", parent=self)

    def _browse_pbo(self):
        """Open file dialog to select a PBO file."""
        filename = filedialog.askopenfilename(
            parent=self,
            title="Select PBO file",
            filetypes=[("PBO files", "*.pbo"), ("All files", "*.*")],
        )
        if filename:
            self.pbo_var.set(filename)

    def _center_on_parent(self):
        """Center the dialog on the parent window."""
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - self.winfo_width()) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _on_inspect(self):
        """Validate inputs and build command arguments."""
        pbo_file = self.pbo_var.get().strip()
        if not pbo_file:
            messagebox.showerror("Error", "Please select a PBO file", parent=self)
            return

        args = [pbo_file]

        # Add format option if not default
        format_choice = self.format_var.get()
        if format_choice != "ascii":
            args.extend(["--format", format_choice])

        self.result = args
        self.destroy()

    def _on_cancel(self):
        """Cancel the dialog without setting result."""
        self.result = None
        self.destroy()


class PboUnpackDialog(tk.Toplevel):
    """Dialog for configuring hemtt utils pbo unpack options."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("HEMTT PBO Unpack")
        self.resizable(False, False)
        self.result = None
        self.parent = parent

        self.transient(parent)
        self.grab_set()

        # Apply dark mode if parent is in dark mode
        if parent.dark_mode:
            self.configure(bg=parent.dark_theme["bg"])

        # PBO file selection
        pbo_frame = ttk.LabelFrame(self, text="PBO File", padding=10)
        pbo_frame.pack(fill=tk.X, padx=10, pady=5)

        self.pbo_var = tk.StringVar()
        pbo_entry_frame = ttk.Frame(pbo_frame)
        pbo_entry_frame.pack(fill=tk.X)
        ttk.Entry(pbo_entry_frame, textvariable=self.pbo_var, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(pbo_entry_frame, text="Browse...", command=self._browse_pbo).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # Output directory selection
        output_frame = ttk.LabelFrame(self, text="Output Directory (Optional)", padding=10)
        output_frame.pack(fill=tk.X, padx=10, pady=5)

        self.output_var = tk.StringVar()
        output_entry_frame = ttk.Frame(output_frame)
        output_entry_frame.pack(fill=tk.X)
        ttk.Entry(output_entry_frame, textvariable=self.output_var, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(output_entry_frame, text="Browse...", command=self._browse_output).pack(
            side=tk.LEFT, padx=(5, 0)
        )
        ttk.Label(
            output_frame,
            text="If not specified, creates a directory named after the PBO file",
            font=("TkDefaultFont", 8),
        ).pack(anchor=tk.W, pady=(5, 0))

        # Options
        options_frame = ttk.LabelFrame(self, text="Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        self.derap_var = tk.BooleanVar(value=False)
        derap_cb = ttk.Checkbutton(
            options_frame,
            text="Derapify rapified files (-r / --derap)",
            variable=self.derap_var,
        )
        derap_cb.pack(anchor=tk.W, pady=2)
        parent._create_tooltip(
            derap_cb,
            "Automatically converts binary config files (config.bin, etc.)\nback to readable format",
        )

        # Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Unpack", command=self._on_unpack).pack(
            side=tk.RIGHT, padx=(5, 0)
        )
        ttk.Button(btn_frame, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT)

        self._center_on_parent()
        self._setup_pbo_dnd()

    def _setup_pbo_dnd(self):
        """Setup drag and drop for PBO files."""
        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)  # type: ignore
                self.dnd_bind("<<Drop>>", self._on_pbo_drop)  # type: ignore
            except Exception:
                pass

    def _on_pbo_drop(self, event):
        """Handle PBO file drops."""
        files = self.tk.splitlist(event.data)
        if files:
            file_path = files[0].strip("{}").strip()
            if file_path.lower().endswith(".pbo"):
                self.pbo_var.set(file_path)
            else:
                messagebox.showwarning("Invalid File", "Please drop a .pbo file", parent=self)

    def _browse_pbo(self):
        """Open file dialog to select a PBO file."""
        filename = filedialog.askopenfilename(
            parent=self,
            title="Select PBO file",
            filetypes=[("PBO files", "*.pbo"), ("All files", "*.*")],
        )
        if filename:
            self.pbo_var.set(filename)

    def _browse_output(self):
        """Open directory dialog to select output directory."""
        dirname = filedialog.askdirectory(parent=self, title="Select output directory")
        if dirname:
            self.output_var.set(dirname)

    def _center_on_parent(self):
        """Center the dialog on the parent window."""
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - self.winfo_width()) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _on_unpack(self):
        """Validate inputs and build command arguments."""
        pbo_file = self.pbo_var.get().strip()
        if not pbo_file:
            messagebox.showerror("Error", "Please select a PBO file", parent=self)
            return

        args = [pbo_file]

        output_dir = self.output_var.get().strip()
        if output_dir:
            args.append(output_dir)

        if self.derap_var.get():
            args.append("--derap")

        self.result = args
        self.destroy()

    def _on_cancel(self):
        """Cancel the dialog without setting result."""
        self.result = None
        self.destroy()


class BuildDialog(BaseCommandDialog):
    """Dialog for configuring hemtt build options."""

    def __init__(self, parent):
        super().__init__(parent, "HEMTT Build Configuration")

        # Build options
        options_frame = ttk.LabelFrame(self, text="Build Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        self.no_bin_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame, text="No Binarize (--no-bin)", variable=self.no_bin_var
        ).pack(anchor=tk.W, pady=2)

        self.no_rap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="No RAP (--no-rap)", variable=self.no_rap_var).pack(
            anchor=tk.W, pady=2
        )

        # Just
        just_frame = ttk.Frame(options_frame)
        just_frame.pack(fill=tk.X, pady=5)
        ttk.Label(just_frame, text="Just (--just):").pack(side=tk.LEFT)
        self.just_var = tk.StringVar()
        ttk.Entry(just_frame, textvariable=self.just_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Label(just_frame, text="(comma-separated)", font=("TkDefaultFont", 8)).pack(
            side=tk.LEFT
        )

        # Global options
        self._create_global_options_frame()

        # Buttons
        self._create_button_frame(self._on_run, self._on_cancel)

        self._center_on_parent()

    def _on_run(self):
        args = ["build"]

        if self.no_bin_var.get():
            args.append("--no-bin")
        if self.no_rap_var.get():
            args.append("--no-rap")

        just = self.just_var.get().strip()
        if just:
            for j in just.split(","):
                j = j.strip()
                if j:
                    args.extend(["--just", j])

        self._add_verbosity_to_args(args)
        self._add_threads_to_args(args)

        self.result = args[1:]  # Remove "build" since it's added by caller
        self.destroy()


class ReleaseDialog(BaseCommandDialog):
    """Dialog for configuring hemtt release options."""

    def __init__(self, parent):
        super().__init__(parent, "HEMTT Release Configuration")

        # Release options
        options_frame = ttk.LabelFrame(self, text="Release Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        self.no_bin_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame, text="No Binarize (--no-bin)", variable=self.no_bin_var
        ).pack(anchor=tk.W, pady=2)

        self.no_rap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="No RAP (--no-rap)", variable=self.no_rap_var).pack(
            anchor=tk.W, pady=2
        )

        self.no_sign_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="No Sign (--no-sign)", variable=self.no_sign_var).pack(
            anchor=tk.W, pady=2
        )

        self.no_archive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame, text="No Archive (--no-archive)", variable=self.no_archive_var
        ).pack(anchor=tk.W, pady=2)

        # Global options
        self._create_global_options_frame()

        # Buttons
        self._create_button_frame(self._on_run, self._on_cancel)

        self._center_on_parent()

    def _on_run(self):
        args = ["release"]

        if self.no_bin_var.get():
            args.append("--no-bin")
        if self.no_rap_var.get():
            args.append("--no-rap")
        if self.no_sign_var.get():
            args.append("--no-sign")
        if self.no_archive_var.get():
            args.append("--no-archive")

        self._add_verbosity_to_args(args)
        self._add_threads_to_args(args)

        self.result = args[1:]  # Remove "release" since it's added by caller
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

        # Apply dark mode if parent is in dark mode
        if parent.dark_mode:
            self.configure(bg=parent.dark_theme["bg"])

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
        ttk.Checkbutton(options_frame, text="Binarize files (-b)", variable=self.binarize_var).pack(
            anchor=tk.W, pady=2
        )

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
