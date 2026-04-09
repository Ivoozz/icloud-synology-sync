import logging
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 8192

class SyncEngine:
    """
    Handles synchronization between iCloud and Synology NAS.
    """
    def __init__(self, icloud_api: Any, syno_api: Any, db: Any, 
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 enable_nas_to_icloud_deletion: bool = False,
                 worker_count: int = 4,
                 max_retries: int = 3,
                 queue_batch_size: int = 50,
                 progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
                 should_pause: Optional[Callable[[], bool]] = None):
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
        self.worker_count = max(1, int(worker_count))
        self.max_retries = max(1, int(max_retries))
        self.queue_batch_size = max(1, int(queue_batch_size))
        self.progress_callback = progress_callback
        self.should_pause = should_pause

    def _report_progress(self, stage: str, **payload: Any) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback({"stage": stage, **payload})
        except Exception as exc:
            logger.debug(f"Progress callback failed: {exc}")

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

    def _stream_file(self, icloud_response: Any, filename: str) -> Tuple[bool, str]:
        """
        Streams a file from iCloud response to Synology API.

        :param icloud_response: Response object from iCloud API with iter_content method.
        :param filename: Name of the file to be saved on Synology.
        :return: True if the transfer was successful, False otherwise.
        """
        hasher = hashlib.sha256()

        def chunk_generator() -> Generator[bytes, None, None]:
            try:
                for chunk in icloud_response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        hasher.update(chunk)
                        yield chunk
            except Exception as e:
                logger.error(f"Error while streaming content for {filename}: {e}")
                raise

        try:
            success = self.syno.upload_stream(chunk_generator(), filename)
            return success, hasher.hexdigest() if success else ""
        except Exception as e:
            logger.error(f"Failed to upload {filename} to Synology: {e}")
            return False, ""

    def _normalize_items(self, current_icloud_items: Iterable[Any]) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        for item in current_icloud_items:
            if isinstance(item, dict):
                icloud_id = item.get("id") or item.get("icloud_id")
                if not icloud_id:
                    continue
                filename = item.get("filename") or item.get("filename_hint") or f"{icloud_id}.jpg"
                normalized.append({"id": icloud_id, "filename": filename})
                continue

            icloud_id = str(item)
            normalized.append({"id": icloud_id, "filename": f"{icloud_id}.jpg"})
        return normalized

    def _single_job_transfer(self, icloud_id: str, filename: str) -> Dict[str, Any]:
        try:
            response = self.icloud.download_photo(icloud_id)
            if not response:
                return {"success": False, "error": "No response returned from iCloud.", "hash": ""}

            success, file_hash = self._stream_file(response, filename)
            if not success:
                return {"success": False, "error": "Upload failed.", "hash": ""}

            return {"success": True, "hash": file_hash, "error": ""}
        except Exception as exc:
            return {"success": False, "error": str(exc), "hash": ""}

    def _next_retry_delay(self, attempts: int) -> int:
        # Exponential backoff capped at 5 minutes.
        return min(300, 2 ** min(max(attempts, 1), 8))

    def _normalize_job_row(self, row: Any) -> Dict[str, Any]:
        if isinstance(row, dict):
            return {
                "icloud_id": row.get("icloud_id") or row.get("id"),
                "filename": row.get("filename"),
                "attempts": int(row.get("attempts") or 0),
            }

        return {
            "icloud_id": row["icloud_id"],
            "filename": row["filename"],
            "attempts": int(row["attempts"] or 0),
        }

    def _build_direct_jobs(self, items: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        return [
            {"icloud_id": item["id"], "filename": item["filename"], "attempts": 0}
            for item in items
            if item.get("id") and item.get("filename")
        ]

    def _wait_if_paused(self) -> None:
        paused_reported = False
        while self.should_pause and self.should_pause():
            if not paused_reported:
                paused_reported = True
                self._report_progress("paused")
                if hasattr(self.db, "record_event"):
                    self.db.record_event("info", "Sync paused by user.")
            time.sleep(0.5)

        if paused_reported:
            self._report_progress("resumed")
            if hasattr(self.db, "record_event"):
                self.db.record_event("info", "Sync resumed by user.")

    def _process_jobs(self, jobs: List[Dict[str, Any]]) -> Dict[str, int]:
        processed = 0
        uploaded = 0
        failed = 0

        if not jobs:
            return {"processed": 0, "uploaded": 0, "failed": 0}

        with ThreadPoolExecutor(max_workers=self.worker_count) as executor:
            futures = {}
            for job in jobs:
                self._wait_if_paused()
                icloud_id = job.get("icloud_id")
                filename = job.get("filename")
                if not icloud_id or not filename:
                    continue
                futures[executor.submit(self._single_job_transfer, icloud_id, filename)] = job

            for future in as_completed(futures):
                job = futures[future]
                processed += 1
                icloud_id = job["icloud_id"]
                filename = job["filename"]
                attempts = int(job.get("attempts") or 0)

                try:
                    result = future.result()
                except Exception as exc:
                    result = {"success": False, "error": str(exc), "hash": ""}

                if result.get("success"):
                    uploaded += 1
                    if hasattr(self.db, "upsert_sync_entry"):
                        self.db.upsert_sync_entry(icloud_id, filename, result.get("hash") or "")
                    if hasattr(self.db, "mark_job_done"):
                        self.db.mark_job_done(icloud_id)
                    if hasattr(self.db, "record_event"):
                        self.db.record_event("add", f"Uploaded {filename} for {icloud_id}.")
                else:
                    failed += 1
                    error_message = result.get("error") or "Unknown transfer failure"
                    retryable = attempts < self.max_retries
                    if hasattr(self.db, "mark_job_failed"):
                        self.db.mark_job_failed(
                            icloud_id,
                            error_message,
                            retryable=retryable,
                            delay_seconds=self._next_retry_delay(attempts),
                        )
                    if hasattr(self.db, "record_event"):
                        level = "warning" if retryable else "error"
                        status_text = "will retry" if retryable else "marked dead"
                        self.db.record_event(level, f"Upload failed for {icloud_id}: {status_text}. {error_message}")

        return {"processed": processed, "uploaded": uploaded, "failed": failed}

    def reconcile(self, current_icloud_ids: List[Any]):
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
            if hasattr(self.db, "record_event"):
                self.db.record_event("warning", "Sync paused because NAS heartbeat failed.")
            return
        # ----------------------------

        current_items = self._normalize_items(current_icloud_ids)
        current_ids = {item["id"] for item in current_items}
        all_db_entries = self.db.get_all_entries()
        db_icloud_ids = {entry['icloud_id'] for entry in all_db_entries}

        if hasattr(self.db, "record_event"):
            self.db.record_event("info", f"Sync cycle started with {len(current_items)} iCloud items.")
        self._report_progress(
            "discovered",
            discovered=len(current_items),
            known=len(db_icloud_ids),
            workers=self.worker_count,
        )
        
        # 1. iCloud Deletions: Items in SQLite but not in current iCloud scan
        for entry in all_db_entries:
            icloud_id = entry['icloud_id']
            syno_id = entry['synology_id']
            
            if icloud_id not in current_ids:
                logger.info(f"Deleting {syno_id} from Synology as it was removed from iCloud...")
                try:
                    if self.syno.delete_file(syno_id):
                        self.db.delete_entry(icloud_id)
                        if hasattr(self.db, "delete_job"):
                            self.db.delete_job(icloud_id)
                        if hasattr(self.db, "record_event"):
                            self.db.record_event("delete", f"Removed {syno_id} from Synology after iCloud deletion.")
                    else:
                        logger.warning(f"Synology delete failed for {syno_id}; keeping DB entry.")
                except Exception as e:
                    logger.error(f"Failed to delete {syno_id} from Synology: {e}")
                continue # Already handled this entry
            
            # 2. NAS Deletions: Items in SQLite but missing from NAS
            try:
                if not self.syno.file_exists(syno_id):
                    logger.info(f"File {syno_id} missing from NAS.")
                    if self.enable_nas_to_icloud_deletion:
                        logger.info(f"Deleting {icloud_id} from iCloud...")
                        if self.icloud.delete_photo(icloud_id):
                            self.db.delete_entry(icloud_id)
                            if hasattr(self.db, "delete_job"):
                                self.db.delete_job(icloud_id)
                            if hasattr(self.db, "record_event"):
                                self.db.record_event("delete", f"Removed {icloud_id} from iCloud after NAS deletion.")
                        else:
                            logger.warning(f"iCloud delete failed for {icloud_id}; keeping DB entry.")
                    else:
                        logger.warning(f"Keeping {icloud_id} in SQLite because NAS deletion is disabled.")
                else:
                    self.db.touch_entry(icloud_id)
            except Exception as e:
                logger.error(f"Error checking NAS file {syno_id}: {e}")

        # 3. Additions: queue new items and process in bounded parallel workers.
        new_items = [item for item in current_items if item["id"] not in db_icloud_ids]
        queued_count = 0
        if new_items and hasattr(self.db, "queue_jobs"):
            queued_count = self.db.queue_jobs(new_items)

        self._report_progress("queued", queued=queued_count, new_items=len(new_items))

        if hasattr(self.db, "reset_in_progress_jobs"):
            self.db.reset_in_progress_jobs()

        total_processed = 0
        total_uploaded = 0
        total_failed = 0

        direct_mode_jobs = self._build_direct_jobs(new_items)
        while True:
            self._wait_if_paused()
            batch_jobs: List[Dict[str, Any]] = []

            if hasattr(self.db, "fetch_pending_jobs"):
                pending_rows = self.db.fetch_pending_jobs(limit=self.queue_batch_size)
                for row in pending_rows:
                    job = self._normalize_job_row(row)
                    if not job.get("icloud_id") or not job.get("filename"):
                        continue
                    if hasattr(self.db, "mark_job_in_progress"):
                        self.db.mark_job_in_progress(job["icloud_id"])
                    job["attempts"] = int(job.get("attempts") or 0) + 1
                    batch_jobs.append(job)

            # Fallback for non-queue-aware DB mocks used in unit tests.
            if not batch_jobs and direct_mode_jobs:
                batch_jobs = direct_mode_jobs
                direct_mode_jobs = []

            if not batch_jobs:
                break

            batch_result = self._process_jobs(batch_jobs)
            total_processed += batch_result["processed"]
            total_uploaded += batch_result["uploaded"]
            total_failed += batch_result["failed"]

            counts = self.db.get_job_counts() if hasattr(self.db, "get_job_counts") else {}
            self._report_progress(
                "batch_complete",
                processed=total_processed,
                uploaded=total_uploaded,
                failed=total_failed,
                queued=counts.get("queued"),
                in_progress=counts.get("in_progress"),
                dead=counts.get("dead"),
            )

            if batch_result["processed"] == 0:
                break

            # Stop when only delayed retries remain.
            if hasattr(self.db, "fetch_pending_jobs") and not self.db.fetch_pending_jobs(limit=1):
                break

        if hasattr(self.db, "purge_completed_jobs"):
            self.db.purge_completed_jobs()

        if hasattr(self.db, "record_event"):
            self.db.record_event(
                "info",
                f"Sync cycle completed. Processed={total_processed}, uploaded={total_uploaded}, failed={total_failed}.",
            )

        final_counts = self.db.get_job_counts() if hasattr(self.db, "get_job_counts") else {}
        self._report_progress(
            "completed",
            processed=total_processed,
            uploaded=total_uploaded,
            failed=total_failed,
            queued=final_counts.get("queued"),
            dead=final_counts.get("dead"),
        )
