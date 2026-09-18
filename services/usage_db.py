"""
services/usage_db.py — Usage tracking for the TDS tool.
Turso if configured, else local SQLite. Stores hashed IPs only.
"""
import os
import sqlite3
import datetime
import threading

DB_PATH = os.environ.get("DEFECT_DB_PATH", "usage.db")
TURSO_URL = os.environ.get("TURSO_URL", "").strip()
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "").strip()
LOCAL_CACHE = "/tmp/usage_cache.db"

_LOCK = threading.Lock()


def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _use_turso():
    return bool(TURSO_URL and TURSO_TOKEN)


def _conn():
    if _use_turso():
        try:
            import libsql
            try:
                c = libsql.connect(LOCAL_CACHE, sync_url=TURSO_URL,
                                    auth_token=TURSO_TOKEN)
            except TypeError:
                c = libsql.connect(database=LOCAL_CACHE,
                                    sync_url=TURSO_URL,
                                    auth_token=TURSO_TOKEN)
            try:
                c.sync()
            except Exception:
                pass
            return c
        except Exception as e:
            print("[usage_db] Turso failed: " + repr(e))
    return sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)


def _sync(c):
    try:
        c.sync()
    except Exception:
        pass


def _day_bounds_utc():
    now = datetime.datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=1)
    return (start.strftime("%Y-%m-%d %H:%M:%S"),
            end.strftime("%Y-%m-%d %H:%M:%S"))


def init_db():
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                ip_hash TEXT,
                tool TEXT,
                source_filename TEXT,
                success INTEGER DEFAULT 0
            )
        """)
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_created "
                        "ON usage(created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_ip_created "
                        "ON usage(ip_hash, created_at)")
        except Exception:
            pass
        c.commit()
        _sync(c)
        try:
            c.close()
        except Exception:
            pass


init_db()


def record_usage(ip_hash, tool, source_filename, success):
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            cur.execute("""
                INSERT INTO usage
                    (created_at, ip_hash, tool, source_filename, success)
                VALUES (?, ?, ?, ?, ?)
            """, (_now(), ip_hash or "", tool or "tds",
                  source_filename or "", 1 if success else 0))
            c.commit()
            _sync(c)
        except Exception as e:
            return False, "Record failed: " + str(e)
        finally:
            try:
                c.close()
            except Exception:
                pass
    return True, None


def count_for_ip_today(ip_hash, tool="tds"):
    start, end = _day_bounds_utc()
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) FROM usage
                WHERE ip_hash=? AND tool=? AND created_at>=? AND created_at<?
            """, (ip_hash or "", tool or "tds", start, end))
            row = cur.fetchone()
            v = row[0] if row else 0
            if isinstance(v, dict):
                v = list(v.values())[0]
            return int(v or 0)
        except Exception as e:
            print("[usage_db] count_for_ip failed: " + repr(e))
            return 0
        finally:
            try:
                c.close()
            except Exception:
                pass


def count_global_today(tool="tds"):
    start, end = _day_bounds_utc()
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) FROM usage
                WHERE tool=? AND created_at>=? AND created_at<?
            """, (tool or "tds", start, end))
            row = cur.fetchone()
            v = row[0] if row else 0
            if isinstance(v, dict):
                v = list(v.values())[0]
            return int(v or 0)
        except Exception as e:
            print("[usage_db] count_global failed: " + repr(e))
            return 0
        finally:
            try:
                c.close()
            except Exception:
                pass


# =====================================================================
# NEW — read-only helpers for the usage dashboard
# =====================================================================
def count_success_fail_today(tool="tds"):
    """Return (success_count, fail_count) for the current UTC day."""
    start, end = _day_bounds_utc()
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        s = f = 0
        try:
            cur.execute("""
                SELECT COALESCE(SUM(success),0),
                       COUNT(*) - COALESCE(SUM(success),0)
                FROM usage WHERE tool=? AND created_at>=? AND created_at<?
            """, (tool or "tds", start, end))
            row = cur.fetchone()
            if row:
                if isinstance(row, dict):
                    vals = list(row.values())
                    s, f = int(vals[0] or 0), int(vals[1] or 0)
                else:
                    s, f = int(row[0] or 0), int(row[1] or 0)
        except Exception as e:
            print("[usage_db] count_success_fail failed: " + repr(e))
        finally:
            try:
                c.close()
            except Exception:
                pass
    return s, f


def distinct_ips_today(tool="tds"):
    start, end = _day_bounds_utc()
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            cur.execute("""
                SELECT COUNT(DISTINCT ip_hash) FROM usage
                WHERE tool=? AND created_at>=? AND created_at<?
            """, (tool or "tds", start, end))
            row = cur.fetchone()
            v = row[0] if row else 0
            if isinstance(v, dict):
                v = list(v.values())[0]
            return int(v or 0)
        except Exception:
            return 0
        finally:
            try:
                c.close()
            except Exception:
                pass


def daily_totals(days=7, tool="tds"):
    """Return [{date, label, total, success, fail}, ...] for the last
    N days, oldest first. Includes today."""
    now = datetime.datetime.utcnow()
    out = []
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            for i in range(days - 1, -1, -1):
                d = now - datetime.timedelta(days=i)
                start = d.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + datetime.timedelta(days=1)
                cur.execute("""
                    SELECT COUNT(*), COALESCE(SUM(success),0)
                    FROM usage WHERE tool=? AND created_at>=? AND created_at<?
                """, (tool or "tds",
                      start.strftime("%Y-%m-%d %H:%M:%S"),
                      end.strftime("%Y-%m-%d %H:%M:%S")))
                row = cur.fetchone()
                total = ok = 0
                if row:
                    if isinstance(row, dict):
                        vals = list(row.values())
                        total, ok = int(vals[0] or 0), int(vals[1] or 0)
                    else:
                        total, ok = int(row[0] or 0), int(row[1] or 0)
                out.append({
                    "date": start.strftime("%Y-%m-%d"),
                    "label": start.strftime("%d %b"),
                    "total": total,
                    "success": ok,
                    "fail": max(0, total - ok),
                })
        except Exception as e:
            print("[usage_db] daily_totals failed: " + repr(e))
        finally:
            try:
                c.close()
            except Exception:
                pass
    return out


def list_recent_usage(limit=200, ip_hash=None):
    """Return the most recent rows, newest first. If ip_hash is given,
    filter to that exact hash."""
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            if ip_hash:
                cur.execute("""
                    SELECT id, created_at, ip_hash, tool,
                           source_filename, success
                    FROM usage WHERE ip_hash=?
                    ORDER BY id DESC LIMIT ?
                """, (ip_hash, int(limit)))
            else:
                cur.execute("""
                    SELECT id, created_at, ip_hash, tool,
                           source_filename, success
                    FROM usage ORDER BY id DESC LIMIT ?
                """, (int(limit),))
            rows = cur.fetchall()
        except Exception as e:
            print("[usage_db] list_recent failed: " + repr(e))
            rows = []
        finally:
            try:
                c.close()
            except Exception:
                pass
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(r)
            continue
        try:
            out.append({
                "id": r[0], "created_at": r[1], "ip_hash": r[2],
                "tool": r[3], "source_filename": r[4],
                "success": bool(r[5]),
            })
        except Exception:
            pass
    return out
