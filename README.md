# iCloud to Synology Sync

Windows desktop app for streaming iCloud Photos directly to Synology Photos without writing temporary files to disk.

## Features

- Memory-only photo streaming from iCloud to Synology
- Safe reconciliation with heartbeat protection
- Optional reverse deletion from Synology to iCloud
- Automatic sync scheduling
- Tray/minimize-to-background mode
- Sync history with event filtering
- Encrypted credential storage through Windows Credential Manager

## Requirements

- Windows 10 or Windows 11
- Python 3.14 or newer for local development
- No separate WiX installation is required for the default build flow; the MSI script downloads a portable WiX 3.14.1 toolset automatically.

## Install from Source

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Launch the app:

```powershell
python -m src.main
```

## Build the EXE

Build the standalone executable with:

```powershell
.\build_exe.ps1
```

The compiled file is written to `dist\iCloudSynoSync.exe`.

## Build the MSI Installer

The MSI packages the built EXE, creates a desktop shortcut, and registers the app in Windows through installer registration and App Paths registry entries.

Build command:

```powershell
.\installer\build_msi.ps1
```

The MSI is written to `dist\installer\iCloudSynoSync.msi`.

If WiX is not already installed, the script downloads a portable WiX 3.14.1 binary package to the user profile and uses that automatically.

The MSI installs per-user, so it can be tested without administrator privileges.

## Build Everything

Build the EXE and MSI in one command:

```powershell
.\build_all.ps1
```

This is the recommended path when you want all release artifacts generated automatically.

## Run Tests

Run the full focused test set with:

```powershell
python -m pytest tests\test_engine.py tests\test_database.py tests\test_config.py tests\test_icloud_api.py tests\test_synology_api.py
```

## Notes

- Tray support requires `pystray` and `pillow`.
- The config file is versioned and migrated automatically when newer defaults are introduced.
- The application version is defined in `src/version.py` and is reused by the UI, CLI, and MSI build.
- Run `python -m src.main --version` to see the current app version.
- Credentials are stored in the system credential store, not in plain text config.