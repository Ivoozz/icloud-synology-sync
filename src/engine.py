import logging
from typing import Any, Generator, List

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 8192

class SyncEngine:
    """
    Handles synchronization between iCloud and Synology NAS.
    """
    def __init__(self, icloud_api: Any, syno_api: Any, db: Any, 
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 enable_nas_to_icloud_deletion: bool = False):
        """
        Initialize the SyncEngine.

        :param icloud_api: API client for iCloud.
        :param syno_api: API client for Synology NAS.
        :param db: Database instance for tracking synced files.
        :param chunk_size: Size of chunks for file streaming.
        :param enable_nas_to_icloud_deletion: If TRUE, delete from iCloud when missing on NAS.
        """
        self.icloud = icloud_api
        self.syno = syno_api
        self.db = db
        self.chunk_size = chunk_size
        self.enable_nas_to_icloud_deletion = enable_nas_to_icloud_deletion

    def heartbeat(self) -> bool:
        """
        Checks if the Synology NAS is reachable.
        
        :return: True if heartbeat succeeds, False otherwise.
        """
        try:
            # We call ping on the syno_api to check connectivity.
            return self.syno.ping()
        except Exception as e:
            logger.error(f"Heartbeat check failed: {e}")
            return False

    def _stream_file(self, icloud_response: Any, filename: str) -> bool:
        """
        Streams a file from iCloud response to Synology API.

        :param icloud_response: Response object from iCloud API with iter_content method.
        :param filename: Name of the file to be saved on Synology.
        :return: True if the transfer was successful, False otherwise.
        """
        def chunk_generator() -> Generator[bytes, None, None]:
            try:
                for chunk in icloud_response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        yield chunk
            except Exception as e:
                logger.error(f"Error while streaming content for {filename}: {e}")
                raise

        try:
            return self.syno.upload_stream(chunk_generator(), filename)
        except Exception as e:
            logger.error(f"Failed to upload {filename} to Synology: {e}")
            return False

    def reconcile(self, current_icloud_ids: List[str]):
        """
        Reconciles the state between iCloud, Synology NAS, and the local DB.

        - Additions: Items in iCloud but not in SQLite -> Stream to NAS.
        - iCloud Deletions: Items in SQLite but not in iCloud -> Delete from NAS.
        - NAS Deletions: Items in SQLite but missing from NAS -> If enable_nas_to_icloud_deletion is TRUE, 
                                                         delete from iCloud; else, remove from SQLite.
        """
        # --- Safe Pause Mechanism ---
        if not self.heartbeat():
            logger.warning("NAS Heartbeat failed. Sync safely paused to prevent accidental deletions.")
            return
        # ----------------------------

        all_db_entries = self.db.get_all_entries()
        db_icloud_ids = {entry['icloud_id'] for entry in all_db_entries}
        
        # 1. iCloud Deletions: Items in SQLite but not in current iCloud scan
        for entry in all_db_entries:
            icloud_id = entry['icloud_id']
            syno_id = entry['synology_id']
            
            if icloud_id not in current_icloud_ids:
                logger.info(f"Deleting {syno_id} from Synology as it was removed from iCloud...")
                try:
                    self.syno.delete_file(syno_id)
                except Exception as e:
                    logger.error(f"Failed to delete {syno_id} from Synology: {e}")
                self.db.delete_entry(icloud_id)
                continue # Already handled this entry
            
            # 2. NAS Deletions: Items in SQLite but missing from NAS
            try:
                if not self.syno.file_exists(syno_id):
                    logger.info(f"File {syno_id} missing from NAS.")
                    if self.enable_nas_to_icloud_deletion:
                        logger.info(f"Deleting {icloud_id} from iCloud...")
                        self.icloud.delete_photo(icloud_id)
                    self.db.delete_entry(icloud_id)
            except Exception as e:
                logger.error(f"Error checking NAS file {syno_id}: {e}")

        # 3. Additions: Items in iCloud but not in SQLite
        for icloud_id in current_icloud_ids:
            if icloud_id not in db_icloud_ids:
                logger.info(f"New item {icloud_id} in iCloud. Streaming to NAS...")
                try:
                    # Assuming icloud_api has download_photo that returns a response object
                    # and we use the icloud_id as filename for now or get it from metadata
                    # Since we don't have metadata here, we'll use icloud_id
                    response = self.icloud.download_photo(icloud_id)
                    if self._stream_file(response, f"{icloud_id}.jpg"): # Placeholder extension
                        self.db.upsert_sync_entry(icloud_id, f"{icloud_id}.jpg", "hash_placeholder")
                except Exception as e:
                    logger.error(f"Failed to stream new item {icloud_id}: {e}")
