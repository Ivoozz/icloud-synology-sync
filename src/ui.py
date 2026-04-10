import customtkinter as ctk
import threading
import logging
import sys
from tkinter import messagebox, simpledialog
from datetime import datetime
from src.version import APP_NAME, APP_VERSION, build_about_text
from src.config import ConfigManager
from src.engine import SyncEngine
from src.icloud_api import ICloudPhotosAPI
from src.synology_api import SynologyPhotosAPI
from src.database import SyncDatabase

try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except ImportError:
    pystray = None
    Image = None
    ImageDraw = None
    PYSTRAY_AVAILABLE = False

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
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("980x900")
        self.minsize(900, 800)

        self.config_manager = ConfigManager()
        self.db = SyncDatabase()
        self._busy = False
        self._auto_sync_job = None
        self._auto_sync_enabled = False
        self._tray_icon = None
        self._tray_thread = None
        self._hidden_to_tray = False
        self._history_event_type = "All"
        self._pause_event = threading.Event()

        self._setup_ui()
        self._load_settings()
        self._setup_logging()
        self._refresh_history()
        self._maybe_schedule_auto_sync()
        self.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        self.bind("<Unmap>", self._on_unmap)

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, corner_radius=18)
        header.grid(row=0, column=0, padx=24, pady=(24, 12), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text=f"{APP_NAME}", font=("Segoe UI Semibold", 28)).grid(row=0, column=0, padx=24, pady=(24, 4), sticky="w")
        ctk.CTkLabel(header, text=f"Version {APP_VERSION} • Encrypted credentials, memory-only transfers, and safer reconciliation.", font=("Segoe UI", 14)).grid(row=1, column=0, padx=24, pady=(0, 16), sticky="w")

        status_row = ctk.CTkFrame(header, fg_color="transparent")
        status_row.grid(row=2, column=0, padx=24, pady=(0, 20), sticky="ew")
        status_row.grid_columnconfigure((0, 1), weight=1)

        self.status_chip = ctk.CTkLabel(status_row, text="Ready", corner_radius=14, fg_color=("#E8F5E9", "#16361D"), text_color=("#1B5E20", "#A5D6A7"), padx=14, pady=8)
        self.status_chip.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(status_row, text="Save once, then sync from the dashboard.", font=("Segoe UI", 12)).grid(row=0, column=1, sticky="e")

        body = ctk.CTkFrame(self, corner_radius=18)
        body.grid(row=1, column=0, padx=24, pady=(0, 24), sticky="nsew")
        body.grid_columnconfigure((0, 1), weight=1)
        body.grid_rowconfigure(1, weight=1)

        connection_card = ctk.CTkFrame(body, corner_radius=16)
        connection_card.grid(row=0, column=0, padx=(20, 10), pady=(20, 10), sticky="nsew")
        connection_card.grid_columnconfigure(0, weight=1)
        self._section_title(connection_card, "Connections")

        self.nas_ip = self._create_entry(connection_card, "NAS IP", 1, placeholder="192.168.1.10")
        self.nas_user = self._create_entry(connection_card, "NAS User", 2, placeholder="admin")
        self.nas_pass = self._create_entry(connection_card, "NAS Password", 3, show="*", placeholder="Stored securely")
        self.apple_id = self._create_entry(connection_card, "Apple ID", 4, placeholder="name@example.com")
        self.apple_pass = self._create_entry(connection_card, "Apple Password", 5, show="*", placeholder="Stored securely")

        sync_card = ctk.CTkFrame(body, corner_radius=16)
        sync_card.grid(row=0, column=1, padx=(10, 20), pady=(20, 10), sticky="nsew")
        sync_card.grid_columnconfigure(0, weight=1)
        self._section_title(sync_card, "Sync Behavior")

        self.sync_interval = self._create_entry(sync_card, "Sync Interval (min)", 1, placeholder="30")
        self.sync_workers = self._create_entry(sync_card, "Parallel uploads", 2, placeholder="4")
        self.max_retries = self._create_entry(sync_card, "Max upload retries", 3, placeholder="3")
        self.queue_batch_size = self._create_entry(sync_card, "Queue batch size", 4, placeholder="50")

        self.auto_sync_enabled = ctk.CTkSwitch(sync_card, text="Enable automatic sync")
        self.auto_sync_enabled.grid(row=5, column=0, padx=18, pady=(8, 4), sticky="w")

        self.enable_deletion = ctk.CTkSwitch(sync_card, text="Allow Synology deletions to remove items from iCloud")
        self.enable_deletion.grid(row=6, column=0, padx=18, pady=(8, 16), sticky="w")

        action_bar = ctk.CTkFrame(sync_card, fg_color="transparent")
        action_bar.grid(row=7, column=0, padx=18, pady=(4, 10), sticky="ew")
        action_bar.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.save_button = ctk.CTkButton(action_bar, text="Save settings", command=self._save_settings, height=40)
        self.save_button.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.sync_button = ctk.CTkButton(action_bar, text="Sync now", command=self._start_sync, height=40)
        self.sync_button.grid(row=0, column=1, padx=(8, 0), sticky="ew")

        self.pause_button = ctk.CTkButton(action_bar, text="Pause", command=self._toggle_pause, height=40, state="disabled")
        self.pause_button.grid(row=0, column=2, padx=(8, 0), sticky="ew")

        self.about_button = ctk.CTkButton(action_bar, text="About", command=self._show_about_dialog, height=40)
        self.about_button.grid(row=0, column=3, padx=(8, 0), sticky="ew")

        self.sync_progress_label = ctk.CTkLabel(sync_card, text="Progress: idle", anchor="w", font=("Segoe UI", 12))
        self.sync_progress_label.grid(row=8, column=0, padx=18, pady=(0, 18), sticky="ew")

        log_card = ctk.CTkFrame(body, corner_radius=16)
        log_card.grid(row=1, column=0, padx=(20, 10), pady=(10, 20), sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        self._section_title(log_card, "Activity Log")
        self.log_output = ctk.CTkTextbox(log_card, state="disabled", wrap="word")
        self.log_output.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")

        history_card = ctk.CTkFrame(body, corner_radius=16)
        history_card.grid(row=1, column=1, padx=(10, 20), pady=(10, 20), sticky="nsew")
        history_card.grid_columnconfigure(0, weight=1)
        history_card.grid_rowconfigure(1, weight=1)

        self._section_title(history_card, "Recent Sync History")
        history_filter_row = ctk.CTkFrame(history_card, fg_color="transparent")
        history_filter_row.grid(row=1, column=0, padx=18, pady=(0, 6), sticky="ew")
        history_filter_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(history_filter_row, text="Filter", font=("Segoe UI", 12)).grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.history_filter = ctk.CTkOptionMenu(
            history_filter_row,
            values=["All", "info", "add", "delete", "warning"],
            command=self._on_history_filter_change,
        )
        self.history_filter.set("All")
        self.history_filter.grid(row=0, column=1, sticky="w")

        self.history_refresh_button = ctk.CTkButton(history_filter_row, text="Refresh", width=100, command=self._refresh_history)
        self.history_refresh_button.grid(row=0, column=2, padx=(10, 0), sticky="e")

        self.history_output = ctk.CTkTextbox(history_card, state="disabled", wrap="word")
        self.history_output.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="nsew")

    def _section_title(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Segoe UI Semibold", 16)).grid(row=0, column=0, padx=18, pady=(16, 8), sticky="w")

    def _create_entry(self, parent, label_text, row, **kwargs):
        placeholder = kwargs.pop("placeholder", "")
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, padx=20, pady=5, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)
        
        label = ctk.CTkLabel(frame, text=label_text, width=190, anchor="w", font=("Segoe UI", 13))
        label.grid(row=0, column=0, padx=10, pady=5)
        
        if placeholder:
            kwargs["placeholder_text"] = placeholder

        entry = ctk.CTkEntry(frame, **kwargs)
        entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        return entry

    def _setup_logging(self):
        handler = TextHandler(self.log_output)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _set_status(self, text, ok=True):
        fg = ("#E8F5E9", "#16361D") if ok else ("#FDECEC", "#3C1414")
        text_color = ("#1B5E20", "#A5D6A7") if ok else ("#B71C1C", "#FFCDD2")
        self.status_chip.configure(text=text, fg_color=fg, text_color=text_color)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.save_button.configure(state="disabled" if busy else "normal")
        self.sync_button.configure(state="disabled" if busy else "normal")
        self.pause_button.configure(state="normal" if busy else "disabled")
        if not busy:
            self.pause_button.configure(text="Pause")
        self.about_button.configure(state="disabled" if busy else "normal")
        self._set_status("Working" if busy else "Ready", ok=not busy)

    def _toggle_pause(self):
        if not self._busy:
            return

        if self._pause_event.is_set():
            self._pause_event.clear()
            self.pause_button.configure(text="Pause")
            self._set_status("Working", ok=True)
            self.sync_progress_label.configure(text="Progress: resumed")
            return

        self._pause_event.set()
        self.pause_button.configure(text="Resume")
        self._set_status("Paused", ok=False)
        self.sync_progress_label.configure(text="Progress: paused")

    def _on_sync_progress(self, payload):
        self.after(0, lambda: self._apply_sync_progress(payload))

    def _apply_sync_progress(self, payload):
        stage = payload.get("stage", "")
        if stage == "discovered":
            discovered = payload.get("discovered", 0)
            workers = payload.get("workers", "?")
            self.sync_progress_label.configure(text=f"Progress: discovered {discovered} item(s), workers={workers}")
            return

        if stage == "queued":
            queued = payload.get("queued", 0)
            self.sync_progress_label.configure(text=f"Progress: queued {queued} item(s)")
            return

        if stage == "batch_complete":
            uploaded = payload.get("uploaded", 0)
            failed = payload.get("failed", 0)
            queued = payload.get("queued")
            dead = payload.get("dead")
            self.sync_progress_label.configure(
                text=f"Progress: uploaded={uploaded}, failed={failed}, queued={queued}, dead={dead}"
            )
            return

        if stage == "paused":
            self.sync_progress_label.configure(text="Progress: paused")
            self.pause_button.configure(text="Resume")
            self._set_status("Paused", ok=False)
            return

        if stage == "resumed":
            self.sync_progress_label.configure(text="Progress: resumed")
            self.pause_button.configure(text="Pause")
            self._set_status("Working", ok=True)
            return

        if stage == "completed":
            uploaded = payload.get("uploaded", 0)
            failed = payload.get("failed", 0)
            dead = payload.get("dead", 0)
            self.sync_progress_label.configure(text=f"Progress: complete (uploaded={uploaded}, failed={failed}, dead={dead})")

    def _get_history_events(self):
        selected_filter = self._history_event_type
        if selected_filter == "All":
            return self.db.get_recent_events(limit=12)
        return self.db.get_recent_events_by_type(selected_filter, limit=12)

    def _refresh_history(self):
        try:
            events = self._get_history_events()
        except Exception as exc:
            logging.error(f"Failed to load sync history: {exc}")
            return

        lines = []
        for event in events:
            created_at = event["created_at"]
            try:
                timestamp = datetime.fromisoformat(str(created_at))
                stamp_text = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                stamp_text = str(created_at)
            lines.append(f"[{stamp_text}] {event['event_type'].upper()}: {event['message']}")

        text = "\n".join(lines) if lines else "No sync history yet."
        self.history_output.configure(state="normal")
        self.history_output.delete("1.0", "end")
        self.history_output.insert("end", text)
        self.history_output.configure(state="disabled")

    def _on_history_filter_change(self, selected_value):
        self._history_event_type = selected_value
        self._refresh_history()

    def _create_tray_image(self):
        if not PYSTRAY_AVAILABLE:
            return None

        image = Image.new("RGBA", (64, 64), (17, 24, 39, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(59, 130, 246, 255))
        draw.text((19, 18), "iC", fill=(255, 255, 255, 255))
        return image

    def _ensure_tray_icon(self):
        if not PYSTRAY_AVAILABLE or self._tray_icon is not None:
            return

        image = self._create_tray_image()
        if image is None:
            return

        menu = pystray.Menu(
            pystray.MenuItem("Restore", lambda icon, item: self.after(0, self._restore_from_tray)),
            pystray.MenuItem("Sync now", lambda icon, item: self.after(0, self._start_sync)),
            pystray.MenuItem("About", lambda icon, item: self.after(0, self._show_about_dialog)),
            pystray.MenuItem("Quit", lambda icon, item: self.after(0, self._quit_from_tray)),
        )
        self._tray_icon = pystray.Icon("iCloudSynoSync", image, "iCloud to Synology Sync", menu)

    def _start_tray_icon(self):
        if not PYSTRAY_AVAILABLE:
            logging.warning("Tray mode is unavailable because pystray/Pillow is not installed.")
            return

        self._ensure_tray_icon()
        if self._tray_icon is None or self._tray_thread is not None:
            return

        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._tray_thread.start()

    def _stop_tray_icon(self):
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        self._tray_thread = None

    def _hide_to_tray(self):
        self._hidden_to_tray = True
        self.withdraw()
        self._start_tray_icon()
        logging.info("Application minimized to the system tray.")
        self.after(0, lambda: self._set_status("Running in tray"))

    def _minimize_to_tray(self):
        if self._busy:
            if not messagebox.askyesno("Sync in progress", "A sync is still running. Hide the app to the tray anyway?"):
                return
        self._hide_to_tray()

    def _restore_from_tray(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()
        self._hidden_to_tray = False
        self._set_status("Ready")

    def _show_about_dialog(self):
        messagebox.showinfo("About", build_about_text())

    def _quit_from_tray(self):
        self._stop_tray_icon()
        self.after(0, self.destroy)

    def _on_unmap(self, event):
        if self.state() == "iconic" and not self._hidden_to_tray:
            self.after(0, self._hide_to_tray)

    def _schedule_auto_sync(self):
        if self._auto_sync_job is not None:
            self.after_cancel(self._auto_sync_job)
            self._auto_sync_job = None

        if not self._auto_sync_enabled:
            return

        try:
            interval_minutes = int(self.sync_interval.get())
        except ValueError:
            logging.warning("Auto-sync disabled because the interval is invalid.")
            return

        delay_ms = max(interval_minutes, 1) * 60 * 1000
        self._auto_sync_job = self.after(delay_ms, self._auto_sync_tick)

    def _maybe_schedule_auto_sync(self):
        self._auto_sync_enabled = self.auto_sync_enabled.get() == 1
        self._schedule_auto_sync()

    def _auto_sync_tick(self):
        self._auto_sync_job = None
        if self._auto_sync_enabled and not self._busy:
            logging.info("Auto-sync triggered.")
            self._start_sync()
        self._schedule_auto_sync()

    def _load_settings(self):
        data = self.config_manager.data
        self.nas_ip.insert(0, data.get("nas_ip", ""))
        self.nas_user.insert(0, data.get("nas_user", ""))
        self.apple_id.insert(0, data.get("apple_id", ""))
        self.sync_interval.insert(0, str(data.get("sync_interval_minutes", 30)))
        self.sync_workers.insert(0, str(data.get("sync_worker_count", 4)))
        self.max_retries.insert(0, str(data.get("max_upload_retries", 3)))
        self.queue_batch_size.insert(0, str(data.get("queue_batch_size", 50)))
        
        if data.get("enable_nas_to_icloud_deletion", False):
            self.enable_deletion.select()
        else:
            self.enable_deletion.deselect()

        auto_sync = data.get("auto_sync_enabled", True)
        if auto_sync:
            self.auto_sync_enabled.select()
        else:
            self.auto_sync_enabled.deselect()

        # Load passwords from keyring
        nas_pass = self.config_manager.get_credential("nas_password")
        if nas_pass:
            self.nas_pass.insert(0, nas_pass)
        
        apple_pass = self.config_manager.get_credential("apple_password")
        if apple_pass:
            self.apple_pass.insert(0, apple_pass)

    def _save_settings(self):
        if self._busy:
            return
        self.config_manager.data["nas_ip"] = self.nas_ip.get()
        self.config_manager.data["nas_user"] = self.nas_user.get()
        normalized_apple_id = ICloudPhotosAPI._normalize_apple_id(self.apple_id.get())
        normalized_apple_password = ICloudPhotosAPI._normalize_password(self.apple_pass.get())
        self.config_manager.data["apple_id"] = normalized_apple_id
        try:
            self.config_manager.data["sync_interval_minutes"] = int(self.sync_interval.get())
        except ValueError:
            messagebox.showerror("Invalid setting", "Sync interval must be a whole number.")
            self._set_status("Fix settings", ok=False)
            return

        try:
            self.config_manager.data["sync_worker_count"] = max(1, int(self.sync_workers.get()))
            self.config_manager.data["max_upload_retries"] = max(1, int(self.max_retries.get()))
            self.config_manager.data["queue_batch_size"] = max(1, int(self.queue_batch_size.get()))
        except ValueError:
            messagebox.showerror("Invalid setting", "Worker, retry, and queue values must be whole numbers.")
            self._set_status("Fix settings", ok=False)
            return

        self.config_manager.data["enable_nas_to_icloud_deletion"] = self.enable_deletion.get() == 1
        self.config_manager.data["auto_sync_enabled"] = self.auto_sync_enabled.get() == 1
        
        self.config_manager.save()
        
        # Save passwords to keyring
        self.config_manager.set_credential("nas_password", self.nas_pass.get())
        self.config_manager.set_credential("apple_password", normalized_apple_password)

        # Keep UI fields aligned with normalized values after save.
        self.apple_id.delete(0, "end")
        self.apple_id.insert(0, normalized_apple_id)
        self.apple_pass.delete(0, "end")
        self.apple_pass.insert(0, normalized_apple_password)
        
        logging.info("Settings saved successfully.")
        self._set_status("Settings saved")
        messagebox.showinfo("Saved", "Settings were saved successfully.")
        self._auto_sync_enabled = self.auto_sync_enabled.get() == 1
        self._schedule_auto_sync()

    def _start_sync(self):
        if self._busy:
            return
        self._pause_event.clear()
        self.pause_button.configure(text="Pause")
        self._set_busy(True)
        threading.Thread(target=self._run_sync, daemon=True).start()

    def _prompt_2fa_code(self):
        result = {"code": None}
        completed = threading.Event()

        def _show_dialog():
            result["code"] = simpledialog.askstring(
                "Apple 2FA",
                "Enter the 6-digit Apple verification code. If no push appears, open iPhone Settings >"
                " [your name] > Sign-In & Security > Get Verification Code.",
                parent=self,
            )
            completed.set()

        self.after(0, _show_dialog)
        completed.wait()
        return result["code"]

    def _handle_icloud_auth_challenge(self, icloud_api: ICloudPhotosAPI) -> bool:
        if icloud_api.requires_2fa:
            for _ in range(3):
                code = self._prompt_2fa_code()
                if not code:
                    return False
                if icloud_api.verify_2fa(code):
                    return True
                logging.error(f"iCloud 2FA verification failed: {icloud_api.last_error}")
            return False

        if icloud_api.requires_2sa:
            device_index = 0
            if not icloud_api.send_2sa_verification_code(device_index=device_index):
                logging.error(f"iCloud 2SA code request failed: {icloud_api.last_error}")
                return False
            for _ in range(3):
                code = self._prompt_2fa_code()
                if not code:
                    return False
                if icloud_api.verify_2sa(code, device_index=device_index):
                    return True
                logging.error(f"iCloud 2SA verification failed: {icloud_api.last_error}")
            return False

        return False

    def _run_sync(self):
        try:
            logging.info("Starting sync process...")
            
            icloud_api = ICloudPhotosAPI(self.apple_id.get(), self.apple_pass.get())
            if not icloud_api.login():
                if icloud_api.requires_2fa or icloud_api.requires_2sa:
                    if not self._handle_icloud_auth_challenge(icloud_api):
                        logging.error("iCloud authentication challenge failed.")
                        self.after(0, lambda: self._set_status("iCloud verification failed", ok=False))
                        return
                else:
                    logging.error("iCloud login failed.")
                    self.after(0, lambda: self._set_status("iCloud login failed", ok=False))
                    return

            syno_api = SynologyPhotosAPI(self.nas_ip.get(), self.nas_user.get(), self.nas_pass.get())
            if not syno_api.login():
                logging.error("Synology login failed.")
                self.after(0, lambda: self._set_status("Synology login failed", ok=False))
                return

            engine = SyncEngine(
                icloud_api=icloud_api,
                syno_api=syno_api,
                db=self.db,
                enable_nas_to_icloud_deletion=(self.enable_deletion.get() == 1),
                worker_count=max(1, int(self.sync_workers.get() or 4)),
                max_retries=max(1, int(self.max_retries.get() or 3)),
                queue_batch_size=max(1, int(self.queue_batch_size.get() or 50)),
                progress_callback=self._on_sync_progress,
                should_pause=lambda: self._pause_event.is_set(),
            )

            photos = icloud_api.list_photo_records()
            logging.info(f"Found {len(photos)} photos in iCloud.")
            
            engine.reconcile(photos)
            
            logging.info("Sync process completed.")
            self.after(0, lambda: self._set_status("Sync completed"))
            self.after(0, self._refresh_history)
        except Exception as e:
            logging.error(f"Sync failed with error: {e}")
            self.after(0, lambda: self._set_status("Sync failed", ok=False))
            self.after(0, self._refresh_history)
        finally:
            self._pause_event.clear()
            self.sync_button.after(0, lambda: self._set_busy(False))

    def destroy(self):
        if self._auto_sync_job is not None:
            try:
                self.after_cancel(self._auto_sync_job)
            except Exception:
                pass
            self._auto_sync_job = None
        self._stop_tray_icon()
        super().destroy()

if __name__ == "__main__":
    app = SyncAppUI()
    app.mainloop()
