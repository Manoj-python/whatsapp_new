from celery import shared_task
import openpyxl
import pandas as pd
import os
from datetime import date

from django.db import transaction
from django.apps import apps

from .utils import clean_header

from .models import UploadHistory

BULK_BATCH_SIZE = 2000
PANDAS_CHUNK_SIZE = 5000


# ---------------------------------------------------------
# SAFE DATE PARSER (FIXES Excel 00:00:00 ISSUE)
# ---------------------------------------------------------
def parse_date_safe(value):
    """
    Converts Excel / CSV / string / datetime into Python date.
    Handles:
    - Excel date cells
    - '2025-01-15'
    - '2025-01-15 00:00:00'
    - empty / NaN
    """
    if value in (None, "", "nan", "NaT"):
        return None

    try:
        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date()
    except Exception:
        return None


# ---------------------------------------------------------
# MODEL RESOLVER
# ---------------------------------------------------------
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
        "esebuzz": "EseBuzz",
        "hero": "Hero",
        "kotakecs": "KotakECS",
        "smsquare": "Smsquare",
        "upi": "Upi",
        "executive_visit_scheduling": "ExecutiveVisitScheduling",

    }

    model_name = mapping.get(file_type.lower())
    if not model_name:
        return None

    return apps.get_model("financehub", model_name)

# ---------------------------------------------------------
# UNIVERSAL FILE PROCESSOR (FINAL FIXED VERSION)
# ---------------------------------------------------------
@shared_task(bind=True)
def process_universal_file(self, upload_id, tmp_path, ext, file_type):

    upload = UploadHistory.objects.get(id=upload_id)

    try:
        if upload.status == "completed":
            return

        upload.status = "processing"
        upload.save(update_fields=["status"])

        Model = get_model_by_type(file_type)
        if not Model:
            upload.status = "error"
            upload.error_message = f"Invalid file_type: {file_type}"
            upload.save()
            return

        model_fields = {f.name for f in Model._meta.fields}
        processed_rows = 0

        # =====================================================
        # 🔥 MODEL-SPECIFIC UNIQUE LOGIC (FIXED)
        # =====================================================
        unique_field = None

        if Model.__name__ == "Lcc":
            unique_field = "loan_number"

        elif Model.__name__ == "CollectionAllocations":
            unique_field = "loan_number"

        elif Model.__name__ == "DueNotice":
            unique_field = None   # ✅ allow duplicates

        elif Model.__name__ == "Dialer":
            unique_field = None   # ✅ allow duplicates

        else:
            for field in ["loan_number", "agreement_number", "employee_number", "ticket_id"]:
                if field in model_fields:
                    unique_field = field
                    break

        # =====================================================
        # 🔥 EXISTING VALUES (ONLY FOR UNIQUE MODELS)
        # =====================================================
        existing_values = set()
        if unique_field:
            existing_values = set(
                Model.objects.values_list(unique_field, flat=True)
            )

        # =====================================================
        # ====================== CSV ===========================
        # =====================================================
        if ext == "csv":

            def process_chunk(chunk):
                nonlocal processed_rows, existing_values

                headers = [clean_header(h) for h in chunk.columns]
                chunk.columns = headers
                header_map = {h: h for h in headers if h in model_fields}

                upload.total_rows += len(chunk)
                upload.save(update_fields=["total_rows"])

                batch = []

                for row in chunk.to_dict("records"):
                    cleaned = {}

                    for col, val in row.items():
                        if col not in header_map:
                            continue

                        field = Model._meta.get_field(col)

                        if isinstance(val, str):
                            val = val.replace('\xa0', ' ')
                            val = val.encode("latin-1", "ignore").decode("latin-1")
                            val = val.strip()

                        if field.get_internal_type() == "DateField":
                            cleaned[col] = parse_date_safe(val)
                        else:
                            cleaned[col] = val if val is not None else ""

                    # ✅ DUPLICATE CHECK (ONLY FOR LCC ETC)
                    if unique_field:
                        val = cleaned.get(unique_field)

                        if not val or val in existing_values:
                            continue

                        existing_values.add(val)

                    batch.append(Model(**cleaned))
                    processed_rows += 1

                    if len(batch) >= BULK_BATCH_SIZE:
                        with transaction.atomic():
                            Model.objects.bulk_create(
                                batch,
                                ignore_conflicts=True
                            )
                        batch = []

                if batch:
                    with transaction.atomic():
                        Model.objects.bulk_create(
                            batch,
                            ignore_conflicts=True
                        )

                upload.processed_rows = processed_rows
                upload.save(update_fields=["processed_rows"])

            try:
                reader = pd.read_csv(
                    tmp_path,
                    dtype=str,
                    keep_default_na=False,
                    chunksize=PANDAS_CHUNK_SIZE,
                    encoding="utf-8",
                    engine="python",
                )

                for chunk in reader:
                    process_chunk(chunk)

            except UnicodeDecodeError:

                reader = pd.read_csv(
                    tmp_path,
                    dtype=str,
                    keep_default_na=False,
                    chunksize=PANDAS_CHUNK_SIZE,
                    encoding="latin-1",
                    engine="python",
                )

                for chunk in reader:
                    process_chunk(chunk)

        # =====================================================
        # ==================== EXCEL ===========================
        # =====================================================
        elif ext in ("xlsx", "xls"):

            wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
            ws = wb.active

            raw_headers = next(ws.iter_rows(values_only=True))
            headers = [clean_header(h) for h in raw_headers]

            header_map = {h: h for h in headers if h in model_fields}

            upload.total_rows = max(ws.max_row - 1, 0)
            upload.save(update_fields=["total_rows"])

            batch = []

            for row in ws.iter_rows(min_row=2, values_only=True):

                if not row or all(v in (None, "", " ") for v in row):
                    continue

                row_dict = dict(zip(headers, row))
                cleaned = {}

                for col, val in row_dict.items():
                    if col not in header_map:
                        continue

                    field = Model._meta.get_field(col)

                    if field.get_internal_type() == "DateField":
                        cleaned[col] = parse_date_safe(val)
                    else:
                        cleaned[col] = "" if val is None else str(val)

                # ✅ DUPLICATE CHECK (ONLY FOR LCC ETC)
                if unique_field:
                    val = cleaned.get(unique_field)

                    if not val or val in existing_values:
                        continue

                    existing_values.add(val)

                batch.append(Model(**cleaned))
                processed_rows += 1

                if len(batch) >= BULK_BATCH_SIZE:
                    with transaction.atomic():
                        Model.objects.bulk_create(
                            batch,
                            ignore_conflicts=True
                        )
                    batch = []

            if batch:
                with transaction.atomic():
                    Model.objects.bulk_create(
                        batch,
                        ignore_conflicts=True
                    )

            upload.processed_rows = processed_rows
            upload.save(update_fields=["processed_rows"])

        upload.status = "completed"
        upload.save(update_fields=["status"])

    except Exception as e:
        upload.status = "error"
        upload.error_message = str(e)
        upload.save()

    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
