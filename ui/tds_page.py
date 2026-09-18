"""
ui/tds_page.py — Standalone TDS → MOS + ITP page.
"""
import asyncio
import datetime
import html as _html_mod
from nicegui import ui

from services import defect_service as svc
from services import tds_service as tds
from services.ai_service import call_gemini_json


STYLE = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Amiri:wght@400;700&display=swap" rel="stylesheet">
<style>
  html, body {
    background: #0b0b0b !important; color: #e8e8e8 !important;
    font-family: 'JetBrains Mono','Amiri','Courier New',monospace !important;
    font-size: 13px; -webkit-font-smoothing: antialiased;
  }
  .nicegui-content { padding: 0 !important; }
  .q-page, .q-layout { background: #0b0b0b !important; }
  .q-btn {
    border-radius: 3px !important; text-transform: none !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 500 !important; min-height: 32px !important;
    padding: 0 12px !important; font-size: 11px !important;
    box-shadow: none !important;
  }
  .btn-primary { background: #5eead4 !important;
                 color: #0b0b0b !important; font-weight: 700 !important; }
  .btn-soft { background: #161616 !important; color: #e8e8e8 !important;
              border: 1px solid #262626 !important; }
  .q-field--outlined .q-field__control {
    border-radius: 3px !important; background: #161616 !important;
  }
  .q-field--outlined .q-field__control:before { border-color: #262626 !important; }
  .q-field--outlined.q-field--focused .q-field__control:after {
    border-color: #5eead4 !important;
  }
  .q-field__label, .q-field__native, .q-field__input {
    color: #e8e8e8 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
  }
  .card { background: #101010; border: 1px solid #1e1e1e;
          border-radius: 4px; padding: 16px; width: 100%;
          box-sizing: border-box; }
  .main-content { padding: 14px; padding-bottom: 40px;
                  max-width: 760px; margin: 0 auto; width: 100%;
                  box-sizing: border-box; }
  .section-head { display: flex; justify-content: space-between;
                  align-items: center; margin-bottom: 10px;
                  padding-bottom: 6px; border-bottom: 1px solid #1e1e1e; }
  .h1 { font-size: 16px; font-weight: 700; color: #e8e8e8;
        letter-spacing: -0.02em; }
  .muted { color: #808080; font-size: 11px; }
  .mono-sm { font-size: 10px; color: #808080; }
  .label { font-size: 9px; font-weight: 700; color: #5a5a5a;
           text-transform: uppercase; letter-spacing: 0.14em; }
  .app-header {
    background: rgba(11,11,11,0.94); border-bottom: 1px solid #1e1e1e;
    padding: 10px 14px; display: flex; align-items: center;
    justify-content: space-between; box-sizing: border-box; width: 100%;
  }
  .app-header .brand { font-weight: 700; font-size: 12px; color: #e8e8e8; }
  .app-header .brand::before {
    content: '\\25CF '; color: #5eead4; font-size: 9px;
    vertical-align: middle; margin-right: 4px;
  }
  .q-uploader { background: #161616 !important;
                border: 1px dashed #262626 !important;
                border-radius: 4px !important; width: 100% !important;
                color: #e8e8e8 !important; }
  .q-uploader__header { background: transparent !important;
                        color: #e8e8e8 !important; }
  .q-uploader__title, .q-uploader__subtitle { color: #e8e8e8 !important; }
  .q-uploader .q-btn { color: #808080 !important; }
  .q-uploader__list { background: transparent !important; }
  .q-uploader__list .q-item { background: #101010 !important;
                              color: #e8e8e8 !important;
                              border-radius: 2px !important;
                              margin: 3px !important; }
  .q-notification {
    border-radius: 3px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important; background: #161616 !important;
    color: #e8e8e8 !important;
    border: 1px solid #262626 !important;
  }
  .scroll-box { max-height: 220px; overflow-y: auto;
                border: 1px solid #1e1e1e; border-radius: 3px;
                padding: 6px; margin-top: 6px;
                background: #161616; }

.footer-wrap { max-width: 760px; margin: 0 auto;
                 padding: 24px 14px 140px;
                 box-sizing: border-box; }
  .footer-line { font-size: 10px; color: #4a4a4a;
                 text-align: center; line-height: 1.7;
                 font-family: 'JetBrains Mono', monospace;
                 letter-spacing: 0.02em; }
  .feedback-bar { position: fixed; bottom: 0; left: 0; right: 0;
                  background: rgba(11,11,11,0.96);
                  backdrop-filter: blur(8px);
                  -webkit-backdrop-filter: blur(8px);
                  border-top: 1px solid #1e1e1e;
                  padding: 10px 14px 12px; z-index: 500; }
  .feedback-inner { max-width: 760px; margin: 0 auto; }
  .feedback-hint { font-size: 10px; color: #5a5a5a;
                   margin-bottom: 6px; display: block;
                   font-family: 'JetBrains Mono', monospace; }
  .feedback-row { display: flex; gap: 8px; align-items: center;
                  background: #161616; border: 1px solid #262626;
                  border-radius: 22px; padding: 4px 4px 4px 14px;
                  transition: border-color 0.15s; }
  .feedback-row:focus-within { border-color: #5eead4; }
  .feedback-input .q-field__control {
    background: transparent !important; border: none !important;
    min-height: 32px !important;
  }
  .feedback-input .q-field__control:before,
  .feedback-input .q-field__control:after {
    border: none !important;
  }
  .feedback-input .q-field__native,
  .feedback-input .q-field__input {
    color: #e8e8e8 !important; font-size: 12px !important;
    font-family: 'JetBrains Mono', monospace !important;
    padding: 6px 0 !important;
  }
  .feedback-send { background: #5eead4 !important;
                   color: #0b0b0b !important;
                   border-radius: 50% !important;
                   min-width: 34px !important;
                   min-height: 34px !important;
                   padding: 0 !important; }
  .feedback-send .q-icon { font-size: 16px !important; }
</style>
"""


_OCR_PROMPT = (
    "You are a precise OCR engine for handwritten and printed documents. "
    "Read every character in this document exactly as it appears."
    "\n\nCRITICAL RULES:"
    "\n1. Detect the language automatically (Arabic, English, or mixed)."
    "\n2. If the text is Arabic, transcribe it in correct right-to-left "
    "reading order, word by word, preserving every letter including "
    "hamza forms, taa marbuta, taa, and any diacritics."
    "\n3. Do NOT translate. Do NOT summarize. Do NOT add commentary, "
    "headings, bullet points, or markdown."
    "\n4. Preserve line breaks exactly as they appear on the page."
    "\n5. For mixed Arabic + English lines, keep each word in its "
    "original language and script."
    "\n6. If a word is unclear, transcribe your best guess using context."
    "\n7. Return ONLY the raw extracted text. No quotes, no labels, "
    "no explanations."
    "\n8. If the image contains no readable text, return an empty string."
)


def _preprocess_for_ocr(file_bytes, mime_type):
    mime = (mime_type or "image/jpeg").lower()
    if mime == "application/pdf" or not mime.startswith("image/"):
        return file_bytes, mime
    try:
        from PIL import Image, ImageOps, ImageFilter
        import io as _io
        img = Image.open(_io.BytesIO(file_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")
        w, h = img.size
        longest = max(w, h)
        if longest < 1400:
            scale = 1400.0 / float(longest)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        elif longest > 2400:
            scale = 2400.0 / float(longest)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=140,
                                                  threshold=3))
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=92, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print("[ocr] preprocess failed: " + repr(e))
        return file_bytes, mime


async def _ocr_handwriting(file_bytes, mime_type):
    if not file_bytes:
        return None, "Empty file."
    try:
        from google.genai import types
    except Exception as e:
        return None, "google-genai not available: " + repr(e)
    payload, mime = _preprocess_for_ocr(file_bytes, mime_type)
    try:
        part = types.Part.from_bytes(data=payload, mime_type=mime)
    except Exception as e:
        return None, "Could not prepare file: " + repr(e)
    try:
        raw = await call_gemini_json([_OCR_PROMPT, part],
                                       temperature=0.0, timeout=45)
    except Exception as e:
        return None, "AI call failed: " + str(e)
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'", "`"):
        text = text[1:-1].strip()
    if not text:
        return "", "No readable text found."
    return text, None
def _render_footer():
    ui.html(
        '<div class="footer-line">'
        'Made by Mohamed Abd Al Aty · Construction Engineer · '
        'AI Product Builder'
        '</div>'
    )


def _render_feedback_bar():
    from services import feedback_db

    with ui.element('div').classes("feedback-bar"):
        with ui.element('div').classes("feedback-inner"):
            ui.label(
                "Your feedback is valuable for making the tool better."
            ).classes("feedback-hint")

            with ui.element('div').classes("feedback-row"):
                msg_in = ui.input(placeholder="Send feedback...").props(
                    "dense borderless").style("flex:1;").classes(
                    "feedback-input")

                def _send():
                    txt = (msg_in.value or "").strip()
                    if not txt:
                        return
                    ok, err = feedback_db.add_feedback(txt, page="tds")
                    if not ok:
                        ui.notify(err or "Could not save feedback.",
                                   type="negative")
                        return
                    msg_in.value = ""
                    ui.notify("Thank you — your feedback was received.",
                               type="positive")

                msg_in.on("keydown.enter", lambda _: _send())
                ui.button(icon="send", on_click=_send).props(
                    "flat dense").classes("feedback-send")

def build_tds_ui():
    ui.add_head_html(STYLE)

    tstate = {"result": None, "running": False, "error": None, "filename": ""}

    with ui.element('div').classes("app-header"):
        ui.label("TDS → MOS & ITP").classes("brand")

    content = ui.element('div').classes("main-content")

    def render():
        content.clear()
        with content:
            _render_body(tstate, render)

    render()

    with ui.element('div').classes("footer-wrap"):
        _render_footer()

    _render_feedback_bar()


def _render_body(tstate, render):
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

    with ui.element('div').classes("card").style("margin-bottom:12px;"):
        upload_status = ui.label("").classes("mono-sm").style(
            "margin-top:6px;display:block;min-height:16px;")

        async def _on_upload(e):
            if tstate["running"]:
                ui.notify("Already processing…", type="warning")
                return
            try:
                data = e.content.read()
                if hasattr(data, "__await__"):
                    data = await data
            except Exception as ex:
                ui.notify("Read failed: " + str(ex), type="negative")
                return

            fname = getattr(e, "name", "") or ""
            name = fname.lower()
            tstate["filename"] = fname
            tstate["result"] = None
            tstate["error"] = None

            upload_status.set_text("Extracting text from " +
                                    (fname or "file") + "…")
            upload_status.style(
                "margin-top:6px;display:block;min-height:16px;"
                "color:#fbbf24;font-size:10px;")

            text = ""
            try:
                if name.endswith((".pdf", ".docx", ".txt", ".md")):
                    text = await asyncio.to_thread(
                        svc.extract_document_text, data, fname)
                elif name.endswith((".jpg", ".jpeg", ".png")):
                    mime = ("image/jpeg"
                            if name.endswith((".jpg", ".jpeg"))
                            else "image/png")
                    text, err = await _ocr_handwriting(data, mime)
                    if err and not text:
                        text = ""
                else:
                    text = await asyncio.to_thread(
                        svc.extract_document_text, data, fname)
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
                result = await tds.generate_mos_itp(text, call_gemini_json)
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

    product = result.get("product") or {}
    mos = result.get("method_statement") or {}
    itp = result.get("inspection_test_plan") or {}
    crit = result.get("critical_parameters") or []

    with ui.element('div').style(
        "display:grid;grid-template-columns:1fr 1fr;gap:6px;"
        "margin-bottom:12px;"
    ):
        def _mos_txt():
            try:
                lines = [mos.get("title") or "METHOD STATEMENT", "=" * 60]
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
                  on_click=_mos_txt).classes("btn-soft").style(
            "width:100%;font-size:10px;")
        ui.button("ITP — TXT", icon="description",
                  on_click=_itp_txt).classes("btn-soft").style(
            "width:100%;font-size:10px;")
        ui.button("Method Statement — PDF", icon="picture_as_pdf",
                  on_click=_dl_mos).classes("btn-primary").style(
            "width:100%;font-size:10px;")
        ui.button("ITP — PDF", icon="picture_as_pdf",
                  on_click=_dl_itp).classes("btn-primary").style(
            "width:100%;font-size:10px;")

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
