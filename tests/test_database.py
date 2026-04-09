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

def test_db_record_event_and_recent_history():
    db = SyncDatabase(":memory:")
    db.record_event("info", "Sync started")
    db.record_event("add", "Uploaded photo.jpg")

    events = db.get_recent_events(limit=2)
    assert len(events) == 2
    assert events[0]["message"] == "Uploaded photo.jpg"
    assert events[1]["message"] == "Sync started"

def test_db_recent_events_by_type():
    db = SyncDatabase(":memory:")
    db.record_event("info", "Sync started")
    db.record_event("warning", "NAS offline")
    db.record_event("info", "Sync finished")

    events = db.get_recent_events_by_type("info", limit=10)
    assert len(events) == 2
    assert all(event["event_type"] == "info" for event in events)

def test_db_sync_queue_lifecycle():
    db = SyncDatabase(":memory:")
    queued = db.queue_jobs([
        {"id": "id1", "filename": "a.jpg"},
        {"id": "id2", "filename": "b.jpg"},
    ])
    assert queued == 2

    pending = db.fetch_pending_jobs(limit=10)
    assert len(pending) == 2

    db.mark_job_in_progress("id1")
    db.mark_job_failed("id1", "temporary", retryable=True, delay_seconds=0)
    db.mark_job_done("id2")

    counts = db.get_job_counts()
    assert counts["failed"] == 1
    assert counts["done"] == 1

    pending_after = db.fetch_pending_jobs(limit=10)
    assert any(row["icloud_id"] == "id1" for row in pending_after)

    db.purge_completed_jobs()
    counts_after = db.get_job_counts()
    assert counts_after["done"] == 0

def test_db_reset_in_progress_jobs():
    db = SyncDatabase(":memory:")
    db.queue_jobs([{"id": "id1", "filename": "a.jpg"}])
    db.mark_job_in_progress("id1")
    db.reset_in_progress_jobs()

    counts = db.get_job_counts()
    assert counts["in_progress"] == 0
    assert counts["failed"] == 1
