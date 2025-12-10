# financehub/tasks.py

from celery import shared_task
import pandas as pd
import openpyxl
import os
from django.db import transaction
from .models import Lcc, UploadHistory
from financehub.utils import normalize_date, PANDAS_CHUNK_SIZE, BULK_BATCH_SIZE


@shared_task(queue="whatsapp_main")
def process_loan_file(upload_id, tmp_path, ext):
    upload = UploadHistory.objects.get(id=upload_id)

    total_rows = 0
    total_inserted = 0

    try:
        # CSV reader
        if ext == "csv":
            reader = pd.read_csv(
                tmp_path,
                dtype=str,
                keep_default_na=False,
                chunksize=PANDAS_CHUNK_SIZE,
                encoding="utf-8"
            )

        else:
            # Excel reader
            wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
            ws = wb.active

            rows = list(ws.iter_rows(values_only=True))
            headers = [str(h).strip().lower().replace(" ", "_") for h in rows[0]]

            df_full = pd.DataFrame(rows[1:], columns=headers).fillna("")

            reader = (df_full[i:i + PANDAS_CHUNK_SIZE]
                      for i in range(0, len(df_full), PANDAS_CHUNK_SIZE))

        model_fields = {f.name for f in Lcc._meta.fields}
        existing = set(Lcc.objects.values_list("loan_number", flat=True))

        for df in reader:
            df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

            if "class" in df.columns:
                df.rename(columns={"class": "vehicle_class"}, inplace=True)

            total_rows += len(df)
            records = []

            for row in df.to_dict(orient="records"):
                ln = str(row.get("loan_number", "")).strip()
                if not ln or ln in existing:
                    continue

                for col in [
                    "loan_date", "first_due_date", "last_due_date",
                    "installment_date", "last_rcvd_date", "seize_date"
                ]:
                    row[col] = normalize_date(row.get(col, ""))

                cleaned = {k: v for k, v in row.items() if k in model_fields}

                records.append(Lcc(**cleaned))
                existing.add(ln)

            if records:
                with transaction.atomic():
                    for i in range(0, len(records), BULK_BATCH_SIZE):
                        batch = records[i:i + BULK_BATCH_SIZE]
                        Lcc.objects.bulk_create(batch)
                        total_inserted += len(batch)

        upload.rows_in_file = total_rows
        upload.rows_inserted = total_inserted
        upload.save()

    except Exception as e:
        upload.error = str(e)
        upload.save()

    finally:
        try:
            os.remove(tmp_path)
        except:
            pass
