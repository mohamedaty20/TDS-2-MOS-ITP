"""
main.py — Standalone TDS → MOS + ITP tool.
"""
import os
from nicegui import ui

from ui.tds_page import build_tds_ui


@ui.page('/')
@ui.page('/tds')
def tds_route():
    build_tds_ui()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        title="TDS → MOS & ITP",
        reload=False,
        reconnect_timeout=60.0,
        storage_secret=os.environ.get("SESSION_SECRET", "change-me-now"),
    )
