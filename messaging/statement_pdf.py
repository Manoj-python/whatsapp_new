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
    """
    Generate statement PDF with Borrower Details, Loan Terms, and Repayment Schedule.
    All inputs are dicts from your extract functions.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, textColor=NAVY, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, textColor=NAVY, spaceBefore=10, spaceAfter=4)
    small = ParagraphStyle("small", parent=normal, fontSize=8, textColor=GREY)
    value_style = ParagraphStyle("value", parent=normal, fontSize=10, textColor=colors.black)

    story = []

    # ----- Header -----
    company = app_name or getattr(settings, 'LEGAL_NAME', 'SM SQUARE CREDIT SERVICES')
    story.append(Paragraph(company, h1))
    story.append(Paragraph(getattr(settings, 'COMPANY_ADDRESS', ''), small))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "STATEMENT OF ACCOUNT",
        ParagraphStyle(
            "title",
            parent=styles["Heading1"],
            fontSize=13,
            textColor=colors.white,
            backColor=NAVY,
            alignment=1,
            spaceAfter=0,
            borderPadding=6
        )
    ))
    story.append(Spacer(1, 4))
    generated = datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S")
    loan_no = _safe_str(loan.get('agreement_no'))
    story.append(Paragraph(
        f"Loan Number: <b>{loan_no}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Generated On: {generated} IST",
        small
    ))
    story.append(Spacer(1, 10))

    # ----- Borrower Details (two columns) -----
    story.append(Paragraph("Borrower Details", h2))
    cust_name = _safe_str(customer.get('customer_name', '')).title()
    father = _safe_str(customer.get('father_name', '')).title()
    mobile = _safe_str(customer.get('contact', ''))
    email = _safe_str(customer.get('email', '')).lower()
    address = _safe_str(customer.get('full_address', ''))
    branch = _safe_str(lcc.get('branch', '')) if lcc else ''
    region = _safe_str(lcc.get('region', '')) if lcc else ''
    vehicle_no = _safe_str(lcc.get('registration_no', '')) if lcc else ''
    vehicle_class = _safe_str(lcc.get('vehicle_class', '')) if lcc else ''

    borrower_rows = [
        [Paragraph("<b>Name</b>", normal), Paragraph(cust_name, value_style),
         Paragraph("<b>Loan No.</b>", normal), Paragraph(loan_no, value_style)],
        [Paragraph("<b>Father's / Spouse</b>", normal), Paragraph(father, value_style),
         Paragraph("<b>Loan Date</b>", normal), Paragraph(_dmy(loan.get('start_date')), value_style)],
        [Paragraph("<b>Mobile No.</b>", normal), Paragraph(mobile, value_style),
         Paragraph("<b>Loan Amount</b>", normal), Paragraph(f"₹{_money(loan.get('loan_amount', 0))}", value_style)],
        [Paragraph("<b>Email ID</b>", normal), Paragraph(email, value_style),
         Paragraph("<b>Loan Status</b>", normal), Paragraph(_safe_str(loan.get('disbursement_status', '')), value_style)],
        [Paragraph("<b>Address</b>", normal), Paragraph(address, value_style),
         Paragraph("<b>Branch (Region)</b>", normal), Paragraph(f"{branch} ({region})" if region else branch, value_style)],
        [Paragraph("<b>Vehicle</b>", normal), Paragraph(f"{vehicle_no} ({vehicle_class})" if vehicle_class else vehicle_no, value_style),
         Paragraph("", normal), Paragraph("", value_style)],
    ]
    b_table = Table(borrower_rows, colWidths=[35 * mm, 55 * mm, 35 * mm, 55 * mm])
    b_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(b_table)
    story.append(Spacer(1, 8))

    # ----- Loan Terms & Due Details (two columns) -----
    story.append(Paragraph("Loan Terms &amp; Due Details", h2))
    overdue = float(loan.get('overdue_amount', 0))
    lpi = float(loan.get('lpi_dues', 0))
    vas = float(loan.get('total_vas_dues', 0))
    total_dues = overdue + lpi + vas  # Correct total

    terms_rows = [
        [Paragraph("<b>ROI (%) | APR (%)</b>", normal),
         Paragraph(f"{loan.get('yearly_indicative_roi', 0):.2f} | {loan.get('effective_apr', 0):.2f}", value_style),
         Paragraph("<b>Installments Paid | Total</b>", normal),
         Paragraph(f"{int(loan.get('no_of_paid_emi', 0))} | {int(loan.get('duration', 0))}", value_style)],
        [Paragraph("<b>Installment Amount</b>", normal),
         Paragraph(f"₹{_money(loan.get('regular_emi_amount', 0))}", value_style),
         Paragraph("<b>Overdue Installments</b>", normal),
         Paragraph(f"{loan.get('emi_due_count', 0):.2f}", value_style)],
        [Paragraph("<b>Tenure (months)</b>", normal),
         Paragraph(str(int(loan.get('duration', 0))), value_style),
         Paragraph("<b>EMI Due</b>", normal),
         Paragraph(f"₹{_money(overdue)}", value_style)],
        [Paragraph("<b>Installment Start | End Date</b>", normal),
         Paragraph(f"{_dmy(loan.get('emi_start_date'))} | {_dmy(loan.get('emi_end_date'))}", value_style),
         Paragraph("<b>Total Dues</b>", normal),
         Paragraph(f"₹{_money(total_dues)}", value_style)],
        [Paragraph("<b>Frequency | Last Paid Date</b>", normal),
         Paragraph(f"{loan.get('installment_type_id', '-')} | {_dmy(loan.get('last_paid_date'))}", value_style),
         Paragraph("<b>Charges Dues | LPC Dues</b>", normal),
         Paragraph(f"₹{_money(vas)} | ₹{_money(lpi)}", value_style)],
        [Paragraph("<b>Repayment Mode</b>", normal),
         Paragraph(_safe_str(loan.get('mode_of_repayment_id', '')), value_style),
         Paragraph("<b>Next Due Date</b>", normal),
         Paragraph(_dmy(loan.get('next_due_date')), value_style)],
    ]
    t = Table(terms_rows, colWidths=[35 * mm, 55 * mm, 35 * mm, 55 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # ----- Repayment Schedule -----
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
    st = Table(
        sched_rows,
        colWidths=[10 * mm, 20 * mm, 22 * mm, 24 * mm, 30 * mm, 18 * mm, 18 * mm, 18 * mm],
        repeatRows=1
    )
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    style.add("LINEABOVE", (0, -1), (-1, -1), 1, NAVY)
    st.setStyle(style)
    story.append(st)
    story.append(Paragraph(
        f"Showing 1 to {len(loan.get('repayment_schedules', []))} entries",
        small
    ))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"For further clarifications please contact us on {getattr(settings, 'HELPLINE_NUMBER', '1800-xxx-xxx')}",
        small,
    ))

    doc.build(story)
    return buf.getvalue()
