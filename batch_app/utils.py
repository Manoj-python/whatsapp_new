# batch_app/utils.py - ADD FULL BATCH SUPPORT

import re
import boto3
import pandas as pd
import io
from django.conf import settings


def format_mobile(x: str) -> str:
    """Format mobile number to +91 format"""
    if not x:
        return ""
    s = str(x).strip()
    digits = re.sub(r"\D", "", s)
    
    if digits.startswith("91") and len(digits) >= 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) >= 10:
        digits = digits[-10:]
    
    return f"+91{digits}" if len(digits) == 10 else x


def read_excel_from_s3(s3_key):
    """Read Excel file directly from S3"""
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        
        obj = s3.get_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=s3_key
        )
        
        excel_data = obj['Body'].read()
        df = pd.read_excel(io.BytesIO(excel_data), dtype=str).fillna('')
        
        return df
        
    except Exception as e:
        print(f"❌ Error reading from S3: {e}")
        return None


def get_total_customers_from_s3(s3_key):
    """Get total customer count from S3 Excel"""
    df = read_excel_from_s3(s3_key)
    if df is not None:
        return len(df)
    return 0


def get_batch_from_s3(s3_key, start_idx, batch_size=1000):
    """Get a specific batch of customers from S3 Excel"""
    df = read_excel_from_s3(s3_key)
    if df is None:
        return [], 0
    
    end_idx = min(start_idx + batch_size, len(df))
    batch_df = df.iloc[start_idx:end_idx]
    
    return batch_df.to_dict('records'), len(batch_df)


# ===== NEW: Get all customers from S3 =====
def get_all_customers_from_s3(s3_key):
    """Get ALL customers from S3 Excel (for FULL batch)"""
    df = read_excel_from_s3(s3_key)
    if df is None:
        return [], 0
    
    return df.to_dict('records'), len(df)


# ===== NEW: Get batches as generator =====
def get_batches_from_s3(s3_key, batch_size=1000):
    """Generator to yield batches from S3 Excel"""
    df = read_excel_from_s3(s3_key)
    if df is None:
        return
    
    total = len(df)
    for i in range(0, total, batch_size):
        end_idx = min(i + batch_size, total)
        batch_df = df.iloc[i:end_idx]
        yield batch_df.to_dict('records'), i, end_idx
