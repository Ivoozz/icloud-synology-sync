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

    def get_all_entries(self):
        return self.conn.execute("SELECT * FROM sync_entries").fetchall()

    def delete_entry(self, icloud_id):
        self.conn.execute("DELETE FROM sync_entries WHERE icloud_id = ?", (icloud_id,))
        self.conn.commit()
