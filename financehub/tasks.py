# financehub/tasks.py

from celery import shared_task
import openpyxl
import pandas as pd
import os
from django.apps import apps
from django.core.cache import cache

from .utils import clean_header, get_model_by_type
from .models import UploadHistory, LoanStatusCache

BULK_BATCH_SIZE = 2000
PANDAS_CHUNK_SIZE = 5000


# ---------------------------------------------------------
# SAFE DATE PARSER
# ---------------------------------------------------------
def parse_datetime_safe(value):
    if value in (None, "", "nan", "NaT"):
        return None

    try:
        if isinstance(value, str) and (("AM" in value.upper()) or ("PM" in value.upper())):
            try:
                return pd.to_datetime(value, format="%b %d,%Y, %I:%M:%S %p").to_pydatetime()
            except:
                pass

        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return None

        return dt.to_pydatetime()

    except Exception:
        return None


# ---------------------------------------------------------
# UNIVERSAL PROCESSOR
# ---------------------------------------------------------
@shared_task(bind=True)
def process_universal_file(self, upload_id, tmp_path, ext, file_type):

    upload = UploadHistory.objects.get(id=upload_id)

    try:
        upload.status = "processing"
        upload.save(update_fields=["status"])

        Model = get_model_by_type(file_type)
        if not Model:
            upload.status = "error"
            upload.error_message = "Invalid file type"
            upload.save()
            return

        model_fields = {f.name for f in Model._meta.fields}
        processed_rows = 0
        model_name = Model.__name__  # ✅ Get model name for header mapping

        # ================= UNIQUE LOGIC =================
        unique_field = None

        if Model.__name__ in ["Lcc", "CollectionAllocations"]:
            unique_field = "loan_number"

        elif Model.__name__ in ["Clu", "Dialer", "DueNotice", "EmployeeMaster", "Paid"]:
            unique_field = None

        else:
            for field in ["loan_number", "agreement_number", "employee_number", "ticket_id"]:
                if field in model_fields:
                    unique_field = field
                    break

        existing_values = set()
        if unique_field:
            existing_values = set(
                Model.objects.values_list(unique_field, flat=True)
            )

        # CLU duplicate prevention
        clu_existing = set()

        if Model.__name__ == "Clu":
            clu_existing = set(
                Model.objects.values_list(
                    "employee_id",
                    "visited_on"
                )
            )

        # =====================================================
        # ====================== CSV ===========================
        # =====================================================
        if ext == "csv":

            def process_chunk(chunk):
                nonlocal processed_rows, existing_values

                # ✅ CRITICAL FIX: Pass model_name to clean_header
                headers = [clean_header(h, model_name) for h in chunk.columns]
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
                            val = val.replace('\xa0', ' ').strip()

                        field_type = field.get_internal_type()

                        # visited_on special
                        if col == "visited_on":
                            dt = parse_datetime_safe(val)
                            cleaned[col] = dt if dt else None

                        elif field_type in ["DateField", "DateTimeField"]:
                            cleaned[col] = parse_datetime_safe(val)

                        elif field_type == "IntegerField":
                            try:
                                cleaned[col] = int(val) if val else None
                            except:
                                cleaned[col] = None

                        elif field_type == "DecimalField":
                            try:
                                cleaned[col] = float(val) if val else None
                            except:
                                cleaned[col] = None

                        else:
                            cleaned[col] = val if val is not None else ""

                    # DUPLICATE CHECK
                    if unique_field:
                        key = cleaned.get(unique_field)
                        if not key or key in existing_values:
                            continue
                        existing_values.add(key)

                    # CLU duplicate check
                    if Model.__name__ == "Clu":
                        visit_key = (
                            str(cleaned.get("employee_id", "")).strip(),
                            str(cleaned.get("visited_on", "")).strip(),
                        )

                        if visit_key in clu_existing:
                            continue

                        clu_existing.add(visit_key)

                    batch.append(Model(**cleaned))
                    processed_rows += 1

                    if len(batch) >= BULK_BATCH_SIZE:
                        Model.objects.bulk_create(batch, ignore_conflicts=True)
                        batch = []

                if batch:
                    Model.objects.bulk_create(batch, ignore_conflicts=True)

                upload.processed_rows = processed_rows
                upload.save(update_fields=["processed_rows"])

            reader = pd.read_csv(tmp_path, dtype=str, chunksize=PANDAS_CHUNK_SIZE)

            for chunk in reader:
                process_chunk(chunk)

        # =====================================================
        # ==================== EXCEL ===========================
        # =====================================================
        elif ext in ("xlsx", "xls"):

            wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
            ws = wb.active

            raw_headers = next(ws.iter_rows(values_only=True))
            # ✅ CRITICAL FIX: Pass model_name to clean_header
            headers = [clean_header(h, model_name) for h in raw_headers]

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

                    if isinstance(val, str):
                        val = val.strip()

                    field_type = field.get_internal_type()

                    if col == "visited_on":
                        cleaned[col] = val.strip() if val else None

                    elif field_type in ["DateField", "DateTimeField"]:
                        cleaned[col] = parse_datetime_safe(val)

                    elif field_type == "IntegerField":
                        try:
                            cleaned[col] = int(val) if val else None
                        except:
                            cleaned[col] = None

                    elif field_type == "DecimalField":
                        try:
                            cleaned[col] = float(val) if val else None
                        except:
                            cleaned[col] = None

                    else:
                        cleaned[col] = val if val is not None else ""

                if unique_field:
                    key = cleaned.get(unique_field)
                    if not key or key in existing_values:
                        continue
                    existing_values.add(key)

                # CLU duplicate check
                if Model.__name__ == "Clu":
                    visit_key = (
                        str(cleaned.get("employee_id", "")).strip(),
                        str(cleaned.get("visited_on", "")).strip(),
                    )

                    if visit_key in clu_existing:
                        continue

                    clu_existing.add(visit_key)

                batch.append(Model(**cleaned))
                processed_rows += 1

                if len(batch) >= BULK_BATCH_SIZE:
                    Model.objects.bulk_create(batch, ignore_conflicts=True)
                    batch = []

            if batch:
                Model.objects.bulk_create(batch, ignore_conflicts=True)

        # FINAL UPDATE
        upload.processed_rows = processed_rows
        upload.status = "completed"
        upload.save()

        if Model.__name__ == "Lcc":
            cache.delete('dropdowns_final_v3')
            deleted_count = LoanStatusCache.objects.all().delete()
            print(f"Cleared LoanStatusCache after LCC upload")

    except Exception as e:
        upload.status = "error"
        upload.error_message = str(e)
        upload.save()
        import traceback
        traceback.print_exc()

    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except:
            pass
