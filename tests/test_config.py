import pytest
import keyring
import json
import os
from pathlib import Path
from keyring.backends.null import Keyring
from src.config import ConfigManager

@pytest.fixture(autouse=True)
def setup_mock_keyring():
    class MockKeyring(Keyring):
        def __init__(self):
            self.passwords = {}
        def set_password(self, service, username, password):
            self.passwords[(service, username)] = password
        def get_password(self, service, username):
            return self.passwords.get((service, username))
    
    keyring.set_keyring(MockKeyring())

@pytest.fixture
def config_file():
    path = Path("test_config.json")
    if path.exists():
        path.unlink()
    yield path
    if path.exists():
        path.unlink()

def test_save_and_load_encrypted_password(config_file):
    cm = ConfigManager(config_path=config_file)
    cm.set_credential("nas_password", "secret123")
    assert cm.get_credential("nas_password") == "secret123"

def test_app_specific_password_handling(config_file):
    cm = ConfigManager(config_path=config_file)
    cm.set_credential("app_specific_password", "xxxx-xxxx-xxxx-xxxx")
    assert cm.get_credential("app_specific_password") == "xxxx-xxxx-xxxx-xxxx"

def test_json_fields_persistence(config_file):
    cm = ConfigManager(config_path=config_file)
    cm.data["nas_ip"] = "192.168.1.100"
    cm.data["nas_user"] = "admin"
    cm.data["apple_id"] = "test@apple.com"
    cm.data["sync_interval_minutes"] = 15
    cm.data["enable_nas_to_icloud_deletion"] = True
    cm.save()

    # Load file and verify raw JSON content
    with open(config_file, "r") as f:
        data = json.load(f)
    
    assert data["nas_ip"] == "192.168.1.100"
    assert data["nas_user"] == "admin"
    assert data["apple_id"] == "test@apple.com"
    assert data["sync_interval_minutes"] == 15
    assert data["enable_nas_to_icloud_deletion"] is True

def test_config_reload_persistence(config_file):
    cm = ConfigManager(config_path=config_file)
    cm.data["nas_ip"] = "10.0.0.1"
    cm.data["sync_interval_minutes"] = 60
    cm.save()

    # Create new ConfigManager with same path
    cm2 = ConfigManager(config_path=config_file)
    assert cm2.data["nas_ip"] == "10.0.0.1"
    assert cm2.data["sync_interval_minutes"] == 60

def test_config_migrates_version_field(config_file):
    config_file.write_text(json.dumps({
        "nas_ip": "10.0.0.5",
        "enable_nas_to_icloud_deletion": True
    }))

    cm = ConfigManager(config_path=config_file)
    assert cm.data["config_version"] == ConfigManager.CURRENT_CONFIG_VERSION
    assert cm.data["nas_ip"] == "10.0.0.5"
    assert cm.data["enable_nas_to_icloud_deletion"] is True

def test_config_contains_large_sync_defaults(config_file):
    cm = ConfigManager(config_path=config_file)
    assert cm.data["sync_worker_count"] == 4
    assert cm.data["max_upload_retries"] == 3
    assert cm.data["queue_batch_size"] == 50
