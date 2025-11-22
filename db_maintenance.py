# db_maintenance.py
import sqlite3

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_appt_start      ON appointments(start_ts);
CREATE INDEX IF NOT EXISTS idx_appt_provider  ON appointments(provider_id);
CREATE INDEX IF NOT EXISTS idx_appt_patient   ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appt_status    ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_invoice_appt   ON invoices(appt_id);
"""

def enable_fk(conn: sqlite3.Connection) -> None:
    # Always enforce referential integrity
    conn.execute("PRAGMA foreign_keys = ON;")

def ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(INDEX_SQL)
