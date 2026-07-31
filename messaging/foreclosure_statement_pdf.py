import datetime as dt
import re
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.pdfencrypt import StandardEncryption

from django.conf import settings

# ============================================================
# CONSTANTS
# ============================================================
IST = timezone(timedelta(hours=5, minutes=30))
NAVY = colors.HexColor("#12355b")
TEAL = colors.HexColor("#0e9494")
LIGHT = colors.HexColor("#e0f4f4")
GREY = colors.HexColor("#64748b")

LOGO_PATH = Path(settings.BASE_DIR) / "static" / "img" / "logo.jpeg" if hasattr(settings, 'BASE_DIR') else None

FORECLOSURE_CHARGE_PCT = 0.04      # 4%
VALIDITY_DAYS = 7                  # 7 days
DAYS_PER_MONTH = 365 / 12          # 30.4167

# ============================================================
# DATE / NUMBER HELPERS
# ============================================================
def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    head = str(value).strip().split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(head, fmt)
        except ValueError:
            continue
    return None

def _dmy(value: str) -> str:
    if not value:
        return "-"
    head = str(value).strip().split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(head, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return str(value)

def _money(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"

# ============================================================
# PDF SECURITY (DOB password)
# ============================================================
_DOB_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y")

def dob_password(dob: str) -> Optional[str]:
    if not dob:
        return None
    head = re.split(r"[T ]", dob.strip(), maxsplit=1)[0]
    for fmt in _DOB_FORMATS:
        try:
            parsed = dt.datetime.strptime(head, fmt).date()
        except ValueError:
            continue
        return parsed.strftime("%d%m%Y")
    return None

def encryption_for(dob: str) -> Optional[StandardEncryption]:
    password = dob_password(dob)
    if not password:
        return None
    return StandardEncryption(
        userPassword=password,
        ownerPassword=password,
        canPrint=1,
        canModify=0,
        canCopy=0,
        canAnnotate=0,
    )

# ============================================================
# QR CODE GENERATION (optional)
# ============================================================
def qr_png(url: str) -> bytes:
    import qrcode
    img = qrcode.make(url, border=1)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def verify_url(doc_type: str, agreement_no: str, amount: float, doc_date: str) -> str:
    from itsdangerous import URLSafeSerializer
    from urllib.parse import urljoin
    serializer = URLSafeSerializer(settings.SECRET_KEY, salt="portal-doc-verify")
    payload = {
        "doc": doc_type,
        "agr": agreement_no,
        "amt": round(float(amount), 2),
        "date": doc_date,
        "gen": datetime.now(IST).strftime("%Y-%m-%d %H:%M"),
    }
    token = serializer.dumps(payload)
    base = getattr(settings, 'PORTAL_BASE_URL', '').rstrip("/") + "/"
    return urljoin(base, f"verify/{token}")

# ============================================================
# 1. CORRECTED FORECLOSURE CALCULATION
# ============================================================
def compute_foreclosure(loan_dict, lcc_dict, as_of=None):
    """
    Returns the foreclosure break-up with correct LPI:
    LPI = AllCloud's loan LPIDues (if available) + 7‑day interest on overdue principal.
    Falls back to LCC's LPCDue only if loan LPIDues is missing.
    """
    import logging
    logger = logging.getLogger(__name__)

    now = datetime.now(IST).replace(tzinfo=None)
    as_of = as_of or (now + timedelta(days=VALIDITY_DAYS))

    # ------------------------------------------------------------------
    # 1.  LATE PAYMENT INTEREST (LPI) – CORRECTED LOGIC
    # ------------------------------------------------------------------
    # 1a. Current LPI – prefer loan's LPIDues, fallback to LCC's LPCDue
    loan_lpi = loan_dict.get('lpi_dues', 0.0)
    lcc_lpi = lcc_dict.get('lpc_due', 0.0)
    current_lpi = loan_lpi if loan_lpi > 0 else lcc_lpi

    logger.info(f"DEBUG: loan_lpi={loan_lpi}, lcc_lpi={lcc_lpi} -> current_lpi={current_lpi}")

    # 1b. Overdue principal – use TotalPrincipalDue if available
    overdue_principal = loan_dict.get('total_principal_due', 0.0)
    logger.info(f"DEBUG: total_principal_due from loan = {overdue_principal}")

    # 1c. If missing, compute from schedule with PRORATION
    if overdue_principal == 0.0:
        schedules = loan_dict.get('repayment_schedules', [])
        for e in schedules:
            due = _parse_date(e.get('due_date'))
            if due and due <= now and e.get('pending_amount', 0) > 0:
                due_amt = e.get('due_amount', 0)
                pending = e.get('pending_amount', 0)
                principal = e.get('principal', 0)
                if due_amt > 0 and pending > 0:
                    overdue_principal += principal * (pending / due_amt)
                else:
                    overdue_principal += principal
        logger.info(f"DEBUG: prorated overdue_principal from schedule = {overdue_principal}")

    lpc_rate = loan_dict.get('lpc_interest_pct', 0.0) / 100.0
    validity_days = (as_of - now).days
    projected_interest = overdue_principal * lpc_rate * (validity_days / DAYS_PER_MONTH)

    total_lpi = current_lpi + projected_interest
    total_lpi = round(total_lpi)

    logger.info(f"DEBUG: projected_interest = {projected_interest}, total_lpi = {total_lpi}")

    # ------------------------------------------------------------------
    # 2.  THE REST OF THE FORECLOSURE BREAK‑UP (unchanged)
    # ------------------------------------------------------------------
    schedules = loan_dict.get('repayment_schedules', [])
    schedule_entries = [e for e in schedules if _parse_date(e.get('due_date'))]
    schedule_entries.sort(key=lambda e: _parse_date(e['due_date']))

    cutoff = None
    next_installment = None
    for e in schedule_entries:
        due = _parse_date(e['due_date'])
        if due <= as_of:
            cutoff = e
        elif next_installment is None:
            next_installment = e
            break

    future_principal = cutoff['principal_os'] if cutoff else (schedule_entries[0]['principal_os'] if schedule_entries else 0.0)

    broken_interest = 0.0
    broken_days = 0
    period_days = 0
    if cutoff and next_installment:
        last_due = _parse_date(cutoff['due_date'])
        next_due = _parse_date(next_installment['due_date'])
        period_days = (next_due - last_due).days
        broken_days = max(0, (as_of - last_due).days)
        if period_days > 0:
            broken_interest = next_installment['interest'] * (broken_days / period_days)

    foreclosure_charges = round(future_principal * FORECLOSURE_CHARGE_PCT)

    emi_due = sum(
        e['pending_amount'] for e in schedule_entries
        if _parse_date(e['due_date']) <= as_of and e.get('pending_amount', 0) > 0
    )

    handloan = lcc_dict.get('hand_loan_due_amount', 0.0) or 0.0

    vas_list = loan_dict.get('vas_list', [])
    insurance_due = sum(
        max(v['amount'] - v.get('received_amount', 0), 0.0)
        for v in vas_list
        if "insurance" in (v.get('vas_type_id') or v.get('name') or "").lower()
    )
    total_vas_dues = loan_dict.get('total_vas_dues', 0.0)
    vas_charge = max(total_vas_dues - insurance_due, 0.0)

    # ------------------------------------------------------------------
    # 3.  BUILD THE RETURN DICT
    # ------------------------------------------------------------------
    items = {
        "foreclosure_charges": foreclosure_charges,
        "emi_due": emi_due,
        "future_principal": future_principal,
        "broken_interest": broken_interest,
        "lpi": total_lpi,
        "handloan": handloan,
        "handloan_lpi": 0.0,    
        "vas_charge": vas_charge,
        "vas_collect_later": 0.0,
        "insurance": insurance_due,
    }
    items["total_receivables"] = round(sum(items.values()), 2)

    items["_as_of"] = as_of
    items["_last_due_date"] = cutoff['due_date'] if cutoff else ""
    items["_next_due_date"] = next_installment['due_date'] if next_installment else ""
    items["_broken_days"] = broken_days
    items["_period_days"] = period_days

    return items


# ============================================================
# 2. FORECLOSURE PDF BUILDER
# ============================================================
def build_foreclosure_statement_pdf(
    customer_name: str,
    customer_contact: str,
    customer_dob: str,
    loan_dict: dict,
    lcc_dict: dict,
) -> bytes:
    """
    Generates the foreclosure PDF with the corrected LPI.
    """
    calc = compute_foreclosure(loan_dict, lcc_dict)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=15*mm,
        bottomMargin=15*mm,
        leftMargin=15*mm,
        rightMargin=15*mm,
        encrypt=encryption_for(customer_dob),
    )
    styles = getSampleStyleSheet()
    value_style = ParagraphStyle("value", parent=styles["Normal"], fontSize=10, textColor=colors.black)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, textColor=NAVY, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, textColor=NAVY, spaceBefore=10, spaceAfter=4)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=GREY)

    def kv(label: str, value: str) -> str:
        return f"<font color='#64748b' size=8>{label}</font><br/><font size=10>{value or '-'}</font>"

    story = []

    # ----- Letterhead -----
    legal_name = getattr(settings, 'LEGAL_NAME', 'SM SQUARE CREDIT SERVICES')
    company_address = getattr(settings, 'COMPANY_ADDRESS', '')
    letterhead_text = [Paragraph(legal_name, h1), Paragraph(company_address, small)]
    if LOGO_PATH and LOGO_PATH.exists():
        logo = Image(str(LOGO_PATH), width=16*mm, height=16*mm)
        letterhead = Table([[logo, letterhead_text]], colWidths=[18*mm, 152*mm])
        letterhead.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ]))
        story.append(letterhead)
    else:
        story.extend(letterhead_text)
    story.append(Spacer(1, 6))
    story.append(Paragraph("FORECLOSURE STATEMENT", ParagraphStyle(
        "title", parent=styles["Heading1"], fontSize=13, textColor=colors.white,
        backColor=NAVY, alignment=1, spaceAfter=0, borderPadding=6,
    )))
    story.append(Spacer(1, 4))

    # ----- Generation + Validity -----
    now_ist = datetime.now(IST)
    generated = now_ist.strftime("%d-%m-%Y %H:%M")
    as_of_str = calc["_as_of"].strftime("%d-%m-%Y")
    story.append(Paragraph(
        f"Loan Number: <b>{loan_dict.get('agreement_no', '')}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Valid Until: <b>{as_of_str}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Generated On: {generated} IST",
        small,
    ))
    story.append(Paragraph(
        f"<b>This foreclosure statement is valid for {VALIDITY_DAYS} days from generation "
        f"— i.e. until {as_of_str}.</b> The figures below already include the interest that will "
        f"accrue over this window, so the total is payable any day up to and including {as_of_str}. "
        f"If not settled within this period, a fresh statement must be requested.",
        ParagraphStyle("validity", parent=small, textColor=colors.HexColor("#b45309")),
    ))
    story.append(Spacer(1, 10))

    # ----- Borrower Details -----
    story.append(Paragraph("Borrower Details", h2))
    branch_region = ((lcc_dict.get('branch') or "") or "-") + (f" ({lcc_dict.get('region')})" if lcc_dict.get('region') else "")
    vehicle = ((lcc_dict.get('registration_no') or "") or "-") + (f" ({lcc_dict.get('vehicle_class')})" if lcc_dict.get('vehicle_class') else "")
    borrower_rows = [
        [Paragraph(kv("Name", customer_name.title()), value_style),
         Paragraph(kv("Loan No.", loan_dict.get('agreement_no', '')), value_style)],
        [Paragraph(kv("Mobile No.", customer_contact), value_style),
         Paragraph(kv("Loan Amount", f"Rs. {_money(loan_dict.get('loan_amount', 0))}"), value_style)],
        [Paragraph(kv("Branch (Region)", branch_region), value_style),
         Paragraph(kv("Vehicle", vehicle), value_style)],
    ]
    t = Table(borrower_rows, colWidths=[90*mm, 90*mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(t)

    # ----- Foreclosure Break-up -----
    story.append(Paragraph("Foreclosure Break-up", h2))
    rows = [
        ["Fore-Closure Charges", _money(calc["foreclosure_charges"])],
        ["EMI Due", _money(calc["emi_due"])],
        ["Future Principal", _money(calc["future_principal"])],
        ["Broken Period Interest", _money(calc["broken_interest"])],
        ["LPI", _money(calc["lpi"])],
        ["Handloan", _money(calc["handloan"])],
        ["Handloan LPI", _money(calc["handloan_lpi"])],
        ["VAS Charge", _money(calc["vas_charge"])],
        ["VAS Collect Later", _money(calc["vas_collect_later"])],
        ["Insurance", _money(calc["insurance"])],
    ]
    bt = Table([["Particulars", "Amount (Rs.)"]] + rows, colWidths=[120*mm, 60*mm])
    style = _table_style()
    bt.setStyle(style)
    story.append(bt)
    story.append(Spacer(1, 2))

    total_row = Table([["Total Receivables", f"Rs. {_money(calc['total_receivables'])}"]], colWidths=[120*mm, 60*mm])
    total_row.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), TEAL),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.white),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(total_row)

    # ----- Notes -----
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Broken Period Interest is calculated from the last due date "
        f"({_dmy(calc['_last_due_date'])}) to the payoff date above "
        f"({calc['_broken_days']} of {calc['_period_days']} days in the current "
        f"installment period), prorated on the next installment's interest amount. "
        f"Fore-Closure Charges are {FORECLOSURE_CHARGE_PCT*100:.0f}% of Future Principal, "
        f"rounded to the nearest rupee.",
        small,
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"For further clarifications please contact us on {getattr(settings, 'HELPLINE_NUMBER', '1800-xxx-xxx')} or "
        f"{getattr(settings, 'GRIEVANCE_EMAIL', '')}. Please quote your Loan Number when you contact us.",
        small,
    ))

    # ----- Verification QR (optional) -----
    try:
        from urllib.parse import urljoin
        url = verify_url("foreclosure", loan_dict.get('agreement_no', ''), calc["total_receivables"], as_of_str)
        qr_img = Image(BytesIO(qr_png(url)), width=20*mm, height=20*mm)
        qr_row = Table(
            [[qr_img, Paragraph(
                "Scan to verify this foreclosure statement was genuinely issued by "
                f"{legal_name} — confirms Loan No., Total Receivables, and validity date.",
                small,
            )]],
            colWidths=[24*mm, 146*mm],
        )
        qr_row.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 0),
        ]))
        story.append(Spacer(1, 8))
        story.append(qr_row)
    except Exception:
        # QR generation fails silently
        pass

    doc.build(story)
    return buf.getvalue()

def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ])
