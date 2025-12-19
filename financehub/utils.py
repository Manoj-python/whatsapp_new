

import pandas as pd
import unicodedata
import re
from django.apps import apps

# Chunk settings
PANDAS_CHUNK_SIZE = 5000
BULK_BATCH_SIZE = 2000


# -------------------------------------------------------
# SMART HEADER MAP (FULL INCLUDING DIALER FIXES)
# -------------------------------------------------------
SMART_HEADER_MAP = {
    # Collection Allocation
    "loannumber": "loan_number",
    "executivename": "executive_name",
    "employeeid": "employee_id",

    # LCC
    "customermobile": "cust_mobile",
    "guarantormobile": "guarantor_mobile",
    "vehiclenumber": "vehicle_no",
    "vehicle_no": "vehicle_no",
    "loan_no": "loan_number",

    # Repo
    "agreementno": "agreement_number",
    "agreementnumber": "agreement_number",
    "regno": "registration_number",
    "registrationno": "registration_number",

    # Due Notice
    "vehicleno": "vehicle_no",
    "barno": "bar_number",

    # General
    "mobileno": "mobile_number",
    "phonenumber": "phone_number",
    "executive": "executive_name",

    # -------------------------------------------------------
    # D I A L E R   F I X E S
    # -------------------------------------------------------
    "callnumber": "call_number",
    "servicename": "service_name",
    "agentname": "agent_name",
    "customername": "customer_name",
    "vehicleclass": "vehicle_class",
    "installmentduedate": "installment_due_date",
    "totaldues": "total_dues",
    "lpcdues": "lpc_dues",
    "runningemicount": "running_emi_count",
    "lastreceiveddate": "last_received_date",
    "guarrantorname": "guarrantor_name",
    "guarrantorcontact": "guarrantor_contact",
    "currentmonthtbc": "current_month_tbc",
    "vasdueamount": "vas_due_amount",
    "handloandueamount": "handloan_due_amount",
    "emiduecount": "emi_due_count",
    "call_start_time": "call_start_time",
    "call_end_time": "call_end_time",
    "ptp_date": "ptp_date",


    # ---- Collection Allocation FIXES ----
    "manageremployeeid": "manager_employee_id",
    "manager_employee": "manager_employee_id",
    "manager_employ": "manager_employee_id",
    "manager employee id": "manager_employee_id",

    "tlemployeeid": "tl_employee_id",
    "tl_employee": "tl_employee_id",
    "tl employee id": "tl_employee_id",
    "tl_employee_i": "tl_employee_id",
}


# -------------------------------------------------------
# HEADER CLEANER
# -------------------------------------------------------
def clean_header(header: str):
    if not header:
        return ""

    h = str(header).strip()

    # Remove invisible characters
    INVISIBLE = ["\u200b", "\u200c", "\u200d", "\ufeff", "\t", "\n", "\r"]
    for ch in INVISIBLE:
        h = h.replace(ch, "")

    # Replace delimiters
    h = re.sub(r"[-./]", " ", h)

    # CamelCase → snake_case
    h = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", h)
    h = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", h)

    # Spaces → underscore
    h = h.replace(" ", "_")

    # Lowercase
    h = h.lower()

    # Smart map
    return SMART_HEADER_MAP.get(h, h)


# -------------------------------------------------------
# VALUE CLEANER FOR EVERY CELL
# -------------------------------------------------------
def clean_value(v):
    if not v:
        return ""
    v = str(v)
    v = unicodedata.normalize("NFKD", v)

    # Remove invisible chars
    INVISIBLE = ["\u200b", "\u200c", "\u200d", "\ufeff", "\t", "\n", "\r"]
    for ch in INVISIBLE:
        v = v.replace(ch, "")

    # Normalize hyphens
    HYPHENS = ["‐", "‒", "–", "—", "―"]
    for h in HYPHENS:
        v = v.replace(h, "-")

    return v.strip()


def normalize_row_values(row_dict):
    return {k: clean_value(v) for k, v in row_dict.items()}


# -------------------------------------------------------
# DATE NORMALIZER
# -------------------------------------------------------
def normalize_date(value):
    if value is None:
        return ""
    v = str(value).strip()
    if v in ["", "nan", "NaT", "None"]:
        return ""
    try:
        dt = pd.to_datetime(v, errors="coerce")
        if pd.isna(dt):
            return ""
        return dt.strftime("%Y-%m-%d")
    except:
        return ""


# -------------------------------------------------------
# MODEL RESOLVER
# -------------------------------------------------------
def get_model_by_type(file_type: str):
    mapping = {
        "lcc": "Lcc",
        "collection_allocations": "CollectionAllocations",
        "clu": "Clu",
        "repo": "Repo",
        "paid": "Paid",
        "closed": "Closed",
        "dialer": "Dialer",
        "duenotice": "DueNotice",
        "visiter": "Visiter",
        "employee_master": "EmployeeMaster",
        "freshdesk": "Freshdesk",
    }

    model_name = mapping.get(file_type.lower())
    if not model_name:
        return None

    return apps.get_model("financehub", model_name)


# -------------------------------------------------------
# UNIQUE FIELD DETECTOR (Option A → NO UNIQUE FOR DIALER)
# -------------------------------------------------------
def get_unique_field(model):
    """
    Returns natural unique field for duplicate prevention.
    BUT:
    - Dialer has no unique key → allow ALL rows
    """
    if model.__name__.lower() == "dialer":
        return None

    priority = [
        "loan_number",
        "agreement_number",
        "employee_number",
        "ticket_id",
        "registration_number",
    ]

    fields = {f.name for f in model._meta.fields}

    for p in priority:
        if p in fields:
            return p

    return None
