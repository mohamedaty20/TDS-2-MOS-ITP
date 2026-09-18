"""
services/defect_service.py — Full file.
Adds build_sub_pdf() + photo strip in notice PDF.
Arabic PDF rendering hardened: multi-mirror font download, system-font
fallback, mixed Arabic/Latin run wrapping, right-aligned Arabic blocks.
Feature #3: nothing renders below the signature tables anymore.
Feature #10: builders accept an optional template_config dict.
"""
import io
import os
import re
import json
import uuid
import base64
import datetime
import asyncio


# =====================================================================
# FONTS
# =====================================================================
_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
_FONT_FALLBACK_DIR = "/tmp/defect_fonts"
_FONT_REG_PATH = os.path.join(_FONT_DIR, "Amiri-Regular.ttf")
_FONT_BOLD_PATH = os.path.join(_FONT_DIR, "Amiri-Bold.ttf")
_FONT_REG_URLS = [
    "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/amiri/Amiri-Regular.ttf",
    "https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Regular.ttf",
    "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf",
]
_FONT_BOLD_URLS = [
    "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/amiri/Amiri-Bold.ttf",
    "https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Bold.ttf",
    "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Bold.ttf",
]
_MONO_REG_PATH = os.path.join(_FONT_DIR, "JetBrainsMono-Regular.ttf")
_MONO_BOLD_PATH = os.path.join(_FONT_DIR, "JetBrainsMono-Bold.ttf")
_MONO_REG_URLS = [
    "https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@master/fonts/ttf/JetBrainsMono-Regular.ttf",
    "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/master/fonts/ttf/JetBrainsMono-Regular.ttf",
    "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Regular.ttf",
]
_MONO_BOLD_URLS = [
    "https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@master/fonts/ttf/JetBrainsMono-Bold.ttf",
    "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/master/fonts/ttf/JetBrainsMono-Bold.ttf",
    "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Bold.ttf",
]

_SYSTEM_ARABIC_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:\\Windows\\Fonts\\tahoma.ttf",
    "C:\\Windows\\Fonts\\segoeui.ttf",
]

_FONT_NAME = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_MONO_NAME = "Courier"
_MONO_BOLD = "Courier-Bold"

_SHAPING_OK = False
_SHAPING_ERR = ""
try:
    import arabic_reshaper as _ar  # noqa: F401
    from bidi.algorithm import get_display as _get_display  # noqa: F401
    _SHAPING_OK = True
except Exception as _e:
    _SHAPING_ERR = repr(_e)
    print("[defect] WARNING: Arabic shaping libs missing: " + _SHAPING_ERR)
    print("[defect]   -> add 'arabic-reshaper' and 'python-bidi' to requirements")


def _writable_dir():
    try:
        os.makedirs(_FONT_DIR, exist_ok=True)
        probe = os.path.join(_FONT_DIR, ".w")
        with open(probe, "w") as f:
            f.write("x")
        try:
            os.remove(probe)
        except Exception:
            pass
        return _FONT_DIR
    except Exception:
        try:
            os.makedirs(_FONT_FALLBACK_DIR, exist_ok=True)
        except Exception:
            pass
        return _FONT_FALLBACK_DIR


def _download_font(url, dest):
    import urllib.request
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
    except Exception:
        pass
    try:
        req = urllib.request.Request(url,
                                      headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if not data or len(data) < 5000:
            return False
        if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"):
            return False
        with open(dest, "wb") as f:
            f.write(data)
        print("[defect] saved " + str(len(data) // 1024) + " KB -> " + dest)
        return True
    except Exception as e:
        print("[defect] fetch fail " + url + " : " + repr(e))
        return False


def _registered():
    try:
        from reportlab.pdfbase import pdfmetrics
        return set(pdfmetrics.getRegisteredFontNames())
    except Exception:
        return set()


def _try_register(name, path):
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont(name, path))
        return True
    except Exception as e:
        print("[defect] register " + name + " failed: " + repr(e))
        return False


def _resolve_path(preferred, urls, fallback_names=None):
    if os.path.exists(preferred):
        return preferred
    alt = os.path.join(_FONT_FALLBACK_DIR, os.path.basename(preferred))
    if os.path.exists(alt):
        return alt
    for u in urls:
        if _download_font(u, preferred):
            return preferred
        if _download_font(u, alt):
            return alt
    if fallback_names:
        for cand in fallback_names:
            if os.path.exists(cand):
                print("[defect] using system font fallback: " + cand)
                return cand
    return None


def _ensure_fonts():
    global _FONT_NAME, _FONT_BOLD, _MONO_NAME, _MONO_BOLD
    try:
        from reportlab.pdfbase import pdfmetrics  # noqa: F401
        from reportlab.pdfbase.ttfonts import TTFont  # noqa: F401
    except Exception as e:
        print("[defect] reportlab missing: " + repr(e))
        return

    have = _registered()

    if "MonoReg" not in have:
        mono_reg = _resolve_path(_MONO_REG_PATH, _MONO_REG_URLS)
        mono_bold = _resolve_path(_MONO_BOLD_PATH, _MONO_BOLD_URLS)
        if mono_reg:
            _try_register("MonoReg", mono_reg)
        if mono_bold:
            _try_register("MonoBold", mono_bold)

    have = _registered()
    if "MonoReg" in have:
        _MONO_NAME = "MonoReg"
        _MONO_BOLD = "MonoBold" if "MonoBold" in have else "MonoReg"
    else:
        _MONO_NAME = "Courier"
        _MONO_BOLD = "Courier-Bold"

    if "ArReg" not in have:
        ar_reg = _resolve_path(_FONT_REG_PATH, _FONT_REG_URLS,
                                fallback_names=_SYSTEM_ARABIC_CANDIDATES)
        ar_bold = _resolve_path(_FONT_BOLD_PATH, _FONT_BOLD_URLS,
                                 fallback_names=_SYSTEM_ARABIC_CANDIDATES)
        if ar_reg:
            _try_register("ArReg", ar_reg)
        if ar_bold:
            _try_register("ArBold", ar_bold)

    have = _registered()
    if "ArReg" in have:
        _FONT_NAME = "ArReg"
        _FONT_BOLD = "ArBold" if "ArBold" in have else "ArReg"
    else:
        _FONT_NAME = "Helvetica"
        _FONT_BOLD = "Helvetica-Bold"
        print("[defect] WARNING: no Arabic-capable font available.")

    try:
        from reportlab.pdfbase import pdfmetrics
        if _MONO_NAME == "MonoReg" and _MONO_BOLD == "MonoBold":
            pdfmetrics.registerFontFamily(
                "MonoReg", normal="MonoReg", bold="MonoBold",
                italic="MonoReg", boldItalic="MonoBold")
        if _FONT_NAME == "ArReg" and _FONT_BOLD == "ArBold":
            pdfmetrics.registerFontFamily(
                "ArReg", normal="ArReg", bold="ArBold",
                italic="ArReg", boldItalic="ArBold")
    except Exception:
        pass

    print("[defect] fonts ready: mono=" + _MONO_NAME +
          " arabic=" + _FONT_NAME +
          " shaping=" + ("on" if _SHAPING_OK else "OFF"))


def _has_arabic(text):
    return any('\u0600' <= ch <= '\u06FF' for ch in str(text or ""))


def _is_arabic_char(ch):
    return '\u0600' <= ch <= '\u06FF' or '\u0750' <= ch <= '\u077F' \
        or '\u08A0' <= ch <= '\u08FF' or '\uFB50' <= ch <= '\uFDFF' \
        or '\uFE70' <= ch <= '\uFEFF'


def _esc_xml(s):
    return (str(s or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _shape_run_arabic(s):
    if not s:
        return s
    if not _SHAPING_OK:
        return s
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(s))
    except Exception as e:
        print("[defect] shaping failed: " + repr(e))
        return s


def _split_script_runs(s):
    runs = []
    if not s:
        return runs
    buf = []
    cur_is_ar = _is_arabic_char(s[0])
    for ch in s:
        is_ar = _is_arabic_char(ch)
        if is_ar == cur_is_ar:
            buf.append(ch)
        else:
            runs.append((cur_is_ar, "".join(buf)))
            buf = [ch]
            cur_is_ar = is_ar
    if buf:
        runs.append((cur_is_ar, "".join(buf)))
    return runs


def _fix(text):
    # No-op kept for backward compat — shaping now happens ONCE in _para().
    # Calling _shape_run_arabic here caused double-shaping (fix F).
    if text is None:
        return ""
    return str(text)


def _font_for(text, bold=False):
    reg = _registered()
    if _has_arabic(text):
        if bold and "ArBold" in reg:
            return "ArBold"
        if "ArReg" in reg:
            return "ArReg"
        return "Helvetica"
    if bold and "MonoBold" in reg:
        return "MonoBold"
    if "MonoReg" in reg:
        return "MonoReg"
    return "Courier"


def _wrap_runs(s, bold=False):
    # Kept for backward compat. No longer called by _para().
    return _esc_xml(str(s or ""))


def _para(text, base_style, bold=False):
    """
    Shape ONCE at the whole-string level and use a single font that covers
    both Arabic presentation forms and Latin. Do NOT split into <font> tags
    per script run — that breaks bidi reordering across word boundaries.
    """
    from reportlab.platypus import Paragraph
    from reportlab.lib.enums import TA_RIGHT
    from copy import copy
    raw = str(text or "")
    if not raw:
        return Paragraph("", base_style)

    style = copy(base_style)
    reg = _registered()

    if _has_arabic(raw):
        shaped = _shape_run_arabic(raw)
        style.alignment = TA_RIGHT
        if "ArReg" in reg:
            style.fontName = ("ArBold" if (bold and "ArBold" in reg)
                              else "ArReg")
        # If ArReg is missing we keep base_style.fontName — the log line
        # "[defect] WARNING: no Arabic-capable font available." will say so.
        return Paragraph(_esc_xml(shaped), style)

    # Pure Latin path — keep the mono look.
    if bold and "MonoBold" in reg:
        style.fontName = "MonoBold"
    elif "MonoReg" in reg:
        style.fontName = "MonoReg"
    else:
        style.fontName = "Courier-Bold" if bold else "Courier"
    return Paragraph(_esc_xml(raw), style)


# =====================================================================
# UID / IMAGES
# =====================================================================
def generate_uid(prefix="NTC"):
    short = uuid.uuid4().hex[:4].upper()
    year = datetime.date.today().year
    seq = uuid.uuid4().int % 10000
    return prefix + "-" + short + "-" + str(year) + "-" + str(seq).zfill(4)


def _shrink_image(photo_bytes, max_side=1024):
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(photo_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_side:
            ratio = max_side / float(max(w, h))
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80, optimize=True)
        out.seek(0)
        return out.read()
    except Exception as e:
        print("[defect] shrink fail: " + repr(e))
        return photo_bytes


def _detect_image_type(data):
    if not data or len(data) < 8:
        return None
    if data[:3] == b'\xff\xd8\xff':
        return "jpeg"
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "png"
    return None


def _thumb(photo_bytes, max_side=280):
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(photo_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_side:
            r = max_side / float(max(w, h))
            img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=75, optimize=True)
        out.seek(0)
        return out.read()
    except Exception:
        return photo_bytes


# =====================================================================
# DOC TEXT
# =====================================================================
def extract_pdf_text(pdf_bytes, max_pages=30, max_chars=40000):
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for i in range(min(max_pages, len(reader.pages))):
            try:
                parts.append(reader.pages[i].extract_text() or "")
            except Exception:
                pass
        return "\n".join(parts)[:max_chars]
    except Exception as e:
        print("[defect] pdf extract fail: " + repr(e))
        return ""


def extract_docx_text(docx_bytes, max_chars=40000):
    try:
        from docx import Document
        doc = Document(io.BytesIO(docx_bytes))
        parts = []
        for para in doc.paragraphs:
            if para.text and para.text.strip():
                parts.append(para.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text and cell.text.strip():
                        parts.append(cell.text)
        return "\n".join(parts)[:max_chars]
    except Exception as e:
        print("[defect] docx extract fail: " + repr(e))
        return ""


def extract_txt_text(txt_bytes, max_chars=40000):
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return txt_bytes.decode(enc)[:max_chars]
        except Exception:
            continue
    return ""


def extract_document_text(file_bytes, filename=None, max_chars=40000):
    name = (filename or "").lower().strip()
    if name.endswith(".pdf"):
        return extract_pdf_text(file_bytes, max_chars=max_chars)
    if name.endswith(".docx"):
        return extract_docx_text(file_bytes, max_chars=max_chars)
    if name.endswith(".doc"):
        print("[defect] .doc not supported; save as .docx")
        return ""
    if name.endswith(".txt") or name.endswith(".md"):
        return extract_txt_text(file_bytes, max_chars=max_chars)
    t = extract_pdf_text(file_bytes, max_chars=max_chars)
    if t and len(t) > 100:
        return t
    return extract_txt_text(file_bytes, max_chars=max_chars)


# =====================================================================
# JSON
# =====================================================================
def _strip_fences(txt):
    t = (txt or "").strip()
    t = re.sub(r'^```json\s*', '', t)
    t = re.sub(r'^```\s*', '', t)
    t = re.sub(r'\s*```$', '', t)
    return t


def _parse_json_object(raw):
    if not raw:
        return None
    txt = _strip_fences(raw)
    start = txt.find('{')
    end = txt.rfind('}')
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(txt[start:end + 1])
    except Exception as e:
        print("[defect] JSON fail: " + repr(e))
        return None


# =====================================================================
# MS CLAUSE EXTRACTION
# =====================================================================
_CLAUSE_PROMPT_TEMPLATE = """You are reading a construction Method Statement (MS).

Task: extract the CLAUSE STRUCTURE from the text below.

Return ONE JSON object with this exact shape:
{
  "clauses": [
    {"id": "3.1", "title": "Bar Spacing", "text": "as per approved shop drawings"},
    {"id": "3.2", "title": "Cover", "text": "minimum 40mm for columns, 25mm for slabs"}
  ]
}

RULES:
- Return EVERY numbered clause you can find, no matter the numbering style.
- The "id" field is the clause number ONLY, as a string.
- The "title" is a short name (1-5 words).
- The "text" field is the clause body, trimmed to at most 200 characters.
- Ignore the MS title page, revision history, and signature blocks.
- MAX 200 clauses. Prioritize the ones with measurable requirements.
- Each clause "text" can be up to 500 characters..
- Output ONLY the JSON object. No prose. No markdown fences.

Method Statement text starts below.
--------
__MS_TEXT__
--------
"""


async def extract_clauses_from_pdf(pdf_bytes, call_gemini_json_fn,
                                    filename=None):
    print("[defect] MS extract, bytes=" + str(len(pdf_bytes) // 1024))
    try:
        text = await asyncio.to_thread(
            extract_document_text, pdf_bytes, filename)
    except Exception as e:
        return {"clauses": [], "raw_text_length": 0,
                "error": "Document parse failed: " + repr(e),
                "full_text": ""}
    if not text or len(text) < 100:
        return {"clauses": [], "raw_text_length": len(text),
                "error": "File has no readable text.",
                "full_text": ""}

    full_text = text[:180000]
    prompt_text = text[:30000]

    prompt = _CLAUSE_PROMPT_TEMPLATE.replace("__MS_TEXT__", prompt_text)
    try:
        raw = await call_gemini_json_fn(prompt, temperature=0.0, timeout=50)
    except Exception as e:
        return {"clauses": [], "raw_text_length": len(text),
                "error": "AI call failed: " + repr(e),
                "full_text": full_text}
    data = _parse_json_object(raw)
    if not data:
        return {"clauses": [], "raw_text_length": len(text),
                "error": "AI returned unparseable output.",
                "full_text": full_text}
    clauses = []
    for c in data.get("clauses", []):
        cid = str(c.get("id", "")).strip()
        title = str(c.get("title", "")).strip()[:80]
        body = str(c.get("text", "")).strip()[:500]
        if not cid or not title:
            continue
        clauses.append({"id": cid, "title": title, "text": body})
    return {"clauses": clauses, "raw_text_length": len(text),
            "error": None, "full_text": full_text}


# =====================================================================
# ECP
# =====================================================================
_ECP_BY_ELEMENT = {
    "column": [
        {"code": "ECP 203 §6.3.1",
         "text": "Minimum concrete cover for columns is 40 mm."},
        {"code": "ECP 203 §6.3.4",
         "text": "Lap length for tension bars is 40 x bar diameter minimum."},
        {"code": "ECP 203 §7.2.1",
         "text": "Column ties spacing shall not exceed the least of: 16x longitudinal bar dia, 48x tie dia, or the least column dimension."},
        {"code": "ECP 203 §4.5.2",
         "text": "Concrete shall be compacted by mechanical vibration. Honeycombing or voids are not permitted."},
    ],
    "beam": [
        {"code": "ECP 203 §6.3.1",
         "text": "Minimum concrete cover for beams is 25 mm (slabs) or 40 mm (exposed to weather)."},
        {"code": "ECP 203 §6.3.4",
         "text": "Lap length for tension bars is 40 x bar diameter minimum."},
        {"code": "ECP 203 §4.5.2",
         "text": "Concrete shall be compacted by mechanical vibration. Honeycombing or voids are not permitted."},
    ],
    "slab": [
        {"code": "ECP 203 §6.3.1",
         "text": "Minimum concrete cover for slabs is 25 mm."},
        {"code": "ECP 203 §6.3.4",
         "text": "Lap length for tension bars is 40 x bar diameter minimum."},
        {"code": "ECP 203 §6.5.1",
         "text": "Slab thickness shall not be less than 100 mm for solid slabs."},
    ],
    "wall": [
        {"code": "ECP 203 §6.3.1",
         "text": "Minimum cover for walls is 25 mm."},
        {"code": "ECP 203 §4.5.2",
         "text": "Concrete shall be compacted by mechanical vibration. Honeycombing or voids are not permitted."},
    ],
    "foundation": [
        {"code": "ECP 203 §8.2.1",
         "text": "Minimum cover for foundation elements is 50 mm."},
        {"code": "ECP 203 §8.3.4",
         "text": "Reinforcement in footings shall be placed on chairs at the designed level before concreting."},
    ],
    "finishing": [
        {"code": "ECP 203 §9.1",
         "text": "Plaster thickness shall be uniform and not less than 15 mm."},
    ],
}


def get_ecp_excerpts(element_type):
    key = (element_type or "").lower().strip()
    return _ECP_BY_ELEMENT.get(key, _ECP_BY_ELEMENT.get("column", []))


def _format_ms_clauses(ms_clauses):
    if not ms_clauses:
        return "(none provided)"
    lines = []
    for c in ms_clauses[:30]:
        lines.append("  id=" + str(c.get("id", "?")) +
                     " - " + str(c.get("title", "")) +
                     " : " + str(c.get("text", ""))[:120])
    return "\n".join(lines)


def _format_ecp(ecp_excerpts):
    if not ecp_excerpts:
        return "(none provided)"
    return "\n".join("  " + e["code"] + " - " + e["text"]
                     for e in ecp_excerpts[:10])


# =====================================================================
# AI — PHOTO
# =====================================================================
_DEFECT_PROMPT = """You are a senior QC engineer inspecting a construction site photo.

Identify visible defects, cite MS clauses / ECP codes ONLY when they truly
apply to what the photo shows.

MATCHING RULE: before citing an MS clause ask: does this clause relate to
what the photo shows?
If NOT: still describe the defect; ms_violations=[]; code_violations=[];
context_mismatch=true.
If YES: cite 1-3 MS ids and 1-3 ECP codes from the lists; context_mismatch=false.

NEVER invent a clause match.

Look for: cracks, honeycombing, exposed/corroded rebar, insufficient cover,
poor formwork, cold joints, segregation, water stains, spalling, poor finish,
missing spacers, rust stains, missing mortar.

USER NOTE: __NOTE__

ELEMENT: __ELEMENT__

MS CLAUSES AVAILABLE:
__MS_CLAUSES__

ECP CODES AVAILABLE:
__ECP__

Return ONE JSON object:
{
  "defects": [
    {
      "name": "Honeycomb on column face",
      "location_hint": "column base",
      "severity": "Medium",
      "ms_violations": ["3.5"],
      "code_violations": ["ECP 203 §6.3.1"],
      "repair_action": "Chip back, patch with non-shrink mortar.",
      "context_mismatch": false
    }
  ]
}

RULES: MAX 6. Only cite ids from above. Severity: Low/Medium/High/Critical.
Output ONLY JSON."""


def _build_defect_prompt(note, element_type, ms_clauses, ecp_excerpts):
    return (_DEFECT_PROMPT
            .replace("__NOTE__", note or "(none)")
            .replace("__ELEMENT__", (element_type or "column").lower())
            .replace("__MS_CLAUSES__", _format_ms_clauses(ms_clauses))
            .replace("__ECP__", _format_ecp(ecp_excerpts)))


async def analyze_defect_photo(photo_bytes, mime_type, note, ms_clauses,
                                element_type, call_gemini_json_fn):
    from google.genai import types
    img_type = _detect_image_type(photo_bytes)
    if img_type is None:
        return {"defects": [], "error": "Not a JPEG/PNG photo."}
    ecp = get_ecp_excerpts(element_type)
    prompt = _build_defect_prompt(note, element_type, ms_clauses, ecp)
    shrunk = _shrink_image(photo_bytes, max_side=1024)
    try:
        img_part = types.Part.from_bytes(data=shrunk, mime_type="image/jpeg")
    except Exception as e:
        return {"defects": [], "error": "Image load failed: " + repr(e)}
    try:
        raw = await call_gemini_json_fn([prompt, img_part],
                                          temperature=0.0, timeout=40)
    except Exception as e:
        return {"defects": [], "error": "AI call failed: " + repr(e)}
    data = _parse_json_object(raw)
    if not data:
        return {"defects": [], "error": "AI returned unparseable output.",
                "raw": (raw or "")[:1500]}
    allowed_ms = {str(c.get("id", "")).strip() for c in (ms_clauses or [])}
    allowed_ecp = {e["code"] for e in ecp}
    defects = []
    for d in data.get("defects", [])[:6]:
        name = str(d.get("name", "")).strip()[:120]
        if not name:
            continue
        ms_v = [str(v).strip() for v in (d.get("ms_violations") or [])]
        ms_v = [v for v in ms_v if v in allowed_ms][:3]
        ecp_v = [str(v).strip() for v in (d.get("code_violations") or [])]
        ecp_v = [v for v in ecp_v if v in allowed_ecp][:3]
        sev = str(d.get("severity", "Medium")).strip().title()
        if sev not in ("Low", "Medium", "High", "Critical"):
            sev = "Medium"
        mm = bool(d.get("context_mismatch", False))
        if not ms_v and not ecp_v:
            mm = True
        defects.append({
            "name": name,
            "location_hint": str(d.get("location_hint", "")).strip()[:60],
            "severity": sev,
            "ms_violations": ms_v,
            "code_violations": ecp_v,
            "repair_action": str(d.get("repair_action", "")).strip()[:180],
            "context_mismatch": mm,
        })
    return {"defects": defects, "error": None, "raw": (raw or "")[:1500]}


# =====================================================================
# AI — TEXT
# =====================================================================
_DEFECT_TEXT_PROMPT = """You are a senior QC engineer. A site engineer typed
a defect description in the field. Turn it into one structured defect.

MATCHING RULE: same as photo. If nothing in the MS matches, set
ms_violations=[], code_violations=[], context_mismatch=true.
NEVER invent a clause match.

DESCRIPTION: __DESC__

EXTRA NOTE: __NOTE__

ELEMENT: __ELEMENT__

MS CLAUSES AVAILABLE:
__MS_CLAUSES__

ECP CODES AVAILABLE:
__ECP__

Return ONE JSON object:
{
  "defects": [
    {
      "name": "Short clean name",
      "location_hint": "where on site",
      "severity": "Medium",
      "ms_violations": [],
      "code_violations": [],
      "repair_action": "...",
      "context_mismatch": true
    }
  ]
}

Output ONLY JSON."""


async def analyze_defect_text(description, note, ms_clauses, element_type,
                               call_gemini_json_fn):
    if not (description or "").strip():
        return {"defects": [], "error": "Description required."}
    ecp = get_ecp_excerpts(element_type)
    prompt = (_DEFECT_TEXT_PROMPT
              .replace("__DESC__", description.strip())
              .replace("__NOTE__", note or "(none)")
              .replace("__ELEMENT__", (element_type or "column").lower())
              .replace("__MS_CLAUSES__", _format_ms_clauses(ms_clauses))
              .replace("__ECP__", _format_ecp(ecp)))
    try:
        raw = await call_gemini_json_fn(prompt, temperature=0.0, timeout=40)
    except Exception as e:
        return {"defects": [], "error": "AI call failed: " + repr(e)}
    data = _parse_json_object(raw)
    if not data:
        return {"defects": [], "error": "AI returned unparseable output.",
                "raw": (raw or "")[:1500]}
    allowed_ms = {str(c.get("id", "")).strip() for c in (ms_clauses or [])}
    allowed_ecp = {e["code"] for e in ecp}
    defects = []
    for d in data.get("defects", [])[:3]:
        name = str(d.get("name", "")).strip()[:120]
        if not name:
            continue
        ms_v = [str(v).strip() for v in (d.get("ms_violations") or [])]
        ms_v = [v for v in ms_v if v in allowed_ms][:3]
        ecp_v = [str(v).strip() for v in (d.get("code_violations") or [])]
        ecp_v = [v for v in ecp_v if v in allowed_ecp][:3]
        sev = str(d.get("severity", "Medium")).strip().title()
        if sev not in ("Low", "Medium", "High", "Critical"):
            sev = "Medium"
        mm = bool(d.get("context_mismatch", False))
        if not ms_v and not ecp_v:
            mm = True
        defects.append({
            "name": name,
            "location_hint": str(d.get("location_hint", "")).strip()[:60],
            "severity": sev,
            "ms_violations": ms_v,
            "code_violations": ecp_v,
            "repair_action": str(d.get("repair_action", "")).strip()[:180],
            "context_mismatch": mm,
        })
    return {"defects": defects, "error": None, "raw": (raw or "")[:1500]}


# =====================================================================
# QR
# =====================================================================
def _make_qr_buffer(text):
    try:
        from services.pdf_service import generate_qr_code
        return generate_qr_code(text)
    except Exception as e:
        print("[defect] QR fail: " + repr(e))
        return None


# =====================================================================
# TEMPLATE HELPERS
# =====================================================================
def _tpl_bool(cfg, key, default=True):
    if not cfg:
        return default
    try:
        v = cfg.get(key)
        if v is None:
            return default
        return bool(v)
    except Exception:
        return default


# =====================================================================
# NOTICE PDF (with photo strip)
# =====================================================================
def build_notice_pdf(project, defects, notice_uid, subcontractor,
                     deadline_days, raise_type="qc_internal",
                     logo_bytes=None, photos=None, template_config=None):
    """
    template_config: optional dict; currently ignored for notices
    (notices are always full). Accepted for API symmetry.
    """
    _ensure_fonts()
    from reportlab.platypus import (
        SimpleDocTemplate, Spacer, Table, TableStyle,
        Image as ReportLabImage, HRFlowable,
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    include_logo = _tpl_bool(template_config, "include_logo", True)
    include_photos = _tpl_bool(template_config, "include_photos", True)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    NAVY = colors.HexColor("#0a0a0a")
    ACCENT = colors.HexColor("#14b8a6")
    GREY = colors.HexColor("#525252")

    title_style = ParagraphStyle("Title", fontName=_MONO_BOLD,
                                  fontSize=14, textColor=NAVY,
                                  spaceAfter=2, leading=18)
    sub_style = ParagraphStyle("Sub", fontName=_MONO_NAME,
                                fontSize=9, textColor=ACCENT,
                                spaceAfter=6, leading=12)
    label_style = ParagraphStyle("Label", fontName=_MONO_BOLD,
                                  fontSize=8, textColor=NAVY, leading=11)
    meta_style = ParagraphStyle("Meta", fontName=_MONO_NAME, fontSize=8.5,
                                 textColor=GREY, leading=12)
    body_style = ParagraphStyle("Body", fontName=_MONO_NAME, fontSize=8.5,
                                 textColor=colors.black, leading=12)
    mono_head_style = ParagraphStyle("MonoHead", fontName=_MONO_BOLD,
                                      fontSize=9.5, textColor=NAVY,
                                      leading=13, spaceAfter=2)
    mono_cite_style = ParagraphStyle("MonoCite", fontName=_MONO_NAME,
                                      fontSize=8, textColor=GREY, leading=10)
    small_style = ParagraphStyle("Small", fontName=_MONO_NAME, fontSize=7,
                                  textColor=GREY, leading=9)

    story = []

    logo_img = ""
    if logo_bytes and include_logo:
        try:
            logo_img = ReportLabImage(io.BytesIO(logo_bytes),
                                       width=26 * mm, height=13 * mm)
        except Exception:
            logo_img = ""

    header_text = [
        _para("NOTICE TO SUBCONTRACTOR", title_style, bold=True),
        _para("NOTICE NO: " + notice_uid, sub_style),
    ]
    if logo_img:
        t_head = Table([[logo_img, header_text]],
                       colWidths=[32 * mm, 148 * mm])
    else:
        t_head = Table([[header_text]], colWidths=[180 * mm])
    t_head.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_head)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                             spaceAfter=10))

    meta_rows = [
        [_para("PROJECT", label_style, bold=True),
         _para(project.get("name", ""), meta_style),
         _para("DATE", label_style, bold=True),
         _para(datetime.date.today().strftime("%Y-%m-%d"), meta_style)],
        [_para("CONTRACTOR", label_style, bold=True),
         _para(project.get("contractor", ""), meta_style),
         _para("LOCATION", label_style, bold=True),
         _para(project.get("location", ""), meta_style)],
        [_para("CONSULTANT", label_style, bold=True),
         _para(project.get("consultant", ""), meta_style),
         _para("RAISED AS", label_style, bold=True),
         _para("QC Internal" if raise_type == "qc_internal"
               else "Consultant / NCR", meta_style)],
    ]
    t_meta = Table(meta_rows, colWidths=[22 * mm, 68 * mm, 25 * mm, 65 * mm])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 10))

    if photos and include_photos:
        valid = [p for p in photos if p][:4]
        if valid:
            thumbs = []
            for p in valid:
                try:
                    thumbs.append(ReportLabImage(
                        io.BytesIO(_thumb(p)), width=42 * mm, height=42 * mm))
                except Exception:
                    thumbs.append("")
            row = [t for t in thumbs if t]
            if row:
                t_photos = Table([row],
                                  colWidths=[44 * mm] * len(row))
                t_photos.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ]))
                story.append(_para("PHOTOS", label_style, bold=True))
                story.append(t_photos)
                story.append(Spacer(1, 10))

    story.append(_para("TO:", label_style, bold=True))
    story.append(_para(subcontractor, body_style))
    story.append(Spacer(1, 4))
    story.append(_para(
        "DEADLINE: " + str(deadline_days) + " working day" +
        ("s" if deadline_days != 1 else "") + " from receipt.", body_style))
    story.append(Spacer(1, 10))
    story.append(_para(
        "You are required to remedy the following defects. "
        "This notice is a permanent record and must be acknowledged on site.",
        body_style))
    story.append(Spacer(1, 12))

    for idx, d in enumerate(defects, start=1):
        raw_name = d.get("name", "Defect")
        name = _fix(raw_name)
        zone = _fix(d.get("zone", "") or "")
        loc = _fix(d.get("location_hint", "") or "")
        severity = d.get("severity", "Medium")
        ms_v = [_fix(v) for v in (d.get("ms_violations") or [])]
        ecp_v = [_fix(v) for v in (d.get("code_violations") or [])]
        repair = _fix(d.get("repair_action", "") or "")
        mismatch = bool(d.get("context_mismatch", False))

        head = str(idx).zfill(2) + ".  " + name
        if zone or loc:
            head += "   //   " + ", ".join(p for p in [zone, loc] if p)
        story.append(_para(head, mono_head_style, bold=True))

        cit_bits = []
        if ms_v:
            cit_bits.append("MS: " + ", ".join(ms_v))
        if ecp_v:
            cit_bits.append("ECP: " + ", ".join(ecp_v))
        if mismatch and not cit_bits:
            cit_bits.append("MS: (no matching clause in the uploaded MS)")
        if cit_bits:
            story.append(_para("    " + "   |   ".join(cit_bits),
                                mono_cite_style))
        if repair:
            story.append(_para("    REPAIR: " + repair, mono_cite_style))
        story.append(_para("    SEVERITY: " + severity, mono_cite_style))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 18))

    sig_data = [
        [_para("ISSUED BY (QC)", label_style, bold=True),
         _para("ACKNOWLEDGED BY (SUBCONTRACTOR)", label_style, bold=True)],
        [_para("_" * 32, body_style), _para("_" * 32, body_style)],
        [_para(project.get("engineer_name", ""), meta_style),
         _para("Name / Date / Signature", small_style)],
    ]
    t_sig = Table(sig_data, colWidths=[90 * mm, 90 * mm])
    t_sig.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_sig)

    doc.build(story)
    buf.seek(0)
    return buf.read()


# =====================================================================
# REGISTER PDF
# =====================================================================
def build_register_pdf(project, rows, logo_bytes=None, template_config=None):
    _ensure_fonts()
    from reportlab.platypus import (
        SimpleDocTemplate, Spacer, Table, TableStyle, HRFlowable,
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm

    include_logo = _tpl_bool(template_config, "include_logo", True)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
    )
    NAVY = colors.HexColor("#0a0a0a")
    ACCENT = colors.HexColor("#14b8a6")
    GREY = colors.HexColor("#525252")

    title_style = ParagraphStyle("Title", fontName=_MONO_BOLD,
                                  fontSize=13, textColor=NAVY, spaceAfter=2)
    sub_style = ParagraphStyle("Sub", fontName=_MONO_NAME,
                                fontSize=8.5, textColor=ACCENT, spaceAfter=6)
    cell_style = ParagraphStyle("Cell", fontName=_MONO_NAME, fontSize=8,
                                 textColor=GREY, leading=10)
    head_style = ParagraphStyle("Head", fontName=_MONO_BOLD,
                                 fontSize=8, textColor=colors.white, leading=10)
    small_style = ParagraphStyle("Small", fontName=_MONO_NAME, fontSize=7,
                                  textColor=GREY, leading=9)

    story = []
    story.append(_para("DEFECT REGISTER", title_style, bold=True))
    story.append(_para(project.get("name", ""), sub_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                             spaceAfter=10))

    head = ["UID", "DEFECT", "ZONE", "SUBCONTRACTOR",
            "SOURCE", "STATUS", "CREATED"]
    data = [[_para(h, head_style, bold=True) for h in head]]
    for r in rows:
        data.append([
            _para(r.get("uid", ""), cell_style),
            _para(r.get("first_defect", "") or "-", cell_style),
            _para(r.get("zone", ""), cell_style),
            _para(r.get("subcontractor", ""), cell_style),
            _para("CONSULTANT" if r.get("raise_type") == "consultant"
                  else "QC", cell_style),
            _para(str(r.get("status", "")).upper(), cell_style),
            _para(str(r.get("created_at", ""))[:10], cell_style),
        ])

    t = Table(data, colWidths=[36*mm, 60*mm, 15*mm, 45*mm, 26*mm, 24*mm, 24*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
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
    story.append(_para("GENERATED " +
                        datetime.date.today().strftime("%Y-%m-%d") +
                        "  ·  " + str(len(rows)) + " RECORD(S)", small_style))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# =====================================================================
# CLOSURE PDF
# =====================================================================
def build_closure_pdf(project, rows, report_uid=None, logo_bytes=None,
                      template_config=None):
    _ensure_fonts()
    from reportlab.platypus import (
        SimpleDocTemplate, Spacer, Table, TableStyle,
        Image as ReportLabImage, HRFlowable,
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    if report_uid is None:
        report_uid = generate_uid("CLR")

    include_logo = _tpl_bool(template_config, "include_logo", True)
    include_signatures = _tpl_bool(template_config, "include_signatures", True)
    include_summary = _tpl_bool(template_config, "include_summary", True)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    NAVY = colors.HexColor("#0a0a0a")
    ACCENT = colors.HexColor("#14b8a6")
    GREY = colors.HexColor("#525252")
    GREEN = colors.HexColor("#16a34a")
    RED = colors.HexColor("#dc2626")

    title_style = ParagraphStyle("Title", fontName=_MONO_BOLD,
                                  fontSize=14, textColor=NAVY, spaceAfter=2)
    sub_style = ParagraphStyle("Sub", fontName=_MONO_NAME,
                                fontSize=9, textColor=ACCENT, spaceAfter=6)
    label_style = ParagraphStyle("Label", fontName=_MONO_BOLD,
                                  fontSize=8, textColor=NAVY, leading=11)
    meta_style = ParagraphStyle("Meta", fontName=_MONO_NAME, fontSize=8.5,
                                 textColor=GREY, leading=11)
    body_style = ParagraphStyle("Body", fontName=_MONO_NAME, fontSize=8.5,
                                 textColor=colors.black, leading=12)
    mono_head_style = ParagraphStyle("MonoHead", fontName=_MONO_BOLD,
                                      fontSize=9, textColor=NAVY,
                                      spaceAfter=2, leading=11)
    small_style = ParagraphStyle("Small", fontName=_MONO_NAME, fontSize=7,
                                  textColor=GREY, leading=9)

    closed_rows = [r for r in rows if r.get("status") == "closed"]
    open_rows = [r for r in rows if r.get("status") != "closed"]

    story = []
    logo_img = ""
    if logo_bytes and include_logo:
        try:
            logo_img = ReportLabImage(io.BytesIO(logo_bytes),
                                       width=26 * mm, height=13 * mm)
        except Exception:
            logo_img = ""

    header_text = [
        _para("DEFECT CLOSURE REPORT", title_style, bold=True),
        _para("REPORT NO: " + report_uid, sub_style),
    ]
    t_head = Table([[logo_img, header_text]] if logo_img else [[header_text]],
                   colWidths=[32 * mm, 148 * mm] if logo_img else [180 * mm])
    t_head.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_head)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                             spaceAfter=10))

    meta_rows = [
        [_para("PROJECT", label_style, bold=True),
         _para(project.get("name", ""), meta_style),
         _para("DATE", label_style, bold=True),
         _para(datetime.date.today().strftime("%Y-%m-%d"), meta_style)],
        [_para("CONTRACTOR", label_style, bold=True),
         _para(project.get("contractor", ""), meta_style),
         _para("CONSULTANT", label_style, bold=True),
         _para(project.get("consultant", ""), meta_style)],
    ]
    t_meta = Table(meta_rows, colWidths=[22 * mm, 68 * mm, 25 * mm, 65 * mm])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 10))

    if include_summary:
        summary = [
            [_para("TOTAL DEFECTS", label_style, bold=True),
             _para(str(len(rows)), meta_style)],
            [_para("CLOSED", label_style, bold=True),
             _para(str(len(closed_rows)), meta_style)],
            [_para("STILL OPEN", label_style, bold=True),
             _para(str(len(open_rows)), meta_style)],
        ]
        t_sum = Table(summary, colWidths=[50 * mm, 30 * mm])
        t_sum.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F5F5F5")),
            ('BOX', (0, 0), (-1, -1), 0.3, colors.HexColor("#BFBFBF")),
            ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#BFBFBF")),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_sum)
        story.append(Spacer(1, 14))

    for idx, r in enumerate(rows, start=1):
        status = str(r.get("status", "")).upper()
        color = GREEN if status == "CLOSED" else RED
        head = (str(idx).zfill(2) + ".  " + _fix(r.get("uid", "")) +
                "   //   " + _fix(r.get("first_defect", "") or "-") +
                "   ·   ZONE " + _fix(r.get("zone", "")))
        story.append(_para(head, mono_head_style, bold=True))
        st_style = ParagraphStyle("St" + str(idx), parent=meta_style,
                                   textColor=color, fontName=_MONO_BOLD)
        story.append(_para("STATUS: " + status, st_style, bold=True))
        story.append(_para("SOURCE: " +
                            ("CONSULTANT" if r.get("raise_type") == "consultant"
                             else "QC INTERNAL"), meta_style))
        story.append(_para("CREATED: " + str(r.get("created_at", ""))[:19],
                            meta_style))
        if r.get("closed_at"):
            story.append(_para("CLOSED: " + str(r["closed_at"])[:19],
                                meta_style))
        story.append(Spacer(1, 6))

    if include_signatures:
        story.append(Spacer(1, 18))
        sig_data = [
            [_para("QC ENGINEER", label_style, bold=True),
             _para("CONSULTANT", label_style, bold=True)],
            [_para("_" * 32, body_style), _para("_" * 32, body_style)],
            [_para(project.get("engineer_name", ""), meta_style),
             _para("Name / Date / Signature", small_style)],
        ]
        t_sig = Table(sig_data, colWidths=[90 * mm, 90 * mm])
        t_sig.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(t_sig)

    doc.build(story)
    buf.seek(0)
    return buf.read()


# =====================================================================
# PER-SUBCONTRACTOR PERFORMANCE PDF
# =====================================================================
def build_sub_pdf(project, sub_name, score, defects,
                   report_uid=None, logo_bytes=None, template_config=None):
    _ensure_fonts()
    from reportlab.platypus import (
        SimpleDocTemplate, Spacer, Table, TableStyle,
        Image as ReportLabImage, HRFlowable,
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    if report_uid is None:
        report_uid = generate_uid("SUB")

    include_logo = _tpl_bool(template_config, "include_logo", True)
    include_signatures = _tpl_bool(template_config, "include_signatures", True)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    NAVY = colors.HexColor("#0a0a0a")
    ACCENT = colors.HexColor("#14b8a6")
    GREY = colors.HexColor("#525252")
    GREEN = colors.HexColor("#16a34a")
    AMBER = colors.HexColor("#d97706")

    title_style = ParagraphStyle("Title", fontName=_MONO_BOLD,
                                  fontSize=14, textColor=NAVY,
                                  spaceAfter=2, leading=18)
    sub_style = ParagraphStyle("Sub", fontName=_MONO_NAME,
                                fontSize=9, textColor=ACCENT,
                                spaceAfter=6, leading=12)
    label_style = ParagraphStyle("Label", fontName=_MONO_BOLD,
                                  fontSize=8, textColor=NAVY, leading=11)
    meta_style = ParagraphStyle("Meta", fontName=_MONO_NAME, fontSize=8.5,
                                 textColor=GREY, leading=12)
    cell_style = ParagraphStyle("Cell", fontName=_MONO_NAME, fontSize=8,
                                 textColor=colors.black, leading=11)
    head_style = ParagraphStyle("Head", fontName=_MONO_BOLD,
                                 fontSize=8, textColor=colors.white, leading=11)
    small_style = ParagraphStyle("Small", fontName=_MONO_NAME, fontSize=7,
                                  textColor=GREY, leading=9)

    story = []

    logo_img = ""
    if logo_bytes and include_logo:
        try:
            logo_img = ReportLabImage(io.BytesIO(logo_bytes),
                                       width=26 * mm, height=13 * mm)
        except Exception:
            logo_img = ""

    header_text = [
        _para("SUBCONTRACTOR PERFORMANCE", title_style, bold=True),
        _para("REPORT NO: " + report_uid, sub_style),
    ]
    t_head = Table([[logo_img, header_text]] if logo_img else [[header_text]],
                   colWidths=[32 * mm, 148 * mm] if logo_img else [180 * mm])
    t_head.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_head)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.8, color=ACCENT,
                             spaceAfter=10))

    story.append(_para("SUBCONTRACTOR", label_style, bold=True))
    name_style = ParagraphStyle("NameBig", fontName=_MONO_BOLD, fontSize=13,
                                 textColor=NAVY, leading=16)
    story.append(_para(sub_name or "-", name_style, bold=True))
    story.append(Spacer(1, 10))

    meta_rows = [
        [_para("PROJECT", label_style, bold=True),
         _para(project.get("name", ""), meta_style),
         _para("DATE", label_style, bold=True),
         _para(datetime.date.today().strftime("%Y-%m-%d"), meta_style)],
    ]
    t_meta = Table(meta_rows, colWidths=[22 * mm, 68 * mm, 25 * mm, 65 * mm])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 14))

    kpi = [
        [_para("TOTAL", label_style, bold=True),
         _para("OPEN", label_style, bold=True),
         _para("OVERDUE", label_style, bold=True),
         _para("CLOSED", label_style, bold=True)],
        [_para(str(score.get("total", 0)), meta_style),
         _para(str(score.get("open", 0)), meta_style),
         _para(str(score.get("overdue", 0)), meta_style),
         _para(str(score.get("closed", 0)), meta_style)],
    ]
    t_kpi = Table(kpi, colWidths=[45 * mm, 45 * mm, 45 * mm, 45 * mm])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F5F5F5")),
        ('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#BFBFBF")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 16))

    story.append(_para("DEFECTS ISSUED TO THIS SUBCONTRACTOR",
                        label_style, bold=True))
    story.append(Spacer(1, 6))

    head = ["UID", "DEFECT", "ZONE", "STATUS", "CREATED", "CLOSED"]
    data = [[_para(h, head_style, bold=True) for h in head]]
    for r in defects:
        st = str(r.get("status", "")).upper()
        cell = cell_style
        if st == "CLOSED":
            cell = ParagraphStyle("c" + str(r.get("id")), parent=cell_style,
                                   textColor=GREEN)
        elif st == "OPEN":
            cell = ParagraphStyle("c" + str(r.get("id")), parent=cell_style,
                                   textColor=AMBER)
        data.append([
            _para(r.get("uid", ""), cell_style),
            _para((r.get("first_defect") or "-")[:70], cell_style),
            _para(r.get("zone", ""), cell_style),
            _para(st, cell, bold=True),
            _para(str(r.get("created_at", ""))[:10], cell_style),
            _para(str(r.get("closed_at", "") or "-")[:10], cell_style),
        ])

    t = Table(data, colWidths=[34*mm, 60*mm, 14*mm, 22*mm, 25*mm, 25*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F5F5F5")]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#BFBFBF")),
    ]))
    story.append(t)

    story.append(Spacer(1, 12))
    story.append(_para(
        "Generated " + datetime.date.today().strftime("%Y-%m-%d") +
        "  ·  " + str(len(defects)) + " record(s)", small_style))

    if include_signatures:
        story.append(Spacer(1, 24))
        sig_data = [
            [_para("QC ENGINEER", label_style, bold=True),
             _para("PROJECT MANAGER", label_style, bold=True)],
            [_para("_" * 32, meta_style), _para("_" * 32, meta_style)],
            [_para(project.get("engineer_name", ""), meta_style),
             _para("Name / Date / Signature", small_style)],
        ]
        t_sig = Table(sig_data, colWidths=[90 * mm, 90 * mm])
        t_sig.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(t_sig)

    doc.build(story)
    buf.seek(0)
    return buf.read()


# =====================================================================
# EXCEL EXPORT
# =====================================================================
def build_register_xlsx(project, rows, logo_bytes=None):
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    navy = PatternFill("solid", fgColor="0A0A0A")
    white_bold = Font(bold=True, color="FFFFFF", size=10, name="Consolas")
    body_font = Font(size=10, name="Consolas")
    header_align = Alignment(vertical="center", horizontal="left",
                              wrap_text=True)
    body_align = Alignment(vertical="top", horizontal="left", wrap_text=True)

    ws1 = wb.active
    ws1.title = "Notices"
    headers1 = ["UID", "Date", "Zone", "Subcontractor", "Source",
                "Status", "Defects", "First defect"]
    ws1.append(headers1)
    for i in range(1, len(headers1) + 1):
        c = ws1.cell(row=1, column=i)
        c.fill = navy
        c.font = white_bold
        c.alignment = header_align

    for r in rows:
        ws1.append([
            str(r.get("uid", "") or ""),
            str(r.get("created_at", "") or "")[:19],
            str(r.get("zone", "") or ""),
            str(r.get("subcontractor", "") or ""),
            "Consultant / NCR" if r.get("raise_type") == "consultant"
            else "QC Internal",
            str(r.get("status", "") or "").upper(),
            int(r.get("count", 0) or 0),
            str(r.get("first_defect", "") or ""),
        ])

    for i, w in enumerate([22, 20, 8, 30, 18, 12, 9, 50], 1):
        ws1.column_dimensions[get_column_letter(i)].width = w
    ws1.freeze_panes = "A2"
    for row in ws1.iter_rows(min_row=2):
        for c in row:
            c.font = body_font
            c.alignment = body_align

    ws2 = wb.create_sheet("Defects")
    headers2 = ["UID", "Date", "Zone", "Subcontractor", "Status",
                "#", "Defect name", "Location", "Severity",
                "MS clauses", "ECP codes", "Repair action"]
    ws2.append(headers2)
    for i in range(1, len(headers2) + 1):
        c = ws2.cell(row=1, column=i)
        c.fill = navy
        c.font = white_bold
        c.alignment = header_align

    for r in rows:
        sel = r.get("selected") or []
        if not sel:
            continue
        for j, s in enumerate(sel, 1):
            ws2.append([
                str(r.get("uid", "") or ""),
                str(r.get("created_at", "") or "")[:19],
                str(r.get("zone", "") or ""),
                str(r.get("subcontractor", "") or ""),
                str(r.get("status", "") or "").upper(),
                j,
                str(s.get("name", "") or ""),
                str(s.get("location_hint", "") or ""),
                str(s.get("severity", "") or ""),
                ", ".join(s.get("ms_violations") or []),
                ", ".join(s.get("code_violations") or []),
                str(s.get("repair_action", "") or ""),
            ])

    for i, w in enumerate([22, 20, 8, 30, 12, 6, 40, 25, 10, 25, 25, 45], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = "A2"
    for row in ws2.iter_rows(min_row=2):
        for c in row:
            c.font = body_font
            c.alignment = body_align

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.read()
# =====================================================================
# EAGER FONT INIT — makes the "fonts ready" line appear in the deploy
# log so we can confirm what Render actually has at boot.
# =====================================================================
try:
    _ensure_fonts()
except Exception as _e:
    print("[defect] eager font init failed: " + repr(_e))
