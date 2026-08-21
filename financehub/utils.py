# financehub/utils.py

import pandas as pd
import unicodedata
import re
from django.apps import apps

# Chunk settings
PANDAS_CHUNK_SIZE = 5000
BULK_BATCH_SIZE = 2000

# ============================================================
# SMART HEADER MAPPING - COMPLETE VERSION
# ============================================================
SMART_HEADER_MAP = {

    # -------------------------------------------------------
    # Collection Allocation
    # -------------------------------------------------------
    "loannumber": "loan_number",
    "loan_number": "loan_number",
    "executivename": "executive_name",
    "executive_name": "executive_name",
    "employeeid": "employee_id",
    "employee_id": "employee_id",
    "manageremployeeid": "manager_employee_id",
    "manager_employee": "manager_employee_id",
    "manager_employ": "manager_employee_id",
    "manager_employee_id": "manager_employee_id",
    "tlemployeeid": "tl_employee_id",
    "tl_employee": "tl_employee_id",
    "tl_employee_id": "tl_employee_id",
    "tl_employee_i": "tl_employee_id",

    # -------------------------------------------------------
    # LCC - Uses customer_name
    # -------------------------------------------------------
    "customer_name": "customer_name",
    "customername": "customer_name",
    "customermobile": "cust_mobile",
    "customer_mobile": "cust_mobile",
    "guarantormobile": "guarantor_mobile",
    "guarantor_mobile": "guarantor_mobile",
    "vehiclenumber": "vehicle_no",
    "vehicle_no": "vehicle_no",
    "loan_no": "loan_number",
    "loannumber": "loan_number",
    "coborrower_name":"coborrower_name",
    "coborrower_mobile":"coborrower_mobile",

    # -------------------------------------------------------
    # ESEBUZZ - Uses customer_name (with underscores)
    # -------------------------------------------------------
    "loanno": "loan_no",
    "loan_no": "loan_no",
    "loantype": "loan_type",
    "loan_type": "loan_type",
    "umrnno": "umrn_no",
    "umrn_no": "umrn_no",
    "amount": "amount",
    "postingdate": "posting_date",
    "posting_date": "posting_date",
    "initiateddate": "initiated_date",
    "initiated_date": "initiated_date",
    "bankaccountno": "bank_account_no",
    "bank_account_no": "bank_account_no",
    "ifsccode": "ifsc_code",
    "ifsc_code": "ifsc_code",
    "mobileno": "mobile_no",
    "mobile_no": "mobile_no",
    "achtype": "ach_type",
    "ach_type": "ach_type",
    "achagent": "ach_agent",
    "ach_agent": "ach_agent",
    "bankformat": "bank_format",
    "bank_format": "bank_format",
    "status": "status",

    # -------------------------------------------------------
    # HERO - Uses customer_name (with underscores)
    # -------------------------------------------------------
    "sno": "sno",
    "umrn": "umrn",
    "amount": "amount",
    "heroagreementno": "hero_agreement_no",
    "hero_agreement_no": "hero_agreement_no",
    "referencenumber": "reference_number",
    "reference_number": "reference_number",
    "date": "date",
    "status": "status",
    "branchcode": "branch_code",
    "branch_code": "branch_code",
    "branchname": "branch_name",
    "branch_name": "branch_name",
    "createdbyusername": "created_by_username",
    "created_by_username": "created_by_username",
    "createdbyemailid": "created_by_email_id",
    "created_by_email_id": "created_by_email_id",
    "encrypttransheaderid": "encrypt_trans_header_id",
    "encrypt_trans_header_id": "encrypt_trans_header_id",

    # -------------------------------------------------------
    # KOTAK ECS - Uses customer_name (with underscores)
    # -------------------------------------------------------
    "loannumber": "loan_number",
    "loan_number": "loan_number",
    "customername": "customer_name",
    "customer_name": "customer_name",
    "vehicleno": "vehicle_no",
    "vehicle_no": "vehicle_no",
    "company": "company",
    "amount": "amount",
    "ecsdate": "ecs_date",
    "ecs_date": "ecs_date",
    "ecsstatus": "ecs_status",
    "ecs_status": "ecs_status",
    "releasestatus": "release_status",
    "release_status": "release_status",
    "released": "released",

    # -------------------------------------------------------
    # SMSQUARE - Uses customer_name (with underscores)
    # -------------------------------------------------------
    "uniqueregistrationnumber": "unique_registration_number",
    "unique_registration_number": "unique_registration_number",
    "transactionid": "transaction_id",
    "transaction_id": "transaction_id",
    "presentmentmode": "presentment_mode",
    "presentment_mode": "presentment_mode",
    "amount": "amount",
    "date": "date",
    "status": "status",
    "reasoncode": "reason_code",
    "reason_code": "reason_code",
    "reasondescription": "reason_description",
    "reason_description": "reason_description",

    # -------------------------------------------------------
    # UPI - Uses customer_name (with underscores)
    # -------------------------------------------------------
    "loannoreference": "loan_no_reference",
    "loan_no_reference": "loan_no_reference",
    "mobileno": "mobile_no",
    "mobile_no": "mobile_no",
    "transactionamount": "transaction_amount",
    "transaction_amount": "transaction_amount",
    "frequency": "frequency",
    "utrno": "utr_no",
    "utr_no": "utr_no",
    "dateofdeduction": "date_of_deduction",
    "date_of_deduction": "date_of_deduction",
    "amounttobededucted": "amount_to_be_deducted",
    "amount_to_be_deducted": "amount_to_be_deducted",
    "initiateddatetime": "initiated_datetime",
    "initiated_datetime": "initiated_datetime",
    "paymentdatetime": "payment_datetime",
    "payment_datetime": "payment_datetime",
    "paymentdescription": "payment_description",
    "payment_description": "payment_description",
    "paymentstatus": "payment_status",
    "payment_status": "payment_status",
    "notificationstatus": "notification_status",
    "notification_status": "notification_status",
    "payresponsecode": "pay_response_code",
    "pay_response_code": "pay_response_code",
    "transactionid": "transaction_id",
    "transaction_id": "transaction_id",
    "accountno": "account_no",
    "account_no": "account_no",
    "ifsccode": "ifsc_code",
    "ifsc_code": "ifsc_code",

    # -------------------------------------------------------
    # Repo
    # -------------------------------------------------------
    "agreementno": "agreement_number",
    "agreementnumber": "agreement_number",
    "agreement_number": "agreement_number",
    "regno": "registration_number",
    "registrationno": "registration_number",
    "registration_number": "registration_number",
    "mobileno": "mobile_number",

    # -------------------------------------------------------
    # Due Notice
    # -------------------------------------------------------
    "vehicleno": "vehicle_no",
    "barno": "bar_number",
    "sendto": "send_to",
    "typenotice": "type_of_notice",
    "noticetype": "type_of_notice",
    "statustype": "notice_status",
    "noticestatus": "notice_status",

    # -------------------------------------------------------
    # DIALER - Uses customer_name
    # -------------------------------------------------------
    "callno": "call_number",
    "call_no": "call_number",
    "callstarttime": "call_start_time",
    "call_start_time": "call_start_time",
    "callendtime": "call_end_time",
    "call_end_time": "call_end_time",
    "servicename": "service_name",
    "service_name": "service_name",
    "agentname": "agent_name",
    "agent_name": "agent_name",
    "status": "disp",
    "ptpdate": "ptp_date",
    "ptp_date": "ptp_date",
    "agreementdate": "agreement_date",
    "agreement_date": "agreement_date",
    "registrationnumber": "registration_number",
    "registration_number": "registration_number",
    "customercontact": "mobile",
    "customer_contact": "mobile",
    "customeraltno": "remarks",
    "customer_altno": "remarks",
    "costumeraddress": "customer_address",
    "costumer_address": "customer_address",
    "customeraddress": "customer_address",
    "consultant": "remarks",
    "vehiclewithconsultant": "remarks",
    "vehicle_with_consultant": "remarks",
    "guarantorname": "guarrantor_name",
    "guarantor_name": "guarrantor_name",
    "guarantorcontact": "guarrantor_contact",
    "guarantor_contact": "guarrantor_contact",
    "installmentduedate": "installment_due_date",
    "installment_due_date": "installment_due_date",
    "currentmonthtbc": "current_month_tbc",
    "current_month_tbc": "current_month_tbc",
    "totaldues": "total_dues",
    "total_dues": "total_dues",
    "lpidue": "lpc_dues",
    "lpi_due": "lpc_dues",
    "vasdueamount": "vas_due_amount",
    "vas_due_amount": "vas_due_amount",
    "emiduecount": "emi_due_count",
    "emi_due_count": "emi_due_count",
    "runningemicount": "running_emi_count",
    "running_emi_count": "running_emi_count",
    "executive": "executive",
    "seizedate": "seize_date",
    "seize_date": "seize_date",
    "lastreceiveddate": "last_received_date",
    "last_received_date": "last_received_date",
    "receivedamount": "remarks",
    "received_amount": "remarks",

    # -------------------------------------------------------
    # General - FALLBACK ONLY
    # -------------------------------------------------------
    "phonenumber": "phone_number",
    "phone_number": "phone_number",
    "remarks": "remarks",

    # -------------------------------------------------------
    # OpenRepo - Uses customer_name
    # -------------------------------------------------------
    "company": "company",
    "remarks": "remarks",
    "bsploading": "bsp_loading",
    "bsp_loading": "bsp_loading",
    "branch": "branch",
    "customername": "customer_name",
    "customer_name": "customer_name",
    "loanno": "loan_no",
    "loan_no": "loan_no",
    "loannumber": "loan_no",
    "loan_number": "loan_no",
    "vehicleno": "vehicle_no",
    "vehicle_no": "vehicle_no",
    "vehiclenumber": "vehicle_no",
    "vehicle_number": "vehicle_no",
    "vehicletype": "vehicle_type",
    "vehicle_type": "vehicle_type",
    "vehicleclass": "vehicle_class",
    "vehicle_class": "vehicle_class",
    "engineno": "engine_no",
    "engine_no": "engine_no",
    "chassisno": "chassis_no",
    "chassis_no": "chassis_no",
    "installmentdate": "installment_date",
    "installment_date": "installment_date",
    "dueamount": "due_amount",
    "due_amount": "due_amount",
    "emidue": "emi_due",
    "emi_due": "emi_due",
    "emidues": "emi_due",
    "emi_dues": "emi_due",

}

# ============================================================
# MODEL-AWARE CLEAN HEADER - FIXED VERSION
# ============================================================
def clean_header(header: str, model_name: str = None):
    """
    Clean header with model-aware mapping.
    This fixes the status and mobile_no field mapping issues.
    """
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

    # ============================================================
    # MODEL-AWARE MAPPING - CRITICAL FIX FOR status AND mobile_no
    # ============================================================

    # LCC uses customer_name
    if model_name == "Lcc":
        special_mapping = {
            "customername": "customer_name",
            "customer_name": "customer_name",
            "loannumber": "loan_number",
            "loan_no": "loan_number",
            "vehiclenumber": "vehicle_no",
            "vehicleno": "vehicle_no",
            "customermobile": "cust_mobile",
            "guarantormobile": "guarantor_mobile",
            "mobileno": "cust_mobile",
            "status": "latest_status",
        }
        return special_mapping.get(h, h)

    # DIALER uses customer_name
    elif model_name == "Dialer":
        special_mapping = {
            "customername": "customer_name",
            "customer_name": "customer_name",
            "customercontact": "mobile",
            "customer_contact": "mobile",
            "customeraltno": "remarks",
            "customer_altno": "remarks",
            "status": "disp",
            "mobileno": "mobile",
            "mobile_no": "mobile",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # ESEBUZZ - status -> status, mobileno -> mobile_no
    # ============================================================
    elif model_name == "EseBuzz":
        special_mapping = {
            "loanno": "loan_no",
            "loantype": "loan_type",
            "umrnno": "umrn_no",
            "amount": "amount",
            "postingdate": "posting_date",
            "initiateddate": "initiated_date",
            "customername": "customer_name",
            "bankaccountno": "bank_account_no",
            "ifsccode": "ifsc_code",
            "mobileno": "mobile_no",
            "achtype": "ach_type",
            "achagent": "ach_agent",
            "bankformat": "bank_format",
            "status": "status",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # HERO - status -> status
    # ============================================================
    elif model_name == "Hero":
        special_mapping = {
            "sno": "sno",
            "umrn": "umrn",
            "amount": "amount",
            "heroagreementno": "hero_agreement_no",
            "referencenumber": "reference_number",
            "customername": "customer_name",
            "date": "date",
            "status": "status",
            "branchcode": "branch_code",
            "branchname": "branch_name",
            "createdbyusername": "created_by_username",
            "createdbyemailid": "created_by_email_id",
            "encrypttransheaderid": "encrypt_trans_header_id",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # KOTAKECS - No status field, ignore it
    # ============================================================
    elif model_name == "KotakECS":
        special_mapping = {
            "loannumber": "loan_number",
            "customername": "customer_name",
            "vehicleno": "vehicle_no",
            "company": "company",
            "amount": "amount",
            "ecsdate": "ecs_date",
            "ecsstatus": "ecs_status",
            "releasestatus": "release_status",
            "released": "released",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # SMSQUARE - status -> status
    # ============================================================
    elif model_name == "Smsquare":
        special_mapping = {
            "uniqueregistrationnumber": "unique_registration_number",
            "transactionid": "transaction_id",
            "presentmentmode": "presentment_mode",
            "customername": "customer_name",
            "amount": "amount",
            "date": "date",
            "status": "status",
            "reasoncode": "reason_code",
            "reasondescription": "reason_description",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # UPI - status -> payment_status, mobileno -> mobile_no
    # ============================================================
    elif model_name == "Upi":
        special_mapping = {
            "loannoreference": "loan_no_reference",
            "customername": "customer_name",
            "mobileno": "mobile_no",
            "transactionamount": "transaction_amount",
            "frequency": "frequency",
            "utrno": "utr_no",
            "dateofdeduction": "date_of_deduction",
            "amounttobededucted": "amount_to_be_deducted",
            "initiateddatetime": "initiated_datetime",
            "paymentdatetime": "payment_datetime",
            "paymentdescription": "payment_description",
            "paymentstatus": "payment_status",
            "status": "payment_status",
            "notificationstatus": "notification_status",
            "payresponsecode": "pay_response_code",
            "transactionid": "transaction_id",
            "accountno": "account_no",
            "ifsccode": "ifsc_code",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # CollectionAllocations
    # ============================================================
    elif model_name == "CollectionAllocations":
        special_mapping = {
            "loannumber": "loan_number",
            "loan_no": "loan_number",
            "employeeid": "employee_id",
            "manageremployeeid": "manager_employee_id",
            "tlemployeeid": "tl_employee_id",
            "executivename": "executive_name",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # CollectionAllocations
    # ============================================================
    elif model_name == "SalesCollectionAllocations":
        special_mapping = {
            "loannumber": "loan_number",
            "loan_no": "loan_number",
            "employeeid": "employee_id",
            "manageremployeeid": "manager_employee_id",
            "tlemployeeid": "tl_employee_id",
            "executivename": "executive_name",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # Repo
    # ============================================================
    elif model_name == "Repo":
        special_mapping = {
            "agreementno": "agreement_number",
            "agreementnumber": "agreement_number",
            "regno": "registration_number",
            "registrationno": "registration_number",
            "customername": "customer_name",
            "mobileno": "mobile_number",
            "status": "status",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # DueNotice
    # ============================================================
    elif model_name == "DueNotice":
        special_mapping = {
            "loannumber": "loan_number",
            "loan_no": "loan_number",
            "vehicleno": "vehicle_no",
            "barno": "bar_number",
            "sendto": "send_to",
            "typenotice": "type_of_notice",
            "noticetype": "type_of_notice",
            "statustype": "notice_status",
            "noticestatus": "notice_status",
            "customername": "customer_name",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # Paid
    # ============================================================
    elif model_name == "Paid":
        special_mapping = {
            "loannumber": "loan_number",
            "loan_no": "loan_number",
            "vehicleno": "vehicle_no",
            "customername": "customer_name",
            "receivedamount": "received_amount",
            "voucherno": "voucher_no",
            "createdby": "created_by",
            "mobileno": "customer_mobile",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # Closed
    # ============================================================
    elif model_name == "Closed":
        special_mapping = {
            "loannumber": "loan_number",
            "loan_no": "loan_number",
            "customername": "customer_name",
            "cifid": "cif_id",
            "maturitydate": "maturity_date",
            "loanamount": "loan_amount",
            "closuredate": "loan_closure_date",
            "mobileno": "customer_number",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # Clu
    # ============================================================
    elif model_name == "Clu":
        special_mapping = {
            "loannumber": "loan_number",
            "employeeid": "employee_id",
            "employeename": "employee_name",
            "customername": "customer_name",
            "branchname": "branch_name",
            "mobilenumber": "employee_mobile_number",
            "status": "status",
            "remarks": "remarks",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # ExecutiveVisitScheduling
    # ============================================================
    elif model_name == "ExecutiveVisitScheduling":
        special_mapping = {
            "loanno": "loanno",
            "empid": "empid",
            "visitscheduledate": "visit_schedule_date",
            "visitstatus": "visit_status",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # Freshdesk
    # ============================================================
    elif model_name == "Freshdesk":
        special_mapping = {
            "ticketid": "ticket_id",
            "subject": "subject",
            "description": "description",
            "status": "status",
            "group": "group",
            "createdtime": "created_time",
            "duebytime": "due_by_time",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # EmployeeMaster
    # ============================================================
    elif model_name == "EmployeeMaster":
        special_mapping = {
            "employeenumber": "employee_number",
            "employeename": "employee_name",
            "joinedon": "joined_on",
            "currdepartment": "curr_department",
            "currlocation": "curr_location",
            "mobileno": "phone",
            "phone": "phone",
            "status": "status",
        }
        return special_mapping.get(h, h)

    # ============================================================
    # Visiter
    # ============================================================
    elif model_name == "Visiter":
        special_mapping = {
            "name": "name",
            "phonenumber": "phone_number",
            "host": "host",
            "email": "email",
            "purpose": "purpose",
            "loannumber": "loan_number",
            "vehiclenumber": "vehicle_number",
            "companyname": "company_name",
            "remarks": "remarks",
            "checkin": "check_in",
            "checkout": "check_out",
            "profilepicture": "profile_picture",
            "rating": "rating",
        }
        return special_mapping.get(h, h)
    
    elif model_name == "NocModel":
        special_mapping = {
            "customername": "customer_name",
            "customer_name": "customer_name",
            "loannumber": "loan_number",
            "loan_no": "loan_number",
            "loan_number": "loan_number",
            "vehiclenumber": "vehicle_number",
            "vehicle_no": "vehicle_number",
            "vehicle_number": "vehicle_number",
            "mobilenumber": "mobile_number",
            "mobile_no": "mobile_number",
            "mobile": "mobile_number",
            "phone": "mobile_number",
            "phonenumber": "mobile_number",
            "customer_mobile": "mobile_number",
        }
        return special_mapping.get(h, h)

    elif model_name == "OpenRepo":
        special_mapping = {
            "company": "company",
            "remarks": "remarks",
            "bsploading": "bsp_loading",
            "branch": "branch",
            "customername": "customer_name",
            "customer_name": "customer_name",
            "loanno": "loan_no",
            "loan_no": "loan_no",
            "loannumber": "loan_no",
            "loan_number": "loan_no",
            "vehicleno": "vehicle_no",
            "vehicle_no": "vehicle_no",
            "vehiclenumber": "vehicle_no",
            "vehicle_number": "vehicle_no",
            "vehicletype": "vehicle_type",
            "vehicle_type": "vehicle_type",
            "vehicleclass": "vehicle_class",
            "vehicle_class": "vehicle_class",
            "engineno": "engine_no",
            "engine_no": "engine_no",
            "chassisno": "chassis_no",
            "chassis_no": "chassis_no",
            "installmentdate": "installment_date",
            "installment_date": "installment_date",
            "dueamount": "due_amount",
            "due_amount": "due_amount",
            "emidue": "emi_due",
            "emi_due": "emi_due",
            "emidues": "emi_due",
            "emi_dues": "emi_due",
        }
        return special_mapping.get(h, h)



    # ============================================================
    # FALLBACK: Return the cleaned header as-is
    # ============================================================
    return h


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
        "sales_collection_allocations":"SalesCollectionAllocations",
        "clu": "Clu",
        "repo": "Repo",
        "paid": "Paid",
        "closed": "Closed",
        "dialer": "Dialer",
        "duenotice": "DueNotice",
        "visiter": "Visiter",
        "employee_master": "EmployeeMaster",
        "freshdesk": "Freshdesk",
        "esebuzz": "EseBuzz",
        "hero": "Hero",
        "kotakecs": "KotakECS",
        "smsquare": "Smsquare",
        "smsquare_payments": "Smsquare",
        "upi": "Upi",
        "executive_visit_scheduling": "ExecutiveVisitScheduling",
        "nocmodel": "NocModel",
        "openrepo":"OpenRepo"
    }

    model_name = mapping.get(file_type.lower())
    if not model_name:
        return None
   
    

    return apps.get_model("financehub", model_name)


# -------------------------------------------------------
# UNIQUE FIELD DETECTOR
# -------------------------------------------------------
def get_unique_field(model):
    """
    Returns natural unique field for duplicate prevention.
    """
    # Models that should allow all rows (no unique check)
    no_unique_models = ["dialer", "paid", "clu","openrepo"]

    if model.__name__.lower() in no_unique_models:
        return None
    if model.__name__ == "NocModel":
        return "vehicle_number"
    if model.__name__ == "OpenRepo":
            return "loan_no"
    

    priority = [
        "loan_number",
        "agreement_number",
        "employee_number",
        "ticket_id",
        "registration_number",
        "loannumber",
        "uniqueregistrationnumber",
    ]

    fields = {f.name for f in model._meta.fields}

    for p in priority:
        if p in fields:
            return p

    return None
