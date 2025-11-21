# services.py — database service layer for metrics & summaries
import sqlite3
from typing import List, Tuple, Dict, Any

def revenue_by_day(conn: sqlite3.Connection, limit: int = 10) -> Tuple[List[str], List[float]]:
    """
    Returns two parallel lists: labels (YYYY-MM-DD) and revenue totals for each day.
    """
    rows = conn.execute("""
        SELECT substr(a.start_ts,1,10) AS day,
               ROUND(COALESCE(SUM(i.total),0), 2) AS revenue
        FROM appointments a
        LEFT JOIN invoices i ON i.appt_id = a.appt_id
        GROUP BY day
        ORDER BY day
        LIMIT ?
    """, (limit,)).fetchall()
    labels = [r["day"] for r in rows]
    values = [float(r["revenue"]) for r in rows]
    return labels, values

def kpis(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Returns a dict with total_revenue, total_appts, avg_invoice, next_appt.
    """
    cur = conn.cursor()
    total_revenue = cur.execute(
        "SELECT ROUND(COALESCE(SUM(total),0),2) FROM invoices"
    ).fetchone()[0] or 0

    total_appts = cur.execute(
        "SELECT COUNT(*) FROM appointments"
    ).fetchone()[0] or 0

    avg = cur.execute(
        "SELECT ROUND(AVG(total),2) FROM invoices"
    ).fetchone()[0]
    avg_invoice = avg if avg is not None else 0

    next_appt = cur.execute(
        "SELECT MIN(start_ts) FROM appointments WHERE datetime(start_ts) >= datetime('now')"
    ).fetchone()[0]

    return {
        "total_revenue": total_revenue,
        "total_appts": total_appts,
        "avg_invoice": avg_invoice,
        "next_appt": next_appt,
    }

def status_mix(conn: sqlite3.Connection) -> Tuple[List[str], List[int]]:
    """
    Returns (labels, counts) for appointment statuses.
    """
    rows = conn.execute(
        "SELECT status, COUNT(*) AS c FROM appointments GROUP BY status ORDER BY status"
    ).fetchall()
    labels = [r["status"] for r in rows]
    counts = [r["c"] for r in rows]
    return labels, counts

def daily_summary(conn: sqlite3.Connection, days: int = 14):
    """
    Returns a list of dicts: [{day, appts, revenue}], ordered by day ASC.
    """
    rows = conn.execute("""
        SELECT substr(a.start_ts,1,10) AS day,
               COUNT(a.appt_id)        AS appts,
               ROUND(COALESCE(SUM(i.total),0), 2) AS revenue
        FROM appointments a
        LEFT JOIN invoices i ON i.appt_id = a.appt_id
        GROUP BY day
        ORDER BY day
        LIMIT ?
    """, (days,)).fetchall()
    return [{"day": r["day"], "appts": r["appts"], "revenue": float(r["revenue"])} for r in rows]