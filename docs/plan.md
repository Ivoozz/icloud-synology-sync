# iCloud to Synology Photos Direct Streamer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows (.exe) application that performs two-way, memory-only synchronization between iCloud Photos and Synology Photos.

**Architecture:** A Python-based engine that streams data directly between APIs via RAM, tracking state in a local SQLite database and providing a simple Windows UI for configuration.

**Tech Stack:** Python 3.11+, `pyicloud`, `requests`, `sqlite3`, `keyring` (for DPAPI), `customtkinter` (for UI), `PyInstaller`.

---

### Task 1: Project Setup & Secure Configuration

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test for secure config**
```python
import pytest
from src.config import ConfigManager

def test_save_and_load_encrypted_password():
    cm = ConfigManager(config_path="test_config.json")
    cm.set_credential("nas_password", "secret123")
    assert cm.get_credential("nas_password") == "secret123"
```

- [ ] **Step 2: Run test to verify failure**
Run: `pytest tests/test_config.py`
Expected: ModuleNotFoundError

- [ ] **Step 3: Implement ConfigManager using keyring**
```python
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
        return {"nas_ip": "", "nas_user": "", "apple_id": "", "sync_interval": 30, "enable_nas_delete": False}

    def save(self):
        self.config_path.write_text(json.dumps(self.data, indent=4))

    def set_credential(self, key, value):
        keyring.set_password("icloud_syno_sync", key, value)

    def get_credential(self, key):
        return keyring.get_password("icloud_syno_sync", key)
```

- [ ] **Step 4: Run test to verify pass**
Run: `pytest tests/test_config.py`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add secure configuration manager"
```

---

### Task 2: Metadata Database (SQLite)

**Files:**
- Create: `src/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write test for database operations**
```python
from src.database import SyncDatabase

def test_db_insert_and_query():
    db = SyncDatabase(":memory:")
    db.upsert_sync_entry("icloud123", "syno456", "hash_abc")
    entry = db.get_entry_by_icloud_id("icloud123")
    assert entry['synology_id'] == "syno456"
```

- [ ] **Step 2: Run test to verify failure**
Run: `pytest tests/test_database.py`

- [ ] **Step 3: Implement SyncDatabase**
```python
import sqlite3

class SyncDatabase:
    def __init__(self, db_path="sync_state.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_entries (
                icloud_id TEXT PRIMARY KEY,
                synology_id TEXT,
                file_hash TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def upsert_sync_entry(self, icloud_id, synology_id, file_hash):
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_entries (icloud_id, synology_id, file_hash) VALUES (?, ?, ?)",
            (icloud_id, synology_id, file_hash)
        )
        self.conn.commit()

    def get_entry_by_icloud_id(self, icloud_id):
        return self.conn.execute("SELECT * FROM sync_entries WHERE icloud_id = ?", (icloud_id,)).fetchone()
```

- [ ] **Step 4: Run test to verify pass**
Run: `pytest tests/test_database.py`

- [ ] **Step 5: Commit**
```bash
git add src/database.py tests/test_database.py
git commit -m "feat: add sqlite metadata database"
```

---

### Task 3: Memory-Only Streaming Bridge

**Files:**
- Create: `src/engine.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write test for memory-only stream**
```python
from src.engine import SyncEngine
from unittest.mock import MagicMock

def test_streaming_transfer():
    engine = SyncEngine(MagicMock(), MagicMock(), MagicMock())
    # Mock a response object with a stream
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
    
    # Verify that it calls the upload with the generator
    success = engine._stream_file(mock_response, "test.jpg")
    assert success is True
```

- [ ] **Step 2: Run test to verify failure**
Run: `pytest tests/test_engine.py`

- [ ] **Step 3: Implement streaming logic**
```python
class SyncEngine:
    def __init__(self, icloud_api, syno_api, db):
        self.icloud = icloud_api
        self.syno = syno_api
        self.db = db

    def _stream_file(self, icloud_response, filename):
        # This function would pipe the response content to the Synology API
        # Using a generator to keep memory usage low
        def chunk_generator():
            for chunk in icloud_response.iter_content(chunk_size=8192):
                yield chunk
        
        return self.syno.upload_stream(chunk_generator(), filename)
```

- [ ] **Step 4: Run test to verify pass**
Run: `pytest tests/test_engine.py`

- [ ] **Step 5: Commit**
```bash
git add src/engine.py tests/test_engine.py
git commit -m "feat: implement memory-only streaming logic"
```

---

### Task 4: Two-Way Reconciliation Logic

**Files:**
- Modify: `src/engine.py`
- Modify: `tests/test_engine.py`

- [ ] **Step 1: Write test for reconciliation (delete case)**
```python
def test_reconcile_deletion_from_icloud():
    db = MagicMock()
    # Entry exists in DB but NOT in current iCloud scan
    db.get_all_entries.return_value = [{"icloud_id": "missing_id", "synology_id": "syno_path"}]
    engine = SyncEngine(MagicMock(), MagicMock(), db)
    
    engine.reconcile(current_icloud_ids=[])
    engine.syno.delete_file.assert_called_with("syno_path")
```

- [ ] **Step 2: Run test to verify failure**
Run: `pytest tests/test_engine.py`

- [ ] **Step 3: Implement reconciliation loop**
```python
    def reconcile(self, current_icloud_ids):
        all_db_entries = self.db.get_all_entries()
        
        # Check for deletions in iCloud
        for entry in all_db_entries:
            if entry['icloud_id'] not in current_icloud_ids:
                print(f"Deleting {entry['synology_id']} from Synology...")
                self.syno.delete_file(entry['synology_id'])
                self.db.delete_entry(entry['icloud_id'])
        
        # New photos would be handled in a similar loop (Scenario A)
```

- [ ] **Step 4: Run test to verify pass**
Run: `pytest tests/test_engine.py`

- [ ] **Step 5: Commit**
```bash
git add src/engine.py tests/test_engine.py
git commit -m "feat: implement two-way reconciliation logic"
```

---

### Task 5: Synology & iCloud API Wrappers

**Files:**
- Create: `src/icloud_api.py`
- Create: `src/synology_api.py`

- [ ] **Step 1: Implement Synology Photos API Wrapper (Upload/List/Delete)**
- [ ] **Step 2: Implement iCloud API Wrapper (pyicloud session management)**
- [ ] **Step 3: Add unit tests for API wrappers with responses mocking**
- [ ] **Step 4: Commit**
```bash
git add src/icloud_api.py src/synology_api.py
git commit -m "feat: add api wrappers for icloud and synology"
```

---

### Task 6: Windows UI & Packaging

**Files:**
- Create: `src/ui.py`
- Create: `src/main.py`
- Create: `build.py` (PyInstaller script)

- [ ] **Step 1: Create a simple CustomTkinter UI for settings**
- [ ] **Step 2: Add "Sync Now" button and status log**
- [ ] **Step 3: Configure PyInstaller for .exe creation**
- [ ] **Step 4: Final manual validation with Test Album**
- [ ] **Step 5: Commit**
```bash
git add src/ui.py src/main.py build.py
git commit -m "feat: add windows ui and build scripts"
```
