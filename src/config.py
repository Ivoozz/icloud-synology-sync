import json
import keyring
from pathlib import Path

class ConfigManager:
    SERVICE_NAME = "icloud_syno_sync"
    CURRENT_CONFIG_VERSION = 3

    def __init__(self, config_path="config.json"):
        self.config_path = Path(config_path)
        self.data = self._load()

    def _load(self):
        defaults = self._defaults()
        if self.config_path.exists():
            try:
                loaded = json.loads(self.config_path.read_text())
                if not isinstance(loaded, dict):
                    return defaults

                version = loaded.get("config_version", 1)
                try:
                    version = int(version)
                except (TypeError, ValueError):
                    version = 1

                defaults.update(loaded)
                defaults["config_version"] = self.CURRENT_CONFIG_VERSION

                if version < self.CURRENT_CONFIG_VERSION:
                    self.data = defaults
                    self.save()

                return defaults
            except json.JSONDecodeError:
                return defaults
        return defaults

    def _defaults(self):
        return {
            "nas_ip": "",
            "nas_user": "",
            "apple_id": "",
            "sync_interval_minutes": 30,
            "enable_nas_to_icloud_deletion": False,
            "auto_sync_enabled": True,
            "sync_worker_count": 4,
            "max_upload_retries": 3,
            "queue_batch_size": 50,
            "config_version": self.CURRENT_CONFIG_VERSION
        }

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self.data, indent=4))

    def set_credential(self, key, value):
        keyring.set_password(self.SERVICE_NAME, key, value)

    def get_credential(self, key):
        return keyring.get_password(self.SERVICE_NAME, key)
