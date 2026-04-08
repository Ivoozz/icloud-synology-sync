import customtkinter as ctk
import threading
import logging
from src.config import ConfigManager
from src.engine import SyncEngine
from src.icloud_api import ICloudPhotosAPI
from src.synology_api import SynologyPhotosAPI
from src.database import SyncDatabase

# Custom logging handler to redirect logs to the UI
class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.after(0, self.append_log, msg)

    def append_log(self, msg):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", msg + "\n")
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")

class SyncAppUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("iCloud to Synology Sync")
        self.geometry("700x850")

        self.config_manager = ConfigManager()
        self.db = SyncDatabase()

        self._setup_ui()
        self._load_settings()
        self._setup_logging()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(self, text="iCloud Synology Sync Settings", font=("Arial", 20, "bold")).grid(row=0, column=0, pady=20)

        # NAS Settings
        self.nas_ip = self._create_entry("NAS IP:", 1)
        self.nas_user = self._create_entry("NAS User:", 2)
        self.nas_pass = self._create_entry("NAS Password:", 3, show="*")

        # iCloud Settings
        self.apple_id = self._create_entry("Apple ID:", 4)
        self.apple_pass = self._create_entry("App-Specific Password:", 5, show="*")

        # Sync Settings
        self.sync_interval = self._create_entry("Sync Interval (min):", 6)
        
        self.enable_deletion = ctk.CTkSwitch(self, text="Enable NAS Deletion -> iCloud")
        self.enable_deletion.grid(row=7, column=0, padx=20, pady=10, sticky="w")

        # Buttons
        button_frame = ctk.CTkFrame(self)
        button_frame.grid(row=8, column=0, padx=20, pady=20, sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.save_button = ctk.CTkButton(button_frame, text="Save Settings", command=self._save_settings)
        self.save_button.grid(row=0, column=0, padx=10, pady=10)

        self.sync_button = ctk.CTkButton(button_frame, text="Sync Now", command=self._start_sync)
        self.sync_button.grid(row=0, column=1, padx=10, pady=10)

        # Log output
        ctk.CTkLabel(self, text="Logs:", font=("Arial", 14, "bold")).grid(row=9, column=0, padx=20, sticky="w")
        self.log_output = ctk.CTkTextbox(self, state="disabled")
        self.log_output.grid(row=10, column=0, padx=20, pady=(0, 20), sticky="nsew")

    def _create_entry(self, label_text, row, **kwargs):
        frame = ctk.CTkFrame(self)
        frame.grid(row=row, column=0, padx=20, pady=5, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)
        
        label = ctk.CTkLabel(frame, text=label_text, width=150, anchor="w")
        label.grid(row=0, column=0, padx=10, pady=5)
        
        entry = ctk.CTkEntry(frame, **kwargs)
        entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        return entry

    def _setup_logging(self):
        handler = TextHandler(self.log_output)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _load_settings(self):
        data = self.config_manager.data
        self.nas_ip.insert(0, data.get("nas_ip", ""))
        self.nas_user.insert(0, data.get("nas_user", ""))
        self.apple_id.insert(0, data.get("apple_id", ""))
        self.sync_interval.insert(0, str(data.get("sync_interval_minutes", 30)))
        
        if data.get("enable_nas_to_icloud_deletion", False):
            self.enable_deletion.select()
        else:
            self.enable_deletion.deselect()

        # Load passwords from keyring
        nas_pass = self.config_manager.get_credential("nas_password")
        if nas_pass:
            self.nas_pass.insert(0, nas_pass)
        
        apple_pass = self.config_manager.get_credential("apple_password")
        if apple_pass:
            self.apple_pass.insert(0, apple_pass)

    def _save_settings(self):
        self.config_manager.data["nas_ip"] = self.nas_ip.get()
        self.config_manager.data["nas_user"] = self.nas_user.get()
        self.config_manager.data["apple_id"] = self.apple_id.get()
        try:
            self.config_manager.data["sync_interval_minutes"] = int(self.sync_interval.get())
        except ValueError:
            logging.error("Invalid sync interval. Must be an integer.")
            return

        self.config_manager.data["enable_nas_to_icloud_deletion"] = self.enable_deletion.get() == 1
        
        self.config_manager.save()
        
        # Save passwords to keyring
        self.config_manager.set_credential("nas_password", self.nas_pass.get())
        self.config_manager.set_credential("apple_password", self.apple_pass.get())
        
        logging.info("Settings saved successfully.")

    def _start_sync(self):
        self.sync_button.configure(state="disabled")
        threading.Thread(target=self._run_sync, daemon=True).start()

    def _run_sync(self):
        try:
            logging.info("Starting sync process...")
            
            icloud_api = ICloudPhotosAPI(self.apple_id.get(), self.apple_pass.get())
            if not icloud_api.login():
                logging.error("iCloud login failed.")
                return

            syno_api = SynologyPhotosAPI(self.nas_ip.get(), self.nas_user.get(), self.nas_pass.get())
            if not syno_api.login():
                logging.error("Synology login failed.")
                return

            engine = SyncEngine(
                icloud_api=icloud_api,
                syno_api=syno_api,
                db=self.db,
                enable_nas_to_icloud_deletion=(self.enable_deletion.get() == 1)
            )

            photos = icloud_api.list_photos()
            logging.info(f"Found {len(photos)} photos in iCloud.")
            
            engine.reconcile(photos)
            
            logging.info("Sync process completed.")
        except Exception as e:
            logging.error(f"Sync failed with error: {e}")
        finally:
            self.sync_button.after(0, lambda: self.sync_button.configure(state="normal"))

if __name__ == "__main__":
    app = SyncAppUI()
    app.mainloop()
