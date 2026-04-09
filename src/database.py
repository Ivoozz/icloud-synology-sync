import sqlite3
from datetime import datetime, timedelta, timezone


def _format_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")

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
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_jobs (
                icloud_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                next_retry_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sync_jobs_status_retry
            ON sync_jobs(status, next_retry_at)
        """)
        self.conn.commit()

    def upsert_sync_entry(self, icloud_id, synology_id, file_hash):
        self.conn.execute(
            """
            INSERT INTO sync_entries (icloud_id, synology_id, file_hash, last_seen)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(icloud_id) DO UPDATE SET
                synology_id = excluded.synology_id,
                file_hash = excluded.file_hash,
                last_seen = CURRENT_TIMESTAMP
            """,
            (icloud_id, synology_id, file_hash)
        )
        self.conn.commit()

    def get_entry_by_icloud_id(self, icloud_id):
        return self.conn.execute("SELECT * FROM sync_entries WHERE icloud_id = ?", (icloud_id,)).fetchone()

    def get_all_entries(self):
        return self.conn.execute("SELECT * FROM sync_entries").fetchall()

    def delete_entry(self, icloud_id):
        self.conn.execute("DELETE FROM sync_entries WHERE icloud_id = ?", (icloud_id,))
        self.conn.commit()

    def touch_entry(self, icloud_id):
        self.conn.execute(
            "UPDATE sync_entries SET last_seen = CURRENT_TIMESTAMP WHERE icloud_id = ?",
            (icloud_id,)
        )
        self.conn.commit()

    def record_event(self, event_type, message):
        self.conn.execute(
            "INSERT INTO sync_events (event_type, message, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (event_type, message)
        )
        self.conn.commit()

    def get_recent_events(self, limit=20):
        return self.conn.execute(
            """
            SELECT event_type, message, created_at
            FROM sync_events
            WHERE (? IS NULL OR event_type = ?)
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (None, None, limit)
        ).fetchall()

    def get_recent_events_by_type(self, event_type, limit=20):
        return self.conn.execute(
            """
            SELECT event_type, message, created_at
            FROM sync_events
            WHERE event_type = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (event_type, limit)
        ).fetchall()

    def queue_jobs(self, items):
        rows = []
        for item in items:
            icloud_id = item.get("id")
            filename = item.get("filename")
            if not icloud_id or not filename:
                continue
            rows.append((icloud_id, filename))

        if not rows:
            return 0

        self.conn.executemany(
            """
            INSERT INTO sync_jobs (icloud_id, filename, status, attempts, last_error, next_retry_at, updated_at)
            VALUES (?, ?, 'queued', 0, NULL, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(icloud_id) DO UPDATE SET
                filename = excluded.filename,
                status = CASE
                    WHEN sync_jobs.status = 'done' THEN sync_jobs.status
                    ELSE 'queued'
                END,
                last_error = CASE
                    WHEN sync_jobs.status = 'done' THEN sync_jobs.last_error
                    ELSE NULL
                END,
                next_retry_at = CASE
                    WHEN sync_jobs.status = 'done' THEN sync_jobs.next_retry_at
                    ELSE NULL
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    def fetch_pending_jobs(self, limit=20):
        return self.conn.execute(
            """
            SELECT icloud_id, filename, status, attempts, last_error, next_retry_at
            FROM sync_jobs
            WHERE
                status = 'queued'
                OR (status = 'failed' AND (next_retry_at IS NULL OR next_retry_at <= datetime('now')))
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    def mark_job_in_progress(self, icloud_id):
        self.conn.execute(
            """
            UPDATE sync_jobs
            SET
                status = 'in_progress',
                attempts = attempts + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE icloud_id = ?
            """,
            (icloud_id,)
        )
        self.conn.commit()

    def mark_job_done(self, icloud_id):
        self.conn.execute(
            """
            UPDATE sync_jobs
            SET
                status = 'done',
                last_error = NULL,
                next_retry_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE icloud_id = ?
            """,
            (icloud_id,)
        )
        self.conn.commit()

    def mark_job_failed(self, icloud_id, error_message, retryable=True, delay_seconds=0):
        if retryable:
            next_retry_at = _format_utc(datetime.now(timezone.utc) + timedelta(seconds=max(delay_seconds, 0)))
            status = "failed"
        else:
            next_retry_at = None
            status = "dead"

        self.conn.execute(
            """
            UPDATE sync_jobs
            SET
                status = ?,
                last_error = ?,
                next_retry_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE icloud_id = ?
            """,
            (status, str(error_message)[:1000], next_retry_at, icloud_id),
        )
        self.conn.commit()

    def get_job_counts(self):
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS queued,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status = 'dead' THEN 1 ELSE 0 END) AS dead,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done
            FROM sync_jobs
            """
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "queued": int(row["queued"] or 0),
            "in_progress": int(row["in_progress"] or 0),
            "failed": int(row["failed"] or 0),
            "dead": int(row["dead"] or 0),
            "done": int(row["done"] or 0),
        }

    def reset_in_progress_jobs(self):
        self.conn.execute(
            """
            UPDATE sync_jobs
            SET
                status = 'failed',
                next_retry_at = datetime('now'),
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'in_progress'
            """
        )
        self.conn.commit()

    def delete_job(self, icloud_id):
        self.conn.execute("DELETE FROM sync_jobs WHERE icloud_id = ?", (icloud_id,))
        self.conn.commit()

    def purge_completed_jobs(self):
        self.conn.execute("DELETE FROM sync_jobs WHERE status = 'done'")
        self.conn.commit()
