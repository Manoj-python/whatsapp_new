import pandas as pd
from docxtpl import DocxTemplate
import subprocess
import os
from datetime import datetime

# -----------------------------
# SAFE HELPERS
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


def force_address_breaks(address, max_chars=35):
    """
    Force line breaks into long addresses without spaces
    """
    if pd.isna(address) or not isinstance(address, str):
        return ""

    address = str(address).strip()

    # Remove H.No prefix
    address = address.replace("HNO:-", "").replace("H.No:-", "").replace("HNO:", "")

    # Insert spaces where missing (capital letters often indicate new words)
    import re
    address = re.sub(r'([a-z])([A-Z])', r'\1 \2', address)

    # Split long string into chunks
    chunks = []
    current_chunk = ""

    for char in address:
        current_chunk += char
        if len(current_chunk) >= max_chars and char in [' ', ',', '.']:
            chunks.append(current_chunk.strip())
            current_chunk = ""

    if current_chunk:
        chunks.append(current_chunk.strip())

    return "\n".join(chunks[:3])  # Max 3 lines



# Add this at the very end of utils.py
def remove_blank_last_page(pdf_path):
    """Remove blank last page from PDF"""
    try:
        from PyPDF2 import PdfReader, PdfWriter

        reader = PdfReader(pdf_path)
        if len(reader.pages) > 1:
            # Keep only first page
            writer = PdfWriter()
            writer.add_page(reader.pages[0])
            with open(pdf_path, 'wb') as f:
                writer.write(f)
            print(f"Removed extra page from {pdf_path}")
            return True
    except Exception as e:
        print(f"Could not remove page: {e}")
    return False

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
# PDF CONVERSION FOR LINUX (LibreOffice)
# -----------------------------
def convert_docx_to_pdf(docx_path, pdf_path):
    """
    Stable DOCX -> PDF conversion for EC2/Linux using LibreOffice.
    Fixes:
    - font rendering inconsistencies
    - broken pagination
    - alignment shifts
    - profile lock issues
    - first run wizard problems
    """

    import os
    import subprocess
    import tempfile
    import shutil

    temp_home = None

    try:
        # Ensure output folder exists
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

        # Create isolated LibreOffice user profile
        temp_home = tempfile.mkdtemp(prefix="libreoffice_profile_")

        env = os.environ.copy()
        env["HOME"] = temp_home
        env["LANG"] = "en_US.UTF-8"
        env["LC_ALL"] = "en_US.UTF-8"

        soffice_cmd = "/usr/local/bin/soffice"

        result = subprocess.run(
            [
                soffice_cmd,
                "--headless",
                "--nologo",
                "--nodefault",
                "--nofirststartwizard",
                "--nolockcheck",
                "--invisible",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                os.path.dirname(pdf_path),
                docx_path,
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )

        print("LibreOffice STDOUT:")
        print(result.stdout)

        print("LibreOffice STDERR:")
        print(result.stderr)

        if result.returncode != 0:
            print(f"LibreOffice conversion failed: {result.returncode}")
            return False

        generated_pdf = os.path.join(
            os.path.dirname(pdf_path),
            os.path.basename(docx_path).replace(".docx", ".pdf")
        )

        if not os.path.exists(generated_pdf):
            print("Generated PDF not found.")
            return False

        # Rename if required
        if generated_pdf != pdf_path:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            os.rename(generated_pdf, pdf_path)

        print(f"PDF created successfully: {pdf_path}")
        return True

    except subprocess.TimeoutExpired:
        print(f"LibreOffice conversion timeout: {docx_path}")
        return False

    except Exception as e:
        print(f"PDF conversion error: {e}")
        return False

    finally:
        if temp_home and os.path.exists(temp_home):
            shutil.rmtree(temp_home, ignore_errors=True)

# -----------------------------
# Borrower Notice
# -----------------------------
def generate_borrower_pdf(excel_path, borrower_tpl, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "generate_borrower_docx")
    pdf_dir = os.path.join(output_dir, "generate_borrower_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        dues_amount = safe_number(row["dues"])

        context = {
            "code": row.get("code", ""),
            "company_name": row.get("company_name", ""),
            "notice_date": format_date(row["notice_date"]),
            "borrower_name": row["borrower_name"],
            "borrower_father": row["borrower_father"],
            "borrower_mobile": format_mobile(row["borrower_mobile"]),
            "borrower_address": force_address_breaks(row.get("borrower_address", "")),
            "pincode":(safe(row.get("pincode"))),
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
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        # Update progress
        if progress_callback:
            progress_callback(idx, total_rows)

# -----------------------------
# Guarantor Notice
# -----------------------------
def generate_guarantor_pdf(excel_path, guarantor_tpl, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "generate_guarantor_docx")
    pdf_dir = os.path.join(output_dir, "generate_guarantor_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, row in enumerate(df.itertuples(index=False), 1):
        dues_amount = safe_number(getattr(row, "dues", 0))

        context = {
            "code": getattr(row, "code", ""),
            "company_name": getattr(row, "company_name", ""),
            "notice_date": format_date(getattr(row, "notice_date", "")),
            "borrower_name": getattr(row, "borrower_name", ""),
            "guarantor_name": getattr(row, "guarantor_name", ""),
            "guarantor_address": force_address_breaks(getattr(row, "guarantor_address", "")),
            "pincode": getattr(row, "pincode", ""),
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
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# -----------------------------
# Co-Borrower Notice
# -----------------------------
def generate_co_borrower_pdf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "generate_co_borrower_docx")
    pdf_dir = os.path.join(output_dir, "generate_co_borrower_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        dues_amount = safe_number(row.dues)

        context = {
            "code": row.get("code", ""),
            "company_name": row.get("company_name", ""),
            "notice_date": format_date(row["notice_date"]),
            "borrower_name": row["borrower_name"],
            "co_borrower_name": row["co_borrower_name"],
            "co_borrower_father": row["co_borrower_father"],
            "co_borrower_address": force_address_breaks(row["co_borrower_address"]),
            "pincode": (safe(row.get("pincode"))),
            "co_borrower_mobile": format_mobile(row["co_borrower_mobile"]),
            "loan_account": row["loan_account"],
            "vehicle_no": row["vehicle_no"],
            "dues": format_indian_number(dues_amount),
            "dues_2": number_to_words_indian(dues_amount),
        }

        loan_no = str(row["loan_account"]).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{loan_no}_co_borrower.docx")
        pdf_path = os.path.join(pdf_dir, f"{loan_no}_co_borrower.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# -----------------------------
# Lok Adalat Generator
# -----------------------------
def generate_lokadalat_pdf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "generate_lokadalat_docx")
    pdf_dir = os.path.join(output_dir, "generate_lokadalat_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, row in enumerate(df.itertuples(index=False), 1):
        context = {
            "company_name": safe(row.company_name),
            "loan_number": safe(row.loan_number),
            "customer_name": safe(row.customer_name),
            "address": force_address_breaks(safe(row.address)),
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
        pdf_path = os.path.join(pdf_dir, f"{loan_no}_lokadalat.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# -----------------------------
# Loan APP Generator
# -----------------------------
def generate_loan_app_pdf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "generate_loan_app_docx")
    pdf_dir = os.path.join(output_dir, "generate_loan_app_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, row in enumerate(df.itertuples(index=False), 1):
        context = {
            "company_name": safe(row.company_name),
            "name": safe(row.name),
            "postal_address": force_address_breaks(safe(row.postal_address)),
            "loan_number": safe(row.loan_number),
            "amount": format_indian_number(safe(row.amount)),
            "date": format_date(safe(row.date)),
        }

        loan_no = str(row.loan_number).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{loan_no}_loan_app.docx")
        pdf_path = os.path.join(pdf_dir, f"{loan_no}_loan_app.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# -----------------------------
# Ledger Generator
# -----------------------------
def generate_ledger_pdf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "generate_ledger_docx")
    pdf_dir = os.path.join(output_dir, "generate_ledger_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, row in enumerate(df.itertuples(index=False), 1):
        context = {
            "month": safe(row.month),
            "day2": safe(row.day2),
            "company_name": safe(row.company_name),
            "emp_id": safe(row.emp_id),
            "name": safe(row.name),
            "address": force_address_breaks(safe(row.address)),
            "phone_number": safe(row.phone_number),
            "amount": format_indian_number(safe(row.amount)),
            "up_to_date": format_date(safe(row.up_to_date)),
            "lok_date": format_date(safe(row.lok_date)),
        }

        emp_id = str(row.emp_id).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{emp_id}_ledger.docx")
        pdf_path = os.path.join(pdf_dir, f"{emp_id}_ledger.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# -----------------------------
# Ledger APP Generator
# -----------------------------
def generate_ledger_app_pdf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "generate_ledger_app_docx")
    pdf_dir = os.path.join(output_dir, "generate_ledger_app_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, row in enumerate(df.itertuples(index=False), 1):
        context = {
            "company_name": safe(row.company_name),
            "name": safe(row.name),
            "postal_address": force_address_breaks(safe(row.postal_address)),
            "emp_id": safe(row.emp_id),
            "amount": format_indian_number(safe(row.amount)),
            "date": format_date(safe(row.date)),
        }

        emp_id = str(row.emp_id).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{emp_id}_ledger_app.docx")
        pdf_path = os.path.join(pdf_dir, f"{emp_id}_ledger_app.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# -----------------------------
# Letter Head Registration Borrower
# -----------------------------
def generate_Letter_Head_Registration_borrower(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "borrower_docx")
    pdf_dir = os.path.join(output_dir, "borrower_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "date": format_date(row.get("date")),
            "name": safe(row.get("name")),
            "address": force_address_breaks(row.get("address")),
            "pincode":(safe(row.get("pincode"))),
            "mobile": format_mobile(row.get("mobile")),
            "loan_number": safe(row.get("loan_number")),
            "vehicle_no": safe(row.get("vehicle_no")),
        }

        file_name = str(row.get("loan_number", "file"))

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# -----------------------------
# Letter Head Registration Guarantor
# -----------------------------
def generate_Letter_Head_Registration_guarantor(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "guarantor_docx")
    pdf_dir = os.path.join(output_dir, "guarantor_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "date": format_date(row.get("date")),
            "name": safe(row.get("name")),
            "address": force_address_breaks(row.get("address")),
            "pincode":(safe(row.get("pincode"))),
            "mobile": format_mobile(row.get("mobile")),
            "loan_number": safe(row.get("loan_number")),
            "vehicle_no": safe(row.get("vehicle_no")),
        }

        file_name = str(row.get("loan_number", "file"))

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# =========================================================
# DEMAND NOTICE PSF
# =========================================================
def generate_demand_notice_psf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "demand_notice_psf_docx")
    pdf_dir = os.path.join(output_dir, "demand_notice_psf_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        dues_amount = safe_number(row.get("dues"))

        context = {
            "notice_date": format_date(row.get("notice_date")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_father": safe(row.get("borrower_father")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "pincode":(safe(row.get("pincode"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "dues": format_indian_number(dues_amount),
            "dues_2": number_to_words_indian(dues_amount),
        }

        file_name = str(row.get("loan_account", "psf_demand")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_psf_demand.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_psf_demand.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# =========================================================
# DEMAND NOTICE SMS
# =========================================================
def generate_demand_notice_sms(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "demand_notice_sms_docx")
    pdf_dir = os.path.join(output_dir, "demand_notice_sms_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        dues_amount = safe_number(row.get("dues"))

        context = {
            "notice_date": format_date(row.get("notice_date")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_father": safe(row.get("borrower_father")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "pincode":(safe(row.get("pincode"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "dues": format_indian_number(dues_amount),
            "dues_2": number_to_words_indian(dues_amount),
        }

        file_name = str(row.get("loan_account", "sms_demand")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_sms_demand.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_sms_demand.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# =========================================================
# DUE NOTICE PSF
# =========================================================
def generate_due_notice_psf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "due_notice_psf_docx")
    pdf_dir = os.path.join(output_dir, "due_notice_psf_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "dues": format_indian_number(row.get("dues")),
            "vas": format_indian_number(row.get("vas")),
        }

        file_name = str(row.get("loan_account", "psf_due")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_psf_due.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_psf_due.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# =========================================================
# DUE NOTICE SMS
# =========================================================
def generate_due_notice_sms(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "due_notice_sms_docx")
    pdf_dir = os.path.join(output_dir, "due_notice_sms_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "date_due": format_date(row.get("date_due")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "pincode":(safe(row.get("pincode"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "dues": format_indian_number(row.get("dues")),
            "vas": format_indian_number(row.get("vas")),
            "over_dues": format_indian_number(row.get("over_dues")),
            "amount": format_indian_number(row.get("amount")),
        }

        file_name = str(row.get("loan_account", "sms_due")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_sms_due.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_sms_due.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# =========================================================
# DUE NOTICE SMF
# =========================================================
def generate_due_notice_smf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "due_notice_smf_docx")
    pdf_dir = os.path.join(output_dir, "due_notice_smf_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "pincode":(safe(row.get("pincode"))),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "dues": format_indian_number(row.get("dues")),
            "vas": format_indian_number(row.get("vas")),
        }

        file_name = str(row.get("loan_account", "smf_due")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_smf_due.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_smf_due.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# =========================================================
# PRE SALE PSF
# =========================================================
def generate_pre_sale_psf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "pre_sale_psf_docx")
    pdf_dir = os.path.join(output_dir, "pre_sale_psf_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "pincode":(safe(row.get("pincode"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
        }

        file_name = str(row.get("loan_account", "psf_pre_sale")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_psf_pre_sale.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_psf_pre_sale.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# =========================================================
# PRE SALE SMS
# =========================================================
def generate_pre_sale_sms(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "pre_sale_sms_docx")
    pdf_dir = os.path.join(output_dir, "pre_sale_sms_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "pincode":(safe(row.get("pincode"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
        }

        file_name = str(row.get("loan_account", "sms_pre_sale")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_sms_pre_sale.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_sms_pre_sale.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# =========================================================
# PRE SALE SMF
# =========================================================
def generate_pre_sale_smf(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "pre_sale_smf_docx")
    pdf_dir = os.path.join(output_dir, "pre_sale_smf_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_due": format_date(row.get("notice_due")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "pincode":(safe(row.get("pincode"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
        }

        file_name = str(row.get("loan_account", "smf_pre_sale")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_smf_pre_sale.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_smf_pre_sale.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

# # =========================================================
# # POLICE INTIMATION PSF
# # =========================================================
# def generate_police_intimation_psf(excel_path, template_path, output_dir, progress_callback=None):
#     df = pd.read_excel(excel_path)
#     total_rows = len(df)

#     docx_dir = os.path.join(output_dir, "police_psf_docx")
#     pdf_dir = os.path.join(output_dir, "police_psf_pdf")

#     os.makedirs(docx_dir, exist_ok=True)
#     os.makedirs(pdf_dir, exist_ok=True)

#     for idx, (_, row) in enumerate(df.iterrows(), 1):
#         context = {
#             "notice_date": format_date(row.get("notice_date")),
#             "place": safe(row.get("place")),
#             "vehicle_no": safe(row.get("vehicle_no")),
#             "model": safe(row.get("model")),
#             "engine_number": safe(row.get("engine_number")),
#             "chassis_number": safe(row.get("chassis_number")),
#             "borrower_name": safe(row.get("borrower_name")),
#             "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
#             "amount": format_indian_number(row.get("amount")),
#         }

#         file_name = str(row.get("vehicle_no", "psf_police")).strip()

#         doc = DocxTemplate(template_path)
#         doc.render(context)

#         docx_path = os.path.join(docx_dir, f"{file_name}_psf_police.docx")
#         pdf_path = os.path.join(pdf_dir, f"{file_name}_psf_police.pdf")

#         doc.save(docx_path)
#         convert_docx_to_pdf(docx_path, pdf_path)
#         remove_blank_last_page(pdf_path)

#         if progress_callback:
#             progress_callback(idx, total_rows)

# # =========================================================
# # POLICE INTIMATION SMS
# # =========================================================
# def generate_police_intimation_sms(excel_path, template_path, output_dir, progress_callback=None):
#     df = pd.read_excel(excel_path)
#     total_rows = len(df)

#     docx_dir = os.path.join(output_dir, "police_sms_docx")
#     pdf_dir = os.path.join(output_dir, "police_sms_pdf")

#     os.makedirs(docx_dir, exist_ok=True)
#     os.makedirs(pdf_dir, exist_ok=True)

#     for idx, (_, row) in enumerate(df.iterrows(), 1):
#         context = {
#             "notice_date": format_date(row.get("notice_date")),
#             "place": safe(row.get("place")),
#             "vehicle_no": safe(row.get("vehicle_no")),
#             "model": safe(row.get("model")),
#             "engine_number": safe(row.get("engine_number")),
#             "chassis_number": safe(row.get("chassis_number")),
#             "borrower_name": safe(row.get("borrower_name")),
#             "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
#             "amount": format_indian_number(row.get("amount")),
#         }

#         file_name = str(row.get("vehicle_no", "sms_police")).strip()

#         doc = DocxTemplate(template_path)
#         doc.render(context)

#         docx_path = os.path.join(docx_dir, f"{file_name}_sms_police.docx")
#         pdf_path = os.path.join(pdf_dir, f"{file_name}_sms_police.pdf")

#         doc.save(docx_path)
#         convert_docx_to_pdf(docx_path, pdf_path)
#         remove_blank_last_page(pdf_path)

#         if progress_callback:
#             progress_callback(idx, total_rows)



def generate_open_repo_letter(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "open_repo_docx")
    pdf_dir = os.path.join(output_dir, "open_repo_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "model": safe(row.get("model")),
            "make": safe(row.get("make")),
            "engine_no": safe(row.get("engine_no")),
            "chassis_no": safe(row.get("chassis_no")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "date": format_date(row.get("date")),
            "loan_account": safe(row.get("loan_account")),

        }

        file_name = str(row.get("vehicle_no", "open_repo")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_open_repo.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_open_repo.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)





# =========================================================
# DUE NOTICE PSF
# =========================================================
def generate_due_notice_psf_guarantor(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "due_notice_guarantor_psf_docx")
    pdf_dir = os.path.join(output_dir, "due_notice_guarantor_psf_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "guarantor_name": safe(row.get("guarantor_name")),
            "guarantor_father": safe(row.get("guarantor_father")),
            "guarantor_address": force_address_breaks(safe(row.get("guarantor_address"))),
            "guarantor_mobile": format_mobile(row.get("guarantor_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "dues": format_indian_number(row.get("dues")),
            "vas": format_indian_number(row.get("vas")),
            "amount": format_indian_number(row.get("amount")),
            "date_due": format_date(row.get("date_due")),
            "borrower_name": safe(row.get("borrower_name")),
        }

        file_name = str(row.get("loan_account", "psf_due")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_psf_guarantor_due.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_psf_guarantor_due.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)







# =========================================================
# DUE NOTICE SMS
# =========================================================
def generate_due_notice_sms_guarantor(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "due_notice_guarantor_sms_docx")
    pdf_dir = os.path.join(output_dir, "due_notice_guarantor_sms_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "date_due": format_date(row.get("date_due")),
            "guarantor_name": safe(row.get("guarantor_name")),
            "guarantor_father": safe(row.get("guarantor_father")),
            "borrower_name": safe(row.get("borrower_name")),
            "guarantor_address": force_address_breaks(safe(row.get("guarantor_address"))),
            "guarantor_mobile": format_mobile(row.get("guarantor_mobile")),
            "loan_account": safe(row.get("loan_account")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "dues": format_indian_number(row.get("dues")),
            "vas": format_indian_number(row.get("vas")),
            "over_dues": format_indian_number(row.get("over_dues")),
            "amount": format_indian_number(row.get("amount")),
        }

        file_name = str(row.get("loan_account", "sms_due")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_sms_guarantor_due.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_sms_guarantor_due.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)





def generate_post_sale_notices(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "post_sale_docx")
    pdf_dir = os.path.join(output_dir, "post_sale_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "vehicle_name": safe(row.get("vehicle_name")),
            "pincode":(safe(row.get("pincode"))),
            "borrower_father":safe(row.get("borrower_father")),
            "borrower_name": safe(row.get("borrower_name")),
            "borrower_address": force_address_breaks(safe(row.get("borrower_address"))),
            "borrower_mobile": format_mobile(row.get("borrower_mobile")),
            "dues": format_indian_number(row.get("dues")),

        }

        file_name = str(row.get("vehicle_no", "post_sale")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_post_sale.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_post_sale.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)









def generate_post_sale_guarantor(excel_path, template_path, output_dir, progress_callback=None):
    df = pd.read_excel(excel_path)
    total_rows = len(df)

    docx_dir = os.path.join(output_dir, "post_sale_guarantor_docx")
    pdf_dir = os.path.join(output_dir, "post_sale_guarantor_pdf")

    os.makedirs(docx_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        context = {
            "notice_date": format_date(row.get("notice_date")),
            "guarantor_name": safe(row.get("guarantor_name")),
            "guarantor_father": safe(row.get("guarantor_father")),
            "borrower_name": safe(row.get("borrower_name")),
            "guarantor_address": force_address_breaks(safe(row.get("guarantor_address"))),
            "mobile": format_mobile(row.get("mobile")),
            "vehicle_no": safe(row.get("vehicle_no")),
            "pincode":(safe(row.get("pincode"))),
            "dues": format_indian_number(row.get("dues")),
            "vehicle_name": safe(row.get("vehicle_name")),
        }

        file_name = str(row.get("vehicle_no", "post_sale_guarantor")).strip()

        doc = DocxTemplate(template_path)
        doc.render(context)

        docx_path = os.path.join(docx_dir, f"{file_name}_post_sale_guarantor.docx")
        pdf_path = os.path.join(pdf_dir, f"{file_name}_post_sale_guarantor.pdf")

        doc.save(docx_path)
        convert_docx_to_pdf(docx_path, pdf_path)
        remove_blank_last_page(pdf_path)

        if progress_callback:
            progress_callback(idx, total_rows)

