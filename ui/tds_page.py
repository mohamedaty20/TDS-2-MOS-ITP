"""
ui/tds_page.py — Standalone TDS → MOS + ITP page.
"""
import asyncio
import datetime
import html as _html_mod
from nicegui import ui, app

from services import defect_service as svc
from services import tds_service as tds
from services import tds_documents_db as tddb
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
  .btn-primary { background: #14b8a6 !important;
                 color: #0b0b0b !important; font-weight: 700 !important; }
  .btn-soft { background: #161616 !important; color: #e8e8e8 !important;
              border: 1px solid #262626 !important; }
  .q-field--outlined .q-field__control {
    border-radius: 3px !important; background: #161616 !important;
  }
  .q-field--outlined .q-field__control:before { border-color: #262626 !important; }
  .q-field--outlined.q-field--focused .q-field__control:after {
    border-color: #14b8a6 !important;
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
    content: '\\25CF '; color: #14b8a6; font-size: 9px;
    vertical-align: middle; margin-right: 4px;
  }

  .page-title-wrap { width: 100%; text-align: center;
                     padding: 26px 14px 6px; box-sizing: border-box;
                     position: relative; }
  .page-title { font-size: 30px; font-weight: 800;
                color: #e8e8e8; letter-spacing: -0.03em;
                font-family: 'JetBrains Mono', monospace; }
  .page-title-refresh { position: absolute; top: 30px; right: 18px; }

  .q-uploader { background: #161616 !important;
                border: 1px dashed #262626 !important;
                border-radius: 4px !important; width: 100% !important;
                color: #e8e8e8 !important; }
  .q-uploader__header { background: transparent !important;
                        color: #e8e8e8 !important;
                        flex-direction: row !important;
                        align-items: center !important;
                        justify-content: center !important;
                        padding: 10px 14px !important;
                        gap: 12px !important;
                        min-height: auto !important; }
  .q-uploader__header-content {
    flex: unset !important;
    text-align: left !important;
    margin: 0 !important;
    padding: 0 !important;
    width: auto !important;
  }
  .q-uploader__header .q-btn,
  .q-uploader__pick {
    background: transparent !important;
    color: #14b8a6 !important;
    border: 1px solid #14b8a6 !important;
    border-radius: 50% !important;
    min-width: 32px !important;
    min-height: 32px !important;
    padding: 0 !important;
    margin: 0 !important;
    flex-shrink: 0 !important;
  }
  .q-uploader__header .q-btn .q-icon,
  .q-uploader__pick .q-icon {
    font-size: 18px !important;
    color: #14b8a6 !important;
  }
  .q-uploader__title, .q-uploader__subtitle {
    color: #e8e8e8 !important; text-align: left !important; }
  .q-uploader__title { font-size: 13px !important;
                       font-weight: 600 !important;
                       letter-spacing: -0.01em !important; }
  .q-uploader__subtitle { font-size: 10px !important;
                          color: #808080 !important; }
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

  .flow-wrap { display: flex; align-items: center;
               justify-content: center; gap: 6px;
               max-width: 460px; margin: 4px auto 0;
               padding: 0 14px; box-sizing: border-box;
               flex-wrap: wrap; }
  .flow-box { background: #101010; border: 1px solid #262626;
              border-radius: 3px; padding: 4px 8px;
              min-width: 84px; flex: 1;
              text-align: center;
              font-family: 'JetBrains Mono', monospace; }
  .flow-num { font-size: 7px; font-weight: 700; color: #14b8a6;
              letter-spacing: 0.1em; margin-bottom: 1px;
              text-transform: uppercase; }
  .flow-title { font-size: 9px; font-weight: 700; color: #e8e8e8;
                margin-bottom: 0; }
  .flow-sub { font-size: 8px; color: #808080; line-height: 1.3; }
  .flow-arrow { color: #14b8a6; font-size: 10px; font-weight: 700;
                font-family: 'JetBrains Mono', monospace; }
  .flow-time { text-align: center; font-size: 9px; color: #5a5a5a;
               margin: 5px 0 14px;
               font-family: 'JetBrains Mono', monospace; }

  .example-btn { color: #14b8a6 !important; font-size: 11px !important;
                 font-weight: 600 !important;
                 font-family: 'JetBrains Mono', monospace !important;
                 padding: 0 !important; margin-top: 10px !important;
                 min-height: 20px !important;
                 background: transparent !important;
                 text-transform: none !important; }
  .example-btn:hover { text-decoration: underline; }

  .page-shell { display: flex; flex-direction: column;
                min-height: 100vh; width: 100%; }
  .page-main { flex: 1 1 auto; width: 100%; }
  .footer-wrap { width: 100%; padding: 40px 14px 40px;
                 box-sizing: border-box; text-align: center; }
  .footer-line { font-size: 10px; color: #4a4a4a;
                 text-align: center; line-height: 1.9;
                 font-family: 'JetBrains Mono', monospace;
                 letter-spacing: 0.02em;
                 max-width: 620px; margin: 0 auto; }
  .footer-line .sep { color: #333333; margin: 0 6px; }
  .footer-note { color: #3a3a3a; font-size: 9.5px; margin-top: 6px;
                 line-height: 1.7; }
  .footer-copy { color: #3a3a3a; font-size: 9.5px; margin-top: 10px;
                 letter-spacing: 0.04em; }

  .feedback-trigger-inline {
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; padding: 6px 10px;
    font-family: 'JetBrains Mono', monospace;
    user-select: none; margin: 0 auto 14px;
    width: fit-content;
  }
  .feedback-trigger-inline:hover .feedback-word {
    text-decoration: underline;
  }
  .feedback-word { color: #14b8a6; font-size: 12px; font-weight: 600;
                   letter-spacing: 0.04em; }
  .feedback-arrow { color: #4a4a4a; font-size: 12px;
                    font-weight: 400; margin-left: 5px;
                    letter-spacing: -1px; }

  .feedback-overlay { position: fixed; inset: 0;
                      background: transparent; z-index: 550; }
  .feedback-bar { position: fixed; bottom: 0; left: 0; right: 0;
                  background: rgba(11,11,11,0.96);
                  backdrop-filter: blur(8px);
                  -webkit-backdrop-filter: blur(8px);
                  border-top: 1px solid #1e1e1e;
                  padding: 10px 14px 12px; z-index: 600; }
  .feedback-inner { max-width: 760px; margin: 0 auto; }
  .feedback-hint { font-size: 10px; color: #5a5a5a;
                   margin-bottom: 6px; display: block;
                   font-family: 'JetBrains Mono', monospace; }
  .feedback-row { display: flex; gap: 8px; align-items: flex-end;
                  background: #161616; border: 1px solid #262626;
                  border-radius: 0; padding: 10px 10px 10px 14px;
                  min-height: 96px;
                  transition: border-color 0.15s; }
  .feedback-row:focus-within { border-color: #14b8a6; }
  .feedback-input { flex: 1; }
  .feedback-input .q-field__control {
    background: transparent !important; border: none !important;
    min-height: 70px !important;
    align-items: flex-start !important;
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
  .feedback-send { background: #14b8a6 !important;
                   color: #0b0b0b !important;
                   border-radius: 3px !important;
                   min-width: 34px !important;
                   min-height: 34px !important;
                   padding: 0 !important; }
  .feedback-send .q-icon { font-size: 16px !important; }

  /* Company header panel */
  .hdr-toggle {
    display: flex; align-items: center; gap: 6px;
    cursor: pointer; user-select: none;
    padding: 8px 10px; margin-bottom: 4px;
    background: #101010; border: 1px solid #1e1e1e;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: #14b8a6; font-weight: 600;
    width: fit-content;
  }
  .hdr-toggle:hover { background: #161616; }
  .hdr-arrow { color: #4a4a4a; font-size: 10px; }
  .hdr-panel { background: #101010; border: 1px solid #1e1e1e;
               border-radius: 4px; padding: 14px 16px;
               margin-bottom: 12px; }
  .hdr-hint { font-size: 10px; color: #5a5a5a; margin-bottom: 10px;
              display: block; line-height: 1.6;
              font-family: 'JetBrains Mono', monospace; }
  .hdr-row { display: grid; grid-template-columns: 1fr 1fr;
             gap: 8px; margin-bottom: 8px; }
  .hdr-row.one { grid-template-columns: 1fr; }
  .hdr-upload { margin-top: 6px; }
</style>
"""


_EXAMPLE_TDS_TEXT = """
TECHNICAL DATA SHEET

PRODUCT: MasterSeal 6100 — Two-Component Cementitious Waterproofing Membrane
MANUFACTURER: Master Builders Solutions
TDS REFERENCE: MS-6100-EN-Rev03
CATEGORY: Cementitious Waterproofing

DESCRIPTION
MasterSeal 6100 is a two-component, polymer-modified cementitious
waterproofing coating for concrete and masonry substrates. Suitable for
potable water tanks, basements, retaining walls, and swimming pools.

TECHNICAL PROPERTIES
- Mix ratio (A:B by weight): 2.5 : 1
- Pot life at 25 C: 45 minutes
- Open time after mixing: 30 minutes
- Application temperature range: +5 C to +35 C
- Substrate moisture content (max): 5 %
- Recoating interval (min): 4 hours
- Recoating interval (max): 24 hours
- Full cure: 7 days at 25 C and 50 % RH
- Recommended dry film thickness per coat: 1.0 - 1.2 mm
- Number of coats required: 2
- Compressive strength at 28 days: >= 35 MPa
- Adhesion to concrete at 28 days: >= 1.0 MPa
- Chloride ion content: <= 0.05 % by mass of cement
- Water vapour permeability: < 5 g/m2.day

SUBSTRATE PREPARATION
- Concrete must be clean, sound, and free of laitance, oil, grease,
  and loose particles.
- Surface must be damp (saturated surface dry) before application.
- Repair all honeycombing, cracks, and voids with a suitable repair
  mortar prior to coating.
- Roughen smooth surfaces by mechanical means.
- All form release agents must be completely removed.

MIXING
- Add the liquid component (A) to a clean mixing vessel.
- Slowly add the powder component (B) while mixing with a slow-speed
  drill (max 500 rpm).
- Mix for 3 minutes, then allow to stand for 5 minutes.
- Remix briefly before use.
- Do NOT add water beyond the specified ratio.

APPLICATION
- Apply the first coat by brush or roller at the specified thickness.
- Allow to cure for at least 4 hours at 25 C before the second coat.
- Apply the second coat in the perpendicular direction to the first.
- Do not apply in direct sunlight, rain, or wind.
- Do not apply if rain is expected within 8 hours.

CURING
- Cure the coating for 7 days by water spray or damp cloth.
- Prevent rapid drying in hot or windy weather.
- Do not allow traffic for at least 48 hours after final coat.

STORAGE
- Store in a dry, covered area between +5 C and +30 C.
- Shelf life: 12 months in unopened containers.
- Protect from freezing.

SAFETY
- Wear suitable gloves and eye protection during mixing and application.
- Avoid contact with skin and eyes.
- Use only in well-ventilated areas.
- Refer to Safety Data Sheet for full handling information.
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


# ---------------------------------------------------------------------
# BROWSER STORAGE — company header persistence
# ---------------------------------------------------------------------
def _load_stored_header():
    try:
        stored = app.storage.browser.get("tds_header") or {}
    except Exception:
        stored = {}
    today = datetime.date.today().strftime("%Y-%m-%d")
    return {
        "company_name": str(stored.get("company_name") or ""),
        "project_name": str(stored.get("project_name") or ""),
        "location": str(stored.get("location") or ""),
        "prepared_by": str(stored.get("prepared_by") or ""),
        "date": str(stored.get("date") or today) or today,
    }


def _save_stored_header(hdr):
    try:
        app.storage.browser["tds_header"] = {
            "company_name": hdr.get("company_name") or "",
            "project_name": hdr.get("project_name") or "",
            "location": hdr.get("location") or "",
            "prepared_by": hdr.get("prepared_by") or "",
            "date": hdr.get("date") or "",
        }
    except Exception as e:
        print("[tds] save header failed: " + repr(e))


def _header_has_content(hdr):
    if not hdr:
        return False
    return bool(
        (hdr.get("company_name") or "").strip()
        or (hdr.get("project_name") or "").strip()
        or (hdr.get("location") or "").strip()
        or (hdr.get("prepared_by") or "").strip()
        or hdr.get("logo_bytes")
    )


def _header_for_pdf(hdr):
    if not _header_has_content(hdr):
        return None
    return {
        "company_name": hdr.get("company_name") or "",
        "project_name": hdr.get("project_name") or "",
        "location": hdr.get("location") or "",
        "prepared_by": hdr.get("prepared_by") or "",
        "date": hdr.get("date") or "",
        "logo_bytes": hdr.get("logo_bytes"),
    }


# ---------------------------------------------------------------------
# COMPANY HEADER PANEL
# ---------------------------------------------------------------------
def _render_company_header_panel(tstate, render):
    # One-time init from browser storage
    if "hdr" not in tstate:
        loaded = _load_stored_header()
        tstate["hdr"] = {
            "company_name": loaded["company_name"],
            "project_name": loaded["project_name"],
            "location": loaded["location"],
            "prepared_by": loaded["prepared_by"],
            "date": loaded["date"],
            "logo_bytes": None,
            "expanded": False,
        }

    hdr = tstate["hdr"]

    def _toggle():
        hdr["expanded"] = not hdr.get("expanded", False)
        render()

    def _on_change(e=None):
        _save_stored_header(hdr)

    # Toggle bar
    arrow = "▼" if hdr.get("expanded") else "▶"
    label = ("Add company header (optional)" if not _header_has_content(hdr)
             else "Company header (added)")
    toggle = ui.element('div').classes("hdr-toggle")
    with toggle:
        ui.label(arrow).classes("hdr-arrow")
        ui.label(label)
    toggle.on("click", _toggle)

    # Body
    if not hdr.get("expanded"):
        return

    with ui.element('div').classes("hdr-panel"):
        ui.label(
            "Optional. If filled, the header renders at the top of page 1 "
            "of the PDF. Skipping this keeps the default PDF unchanged."
        ).classes("hdr-hint")

        # Row 1: company name + project name
        with ui.element('div').classes("hdr-row"):
            ui.input("Company name").bind_value(
                hdr, "company_name").style("width:100%;").on(
                "update:model-value", _on_change)
            ui.input("Project name").bind_value(
                hdr, "project_name").style("width:100%;").on(
                "update:model-value", _on_change)

        # Row 2: location + prepared by
        with ui.element('div').classes("hdr-row"):
            ui.input("Location").bind_value(
                hdr, "location").style("width:100%;").on(
                "update:model-value", _on_change)
            ui.input("Prepared by").bind_value(
                hdr, "prepared_by").style("width:100%;").on(
                "update:model-value", _on_change)

        # Row 3: date (single column, narrower)
        with ui.element('div').classes("hdr-row one"):
            ui.input("Date").bind_value(
                hdr, "date").style("width:100%;").on(
                "update:model-value", _on_change)

        # Logo upload
        logo_status = ui.label(
            "Logo attached" if hdr.get("logo_bytes") else "No logo"
        ).classes("mono-sm").style(
            "margin-top:8px;display:block;"
            + ("color:#4ade80;" if hdr.get("logo_bytes") else ""))

        async def _on_logo(e):
            try:
                data = e.content.read()
                if hasattr(data, "__await__"):
                    data = await data
            except Exception as ex:
                ui.notify("Logo read failed: " + str(ex), type="negative")
                return
            if not data:
                ui.notify("Empty file.", type="warning")
                return
            hdr["logo_bytes"] = data
            ui.notify("Logo attached.", type="positive")
            render()

        with ui.element('div').classes("hdr-upload"):
            ui.upload(on_upload=_on_logo, auto_upload=True).style(
                "width:100%;").props(
                "flat bordered accept=image/* label='Upload logo (PNG / JPG)'")
            logo_status

        def _clear_logo():
            hdr["logo_bytes"] = None
            render()

        if hdr.get("logo_bytes"):
            ui.button("Clear logo", on_click=_clear_logo).classes(
                "btn-soft").style("margin-top:6px;font-size:10px;")


# ---------------------------------------------------------------------
# FOOTER + FEEDBACK
# ---------------------------------------------------------------------
def _render_footer(open_feedback_fn):
    with ui.element('div').classes("footer-wrap"):
        trigger = ui.element('div').classes("feedback-trigger-inline")
        with trigger:
            ui.label("Feedback").classes("feedback-word")
            ui.label("»").classes("feedback-arrow")
        trigger.on("click", open_feedback_fn)

        ui.html(
            '<div class="footer-line">'
            'Made by Mohamed Abd Al Aty'
            '<span class="sep">·</span>Construction Engineer'
            '<span class="sep">·</span>AI Product Builder'
            '<div class="footer-note">'
            'Built with a highly trained AI module. All outputs should be '
            'reviewed and verified by a qualified engineer before use in '
            'decision-making.'
            '</div>'
            '<div class="footer-copy">'
            '© 2026 Mohamed Abd Al Aty. All rights reserved.'
            '</div>'
            '</div>'
        )


def _render_feedback_panel():
    from services import feedback_db

    overlay = ui.element('div').classes("feedback-overlay")
    overlay.style("display:none;")

    panel = ui.element('div').classes("feedback-bar")
    panel.style("display:none;")
    with panel:
        with ui.element('div').classes("feedback-inner"):
            ui.label(
                "Your feedback is valuable for making the tool better."
            ).classes("feedback-hint")
            with ui.element('div').classes("feedback-row"):
                msg_in = ui.textarea(
                    placeholder="Send feedback..."
                ).props("dense borderless autogrow").classes(
                    "feedback-input")
                send_btn = ui.button(icon="send").props("flat dense").classes(
                    "feedback-send")

    def _open(e=None):
        overlay.style("display:block;")
        panel.style("display:block;")

    def _close(e=None):
        overlay.style("display:none;")
        panel.style("display:none;")

    def _send():
        txt = (msg_in.value or "").strip()
        if not txt:
            return
        ok, err = feedback_db.add_feedback(txt, page="tds")
        if not ok:
            ui.notify(err or "Could not save feedback.", type="negative")
            return
        msg_in.value = ""
        ui.notify("Thank you — your feedback was received.",
                   type="positive")
        _close()

    overlay.on("click", _close)
    send_btn.on("click", _send)

    return _open


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def build_tds_ui():
    ui.add_head_html(STYLE)

    tstate = {"result": None, "running": False, "error": None, "filename": ""}

    refresh_holder = {"fn": None}

    def _do_refresh():
        tstate["result"] = None
        tstate["error"] = None
        if refresh_holder["fn"]:
            refresh_holder["fn"]()

    with ui.element('div').classes("page-shell"):
        with ui.element('div').classes("app-header"):
            ui.label("TDS → MOS & ITP").classes("brand")

        with ui.element('div').classes("page-title-wrap"):
            ui.label("TDS → MOS & ITP").classes("page-title")
            with ui.element('div').classes("page-title-refresh"):
                ui.button(icon="refresh", on_click=_do_refresh).props(
                    "flat round dense size=sm").style("color:#808080;")

        content = ui.element('div').classes("page-main main-content")

        def render():
            content.clear()
            with content:
                _render_body(tstate, render)

        refresh_holder["fn"] = render
        render()

        open_feedback = _render_feedback_panel()
        _render_footer(open_feedback)


def _render_body(tstate, render):
    ui.label(
        "Upload a manufacturer Technical Data Sheet (PDF, DOCX, TXT, "
        "or image). The tool extracts critical parameters with AI and "
        "drafts a Method Statement + an Inspection & Test Plan."
    ).classes("muted").style("margin-bottom:14px;line-height:1.6;")

    with ui.element('div').classes("flow-wrap"):
        with ui.element('div').classes("flow-box"):
            ui.html('<div class="flow-num">1. Upload</div>'
                    '<div class="flow-title">Drop a TDS</div>'
                    '<div class="flow-sub">PDF / DOCX / TXT / Image</div>')
        ui.html('<div class="flow-arrow">&rarr;</div>')
        with ui.element('div').classes("flow-box"):
            ui.html('<div class="flow-num">2. AI Reads</div>'
                    '<div class="flow-title">Extracts parameters</div>'
                    '<div class="flow-sub">Product data &amp; limits</div>')
        ui.html('<div class="flow-arrow">&rarr;</div>')
        with ui.element('div').classes("flow-box"):
            ui.html('<div class="flow-num">3. Download</div>'
                    '<div class="flow-title">MOS + ITP</div>'
                    '<div class="flow-sub">PDF or TXT</div>')
    ui.html('<div class="flow-time">'
            'Typical generation time: 45&ndash;90 seconds.'
            '</div>')

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

        async def _run_example():
            if tstate["running"]:
                ui.notify("Already processing…", type="warning")
                return
            tstate["result"] = None
            tstate["error"] = None
            tstate["filename"] = "EXAMPLE — MasterSeal 6100 TDS"
            upload_status.set_text(
                "Loading example TDS. Calling AI to draft MOS + ITP… "
                "(45–90 seconds)")
            upload_status.style(
                "margin-top:6px;display:block;min-height:16px;"
                "color:#fbbf24;font-size:10px;")
            tstate["running"] = True
            try:
                result = await tds.generate_mos_itp(
                    _EXAMPLE_TDS_TEXT, call_gemini_json)
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

        def _load_example():
            asyncio.create_task(_run_example())

        ui.button(
            "Don't have a TDS? Try an example →",
            on_click=_load_example
        ).props("flat dense no-caps").classes("example-btn")

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

    # -------- Company header panel (collapsed by default) --------
    _render_company_header_panel(tstate, render)

    hdr = tstate.get("hdr") or {}
    hdr_present = _header_has_content(hdr)

    def _record_meta(doc_type):
        """Save header metadata (not logo bytes) to the tds_documents table."""
        if not hdr_present:
            return
        try:
            tddb.save_document_meta(
                company_name=hdr.get("company_name") or "",
                project_name=hdr.get("project_name") or "",
                location=hdr.get("location") or "",
                prepared_by=hdr.get("prepared_by") or "",
                doc_date=hdr.get("date") or "",
                product_name=product.get("name") or "",
                doc_type=doc_type,
            )
        except Exception as ex:
            print("[tds] save meta failed: " + repr(ex))

    # -------- Download buttons --------
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

        def _dl_mos_no_header():
            try:
                pdf = tds.build_mos_pdf(product, mos, crit, header=None)
                ui.download(pdf, filename="method_statement.pdf")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ui.notify("PDF failed: " + str(ex), type="negative")

        def _dl_itp_no_header():
            try:
                pdf = tds.build_itp_pdf(product, itp, header=None)
                ui.download(pdf, filename="inspection_test_plan.pdf")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ui.notify("PDF failed: " + str(ex), type="negative")

        def _dl_mos_with_header():
            try:
                _record_meta("MOS")
                pdf = tds.build_mos_pdf(product, mos, crit,
                                          header=_header_for_pdf(hdr))
                ui.download(pdf, filename="method_statement_header.pdf")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ui.notify("PDF failed: " + str(ex), type="negative")

        def _dl_itp_with_header():
            try:
                _record_meta("ITP")
                pdf = tds.build_itp_pdf(product, itp,
                                          header=_header_for_pdf(hdr))
                ui.download(pdf, filename="inspection_test_plan_header.pdf")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                ui.notify("PDF failed: " + str(ex), type="negative")

        # Row 1: TXT
        ui.button("Method Statement — TXT", icon="description",
                  on_click=_mos_txt).classes("btn-soft").style(
            "width:100%;font-size:10px;")
        ui.button("ITP — TXT", icon="description",
                  on_click=_itp_txt).classes("btn-soft").style(
            "width:100%;font-size:10px;")

        # Row 2: PDF without header (always available)
        ui.button("MOS PDF — no header", icon="picture_as_pdf",
                  on_click=_dl_mos_no_header).classes("btn-soft").style(
            "width:100%;font-size:10px;")
        ui.button("ITP PDF — no header", icon="picture_as_pdf",
                  on_click=_dl_itp_no_header).classes("btn-soft").style(
            "width:100%;font-size:10px;")

        # Row 3: PDF with header (only if header has content)
        if hdr_present:
            ui.button("MOS PDF — with header", icon="picture_as_pdf",
                      on_click=_dl_mos_with_header).classes(
                "btn-primary").style("width:100%;font-size:10px;")
            ui.button("ITP PDF — with header", icon="picture_as_pdf",
                      on_click=_dl_itp_with_header).classes(
                "btn-primary").style("width:100%;font-size:10px;")

    # -------- Product card --------
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

    # -------- MOS preview --------
    with ui.element('div').classes("card").style("margin-bottom:12px;"):
        ui.html(
            '<div style="font-size:15px;font-weight:700;'
            'color:#14b8a6;border-bottom:1px solid rgba(20,184,166,0.3);'
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
                'color:#14b8a6;margin-top:14px;margin-bottom:4px;'
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

    # -------- ITP preview --------
    with ui.element('div').classes("card").style("margin-bottom:12px;"):
        ui.html(
            '<div style="font-size:15px;font-weight:700;'
            'color:#14b8a6;border-bottom:1px solid rgba(20,184,166,0.3);'
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
                         'color:#14b8a6;text-transform:uppercase;'
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
