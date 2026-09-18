"""
services/tds_service.py — TDS → Method Statement + ITP generator.

Takes a manufacturer Technical Data Sheet text, calls Gemini with a strict
extraction prompt, returns structured {product, critical_parameters,
method_statement, inspection_test_plan}. Also builds the two downloadable
PDFs. Reuses fonts + ReportLab setup from defect_service.
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


# ---------------------------------------------------------------------
# PDF BUILDERS
# ---------------------------------------------------------------------
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


def _mono_names():
    return (getattr(svc, "_MONO_NAME", "Courier"),
            getattr(svc, "_MONO_BOLD", "Courier-Bold"))


def build_mos_pdf(product, mos, critical_params=None):
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
    mono, mono_b = _mono_names()

    title_style = ParagraphStyle("T", fontName=mono_b, fontSize=14,
                                  textColor=NAVY, spaceAfter=2, leading=18)
    sub_style = ParagraphStyle("S", fontName=mono, fontSize=9,
                                textColor=ACCENT, spaceAfter=6, leading=12)
    h_style = ParagraphStyle("H", fontName=mono_b, fontSize=11,
                              textColor=ACCENT, spaceBefore=10,
                              spaceAfter=4, leading=14)
    body_style = ParagraphStyle("B", fontName=mono, fontSize=9.5,
                                 textColor=colors.black, leading=13.5)
    label_style = ParagraphStyle("L", fontName=mono_b, fontSize=8,
                                  textColor=NAVY, leading=11)
    meta_style = ParagraphStyle("M", fontName=mono, fontSize=8.5,
                                 textColor=GREY, leading=12)
    small_style = ParagraphStyle("Sm", fontName=mono, fontSize=7,
                                  textColor=GREY, leading=9)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)

    story = []
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
         Paragraph(_esc(str(p.get("name") or "Not specified")), meta_style),
         Paragraph("<b>Manufacturer:</b>", label_style),
         Paragraph(_esc(str(p.get("manufacturer") or "Not specified")),
                    meta_style)],
        [Paragraph("<b>TDS ref:</b>", label_style),
         Paragraph(_esc(str(p.get("tds_reference") or "Not specified")),
                    meta_style),
         Paragraph("<b>Category:</b>", label_style),
         Paragraph(_esc(str(p.get("category") or "Not specified")),
                    meta_style)],
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
        story.append(Paragraph(_esc(desc), body_style))
        story.append(Spacer(1, 6))

    if critical_params:
        story.append(Paragraph("KEY PARAMETERS FROM TDS", h_style))
        rows = [[
            Paragraph("<b>Parameter</b>", label_style),
            Paragraph("<b>Value</b>", label_style),
            Paragraph("<b>Source</b>", label_style),
        ]]
        for cp in critical_params[:40]:
            rows.append([
                Paragraph(_esc(str(cp.get("parameter") or "")), body_style),
                Paragraph(_esc(str(cp.get("value") or "")), body_style),
                Paragraph(_esc(str(cp.get("source_note") or "")), meta_style),
            ])
        tt = Table(rows, colWidths=[55 * mm, 55 * mm, 50 * mm])
        tt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
            ('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#BFBFBF")),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(tt)
        story.append(Spacer(1, 8))

    for sec in (mos.get("sections") or []):
        num = str(sec.get("number") or "").strip()
        head = str(sec.get("heading") or "").strip()
        head_line = (num + ". " + head) if num else head
        if not head_line:
            continue
        story.append(Paragraph(_esc(head_line), h_style))
        body = str(sec.get("body") or "").strip()
        for para in [x.strip() for x in body.split("\n") if x.strip()]:
            story.append(Paragraph(_esc(para), body_style))
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


def build_itp_pdf(product, itp):
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
    mono, mono_b = _mono_names()

    title_style = ParagraphStyle("T", fontName=mono_b, fontSize=13,
                                  textColor=NAVY, spaceAfter=2)
    sub_style = ParagraphStyle("S", fontName=mono, fontSize=9,
                                textColor=ACCENT, spaceAfter=6)
    cell_style = ParagraphStyle("C", fontName=mono, fontSize=8,
                                 textColor=colors.black, leading=10)
    head_style = ParagraphStyle("H", fontName=mono_b, fontSize=8,
                                 textColor=colors.white, leading=10)
    small_style = ParagraphStyle("Sm", fontName=mono, fontSize=7,
                                  textColor=GREY, leading=9)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm)

    story = []
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
            Paragraph(_esc(str(r.get("activity") or "")), cell_style),
            Paragraph(_esc(str(r.get("reference") or "")), cell_style),
            Paragraph(_esc(str(r.get("checkpoint") or "")), cell_style),
            Paragraph(_esc(str(r.get("acceptance_criteria") or "")),
                      cell_style),
            Paragraph(_esc(str(r.get("method") or "")), cell_style),
            Paragraph(_esc(str(r.get("frequency") or "")), cell_style),
            Paragraph(_esc(str(r.get("responsible") or "")), cell_style),
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
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F5F5F5")]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#BFBFBF")),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph("Generated " +
                            datetime.date.today().strftime("%Y-%m-%d"),
                            small_style))
    doc.build(story)
    buf.seek(0)
    return buf.read()
