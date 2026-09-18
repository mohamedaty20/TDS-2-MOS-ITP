"""
services/tds_documents_db.py — Metadata for TDS-generated documents.
Stores company header info (no logo bytes) so the owner can review
what was generated. Turso if configured, else local SQLite.
"""
import os
import sqlite3
import datetime
import threading

DB_PATH = os.environ.get("DEFECT_DB_PATH", "tds_documents.db")
TURSO_URL = os.environ.get("TURSO_URL", "").strip()
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "").strip()
LOCAL_CACHE = "/tmp/tds_documents_cache.db"

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
            print("[tds_docs] Turso failed: " + repr(e))
    return sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)


def _sync(c):
    try:
        c.sync()
    except Exception:
        pass


def init_db():
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tds_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                project_name TEXT,
                location TEXT,
                prepared_by TEXT,
                doc_date TEXT,
                product_name TEXT,
                doc_type TEXT,
                created_at TEXT
            )
        """)
        c.commit()
        _sync(c)
        try:
            c.close()
        except Exception:
            pass


init_db()


def save_document_meta(company_name="", project_name="", location="",
                        prepared_by="", doc_date="",
                        product_name="", doc_type="MOS"):
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            cur.execute("""
                INSERT INTO tds_documents
                    (company_name, project_name, location, prepared_by,
                     doc_date, product_name, doc_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_name or "", project_name or "", location or "",
                  prepared_by or "", doc_date or "", product_name or "",
                  doc_type or "MOS", _now()))
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


def list_documents(limit=200):
    with _LOCK:
        c = _conn()
        cur = c.cursor()
        try:
            cur.execute("""
                SELECT id, company_name, project_name, location,
                       prepared_by, doc_date, product_name, doc_type,
                       created_at
                FROM tds_documents
                ORDER BY id DESC LIMIT ?
            """, (int(limit),))
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
            out.append({
                "id": r[0], "company_name": r[1], "project_name": r[2],
                "location": r[3], "prepared_by": r[4], "doc_date": r[5],
                "product_name": r[6], "doc_type": r[7], "created_at": r[8],
            })
        except Exception:
            pass
    return out
