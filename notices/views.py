from django.shortcuts import render
from django.conf import settings
import os
import tempfile
import shutil
import boto3
import uuid
from botocore.config import Config   # ✅ IMPORTANT

from .utils import (
    generate_borrower_pdf,
    generate_guarantor_pdf,
    generate_co_borrower_pdf,
    generate_lokadalat_pdf,
    generate_loan_app_pdf,
    generate_ledger_pdf,
    generate_ledger_app_pdf,
    generate_loss_notice_pdf
)


def create_zip(folder_path, zip_path):
    return shutil.make_archive(zip_path, 'zip', folder_path)


def upload_excel(request):

    # ✅ ALWAYS RETURN FOR GET
    if request.method != "POST":
        return render(request, "notices/upload.html")

    notice_type = request.POST.get("notice_type")
    excel_file = request.FILES.get("excel")

    if not notice_type:
        return render(request, "notices/upload.html", {
            "message": "❌ Please select a notice type"
        })

    if not excel_file:
        return render(request, "notices/upload.html", {
            "message": "❌ Please upload Excel"
        })

    try:
        # 🔥 TEMP DIRECTORY (NO MEDIA)
        with tempfile.TemporaryDirectory() as temp_dir:

            # Save Excel temporarily
            excel_path = os.path.join(temp_dir, excel_file.name)

            with open(excel_path, "wb+") as f:
                for chunk in excel_file.chunks():
                    f.write(chunk)

            # -----------------------------
            # SAME LOGIC (UNCHANGED)
            # -----------------------------
            if notice_type == "sm_borrower":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sm_borrower_notice.docx")
                generate_borrower_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_borrower_pdf")

            elif notice_type == "sm_guarantor":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sm_guarantor_notice.docx")
                generate_guarantor_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_guarantor_pdf")

            elif notice_type == "sm_co_borrower":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sm_co_borrower_notice.docx")
                generate_co_borrower_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_co_borrower_pdf")

            elif notice_type == "padmasai_borrower":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "padmasai_borrower_notice.docx")
                generate_borrower_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_borrower_pdf")

            elif notice_type == "padmasai_guarantor":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "padmasai_guarantor_notice.docx")
                generate_guarantor_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_guarantor_pdf")

            elif notice_type == "padmasai_co_borrower":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "co_padmasai_borrower_notice.docx")
                generate_co_borrower_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_co_borrower_pdf")

            elif notice_type == "lok_adalat":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "lokadalat_template.docx")
                generate_lokadalat_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_lokadalat_pdf")

            elif notice_type == "loan_app":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "loan_app_template.docx")
                generate_loan_app_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_loan_app_pdf")

            elif notice_type == "ledger":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "ledger_template.docx")
                generate_ledger_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_ledger_pdf")

            elif notice_type == "ledger_app":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "ledger_app_template.docx")
                generate_ledger_app_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_ledger_app_pdf")

            elif notice_type == "loss_notice":

                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "loss_notice_template.docx")
                generate_loss_notice_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "loss_notice_pdf")

            else:
                return render(request, "notices/upload.html", {
                    "message": "❌ Invalid document type"
                })

            # -----------------------------
            # ZIP ONLY PDF FOLDER
            # -----------------------------
            zip_name = f"{notice_type}_{uuid.uuid4().hex}"
            zip_path = create_zip(pdf_folder, os.path.join(temp_dir, zip_name))

            # -----------------------------
            # UPLOAD TO S3 (FIXED ✅)
            # -----------------------------
            s3 = boto3.client(
                "s3",
                region_name=settings.AWS_S3_REGION_NAME,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4")  # 🔥 FIX
            )

            bucket = settings.AWS_STORAGE_BUCKET_NAME
            s3_key = f"{notice_type}/{zip_name}.zip"

            s3.upload_file(zip_path, bucket, s3_key)

            # -----------------------------
            # SIGNED DOWNLOAD URL
            # -----------------------------
            zip_url = s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket,
                    'Key': s3_key
                },
                ExpiresIn=3600
            )

            return render(request, "notices/upload.html", {
                "message": "✅ Download Ready",
                "zip_url": zip_url
            })

    except Exception as e:
        return render(request, "notices/upload.html", {
            "message": f"❌ Error: {str(e)}"
        })
