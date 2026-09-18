"""
ui/usage_page.py — Owner-only usage dashboard for the TDS tool.
Shows today's totals, a 7-day bar chart, and a scrollable row log.
Admin-key required (?key=... or the tds_admin_bypass cookie).
"""
import html as _html_mod
from nicegui import ui, context

from services import usage_limiter as usage_lim
from services import usage_db


STYLE = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  html, body {
    background: #0b0b0b !important; color: #e8e8e8 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px; -webkit-font-smoothing: antialiased;
  }
  .nicegui-content { padding: 0 !important; }
  .q-page, .q-layout { background: #0b0b0b !important; }
  .q-btn {
    border-radius: 3px !important; text-transform: none !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 500 !important; min-height: 30px !important;
    padding: 0 10px !important; font-size: 11px !important;
    box-shadow: none !important;
  }
  .btn-soft { background: #161616 !important; color: #e8e8e8 !important;
              border: 1px solid #262626 !important; }
  .q-field--outlined .q-field__control {
    border-radius: 3px !important; background: #161616 !important;
    min-height: 32px !important;
  }
  .q-field--outlined .q-field__control:before { border-color: #262626 !important; }
  .q-field--outlined.q-field--focused .q-field__control:after {
    border-color: #14b8a6 !important;
  }
  .q-field__native, .q-field__input {
    color: #e8e8e8 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
  }
  .page-shell { display: flex; flex-direction: column;
                min-height: 100vh; width: 100%; }
  .app-header {
    background: rgba(11,11,11,0.94);
    border-bottom: 1px solid #1e1e1e;
    padding: 10px 14px; display: flex; align-items: center;
    justify-content: space-between; box-sizing: border-box;
    width: 100%;
  }
  .app-header .brand { font-weight: 700; font-size: 12px; color: #e8e8e8; }
  .app-header .brand::before {
    content: '\\25CF '; color: #14b8a6; font-size: 9px;
    vertical-align: middle; margin-right: 4px;
  }
  .main-content { padding: 14px; padding-bottom: 40px;
                  max-width: 980px; margin: 0 auto; width: 100%;
                  box-sizing: border-box; }
  .h1 { font-size: 20px; font-weight: 800; color: #e8e8e8;
        letter-spacing: -0.02em; margin-bottom: 4px; }
  .sub { font-size: 11px; color: #808080; margin-bottom: 14px; }
  .card { background: #101010; border: 1px solid #1e1e1e;
          border-radius: 4px; padding: 14px 16px; width: 100%;
          box-sizing: border-box; margin-bottom: 12px; }
  .metric-strip {
    display: grid; grid-template-columns: repeat(4, 1fr);
    background: #101010; border: 1px solid #1e1e1e;
    border-radius: 4px; overflow: hidden; margin-bottom: 12px;
  }
  .metric-cell { padding: 12px 14px; border-right: 1px solid #1e1e1e; }
  .metric-cell:last-child { border-right: none; }
  .metric-label {
    font-size: 9px; font-weight: 700; color: #5a5a5a;
    letter-spacing: 0.14em; text-transform: uppercase;
    margin-bottom: 4px;
  }
  .metric-value {
    font-size: 22px; font-weight: 700; color: #e8e8e8;
    line-height: 1.1; font-variant-numeric: tabular-nums;
  }
  .metric-value.accent { color: #14b8a6; }
  .metric-value.warn { color: #fbbf24; }
  .metric-value.danger { color: #f87171; }
  .metric-value.success { color: #4ade80; }
  .metric-sub { font-size: 10px; color: #5a5a5a; margin-top: 3px; }
  .label { font-size: 9px; font-weight: 700; color: #5a5a5a;
           text-transform: uppercase; letter-spacing: 0.14em;
           display: block; margin-bottom: 8px; }
  table.usage {
    width: 100%; border-collapse: collapse; font-size: 11px;
    font-variant-numeric: tabular-nums;
  }
  table.usage th {
    text-align: left; padding: 6px 8px;
    font-size: 9px; letter-spacing: 0.14em;
    color: #14b8a6; text-transform: uppercase;
    background: #0a0a0a; border-bottom: 2px solid #d0d0d0;
  }
  table.usage td {
    padding: 6px 8px; color: #d0d0d0;
    border-bottom: 1px solid #1e1e1e;
    word-break: break-word;
  }
  table.usage tr:hover td { background: #161616; }
  .pill-ok { color: #4ade80; font-weight: 700; font-size: 10px; }
  .pill-fail { color: #f87171; font-weight: 700; font-size: 10px; }
  .ip-link { color: #14b8a6; cursor: pointer;
             font-family: 'JetBrains Mono', monospace; }
  .ip-link:hover { text-decoration: underline; }
  .scroll-log { max-height: 520px; overflow-y: auto;
                border: 1px solid #1e1e1e; border-radius: 4px;
                background: #0e0e0e; width: 100%; }
  .deny-wrap { display: flex; align-items: center; justify-content: center;
               min-height: 60vh; }
  .deny-card { background: #101010; border: 1px solid #1e1e1e;
               border-left: 3px solid #f87171; border-radius: 4px;
               padding: 24px 28px; max-width: 480px; text-align: center; }
  .deny-title { font-size: 16px; font-weight: 700; color: #f87171;
                margin-bottom: 8px; }
  .deny-msg { font-size: 12px; color: #b8b8b8; line-height: 1.6; }
</style>
"""


def _get_provided_key(key_param):
    provided = (key_param or "").strip()
    if provided:
        return provided
    try:
        req = context.client.request
        if req is not None:
            c = req.cookies.get(usage_lim.COOKIE_NAME, "")
            if c:
                return c
    except Exception:
        pass
    return ""


def _metric(label, value, variant, subtext):
    with ui.element('div').classes("metric-cell"):
        ui.label(label).classes("metric-label")
        cls = "metric-value"
        if variant:
            cls += " " + variant
        ui.label(str(value)).classes(cls)
        if subtext:
            ui.label(subtext).classes("metric-sub")


@ui.page('/tds/usage')
def tds_usage_page(key: str = ""):
    ui.add_head_html(STYLE)

    admin_key = usage_lim.TDS_ADMIN_KEY
    provided = _get_provided_key(key)

    if not admin_key or provided != admin_key:
        with ui.element('div').classes("deny-wrap"):
            with ui.element('div').classes("deny-card"):
                ui.label("Access denied").classes("deny-title")
                ui.label(
                    "This page is private. Append ?key=YOUR_TDS_ADMIN_KEY "
                    "to the URL. If the key is correct, the browser will "
                    "remember it for 30 days."
                ).classes("deny-msg")
        return

    state = {"ip_filter": ""}

    with ui.element('div').classes("page-shell"):
        with ui.element('div').classes("app-header"):
            ui.label("TDS USAGE · ADMIN").classes("brand")
            with ui.element('div').style("display:flex;gap:8px;"):
                ui.button(
                    "Usage status (JSON)",
                    on_click=lambda: ui.navigate.to(
                        "/tds/usage-status?key=" + admin_key)
                ).classes("btn-soft")
                ui.button("Back to tool",
                          on_click=lambda: ui.navigate.to("/tds")
                          ).classes("btn-soft")

        with ui.element('div').classes("main-content"):
            ui.label("USAGE DASHBOARD").classes("h1")
            ui.label(
                "All times in UTC. IPs are stored only as SHA-256 hashes "
                "and cannot be reversed to a raw address."
            ).classes("sub")

            metrics_holder = ui.element('div').style("width:100%;")

            def render_metrics():
                metrics_holder.clear()
                s = usage_lim.usage_status("tds")
                global_c = s["global_count"]
                global_lim = s["global_limit"]
                per_ip_lim = s["per_ip_limit"]
                ok, fail = usage_db.count_success_fail_today("tds")
                unique_ips = usage_db.distinct_ips_today("tds")

                pct = 0
                if global_lim > 0:
                    pct = int(round(100.0 * global_c / global_lim))

                cap_cls = "accent"
                if pct >= 100:
                    cap_cls = "danger"
                elif pct >= 75:
                    cap_cls = "warn"

                with metrics_holder:
                    with ui.element('div').classes("metric-strip"):
                        _metric("TODAY TOTAL", str(global_c),
                                 cap_cls,
                                 "of " + str(global_lim) + " (" +
                                 str(pct) + "%)")
                        _metric("SUCCESS", str(ok), "success", "")
                        _metric("FAILED", str(fail), "", "")
                        _metric("UNIQUE IPs", str(unique_ips), "accent",
                                 "per-IP limit " + str(per_ip_lim))

            render_metrics()

            with ui.element('div').classes("card"):
                ui.label("LAST 7 DAYS").classes("label")
                chart_holder = ui.element('div').style("width:100%;")

                def render_chart():
                    chart_holder.clear()
                    totals = usage_db.daily_totals(days=7, tool="tds")
                    labels = [d["label"] for d in totals]
                    values = [d["total"] for d in totals]
                    successes = [d["success"] for d in totals]
                    with chart_holder:
                        ui.echart({
                            "backgroundColor": "transparent",
                            "tooltip": {"trigger": "axis"},
                            "legend": {
                                "data": ["Total", "Success"],
                                "textStyle": {"color": "#808080",
                                              "fontSize": 10},
                                "top": 0,
                            },
                            "grid": {"left": 40, "right": 14,
                                     "top": 30, "bottom": 28},
                            "xAxis": {
                                "type": "category",
                                "data": labels,
                                "axisLine": {"lineStyle":
                                              {"color": "#262626"}},
                                "axisLabel": {"color": "#808080",
                                              "fontSize": 10},
                            },
                            "yAxis": {
                                "type": "value",
                                "axisLine": {"lineStyle":
                                              {"color": "#262626"}},
                                "axisLabel": {"color": "#808080",
                                              "fontSize": 10},
                                "splitLine": {"lineStyle":
                                               {"color": "#1a1a1a"}},
                            },
                            "series": [
                                {
                                    "name": "Total",
                                    "type": "bar",
                                    "data": values,
                                    "itemStyle": {
                                        "color": "#14b8a6",
                                        "borderRadius": [3, 3, 0, 0],
                                    },
                                    "barWidth": "45%",
                                },
                                {
                                    "name": "Success",
                                    "type": "line",
                                    "smooth": True,
                                    "symbol": "circle",
                                    "symbolSize": 6,
                                    "lineStyle": {"width": 2,
                                                   "color": "#4ade80"},
                                    "itemStyle": {"color": "#4ade80"},
                                    "data": successes,
                                },
                            ],
                        }).style("height:220px;width:100%;")

                render_chart()

            with ui.element('div').classes("card"):
                with ui.element('div').style(
                    "display:flex;justify-content:space-between;"
                    "align-items:center;gap:8px;margin-bottom:10px;"
                    "flex-wrap:wrap;"
                ):
                    ui.label("RECENT GENERATIONS").classes("label").style(
                        "margin-bottom:0;")
                    with ui.element('div').style(
                        "display:flex;gap:6px;align-items:center;"
                    ):
                        filter_in = ui.input(
                            placeholder="Filter by ip_hash prefix…"
                        ).props("dense clearable").style("width:220px;")
                        ui.button("Refresh", icon="refresh",
                                  on_click=lambda: _refresh_all()
                                  ).classes("btn-soft")
                        ui.button("Clear filter", icon="clear_all",
                                  on_click=lambda: _clear_filter()
                                  ).classes("btn-soft")

                log_holder = ui.element('div').classes("scroll-log")

                def render_log():
                    log_holder.clear()
                    filt = (state.get("ip_filter") or "").strip().lower()
                    rows = usage_db.list_recent_usage(limit=200)
                    if filt:
                        rows = [r for r in rows
                                if (r.get("ip_hash") or "")
                                .lower().startswith(filt)]

                    with log_holder:
                        if not rows:
                            ui.label("No rows.").classes("sub").style(
                                "text-align:center;padding:26px 0;"
                                "margin-bottom:0;color:#5a5a5a;")
                            return
                        html = ['<table class="usage">',
                                '<thead><tr>',
                                '<th>ID</th>',
                                '<th>Time (UTC)</th>',
                                '<th>IP hash</th>',
                                '<th>Tool</th>',
                                '<th>File</th>',
                                '<th>Status</th>',
                                '</tr></thead><tbody>']
                        for r in rows:
                            rid = r.get("id", "")
                            ts = str(r.get("created_at") or "")[:19]
                            iph = r.get("ip_hash") or ""
                            iph_short = iph[:12] + ("…"
                                                     if len(iph) > 12 else "")
                            tool = str(r.get("tool") or "")
                            fn = str(r.get("source_filename") or "")
                            fn_short = fn[:48] + ("…"
                                                   if len(fn) > 48 else "")
                            okflag = bool(r.get("success"))
                            status = ('<span class="pill-ok">OK</span>'
                                      if okflag else
                                      '<span class="pill-fail">FAIL</span>')
                            html.append('<tr>')
                            html.append('<td>' +
                                        _html_mod.escape(str(rid)) + '</td>')
                            html.append('<td>' +
                                        _html_mod.escape(ts) + '</td>')
                            html.append(
                                '<td><span class="ip-link" '
                                'data-ip="' +
                                _html_mod.escape(iph) +
                                '">' +
                                _html_mod.escape(iph_short) +
                                '</span></td>')
                            html.append('<td>' +
                                        _html_mod.escape(tool) + '</td>')
                            html.append('<td>' +
                                        _html_mod.escape(fn_short) +
                                        '</td>')
                            html.append('<td>' + status + '</td>')
                            html.append('</tr>')
                        html.append('</tbody></table>')
                        ui.html("".join(html))
                        ui.run_javascript("""
                            (function(){
                              var links = document.querySelectorAll(
                                '.scroll-log .ip-link');
                              links.forEach(function(el){
                                el.onclick = function(){
                                  var ip = el.getAttribute('data-ip') || '';
                                  emitEvent('usage_pick_ip', ip);
                                };
                              });
                            })();
                        """)

                def _clear_filter():
                    try:
                        filter_in.value = ""
                    except Exception:
                        pass
                    state["ip_filter"] = ""
                    render_log()

                def _refresh_all():
                    render_metrics()
                    render_chart()
                    render_log()

                def _on_pick_ip(e):
                    try:
                        ip = e.args[0] if e.args else ""
                    except Exception:
                        ip = ""
                    if not ip:
                        return
                    state["ip_filter"] = ip
                    try:
                        filter_in.value = ip[:12]
                    except Exception:
                        pass
                    render_log()

                ui.on("usage_pick_ip", _on_pick_ip)

                def _on_filter(e=None):
                    val = ""
                    try:
                        val = (filter_in.value or "").strip()
                    except Exception:
                        val = ""
                    state["ip_filter"] = val
                    render_log()

                filter_in.on("update:model-value", _on_filter)

                render_log()
