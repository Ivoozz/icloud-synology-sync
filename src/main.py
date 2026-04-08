import sys
import argparse
import logging
from src.ui import SyncAppUI
from src.config import ConfigManager
from src.engine import SyncEngine
from src.icloud_api import ICloudPhotosAPI
from src.synology_api import SynologyPhotosAPI
from src.database import SyncDatabase

def run_cli():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("Running in CLI mode...")
    
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

    photos = icloud_api.list_photos()
    logging.info(f"Found {len(photos)} photos in iCloud.")
    
    engine.reconcile(photos)
    logging.info("Sync completed.")

def main():
    parser = argparse.ArgumentParser(description="iCloud to Synology Sync")
    parser.add_argument("--cli", action="store_true", help="Run a single sync in CLI mode")
    args = parser.parse_args()

    if args.cli:
        run_cli()
    else:
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
