APP_NAME = "iCloud to Synology Sync"
APP_VERSION = "1.0.2"


def to_installer_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) == 3:
        return f"{version}.0"
    if len(parts) == 4:
        return version
    raise ValueError(f"Unsupported version format: {version}")


INSTALLER_VERSION = to_installer_version(APP_VERSION)
__version__ = APP_VERSION


def build_about_text() -> str:
    return (
        f"{APP_NAME} {APP_VERSION}\n\n"
        "Streams iCloud Photos to Synology Photos without writing temporary files to disk.\n\n"
        "Tray support requires pystray and pillow."
    )