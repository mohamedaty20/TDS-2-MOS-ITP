"""
main.py — Standalone TDS → MOS + ITP tool.
"""
import os
import json as _json
from nicegui import ui, app
from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware

from ui.tds_page import build_tds_ui
from services import usage_limiter as usage_lim
from services import usage_db as usage_db_mod


class TDSAdminKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        try:
            if usage_lim.TDS_ADMIN_KEY:
                k = request.query_params.get("key", "")
                if k and k == usage_lim.TDS_ADMIN_KEY:
                    response.set_cookie(
                        usage_lim.COOKIE_NAME,
                        k,
                        max_age=usage_lim.COOKIE_MAX_AGE,
                        httponly=True,
                        secure=True,
                        samesite="lax",
                        path="/",
                    )
        except Exception as e:
            print("[tds] admin-cookie middleware err: " + repr(e))
        return response


app.add_middleware(TDSAdminKeyMiddleware)


@ui.page('/')
@ui.page('/tds')
def tds_route():
    build_tds_ui()


@app.get('/tds/usage-status')
def tds_usage_status(key: str = ""):
    if not usage_lim.TDS_ADMIN_KEY or key != usage_lim.TDS_ADMIN_KEY:
        return Response(content='{"error":"forbidden"}', status_code=403,
                        media_type="application/json")
    return Response(content=_json.dumps(usage_lim.usage_status("tds")),
                     media_type="application/json")


# --- Register the usage dashboard page ---
# Imported here (not at the top) so the nicegui `ui` name above is not
# shadowed by the local `ui` package.
from ui import usage_page as _tds_usage_page  # noqa: E402,F401


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        title="TDS → MOS & ITP",
        reload=False,
        reconnect_timeout=60.0,
        storage_secret=os.environ.get("SESSION_SECRET", "change-me-now"),
    )
