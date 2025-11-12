# HEMTT GUI

A lightweight cross-platform (Windows-focused) Tkinter GUI wrapper for the `hemtt` CLI tool.

## Features

- Run common commands: `hemtt build`, `hemtt release`, `hemtt ln sort` via buttons.
- Run arbitrary custom command arguments (see [hemtt Book](http://hemtt.dev)).
- Live streaming output pane with scrolling.
- Cancel running command.
- Select `hemtt` executable and project directory; persisted locally to `config.json`.
- Elapsed time and status bar.

## Requirements

- Python 3.11+ (3.9+ may work; not tested).
- `hemtt` installed and available in PATH, or you can browse to an executable.

Tkinter ships with the standard CPython distribution; no external dependencies required.

## Running

```pwsh
python hemtt_gui.py
```

Use the Browse buttons to set your project directory and (optionally) the `hemtt` executable path.

## Custom Commands

Enter additional arguments exactly as you would after `hemtt` on the CLI. Example:

```text
validate
```

Then press Run.

## Packaging (Windows executable)

Using PyInstaller to create a single-folder distribution:

```pwsh
pip install pyinstaller
pyinstaller --name HemttGUI --windowed --onefile hemtt_gui.py
```

This will produce `dist/HemttGUI.exe`. Distribute that file along with a README if desired.

If you need to embed an icon:

```pwsh
pyinstaller --name HemttGUI --windowed --onefile --icon=icon.ico hemtt_gui.py
```

## Code Structure

- `hemtt_gui.py` – Main Tkinter application.
- `command_runner.py` – Background process runner & output streaming.
- `config_store.py` – Simple JSON config persistence.
- `tests.py` – Basic helper tests.

## GitHub Actions: Build on Release

This repository includes a workflow at `.github/workflows/release.yml` that:

- Builds the Windows executable with PyInstaller
- Attaches the `HemttGUI.exe` artifact to the GitHub Release

Trigger it by publishing a new Release in GitHub (or run manually via the Actions tab). Ensure Actions are enabled and the default `GITHUB_TOKEN` has `contents: write` (the workflow sets this).

## Limitations / Future Improvements

- No progress bar (HEMTT doesn't emit structured progress; could parse lines heuristically).
- Could support a list of favorite custom commands.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `hemtt` not found | Ensure it's installed or browse to executable. |
| GUI freezes | Shouldn't happen; output is threaded. Report the issue. |
| No output until end | Some commands may buffer; consider adding `--no-buffer` if supported. |

## License

[MIT LICENSE](LICENSE)
