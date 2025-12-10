import pandas as pd

PANDAS_CHUNK_SIZE = 5000
BULK_BATCH_SIZE = 2000

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
