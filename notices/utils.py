import pandas as pd
from docxtpl import DocxTemplate
from docx2pdf import convert
import os
from datetime import datetime



# -----------------------------
# SAFE HELPERS (ADD THIS)
# -----------------------------
def safe(value, default=""):
    if pd.isna(value):
        return default
    return value


def safe_number(value, default=0):
    if pd.isna(value):
        return default
    try:
        return int(float(value))
    except:
        return default

# -----------------------------
# Date formatter
# -----------------------------
def format_date(value):
    if pd.isna(value):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    return str(value)

def format_mobile(value):
    if pd.isna(value):
        return ""
    return str(value).split(".")[0]

def format_indian_number(value):
    # Handle NaN / empty values
    if pd.isna(value):
        return ""

    try:
        value = int(float(value))
    except (ValueError, TypeError):
        return ""

    s = str(value)

    if len(s) <= 3:
        return s

    last3 = s[-3:]
    rest = s[:-3]

    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]

    if rest:
        parts.insert(0, rest)

    return ",".join(parts) + "," + last3
# Address formatter
# -----------------------------
def format_address(address, max_lines=3, max_chars_per_line=40):

    if not isinstance(address, str):
        return address

    words = address.replace(",", "").split()

    lines = []
    current_line = ""

    for word in words:

        if len(current_line) + len(word) + 1 <= max_chars_per_line:
            current_line += (" " if current_line else "") + word
        else:
            lines.append(current_line)
            current_line = word

        if len(lines) == max_lines:
            break

    if len(lines) < max_lines and current_line:
        lines.append(current_line)

    return "\n".join(lines)


# -----------------------------
# Number to words
# -----------------------------
ONES = (
    "", "One", "Two", "Three", "Four", "Five",
    "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen",
    "Fifteen", "Sixteen", "Seventeen", "Eighteen",
    "Nineteen"
)

TENS = (
    "", "", "Twenty", "Thirty", "Forty",
    "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"
)

def number_to_words_indian(num):

    num = safe_number(num, 0)

    if num == 0:
        return "Zero Rupees Only"

    def two_digits(n):
        if n < 20:
            return ONES[n]
        return TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")

    words = []

    crore = num // 10000000
    num %= 10000000
    if crore:
        words.append(two_digits(crore) + " Crore")

    lakh = num // 100000
    num %= 100000
    if lakh:
        words.append(two_digits(lakh) + " Lakh")

    thousand = num // 1000
    num %= 1000
    if thousand:
        words.append(two_digits(thousand) + " Thousand")

    hundred = num // 100
    num %= 100
    if hundred:
        words.append(ONES[hundred] + " Hundred")

    if num:
        words.append(two_digits(num))

    return " ".join(words) + " Rupees Only"


# -----------------------------
# Borrower Notice
# -----------------------------
def generate_borrower_pdf(excel_path, borrower_tpl, output_dir):

    df = pd.read_excel(excel_path)

    docx_dir = os.path.join(output_dir, "generate_borrower_docx")
    pdf_dir = os.path.join(output_dir, "generate_borrower_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for _, row in df.iterrows():

        dues_amount = safe_number(row["dues"])

        context = {
            "code": row.get("code", ""),
            "company_name": row.get("company_name", ""),
            "notice_date": format_date(row["notice_date"]),

            "borrower_name": row["borrower_name"],
            "borrower_father": row["borrower_father"],
            "borrower_address": format_address(row["borrower_address"]),
            "borrower_mobile": format_mobile(row["borrower_mobile"]),

            "loan_account": row["loan_account"],
            "vehicle_no": row["vehicle_no"],

            "dues": format_indian_number(dues_amount),
            "dues_2": number_to_words_indian(dues_amount),
        }

        loan_no = str(row["loan_account"]).strip()

        doc = DocxTemplate(borrower_tpl)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{loan_no}_borrower.docx")
        pdf_path = os.path.join(pdf_dir, f"{loan_no}_borrower.pdf")

        doc.save(docx_path)
        
    convert(docx_path, pdf_path, keep_active=True)
    

# -----------------------------
# Guarantor Notice
# -----------------------------
def generate_guarantor_pdf(excel_path, guarantor_tpl, output_dir):

    import pandas as pd
    import os
    from docxtpl import DocxTemplate
    from docx2pdf import convert

    df = pd.read_excel(excel_path)

    docx_dir = os.path.join(output_dir, "generate_guarantor_docx")
    pdf_dir = os.path.join(output_dir, "generate_guarantor_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for row in df.itertuples(index=False):

        dues_amount = safe_number(getattr(row, "dues", 0))

        context = {
            "code": getattr(row, "code", ""),
            "company_name": getattr(row, "company_name", ""),
            "notice_date": format_date(getattr(row, "notice_date", "")),

            "borrower_name": getattr(row, "borrower_name", ""),

            "guarantor_name": getattr(row, "guarantor_name", ""),
            "guarantor_address": format_address(getattr(row, "guarantor_address", "")),
            "guarantor_mobile": format_mobile(getattr(row, "guarantor_mobile", "")),

            "loan_account": getattr(row, "loan_account", ""),
            "vehicle_no": getattr(row, "vehicle_no", ""),

            "dues": format_indian_number(dues_amount),
            "dues_2": number_to_words_indian(dues_amount),
        }

        loan_no = str(getattr(row, "loan_account", "")).strip()

        doc = DocxTemplate(guarantor_tpl)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{loan_no}_guarantor.docx")
        pdf_path = os.path.join(pdf_dir, f"{loan_no}_guarantor.pdf")

        doc.save(docx_path)
    
    convert(docx_path, pdf_path, keep_active=True)


# -----------------------------
# Co-Borrower Notice
# -----------------------------
def generate_co_borrower_pdf(excel_path, template_path, output_dir):

    df = pd.read_excel(excel_path)

    # ✅ Proper subfolders (same pattern as others)
    docx_dir = os.path.join(output_dir, "generate_co_borrower_docx")
    pdf_dir = os.path.join(output_dir, "generate_co_borrower_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for _, row in df.iterrows():

        dues_amount = safe_number(row.dues)

        context = {
            "code": row.get("code", ""),
            "company_name": row.get("company_name", ""),
            "notice_date": format_date(row["notice_date"]),

            "borrower_name": row["borrower_name"],

            "co_borrower_name": row["co_borrower_name"],
            "co_borrower_father": row["co_borrower_father"],
            "co_borrower_address": format_address(row["co_borrower_address"]),
            "co_borrower_mobile": format_mobile(row["co_borrower_mobile"]),

            "loan_account": row["loan_account"],
            "vehicle_no": row["vehicle_no"],

            "dues": format_indian_number(dues_amount),
            "dues_2": number_to_words_indian(dues_amount),
        }

        loan_no = str(row["loan_account"]).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        # ✅ Save inside structured folders
        docx_path = os.path.join(docx_dir, f"{loan_no}_co_borrower.docx")
        pdf_path = os.path.join(pdf_dir, f"{loan_no}_co_borrower.pdf")

        doc.save(docx_path)
    
    convert(docx_path, pdf_path, keep_active=True)
        

import pandas as pd
from docxtpl import DocxTemplate
from docx2pdf import convert
import os



# -----------------------------
# Lok Adalat Generator
# -----------------------------
def generate_lokadalat_pdf(excel_path, template_path, output_dir):

    df = pd.read_excel(excel_path)

    docx_dir = os.path.join(output_dir, "generate_lokadalat_docx")
    pdf_dir = os.path.join(output_dir, "generate_lokadalat_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for row in df.itertuples(index=False):

        context = {
            "company_name": safe(row.company_name),
            "loan_number": safe(row.loan_number),
            "customer_name": safe(row.customer_name),
            "address": format_address(safe(row.address)),
            "phone_numbers": safe(row.phone_numbers),
            "amount": format_indian_number(safe(row.amount)),
            "upto_date": format_date(safe(row.upto_date)),
            "lok_date": format_date(safe(row.lok_date)),
            "day2": safe(row.day2),
            "month": safe(row.month),
        }

        loan_no = str(row.loan_number).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{loan_no}_lokadalat.docx")

        doc.save(docx_path)
    
    convert(docx_dir, pdf_dir)
    


# -----------------------------
# Loan APP Generator
# -----------------------------
def generate_loan_app_pdf(excel_path, template_path, output_dir):

    df = pd.read_excel(excel_path)

    docx_dir = os.path.join(output_dir, "generate_loan_app_docx")
    pdf_dir = os.path.join(output_dir, "generate_loan_app_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for row in df.itertuples(index=False):

        context = {
            "company_name": safe(row.company_name),
            "name": safe(row.name),
            "postal_address": format_address(safe(row.postal_address)),
            "loan_number": safe(row.loan_number),
            "amount": format_indian_number(safe(row.amount)),
            "date": format_date(safe(row.date)),
        }

        loan_no = str(row.loan_number).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{loan_no}_loan_app.docx")

        doc.save(docx_path)
    
    convert(docx_dir, pdf_dir)
    


# -----------------------------
# Ledger Generator
# -----------------------------
def generate_ledger_pdf(excel_path, template_path, output_dir):

    df = pd.read_excel(excel_path)

    docx_dir = os.path.join(output_dir, "generate_ledger_docx")
    pdf_dir = os.path.join(output_dir, "generate_ledger_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for row in df.itertuples(index=False):

        context = {
            "month": safe(row.month),
            "day2": safe(row.day2),
            "company_name": safe(row.company_name),
            "emp_id": safe(row.emp_id),
            "name": safe(row.name),
            "address": format_address(safe(row.address)),
            "phone_number": safe(row.phone_number),
            "amount": format_indian_number(safe(row.amount)),
            "up_to_date": format_date(safe(row.up_to_date)),
            "lok_date": format_date(safe(row.lok_date)),
        }

        emp_id = str(row.emp_id).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{emp_id}_ledger.docx")

        doc.save(docx_path)
    
    convert(docx_dir, pdf_dir)
    


# -----------------------------
# Ledger APP Generator
# -----------------------------
def generate_ledger_app_pdf(excel_path, template_path, output_dir):

    df = pd.read_excel(excel_path)

    docx_dir = os.path.join(output_dir, "generate_ledger_app_docx")
    pdf_dir = os.path.join(output_dir, "generate_ledger_app_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for row in df.itertuples(index=False):

        context = {
            "company_name": safe(row.company_name),
            "name": safe(row.name),
            "postal_address": format_address(safe(row.postal_address)),
            "emp_id": safe(row.emp_id),
            "amount": format_indian_number(safe(row.amount)),
            "date": format_date(safe(row.date)),
        }

        emp_id = str(row.emp_id).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{emp_id}_ledger_app.docx")

        doc.save(docx_path)

    convert(docx_dir, pdf_dir)
    



def generate_loss_notice_pdf(excel_path, template_path, output_dir):

    df = pd.read_excel(excel_path)

    docx_dir = os.path.join(output_dir, "loss_notice_docx")
    pdf_dir = os.path.join(output_dir, "loss_notice_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for row in df.itertuples(index=False):

        context = {

            "date": format_date(row.date),

            "name": safe(row.name),
            "address": format_address(safe(row.address)),
            "number": safe(row.number),

            "vehicle_no": safe(row.vehicle_no),

            "company": safe(row.company),
            "class_name": safe(row.class_name),
            "year": safe(row.year),
        

            "sale_price": format_indian_number(row.sale_price),

            "rep_fee": format_indian_number(row.rep_fee),
            "yard_fee": format_indian_number(row.yard_fee),
            "auction_fee": format_indian_number(row.auction_fee),
            "repair_cost": format_indian_number(row.repair_cost),
            "others": format_indian_number(row.others),

            "total_deductions": format_indian_number(row.total_deductions),
            "remaing_blc": format_indian_number(row.remaing_blc),

            "final_amount": format_indian_number(row.final_amount),

            "loan_no": safe(row.loan_no)
        }

        loan_no = str(row.loan_no).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{loan_no}_loss_notice.docx")
        pdf_path = os.path.join(pdf_dir, f"{loan_no}_loss_notice.pdf")

        doc.save(docx_path)

    convert(docx_dir, pdf_dir)
    
