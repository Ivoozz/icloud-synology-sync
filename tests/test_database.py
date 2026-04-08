from src.database import SyncDatabase

def test_db_insert_and_query():
    db = SyncDatabase(":memory:")
    db.upsert_sync_entry("icloud123", "syno456", "hash_abc")
    entry = db.get_entry_by_icloud_id("icloud123")
    assert entry['synology_id'] == "syno456"

def test_db_get_all_entries():
    db = SyncDatabase(":memory:")
    db.upsert_sync_entry("id1", "s1", "h1")
    db.upsert_sync_entry("id2", "s2", "h2")
    entries = db.get_all_entries()
    assert len(entries) == 2

def test_db_delete_entry():
    db = SyncDatabase(":memory:")
    db.upsert_sync_entry("id1", "s1", "h1")
    db.delete_entry("id1")
    entry = db.get_entry_by_icloud_id("id1")
    assert entry is None
