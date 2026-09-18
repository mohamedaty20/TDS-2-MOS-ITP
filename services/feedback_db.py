"""
services/feedback_db.py — Feedback storage (Turso if configured, else local SQLite).
"""
import os
import sqlite3
import datetime
import threading

DB_PATH = os.environ.get("DEFECT_DB_PATH", "feedback.db")
TURSO_URL = os.environ.get("TURSO_URL", "").strip()
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "").strip()
LOCAL_CACHE = "/tmp/feedback_cache.db"

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
            print("[feedback] Turso failed: " + repr(e))
    return sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)


def _sync(c):
    try:
        c.sync()
    except Exception:
        pass


def init_feedback_db():
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                page TEXT,
                created_at TEXT
            )
        """)
        c.commit()
        _sync(c)
        try:
            c.close()
        except Exception:
            pass


init_feedback_db()


def add_feedback(text, page="tds"):
    text = (text or "").strip()
    if not text:
        return False, "Empty feedback."
    if len(text) > 4000:
        text = text[:4000]
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            cur.execute(
                "INSERT INTO feedback (text, page, created_at) "
                "VALUES (?, ?, ?)",
                (text, page, _now()))
            c.commit()
            _sync(c)
        except Exception as e:
            return False, "Save failed: " + str(e)
        finally:
            try:
                c.close()
            except Exception:
                pass
    return True, None


def list_feedback(limit=200):
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            cur.execute(
                "SELECT id, text, page, created_at FROM feedback "
                "ORDER BY id DESC LIMIT ?", (int(limit),))
            rows = cur.fetchall()
        except Exception:
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
            out.append({"id": r[0], "text": r[1], "page": r[2],
                        "created_at": r[3]})
        except Exception:
            pass
    return out
