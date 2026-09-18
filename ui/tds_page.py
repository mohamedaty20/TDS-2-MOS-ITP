"""
ui/tds_page.py — Standalone TDS → MOS + ITP generator.

Extracts ONLY the TDS feature from ui/defect_page.py into a dedicated
route /tds. Reuses:
  - services.tds_service.generate_mos_itp        (AI generation)
  - services.tds_service.build_mos_pdf           (PDF export)
  - services.tds_service.build_itp_pdf           (PDF export)
  - services.ai_service.call_gemini_json         (Gemini client)
  - services.defect_service.extract_document_text (document text)
  - ui.defect_page._ocr_handwriting              (image OCR)
"""
import asyncio
import datetime
import html as _html_mod
from nicegui import ui, app

from services import defect_db as db
from services import defect_service as svc
from services import tds_service as tds
from services.ai_service import call_gemini_json
from ui.pwa import inject_pwa
from ui.defect_page import (
    _inject_theme, _ocr_handwriting,
    BTN_PRIMARY, BTN_SOFT, BTN_DANGER, BTN_OUTLINE, BTN_SUCCESS,
)


def build_tds_ui(user_id):
    _inject_theme()
    inject_pwa()

    user = db.get_user(user_id)
    tstate = {
        "result": None,
        "running": False,
        "error": None,
        "filename": "",
    }

    # ---- Top bar ----
    with ui.element('div').classes("app-topbar"):
        with ui.element('div').classes("app-header"):
            with ui.element('div').style(
                "display:flex;align-items:center;gap:10px;"
            ):
                ui.label("TDS → MOS & ITP").classes("brand")
            with ui.element('div').style(
                "display:flex;align-items:center;gap:6px;"
            ):
                if user and user.get("name"):
                    ui.label(str(user["name"])).style(
                        "font-size:11px;color:#808080;"
                        "max-width:180px;overflow:hidden;"
                        "text-overflow:ellipsis;white-space:nowrap;")
                ui.button("Back to app",
                          on_click=lambda: ui.navigate.to("/app")).props(
                    "flat dense no-caps size=sm").style(
                    "color:#e8e8e8;font-weight:600;font-size:10px;"
                    "border:1px solid #262626;border-radius:2px;"
                    "padding:0 8px;min-height:26px;")

    content = ui.element('div').classes("main-content")

    def render():
        content.clear()
        with content:
            _render_tds(tstate, render)

    render()


def _render_tds(tstate, render):
    with ui.element('div').classes("section-head"):
        ui.label("TDS → MOS & ITP").classes("h1")

        def _refresh():
            tstate["result"] = None
            tstate["error"] = None
            render()
        ui.button(icon="refresh", on_click=_refresh).props(
            "flat round dense size=sm").style("color:#808080;")

    ui.label(
        "Upload a manufacturer Technical Data Sheet (PDF, DOCX, TXT, "
        "or image). The tool extracts critical parameters with AI and "
        "drafts a Method Statement + an Inspection & Test Plan."
    ).classes("muted").style("margin-bottom:12px;line-height:1.6;")

    # ---- Upload card ----
    with ui.element('div').classes("card").style("margin-bottom:12px;"):
        upload_status = ui.label("").classes("mono-sm").style(
            "margin-top:6px;display:block;min-height:16px;")

        async def _on_upload(e):
            if tstate["running"]:
                ui.notify("Already processing…", type="warning")
                return
            try:
                data = await e.file.read()
            except Exception as ex:
                ui.notify("Read failed: " + str(ex), type="negative")
                return

            name = (e.file.name or "").lower()
            tstate["filename"] = e.file.name or ""
            tstate["result"] = None
            tstate["error"] = None

            upload_status.set_text("Extracting text from " +
                                    (e.file.name or "file") + "…")
            upload_status.style(
                "margin-top:6px;display:block;min-height:16px;"
                "color:#fbbf24;font-size:10px;")

            text = ""
            try:
                if name.endswith((".pdf", ".docx", ".txt", ".md")):
                    text = await asyncio.to_thread(
                        svc.extract_document_text, data, e.file.name)
                elif name.endswith((".jpg", ".jpeg", ".png")):
                    mime = ("image/jpeg"
                            if name.endswith((".jpg", ".jpeg"))
                            else "image/png")
                    text, err = await _ocr_handwriting(data, mime)
                    if err and not text:
                        text = ""
                else:
                    text = await asyncio.to_thread(
                        svc.extract_document_text, data, e.file.name)
            except Exception as ex:
                print("[tds] extract failed: " + repr(ex))
                text = ""

            if not text or len(text.strip()) < 100:
                tstate["error"] = (
                    "Could not read enough text from the file. "
                    "Try a text-based PDF or DOCX."
                )
                upload_status.set_text("Failed: not enough text.")
                upload_status.style(
                    "margin-top:6px;display:block;min-height:16px;"
                    "color:#f87171;font-size:10px;")
                render()
                return

            upload_status.set_text(
                "Extracted " + str(len(text)) + " chars. "
                "Calling AI to draft MOS + ITP… (up to 2 min)")

            tstate["running"] = True
            try:
                result = await tds.generate_mos_itp(text,
                                                     call_gemini_json)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                result = {"error": "AI failed: " + repr(ex)}
            tstate["running"] = False

            if result.get("error"):
                tstate["error"] = result["error"]
            else:
                tstate["result"] = result
            render()

        ui.upload(on_upload=_on_upload, auto_upload=True).style(
            "width:100%;").props(
            "flat bordered accept=.pdf,.docx,.txt,.md,.jpg,.jpeg,.png "
            "label='Upload TDS (PDF / DOCX / TXT / Image)'")
        upload_status

    # ---- Error ----
    if tstate.get("error"):
        with ui.element('div').classes("card").style(
            "border-left:3px solid #f87171;margin-bottom:12px;"
        ):
            ui.label("Error").style(
                "font-size:11px;font-weight:700;color:#f87171;")
            ui.label(str(tstate["error"])).classes("mono-sm").style(
                "margin-top:4px;line-height:1.6;color:#b8b8b8;")
            raw = tstate.get("result") or {}
            if raw.get("raw"):
                ui.label(str(raw["raw"])[:500]).classes("mono-sm").style(
                    "margin-top:6px;color:#5a5a5a;font-size:9px;")

    result = tstate.get("result")
    if not result:
        return

    # ---- Results ----
    product = result.get("product") or {}
    mos = result.get("method_statement") or {}
    itp = result.get("inspection_test_plan") or {}
    crit = result.get("critical_parameters") or []

    # Download buttons
    with ui.element('div').style(
        "display:grid;grid-template-columns:1fr 1fr;gap:6px;"
        "margin-bottom:12px;"
    ):
        def _mos_txt():
            try:
                lines = []
                lines.append(mos.get("title") or "METHOD STATEMENT")
                lines.append("=" * 60)
                p_bits = []
                if product.get("name"):
                    p_bits.append("Product: " + str(product["name"]))
                if product.get("manufacturer"):
                    p_bits.append("Manufacturer: " +
                                  str(product["manufacturer"]))
                if product.get("tds_reference"):
                    p_bits.append("TDS ref: " +
                                  str(product["tds_reference"]))
                if product.get("category"):
                    p_bits.append("Category: " +
                                  str(product["category"]))
                lines.extend(p_bits)
                lines.append("Date: " +
                             datetime.date.today().strftime("%Y-%m-%d"))
                lines.append("")
                if product.get("description"):
                    lines.append(str(product["description"]))
                    lines.append("")
                if crit:
                    lines.append("KEY PARAMETERS FROM TDS")
                    lines.append("-" * 60)
                    for cp in crit:
                        lines.append(
                            str(cp.get("parameter") or "") + " : " +
                            str(cp.get("value") or "")
                            + ("  (" + str(cp["source_note"]) + ")"
                               if cp.get("source_note") else "")
                        )
                    lines.append("")
                for sec in (mos.get("sections") or []):
                    num = str(sec.get("number") or "").strip()
                    head = str(sec.get("heading") or "").strip()
                    head_line = (num + ". " + head) if num else head
                    if not head_line:
                        continue
                    lines.append(head_line)
                    lines.append("-" * len(head_line))
                    body = str(sec.get("body") or "").strip()
                    if body:
                        lines.append(body)
                    lines.append("")
                lines.append("")
                lines.append("PREPARED BY (QC): ____________________")
                lines.append("APPROVED BY (CONSULTANT): ____________________")
                lines.append("")
                txt = "\n".join(lines).encode("utf-8")
                ui.download(txt, filename="method_statement.txt")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ui.notify("TXT failed: " + str(ex), type="negative")

        def _itp_txt():
            try:
                lines = []
                lines.append(itp.get("title") or
                             "INSPECTION & TEST PLAN")
                lines.append("=" * 100)
                p_bits = []
                if product.get("name"):
                    p_bits.append("Product: " + str(product["name"]))
                if product.get("manufacturer"):
                    p_bits.append("Manufacturer: " +
                                  str(product["manufacturer"]))
                lines.extend(p_bits)
                lines.append("Date: " +
                             datetime.date.today().strftime("%Y-%m-%d"))
                lines.append("")
                headers = ["#", "Activity", "Reference", "Checkpoint",
                           "Acceptance criteria", "Method",
                           "Frequency", "Responsible"]
                widths = [3, 22, 16, 26, 34, 20, 12, 14]
                def _row(cells):
                    out = []
                    for i, c in enumerate(cells):
                        c = str(c or "").replace("\n", " ")
                        w = widths[i]
                        if i == 0:
                            out.append(c.rjust(w))
                        else:
                            out.append(c[:w].ljust(w))
                    return " | ".join(out)
                lines.append(_row(headers))
                lines.append("-+-".join("-" * w for w in widths))
                for i, r in enumerate(itp.get("rows") or [], start=1):
                    lines.append(_row([
                        str(i),
                        r.get("activity") or "",
                        r.get("reference") or "",
                        r.get("checkpoint") or "",
                        r.get("acceptance_criteria") or "",
                        r.get("method") or "",
                        r.get("frequency") or "",
                        r.get("responsible") or "",
                    ]))
                lines.append("")
                txt = "\n".join(lines).encode("utf-8")
                ui.download(txt, filename="inspection_test_plan.txt")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ui.notify("TXT failed: " + str(ex), type="negative")

        def _dl_mos():
            try:
                pdf = tds.build_mos_pdf(product, mos, crit)
                ui.download(pdf, filename="method_statement.pdf")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ui.notify("PDF failed: " + str(ex), type="negative")

        def _dl_itp():
            try:
                pdf = tds.build_itp_pdf(product, itp)
                ui.download(pdf, filename="inspection_test_plan.pdf")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ui.notify("PDF failed: " + str(ex), type="negative")

        ui.button("Method Statement — TXT", icon="description",
                  on_click=_mos_txt).classes(BTN_SOFT).style(
            "width:100%;font-size:10px;")
        ui.button("ITP — TXT", icon="description",
                  on_click=_itp_txt).classes(BTN_SOFT).style(
            "width:100%;font-size:10px;")
        ui.button("Method Statement — PDF", icon="picture_as_pdf",
                  on_click=_dl_mos).classes(BTN_PRIMARY).style(
            "width:100%;font-size:10px;")
        ui.button("ITP — PDF", icon="picture_as_pdf",
                  on_click=_dl_itp).classes(BTN_PRIMARY).style(
            "width:100%;font-size:10px;")

    # Product card
    with ui.element('div').classes("card").style("margin-bottom:12px;"):
        ui.label("PRODUCT").classes("label")
        ui.label(str(product.get("name") or "Not specified")).style(
            "font-size:14px;font-weight:700;color:#e8e8e8;margin-top:4px;")
        bits = []
        if product.get("manufacturer"):
            bits.append("Mfr: " + str(product["manufacturer"]))
        if product.get("tds_reference"):
            bits.append("TDS: " + str(product["tds_reference"]))
        if product.get("category"):
            bits.append("Cat: " + str(product["category"]))
        if bits:
            ui.label(" · ".join(bits)).classes("mono-sm").style(
                "margin-top:4px;color:#b8b8b8;")

    # MOS preview
    with ui.element('div').classes("card").style("margin-bottom:12px;"):
        ui.html(
            '<div style="font-size:15px;font-weight:700;'
            'color:#5eead4;border-bottom:1px solid rgba(94,234,212,0.3);'
            'padding-bottom:8px;margin-bottom:12px;'
            'letter-spacing:-0.01em;">' +
            _html_mod.escape(mos.get("title") or "METHOD STATEMENT") +
            '</div>'
        )
        for sec in (mos.get("sections") or []):
            num = str(sec.get("number") or "").strip()
            head = str(sec.get("heading") or "").strip()
            head_line = (num + ". " + head) if num else head
            if not head_line:
                continue
            ui.html(
                '<div style="font-size:12px;font-weight:700;'
                'color:#5eead4;margin-top:14px;margin-bottom:4px;'
                'letter-spacing:0.02em;">' +
                _html_mod.escape(head_line) + '</div>'
            )
            body = str(sec.get("body") or "").strip()
            if body:
                ui.html(
                    '<pre style="margin:0 0 4px 0;white-space:pre-wrap;'
                    'word-break:break-word;font-family:inherit;'
                    'font-size:12px;line-height:1.7;color:#d0d0d0;">' +
                    _html_mod.escape(body) + '</pre>'
                )

    # ITP preview
    with ui.element('div').classes("card").style("margin-bottom:12px;"):
        ui.html(
            '<div style="font-size:15px;font-weight:700;'
            'color:#5eead4;border-bottom:1px solid rgba(94,234,212,0.3);'
            'padding-bottom:8px;margin-bottom:12px;'
            'letter-spacing:-0.01em;">' +
            _html_mod.escape(itp.get("title") or "INSPECTION & TEST PLAN") +
            '</div>'
        )
        rows = itp.get("rows") or []
        if not rows:
            ui.label("No ITP rows generated.").classes("muted")
        else:
            html = ('<table style="width:100%;border-collapse:collapse;'
                    'font-size:10.5px;'
                    'font-variant-numeric:tabular-nums;">'
                    '<thead><tr style="background:#0a0a0a;">')
            heads = ["#", "Activity", "Reference", "Checkpoint",
                     "Acceptance criteria", "Method", "Freq.", "Resp."]
            for h in heads:
                html += ('<th style="text-align:left;padding:6px 6px;'
                         'font-size:9px;letter-spacing:0.12em;'
                         'color:#5eead4;text-transform:uppercase;'
                         'border-bottom:1px solid #1e1e1e;">' +
                         _html_mod.escape(h) + '</th>')
            html += '</tr></thead><tbody>'
            for i, r in enumerate(rows, start=1):
                html += '<tr style="border-bottom:1px solid #1e1e1e;">'
                cells = [
                    str(i),
                    str(r.get("activity") or ""),
                    str(r.get("reference") or ""),
                    str(r.get("checkpoint") or ""),
                    str(r.get("acceptance_criteria") or ""),
                    str(r.get("method") or ""),
                    str(r.get("frequency") or ""),
                    str(r.get("responsible") or ""),
                ]
                for j, c in enumerate(cells):
                    col = "#e8e8e8" if j == 0 else "#d0d0d0"
                    html += ('<td style="padding:6px 6px;'
                             'vertical-align:top;color:' + col + ';'
                             'font-size:10.5px;line-height:1.45;">' +
                             _html_mod.escape(c) + '</td>')
                html += '</tr>'
            html += '</tbody></table>'
            ui.html(html)
