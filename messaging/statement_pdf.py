import io
from datetime import datetime, timedelta, timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from django.conf import settings

IST = timezone(timedelta(hours=5, minutes=30))
NAVY = colors.HexColor("#12355b")
LIGHT = colors.HexColor("#e0f4f4")
GREY = colors.HexColor("#64748b")

def _safe_str(value):
    return '' if value is None else str(value)

def _dmy(value):
    if not value:
        return "-"
    head = str(value).strip().split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(head, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return str(value)

def _money(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"

def _paid_amount(value):
    if not value:
        return 0.0
    total = 0.0
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            total += float(part)
        except ValueError:
            continue
    return total

def _last_date(value):
    if not value:
        return "-"
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    return _dmy(parts[-1]) if parts else "-"

def build_statement_pdf(customer, loan, lcc=None, app_name=None) -> bytes:
    """PDF with Borrower Details, Loan Details, Repayment Schedule."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        topMargin=15*mm, bottomMargin=15*mm,
        leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, textColor=NAVY, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, textColor=NAVY, spaceBefore=10, spaceAfter=4)
    small = ParagraphStyle("small", parent=normal, fontSize=8, textColor=GREY)
    value_style = ParagraphStyle("value", parent=normal, fontSize=10, textColor=colors.black)

    story = []

    # Header
    company = app_name or settings.LEGAL_NAME or "SM SQUARE CREDIT SERVICES"
    story.append(Paragraph(company, h1))
    story.append(Paragraph(settings.COMPANY_ADDRESS or "", small))
    story.append(Spacer(1, 6))
    story.append(Paragraph("STATEMENT OF ACCOUNT", ParagraphStyle(
        "title", parent=styles["Heading1"], fontSize=13, textColor=colors.white,
        backColor=NAVY, alignment=1, spaceAfter=0, borderPadding=6)))
    story.append(Spacer(1, 4))
    generated = datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S")
    loan_no = _safe_str(loan.get('agreement_no'))
    story.append(Paragraph(
        f"Loan Number: <b>{loan_no}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Generated On: {generated} IST",
        small))
    story.append(Spacer(1, 10))

    # Borrower Details
    story.append(Paragraph("Borrower Details", h2))
    borrower_fields = [
        ("Customer name", _safe_str(customer.get('customer_name', '')).title()),
        ("Mobile No.", _safe_str(customer.get('contact', ''))),
        ("Address", _safe_str(customer.get('full_address', ''))),
        ("Branch", _safe_str(lcc.get('branch', '')) if lcc else ''),
        ("Region", _safe_str(lcc.get('region', '')) if lcc else ''),
        ("Vehicle No.", _safe_str(lcc.get('registration_no', '')) if lcc else ''),
        ("Vehicle Class", _safe_str(lcc.get('vehicle_class', '')) if lcc else ''),
    ]
    b_table = Table(
        [[Paragraph(f"<b>{label}</b>", normal), Paragraph(value, value_style)]
         for label, value in borrower_fields],
        colWidths=[60*mm, 90*mm])
    b_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (0,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(b_table)
    story.append(Spacer(1, 8))

    # Loan Details
    story.append(Paragraph("Loan Details", h2))
    total_due = float(loan.get('total_due', 0))  # already computed via get_payment_details

    loan_fields = [
        ("Loan type", _safe_str(loan.get('product_type', '')).replace("Loan", "Loan")),
        ("Loan amount", f"₹{_money(loan.get('loan_amount', 0))}"),
        ("Total EMIs", str(int(loan.get('duration', 0)))),
        ("Next due", _dmy(loan.get('next_due_date', ''))),
        ("EMIs received", f"{_money(loan.get('no_of_paid_emi', 0))}"),
        ("EMIs due", f"{_money(loan.get('emi_due_count', 0))}"),
        ("EMI", f"₹{_money(loan.get('regular_emi_amount', 0))}"),
        ("Total due", f"₹{_money(total_due)}"),
    ]
    l_table = Table(
        [[Paragraph(f"<b>{label}</b>", normal), Paragraph(value, value_style)]
         for label, value in loan_fields],
        colWidths=[60*mm, 90*mm])
    l_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 2),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (0,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(l_table)
    story.append(Spacer(1, 12))

    # Repayment Schedule (kept as before)
    story.append(Paragraph("Repayment Schedule", h2))
    sched_rows = [["#", "EMI", "Date", "EMI Received", "Last Receipt Date", "LPI", "Discount", "LPI Due"]]
    total_emi = total_received = total_lpi = total_lpi_due = 0.0
    for e in loan.get('repayment_schedules', []):
        received = _paid_amount(e.get('paid_amount', ''))
        sched_rows.append([
            str(e.get('installment_no', '')),
            _money(e.get('due_amount', 0)),
            _dmy(e.get('due_date', '')),
            _money(received) if received else "-",
            _last_date(e.get('payment_date', '')),
            _money(e.get('lpc_received', 0)) if e.get('lpc_received') else "-",
            "0.00",
            _money(e.get('lpc', 0))
        ])
        total_emi += float(e.get('due_amount', 0))
        total_received += received
        total_lpi += float(e.get('lpc_received', 0))
        total_lpi_due += float(e.get('lpc', 0))
    sched_rows.append([
        "", _money(total_emi), "", _money(total_received), "",
        _money(total_lpi), "0.00", _money(total_lpi_due),
    ])
    st = Table(sched_rows, colWidths=[10*mm, 20*mm, 22*mm, 24*mm, 30*mm, 18*mm, 18*mm, 18*mm], repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ])
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    style.add("LINEABOVE", (0, -1), (-1, -1), 1, NAVY)
    st.setStyle(style)
    story.append(st)
    story.append(Paragraph(f"Showing 1 to {len(loan.get('repayment_schedules', []))} entries", small))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"For further clarifications please contact us on {settings.HELPLINE_NUMBER or '1800-xxx-xxx'}",
        small,
    ))

    doc.build(story)
    return buf.getvalue()
