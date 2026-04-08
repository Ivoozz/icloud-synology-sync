import json
import keyring
from pathlib import Path

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = Path(config_path)
        self.data = self._load()

    def _load(self):
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {
            "nas_ip": "",
            "nas_user": "",
            "apple_id": "",
            "sync_interval_minutes": 30,
            "enable_nas_to_icloud_deletion": False
        }

    def save(self):
        self.config_path.write_text(json.dumps(self.data, indent=4))

    def set_credential(self, key, value):
        keyring.set_password("icloud_syno_sync", key, value)

    def get_credential(self, key):
        return keyring.get_password("icloud_syno_sync", key)
