"""
services/usage_limiter.py — Per-IP + global daily rate limiting for TDS.
Hashes IPs with SHA-256 + IP_SALT. Never stores raw IPs.
"""
import os
import datetime
import hashlib

from services import usage_db


IP_SALT = os.environ.get("IP_SALT", "change-me-ip-salt").strip()
TDS_ADMIN_KEY = os.environ.get("TDS_ADMIN_KEY", "").strip()

PER_IP_DAILY_LIMIT = 20
GLOBAL_DAILY_LIMIT = 300

COOKIE_NAME = "tds_admin_bypass"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days


def hash_ip(ip):
    if not ip:
        ip = "unknown"
    return hashlib.sha256((IP_SALT + "|" + str(ip)).encode()).hexdigest()


def get_client_ip(request):
    if request is None:
        return "unknown"
    try:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    except Exception:
        pass
    try:
        xri = request.headers.get("x-real-ip", "")
        if xri:
            return xri.strip()
    except Exception:
        pass
    try:
        if request.client and request.client.host:
            return request.client.host
    except Exception:
        pass
    return "unknown"


def is_admin_bypass(request):
    if not TDS_ADMIN_KEY or request is None:
        return False
    try:
        c = request.cookies.get(COOKIE_NAME, "")
        if c and c == TDS_ADMIN_KEY:
            return True
    except Exception:
        pass
    try:
        q = request.query_params.get("key", "")
        if q and q == TDS_ADMIN_KEY:
            return True
    except Exception:
        pass
    return False


def _next_midnight_utc():
    now = datetime.datetime.utcnow()
    return (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)


def _reset_text():
    now = datetime.datetime.utcnow()
    nm = _next_midnight_utc()
    secs = int((nm - now).total_seconds())
    if secs < 0:
        secs = 0
    h = secs // 3600
    m = (secs % 3600) // 60
    if h > 0:
        return "Resets in " + str(h) + "h " + str(m) + "m (midnight UTC)."
    if m > 0:
        return "Resets in " + str(m) + "m (midnight UTC)."
    return "Resets at midnight UTC."


def check_limit(ip, tool="tds"):
    """Return (allowed, message). If allowed, message is ''."""
    ip_hash = hash_ip(ip)
    per_ip = usage_db.count_for_ip_today(ip_hash, tool)
    if per_ip >= PER_IP_DAILY_LIMIT:
        return False, (
            "You've reached today's limit of " +
            str(PER_IP_DAILY_LIMIT) + " generations from this device. "
            + _reset_text()
        )
    global_count = usage_db.count_global_today(tool)
    if global_count >= GLOBAL_DAILY_LIMIT:
        return False, (
            "The tool is at capacity today. Try again tomorrow. "
            + _reset_text()
        )
    return True, ""


def record(ip, tool, filename, success):
    return usage_db.record_usage(hash_ip(ip), tool, filename, success)


def usage_status(tool="tds"):
    start, end = usage_db._day_bounds_utc()
    return {
        "tool": tool,
        "day_utc": start[:10],
        "global_count": usage_db.count_global_today(tool),
        "global_limit": GLOBAL_DAILY_LIMIT,
        "per_ip_limit": PER_IP_DAILY_LIMIT,
        "resets_utc": _next_midnight_utc().strftime("%Y-%m-%d %H:%M:%S"),
        "admin_key_configured": bool(TDS_ADMIN_KEY),
    }
