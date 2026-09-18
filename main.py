# =====================================================================
# TDS TOOLS (standalone)
# =====================================================================
@ui.page('/tds')
def tds_route():
    uid = _current_user_id()
    if not uid:
        ui.navigate.to('/login')
        return
    active, plan, reason = bdb.is_active(uid)
    if not active:
        _render_expired(plan, reason)
        return
    from ui.tds_page import build_tds_ui
    build_tds_ui(uid)
