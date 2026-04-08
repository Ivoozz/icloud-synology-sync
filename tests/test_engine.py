from src.engine import SyncEngine
from unittest.mock import MagicMock, patch
import pytest

def test_streaming_transfer():
    syno_api = MagicMock()
    syno_api.upload_stream.return_value = True
    engine = SyncEngine(MagicMock(), syno_api, MagicMock())
    # Mock a response object with a stream
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
    
    filename = "test.jpg"
    success = engine._stream_file(mock_response, filename)
    
    assert success is True
    # Verify syno_api.upload_stream was called with filename
    args, kwargs = syno_api.upload_stream.call_args
    assert args[1] == filename
    # Verify it was called with a generator
    generator = args[0]
    chunks = list(generator)
    assert chunks == [b"chunk1", b"chunk2"]
    # Verify it called iter_content with the default chunk size
    mock_response.iter_content.assert_called_with(chunk_size=8192)

def test_streaming_transfer_with_custom_chunk_size():
    syno_api = MagicMock()
    # Ensure upload_stream exhausts the generator
    def exhaust_generator(gen, filename):
        list(gen)
        return True
    syno_api.upload_stream.side_effect = exhaust_generator
    
    custom_chunk_size = 1024
    engine = SyncEngine(MagicMock(), syno_api, MagicMock(), chunk_size=custom_chunk_size)
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"chunk1"]
    
    engine._stream_file(mock_response, "test.jpg")
    mock_response.iter_content.assert_called_with(chunk_size=custom_chunk_size)

def test_streaming_transfer_synology_failure():
    syno_api = MagicMock()
    syno_api.upload_stream.side_effect = Exception("Upload failed")
    engine = SyncEngine(MagicMock(), syno_api, MagicMock())
    mock_response = MagicMock()
    
    success = engine._stream_file(mock_response, "test.jpg")
    assert success is False

def test_streaming_transfer_icloud_failure():
    syno_api = MagicMock()
    # Ensure upload_stream exhausts the generator
    def exhaust_generator(gen, filename):
        list(gen)
        return True
    syno_api.upload_stream.side_effect = exhaust_generator
    
    engine = SyncEngine(MagicMock(), syno_api, MagicMock())
    mock_response = MagicMock()
    mock_response.iter_content.side_effect = Exception("Download failed")
    
    # In this case _stream_file should return False because of the exception in generator
    success = engine._stream_file(mock_response, "test.jpg")
    assert success is False

def test_reconcile_deletion_from_icloud():
    db = MagicMock()
    # Entry exists in DB but NOT in current iCloud scan
    db.get_all_entries.return_value = [{"icloud_id": "missing_id", "synology_id": "syno_path"}]
    engine = SyncEngine(MagicMock(), MagicMock(), db)
    
    engine.reconcile(current_icloud_ids=[])
    engine.syno.delete_file.assert_called_with("syno_path")
    db.delete_entry.assert_called_with("missing_id")

def test_reconcile_nas_deletion_with_icloud_sync():
    db = MagicMock()
    icloud = MagicMock()
    syno = MagicMock()
    
    # File exists in iCloud and DB, but is MISSING from NAS
    db.get_all_entries.return_value = [{"icloud_id": "id1", "synology_id": "path1"}]
    syno.file_exists.return_value = False
    
    # CASE: enable_nas_to_icloud_deletion = TRUE
    engine = SyncEngine(icloud, syno, db, enable_nas_to_icloud_deletion=True)
    engine.reconcile(current_icloud_ids=["id1"])
    
    icloud.delete_photo.assert_called_with("id1")
    db.delete_entry.assert_called_with("id1")

def test_reconcile_nas_deletion_without_icloud_sync():
    db = MagicMock()
    icloud = MagicMock()
    syno = MagicMock()
    
    # File exists in iCloud and DB, but is MISSING from NAS
    db.get_all_entries.return_value = [{"icloud_id": "id1", "synology_id": "path1"}]
    syno.file_exists.return_value = False
    
    # CASE: enable_nas_to_icloud_deletion = FALSE
    engine = SyncEngine(icloud, syno, db, enable_nas_to_icloud_deletion=False)
    engine.reconcile(current_icloud_ids=["id1"])
    
    icloud.delete_photo.assert_not_called()
    db.delete_entry.assert_called_with("id1")

def test_reconcile_additions():
    db = MagicMock()
    icloud = MagicMock()
    syno = MagicMock()
    
    # New item in iCloud scan, not in DB
    db.get_all_entries.return_value = []
    engine = SyncEngine(icloud, syno, db)
    
    # Mock download_photo to return a response object
    mock_response = MagicMock()
    icloud.download_photo.return_value = mock_response
    # Mock successful streaming
    syno.upload_stream.return_value = True
    
    engine.reconcile(current_icloud_ids=["new_id"])
    
    icloud.download_photo.assert_called_with("new_id")
    # Should call upsert_sync_entry with new mapping
    db.upsert_sync_entry.assert_called_once()
    args, _ = db.upsert_sync_entry.call_args
    assert args[0] == "new_id"
    assert args[1] == "new_id.jpg"

def test_reconcile_heartbeat_failure():
    db = MagicMock()
    icloud = MagicMock()
    syno = MagicMock()
    
    # Mock heartbeat to FAIL
    syno.ping.return_value = False
    
    # Some items in DB and iCloud scan
    db.get_all_entries.return_value = [{"icloud_id": "id1", "synology_id": "path1"}]
    engine = SyncEngine(icloud, syno, db)
    
    engine.reconcile(current_icloud_ids=["id1"])
    
    # Verify NO actions were taken
    syno.delete_file.assert_not_called()
    icloud.delete_photo.assert_not_called()
    db.delete_entry.assert_not_called()
    icloud.download_photo.assert_not_called()

