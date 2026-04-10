import sys
import argparse
import logging
import os

_STREAM_HANDLES = []


def _ensure_standard_streams() -> None:
    # In PyInstaller --windowed mode, stdio can be None; some deps call .isatty().
    if sys.stdin is None:
        handle = open(os.devnull, "r", encoding="utf-8", errors="ignore")
        _STREAM_HANDLES.append(handle)
        sys.stdin = handle
    if sys.stdout is None:
        handle = open(os.devnull, "w", encoding="utf-8", errors="ignore")
        _STREAM_HANDLES.append(handle)
        sys.stdout = handle
    if sys.stderr is None:
        handle = open(os.devnull, "w", encoding="utf-8", errors="ignore")
        _STREAM_HANDLES.append(handle)
        sys.stderr = handle

def run_cli():
    from src.version import APP_NAME, APP_VERSION
    from src.config import ConfigManager
    from src.engine import SyncEngine
    from src.icloud_api import ICloudPhotosAPI
    from src.synology_api import SynologyPhotosAPI
    from src.database import SyncDatabase

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f"Running in CLI mode for {APP_NAME} {APP_VERSION}...")
    
    config_manager = ConfigManager()
    data = config_manager.data
    db = SyncDatabase()

    nas_pass = config_manager.get_credential("nas_password")
    apple_pass = config_manager.get_credential("apple_password")

    if not all([data.get("nas_ip"), data.get("nas_user"), nas_pass, data.get("apple_id"), apple_pass]):
        logging.error("Missing configuration. Please run the UI first to save settings.")
        sys.exit(1)

    icloud_api = ICloudPhotosAPI(data["apple_id"], apple_pass)
    if not icloud_api.login():
        if icloud_api.requires_2fa:
            print("Two-factor authentication required for iCloud.")
            print("If no push appears, generate a code on a trusted Apple device:")
            print("Settings > [your name] > Sign-In & Security > Get Verification Code")
            code = input("Enter the 2FA code from your Apple device: ").strip()
            if not icloud_api.verify_2fa(code):
                logging.error("iCloud 2FA verification failed.")
                sys.exit(1)
        elif icloud_api.requires_2sa:
            print("Two-step authentication required for iCloud.")
            if not icloud_api.send_2sa_verification_code(device_index=0):
                logging.error(f"Failed to send 2SA code: {icloud_api.last_error}")
                sys.exit(1)
            code = input("Enter the verification code received on your trusted device: ").strip()
            if not icloud_api.verify_2sa(code, device_index=0):
                logging.error("iCloud 2SA verification failed.")
                sys.exit(1)
        else:
            logging.error("iCloud login failed.")
            sys.exit(1)

    syno_api = SynologyPhotosAPI(data["nas_ip"], data["nas_user"], nas_pass)
    if not syno_api.login():
        logging.error("Synology login failed.")
        sys.exit(1)

    engine = SyncEngine(
        icloud_api=icloud_api,
        syno_api=syno_api,
        db=db,
        enable_nas_to_icloud_deletion=data.get("enable_nas_to_icloud_deletion", False)
    )

    photos = icloud_api.list_photo_records()
    logging.info(f"Found {len(photos)} photos in iCloud.")
    
    engine.reconcile(photos)
    logging.info("Sync completed.")

def main():
    _ensure_standard_streams()

    from src.version import APP_NAME, APP_VERSION

    parser = argparse.ArgumentParser(description=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument("--cli", action="store_true", help="Run a single sync in CLI mode")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    args = parser.parse_args()

    if args.cli:
        run_cli()
    else:
        from src.ui import SyncAppUI

        # Check if we are in a headless environment
        try:
            app = SyncAppUI()
            app.mainloop()
        except Exception as e:
            logging.error(f"Failed to start UI: {e}")
            logging.info("Falling back to CLI mode if possible or exiting.")
            sys.exit(1)

if __name__ == "__main__":
    main()
