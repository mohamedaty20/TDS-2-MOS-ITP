"""
services/tds_service.py — TDS → Method Statement + ITP generator.

Takes a manufacturer Technical Data Sheet text, calls Gemini with a strict
extraction prompt, returns structured {product, critical_parameters,
method_statement, inspection_test_plan}. Also builds the two downloadable
PDFs.

PDF notes:
- Body font is Helvetica (not monospace). Web UI keeps its own monospace.
- Temperatures are normalised to "NN °C".
- The critical-parameters table drops the Source column when every row
  shares the same source.
- Table row borders are 1px solid #d0d0d0; header row bottom border is
  heavier.
- Uploaded logos are composited onto a white rectangle with 8px padding
  so dark logos remain visible.
"""
import io
import re
import json
import datetime

from services import defect_service as svc


_TDS_PROMPT_TEMPLATE = """You are an expert Civil Quality Control Engineer and Technical Document Specialist.

Your task is to analyze the manufacturer Technical Data Sheet (TDS) text below and extract all critical parameters required to draft a Method Statement (MOS) and an Inspection and Test Plan (ITP).

Strictly adhere to the following extraction rules:
1. Extract exact numerical values, temperature ranges, time limits, and ratios (e.g., mixing ratios, pot life, curing time, layer thickness). Do not guess or extrapolate; if a value is not stated, return "Not specified".
2. Categorize substrate preparation requirements precisely as stated in the TDS.
3. Identify all quality control verification points, tests, and acceptance criteria needed for an ITP inspection matrix.
4. Output your response strictly in the JSON format specified below.

Output ONLY the JSON object. No prose. No markdown fences. No commentary.

{
  "product": {
    "name": "",
    "manufacturer": "",
    "tds_reference": "",
    "category": "",
    "description": ""
  },
  "critical_parameters": [
    {"parameter": "", "value": "", "source_note": ""}
  ],
  "method_statement": {
    "title": "Method Statement — <product name>",
    "sections": [
      {"number": "1", "heading": "SCOPE AND PURPOSE", "body": ""},
      {"number": "2", "heading": "REFERENCED DOCUMENTS", "body": ""},
      {"number": "3", "heading": "MATERIALS AND PRODUCT DATA", "body": ""},
      {"number": "4", "heading": "SUBSTRATE PREPARATION", "body": ""},
      {"number": "5", "heading": "MIXING AND APPLICATION", "body": ""},
      {"number": "6", "heading": "CURING AND PROTECTION", "body": ""},
      {"number": "7", "heading": "QUALITY CONTROL", "body": ""},
      {"number": "8", "heading": "SAFETY AND ENVIRONMENT", "body": ""}
    ]
  },
  "inspection_test_plan": {
    "title": "Inspection & Test Plan — <product name>",
    "rows": [
      {
        "activity": "",
        "reference": "",
        "checkpoint": "",
        "acceptance_criteria": "",
        "method": "",
        "frequency": "",
        "responsible": ""
      }
    ]
  }
}

RULES FOR METHOD STATEMENT SECTIONS:
- Each section "body" must be 3-8 sentences of professional QC prose.
- Reference exact TDS values wherever they exist. If a value is missing, write "Not specified in TDS".
- Do NOT invent clause numbers from standards that are not in the TDS. Only cite the TDS.
- Be technically detailed — this will be issued as a site document and signed.
- Return exactly 8 sections in the order shown. Keep the exact headings above.

RULES FOR ITP ROWS:
- Provide 10-15 rows covering: materials verification, substrate prep, mixing, application, curing, final inspection.
- "acceptance_criteria" must quote the exact TDS limit when stated; otherwise "Not specified in TDS".
- "frequency" must be one of: 100%, Batch, Daily, Per element, Random.
- "responsible" must be one of: QC Engineer, Site Engineer, Foreman, Third Party.

TDS TEXT STARTS BELOW
--------
__TDS_TEXT__
--------
"""


def _parse_json(raw):
    if not raw:
        return None
    txt = raw.strip()
    txt = re.sub(r'^```json\s*', '', txt)
    txt = re.sub(r'^```\s*', '', txt)
    txt = re.sub(r'\s*```$', '', txt)
    start = txt.find('{')
    end = txt.rfind('}')
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(txt[start:end + 1])
    except Exception:
        return None


async def generate_mos_itp(tds_text, call_gemini_json_fn):
    """Return {product, critical_parameters, method_statement,
    inspection_test_plan} or {error}."""
    text = (tds_text or "").strip()
    if len(text) < 200:
        return {"error": "Not enough text extracted from the TDS."}
    prompt = _TDS_PROMPT_TEMPLATE.replace("__TDS_TEXT__", text[:30000])
    try:
        raw = await call_gemini_json_fn(prompt, temperature=0.0,
                                          timeout=120, max_tokens=8192)
    except Exception as e:
        return {"error": "AI call failed: " + repr(e)}
    data = _parse_json(raw)
    if not data:
        return {"error": "AI returned unparseable JSON.",
                "raw": (raw or "")[:1500]}
    data.setdefault("product", {})
    data.setdefault("critical_parameters", [])
    data.setdefault("method_statement", {})
    data.setdefault("inspection_test_plan", {})
    return data


# =====================================================================
# PDF HELPERS
# =====================================================================
PDF_FONT = "Helvetica"
PDF_FONT_BOLD = "Helvetica-Bold"

# Table border colours / widths
ROW_BORDER_COLOR = "#d0d0d0"
ROW_BORDER_WIDTH = 1.0
HEADER_BORDER_WIDTH = 2.0


def _ensure():
    try:
        svc._ensure_fonts()
    except Exception:
        pass


def _esc(s):
    return (str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _fix_temps(s):
    """Force every bare 'C' that follows a number to render as '°C'.
    Safe against C30/37 concrete grades, ECP codes, and Arabic text.
    """
    if s is None:
        return ""
    text = str(s)
    # Normalise existing °C / ºC forms to a canonical " °C"
    text = re.sub(r'(\d)\s*[°º]\s*C\b', r'\1 °C', text)
    # Convert a bare C after a digit to " °C"
    text = re.sub(r'(\d)\s*C\b', r'\1 °C', text)
    return text


def _mono_names():
    """Kept for backward compatibility with anything that imports it.
    The PDF now uses Helvetica, so callers should ignore these values."""
    return (getattr(svc, "_MONO_NAME", "Courier"),
            getattr(svc, "_MONO_BOLD", "Courier-Bold"))


def _header_has_content(header):
    if not header:
        return False
    return bool(
        (header.get("company_name") or "").strip()
        or (header.get("project_name") or "").strip()
        or (header.get("location") or "").strip()
        or (header.get("prepared_by") or "").strip()
        or header.get("logo_bytes")
    )


def _logo_on_white(logo_bytes, padding=8):
    """Composite a logo onto a white RGB rectangle with N-pixel padding.
    Preserves transparency (PNG alpha) by pasting onto white.
    Falls back to the original bytes if anything fails.
    """
    if not logo_bytes:
        return None
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(logo_bytes))

        # Compose transparent logos onto white
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            alpha = img.split()[-1]
            bg.paste(img, mask=alpha)
            img = bg
        elif img.mode == "P":
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode == "L":
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        new_w = w + 2 * padding
        new_h = h + 2 * padding
        canvas = Image.new("RGB", (new_w, new_h), (255, 255, 255))
        canvas.paste(img, (padding, padding))

        buf = _io.BytesIO()
        canvas.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print("[tds] logo composite failed: " + repr(e))
        return logo_bytes


def _build_header_block(header):
    """Return a list of ReportLab flowables that render the optional
    company header at the top of page 1. Returns [] when header is
    empty or missing. Body font is Helvetica.
    """
    if not _header_has_content(header):
        return []
    from reportlab.platypus import (Table, TableStyle, Spacer, HRFlowable,
                                     Image as ReportLabImage, Paragraph)
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    import io as _io

    NAVY = colors.HexColor("#0a0a0a")
    ACCENT = colors.HexColor("#14b8a6")

    company_style = ParagraphStyle("HdrCompany", fontName=PDF_FONT_BOLD,
                                    fontSize=13, textColor=NAVY,
                                    leading=16, spaceAfter=2)
    label_style = ParagraphStyle("HdrLabel", fontName=PDF_FONT_BOLD,
                                  fontSize=8, textColor=ACCENT,
                                  leading=11)
    value_style = ParagraphStyle("HdrValue", fontName=PDF_FONT,
                                  fontSize=9.5, textColor=colors.black,
                                  leading=12)

    company_name = (header.get("company_name") or "").strip()
    project_name = (header.get("project_name") or "").strip()
    location = (header.get("location") or "").strip()
    prepared_by = (header.get("prepared_by") or "").strip()
    date_str = (header.get("date") or "").strip()
    logo_bytes = header.get("logo_bytes")

    logo_cell = ""
    if logo_bytes:
        try:
            clean_logo = _logo_on_white(logo_bytes, padding=8)
            logo_cell = ReportLabImage(_io.BytesIO(clean_logo),
                                        width=30 * mm, height=16 * mm)
        except Exception:
            logo_cell = ""

    right_flowables = []
    if company_name:
        right_flowables.append(Paragraph(_esc(company_name), company_style))

    detail_rows = []
    if project_name:
        detail_rows.append([
            Paragraph("PROJECT", label_style),
            Paragraph(_esc(_fix_temps(project_name)), value_style)])
    if location:
        detail_rows.append([
            Paragraph("LOCATION", label_style),
            Paragraph(_esc(_fix_temps(location)), value_style)])
    if prepared_by:
        detail_rows.append([
            Paragraph("PREPARED BY", label_style),
            Paragraph(_esc(_fix_temps(prepared_by)), value_style)])
    if date_str:
        detail_rows.append([
            Paragraph("DATE", label_style),
            Paragraph(_esc(_fix_temps(date_str)), value_style)])

    if detail_rows:
        t_details = Table(detail_rows, colWidths=[26 * mm, 118 * mm])
        t_details.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        right_flowables.append(Spacer(1, 3))
        right_flowables.append(t_details)

    if logo_cell:
        t_header = Table([[logo_cell, right_flowables]],
                          colWidths=[34 * mm, 146 * mm])
    else:
        t_header = Table([[right_flowables]], colWidths=[180 * mm])

    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    t_header.hAlign = 'LEFT'

    return [
        t_header,
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                    spaceAfter=10),
    ]


# =====================================================================
# MOS PDF
# =====================================================================
def build_mos_pdf(product, mos, critical_params=None, header=None):
    _ensure()
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, HRFlowable)
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    NAVY = colors.HexColor("#0a0a0a")
    ACCENT = colors.HexColor("#14b8a6")
    GREY = colors.HexColor("#525252")

    title_style = ParagraphStyle("T", fontName=PDF_FONT_BOLD, fontSize=14,
                                  textColor=NAVY, spaceAfter=2, leading=18)
    sub_style = ParagraphStyle("S", fontName=PDF_FONT, fontSize=9,
                                textColor=ACCENT, spaceAfter=6, leading=12)
    h_style = ParagraphStyle("H", fontName=PDF_FONT_BOLD, fontSize=11,
                              textColor=ACCENT, spaceBefore=10,
                              spaceAfter=4, leading=14)
    body_style = ParagraphStyle("B", fontName=PDF_FONT, fontSize=9.5,
                                 textColor=colors.black, leading=13.5)
    label_style = ParagraphStyle("L", fontName=PDF_FONT_BOLD, fontSize=8,
                                  textColor=NAVY, leading=11)
    meta_style = ParagraphStyle("M", fontName=PDF_FONT, fontSize=8.5,
                                 textColor=GREY, leading=12)
    small_style = ParagraphStyle("Sm", fontName=PDF_FONT, fontSize=7,
                                  textColor=GREY, leading=9)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)

    story = []
    story.extend(_build_header_block(header))
    story.append(Paragraph(_esc(mos.get("title") or
                                 "METHOD STATEMENT"), title_style))
    p = product or {}
    sub_bits = []
    if p.get("name"):
        sub_bits.append(str(p["name"]))
    if p.get("manufacturer"):
        sub_bits.append(str(p["manufacturer"]))
    story.append(Paragraph(_esc(" · ".join(sub_bits) or
                                 "TDS-derived method statement"),
                            sub_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                             spaceAfter=10))

    meta_rows = [
        [Paragraph("<b>Product:</b>", label_style),
         Paragraph(_esc(_fix_temps(str(p.get("name") or "Not specified"))),
                    meta_style),
         Paragraph("<b>Manufacturer:</b>", label_style),
         Paragraph(_esc(_fix_temps(str(p.get("manufacturer")
                                        or "Not specified"))), meta_style)],
        [Paragraph("<b>TDS ref:</b>", label_style),
         Paragraph(_esc(_fix_temps(str(p.get("tds_reference")
                                        or "Not specified"))), meta_style),
         Paragraph("<b>Category:</b>", label_style),
         Paragraph(_esc(_fix_temps(str(p.get("category")
                                        or "Not specified"))), meta_style)],
        [Paragraph("<b>Date:</b>", label_style),
         Paragraph(datetime.date.today().strftime("%Y-%m-%d"), meta_style),
         Paragraph("", label_style), Paragraph("", meta_style)],
    ]
    t = Table(meta_rows, colWidths=[22 * mm, 68 * mm, 25 * mm, 65 * mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    desc = str(p.get("description") or "").strip()
    if desc:
        story.append(Paragraph(_esc(_fix_temps(desc)), body_style))
        story.append(Spacer(1, 6))

    # --- Critical parameters table (Source column conditionally hidden) ---
    if critical_params:
        story.append(Paragraph("KEY PARAMETERS FROM TDS", h_style))

        capped = critical_params[:40]
        sources_raw = [str(cp.get("source_note") or "").strip()
                        for cp in capped]
        nonempty_sources = [s for s in sources_raw if s]
        # Show the Source column only when 2+ distinct non-empty sources
        show_source = len(set(nonempty_sources)) >= 2

        if show_source:
            rows = [[
                Paragraph("<b>Parameter</b>", label_style),
                Paragraph("<b>Value</b>", label_style),
                Paragraph("<b>Source</b>", label_style),
            ]]
            for cp in capped:
                rows.append([
                    Paragraph(_esc(_fix_temps(cp.get("parameter") or "")),
                              body_style),
                    Paragraph(_esc(_fix_temps(cp.get("value") or "")),
                              body_style),
                    Paragraph(_esc(_fix_temps(cp.get("source_note") or "")),
                              meta_style),
                ])
            col_widths = [55 * mm, 55 * mm, 50 * mm]
        else:
            rows = [[
                Paragraph("<b>Parameter</b>", label_style),
                Paragraph("<b>Value</b>", label_style),
            ]]
            for cp in capped:
                rows.append([
                    Paragraph(_esc(_fix_temps(cp.get("parameter") or "")),
                              body_style),
                    Paragraph(_esc(_fix_temps(cp.get("value") or "")),
                              body_style),
                ])
            col_widths = [70 * mm, 90 * mm]

        tt = Table(rows, colWidths=col_widths)
        tt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            # Heavier border directly under the header row
            ('LINEBELOW', (0, 0), (-1, 0), HEADER_BORDER_WIDTH,
             colors.HexColor(ROW_BORDER_COLOR)),
            # 1px row borders between all body rows
            ('LINEBELOW', (0, 1), (-1, -2), ROW_BORDER_WIDTH,
             colors.HexColor(ROW_BORDER_COLOR)),
            # 1px border under the last row
            ('LINEBELOW', (0, -1), (-1, -1), ROW_BORDER_WIDTH,
             colors.HexColor(ROW_BORDER_COLOR)),
        ]))
        story.append(tt)
        story.append(Spacer(1, 8))

    # --- MOS sections ---
    for sec in (mos.get("sections") or []):
        num = str(sec.get("number") or "").strip()
        head = str(sec.get("heading") or "").strip()
        head_line = (num + ". " + head) if num else head
        if not head_line:
            continue
        story.append(Paragraph(_esc(head_line), h_style))
        body = str(sec.get("body") or "").strip()
        for para in [x.strip() for x in body.split("\n") if x.strip()]:
            story.append(Paragraph(_esc(_fix_temps(para)), body_style))
            story.append(Spacer(1, 3))

    story.append(Spacer(1, 20))
    sig = [
        [Paragraph("<b>PREPARED BY (QC)</b>", label_style),
         Paragraph("<b>APPROVED BY (CONSULTANT)</b>", label_style)],
        [Paragraph("_" * 32, body_style), Paragraph("_" * 32, body_style)],
        [Paragraph("Name / Date / Signature", small_style),
         Paragraph("Name / Date / Signature", small_style)],
    ]
    ts = Table(sig, colWidths=[90 * mm, 90 * mm])
    ts.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(ts)

    doc.build(story)
    buf.seek(0)
    return buf.read()


# =====================================================================
# ITP PDF
# =====================================================================
def build_itp_pdf(product, itp, header=None):
    _ensure()
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, HRFlowable)
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm

    NAVY = colors.HexColor("#0a0a0a")
    ACCENT = colors.HexColor("#14b8a6")
    GREY = colors.HexColor("#525252")

    title_style = ParagraphStyle("T", fontName=PDF_FONT_BOLD, fontSize=13,
                                  textColor=NAVY, spaceAfter=2)
    sub_style = ParagraphStyle("S", fontName=PDF_FONT, fontSize=9,
                                textColor=ACCENT, spaceAfter=6)
    cell_style = ParagraphStyle("C", fontName=PDF_FONT, fontSize=8,
                                 textColor=colors.black, leading=10)
    head_style = ParagraphStyle("H", fontName=PDF_FONT_BOLD, fontSize=8,
                                 textColor=colors.white, leading=10)
    small_style = ParagraphStyle("Sm", fontName=PDF_FONT, fontSize=7,
                                  textColor=GREY, leading=9)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm)

    story = []
    story.extend(_build_header_block(header))
    story.append(Paragraph(_esc(itp.get("title") or
                                 "INSPECTION & TEST PLAN"), title_style))
    p = product or {}
    sub_bits = []
    if p.get("name"):
        sub_bits.append(str(p["name"]))
    if p.get("manufacturer"):
        sub_bits.append(str(p["manufacturer"]))
    story.append(Paragraph(_esc(" · ".join(sub_bits) or
                                 "TDS-derived ITP"), sub_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                             spaceAfter=10))

    head = ["#", "Activity", "Reference", "Checkpoint",
            "Acceptance criteria", "Method", "Frequency", "Responsible"]
    data = [[Paragraph("<b>" + h + "</b>", head_style) for h in head]]
    for i, r in enumerate(itp.get("rows") or [], start=1):
        data.append([
            Paragraph(str(i), cell_style),
            Paragraph(_esc(_fix_temps(r.get("activity") or "")), cell_style),
            Paragraph(_esc(_fix_temps(r.get("reference") or "")), cell_style),
            Paragraph(_esc(_fix_temps(r.get("checkpoint") or "")),
                      cell_style),
            Paragraph(_esc(_fix_temps(r.get("acceptance_criteria") or "")),
                      cell_style),
            Paragraph(_esc(_fix_temps(r.get("method") or "")), cell_style),
            Paragraph(_esc(_fix_temps(r.get("frequency") or "")), cell_style),
            Paragraph(_esc(_fix_temps(r.get("responsible") or "")),
                      cell_style),
        ])
    col_w = [8 * mm, 30 * mm, 24 * mm, 34 * mm, 48 * mm, 30 * mm,
             20 * mm, 22 * mm]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        # Heavier border directly under the header row
        ('LINEBELOW', (0, 0), (-1, 0), HEADER_BORDER_WIDTH,
         colors.HexColor(ROW_BORDER_COLOR)),
        # 1px row borders between all body rows
        ('LINEBELOW', (0, 1), (-1, -2), ROW_BORDER_WIDTH,
         colors.HexColor(ROW_BORDER_COLOR)),
        # 1px border under the last row
        ('LINEBELOW', (0, -1), (-1, -1), ROW_BORDER_WIDTH,
         colors.HexColor(ROW_BORDER_COLOR)),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph("Generated " +
                            datetime.date.today().strftime("%Y-%m-%d"),
                            small_style))
    doc.build(story)
    buf.seek(0)
    return buf.read()
