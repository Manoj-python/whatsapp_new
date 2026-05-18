from django.shortcuts import render
from django.conf import settings
import os
import tempfile
import shutil
import boto3
import uuid
from botocore.config import Config

from .utils import (
    generate_borrower_pdf,
    generate_guarantor_pdf,
    generate_co_borrower_pdf,
    generate_lokadalat_pdf,
    generate_loan_app_pdf,
    generate_ledger_pdf,
    generate_ledger_app_pdf,
    generate_loss_notice_pdf,
    generate_Letter_Head_Registration_borrower,
    generate_Letter_Head_Registration_guarantor,
    generate_demand_notice_psf,
    generate_demand_notice_sms,
    generate_due_notice_psf,
    generate_due_notice_sms,
    generate_due_notice_smf,
    generate_pre_sale_psf,
    generate_pre_sale_sms,
    generate_pre_sale_smf,
    generate_police_intimation_psf,
    generate_police_intimation_sms,
)

def create_zip(folder_path, zip_path):
    return shutil.make_archive(zip_path, 'zip', folder_path)

def upload_excel(request):

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
        with tempfile.TemporaryDirectory() as temp_dir:

            excel_path = os.path.join(temp_dir, excel_file.name)

            with open(excel_path, "wb+") as f:
                for chunk in excel_file.chunks():
                    f.write(chunk)

            # =========================================================
            # EXISTING NOTICE TYPES
            # =========================================================

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

            elif notice_type == "sree_mani_borrower":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sree_mani_borrower.docx")
                generate_borrower_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_borrower_pdf")

            elif notice_type == "sree_mani_guarantor":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sree_mani_guarantor.docx")
                generate_guarantor_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_guarantor_pdf")

            elif notice_type == "write_off_psf_borrower":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "write_off_psf_borrower.docx")
                generate_borrower_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_borrower_pdf")

            elif notice_type == "write_off_psf_guarantor":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "write_off_psf_guarantor.docx")
                generate_guarantor_pdf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "generate_guarantor_pdf")

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

            # =========================================================
            # LETTER HEAD FIXED
            # =========================================================

            elif notice_type == "ps_lh_borrower":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "PSF_Square_Letter_Head_Registration_borrower.docx")
                generate_Letter_Head_Registration_borrower(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "borrower_pdf")

            elif notice_type == "ps_lh_guarantor":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "PSF_Square_Letter_Head_Registration_guarantor.docx")
                generate_Letter_Head_Registration_guarantor(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "guarantor_pdf")

            elif notice_type == "sm_lh_borrower":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "SM_Square_Letter_Head_Registration_borrower.docx")
                generate_Letter_Head_Registration_borrower(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "borrower_pdf")

            elif notice_type == "sm_lh_guarantor":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "SM_Square_Letter_Head_Registration_guarantor.docx")
                generate_Letter_Head_Registration_guarantor(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "guarantor_pdf")

            elif notice_type == "smf_lh_borrower":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "smf_Square_Letter_Head_Registration_borrower.docx")
                generate_Letter_Head_Registration_borrower(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "borrower_pdf")

            elif notice_type == "smf_lh_guarantor":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "smf_Square_Letter_Head_Registration_guarantor.docx")
                generate_Letter_Head_Registration_guarantor(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "guarantor_pdf")

            # =========================================================
            # NEW NOTICE TYPES
            # =========================================================

            elif notice_type == "demand_notice_psf":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "Demand_Notice_Template_PSF.docx")
                generate_demand_notice_psf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "demand_notice_psf_pdf")

            elif notice_type == "demand_notice_sms":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "Demand_Notice_Template_SMS.docx")
                generate_demand_notice_sms(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "demand_notice_sms_pdf")

            elif notice_type == "due_notice_psf":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "Due_Notice_PSF_Template.docx")
                generate_due_notice_psf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "due_notice_psf_pdf")

            elif notice_type == "due_notice_sms":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "Due_Notice_SMS_Template.docx")
                generate_due_notice_sms(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "due_notice_sms_pdf")

            elif notice_type == "due_notice_smf":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "Due_Notice_SMF.docx")
                generate_due_notice_smf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "due_notice_smf_pdf")

            elif notice_type == "pre_sale_psf":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "pre_sale_psf.docx")
                generate_pre_sale_psf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "pre_sale_psf_pdf")

            elif notice_type == "pre_sale_sms":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "pre_sale_sms.docx")
                generate_pre_sale_sms(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "pre_sale_sms_pdf")

            elif notice_type == "pre_sale_smf":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "pre_sale_smf.docx")
                generate_pre_sale_smf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "pre_sale_smf_pdf")

            elif notice_type == "police_intimation_psf":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "psf_ps_intimation.docx")
                generate_police_intimation_psf(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "police_psf_pdf")

            elif notice_type == "police_intimation_sms":
                tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sms_ps_intimation.docx")
                generate_police_intimation_sms(excel_path, tpl, temp_dir)
                pdf_folder = os.path.join(temp_dir, "police_sms_pdf")

            else:
                return render(request, "notices/upload.html", {
                    "message": "❌ Invalid document type"
                })

            # Check if PDF folder exists and has files
            if not os.path.exists(pdf_folder) or not os.listdir(pdf_folder):
                raise Exception("No PDF files were generated. Please check the Excel data and template.")

            zip_name = f"{notice_type}_{uuid.uuid4().hex}"
            zip_path = create_zip(pdf_folder, os.path.join(temp_dir, zip_name))

            s3 = boto3.client(
                "s3",
                region_name=settings.AWS_S3_REGION_NAME,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version="s3v4")
            )

            bucket = settings.AWS_STORAGE_BUCKET_NAME
            s3_key = f"{notice_type}/{zip_name}.zip"

            s3.upload_file(zip_path, bucket, s3_key)

            zip_url = s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": s3_key
                },
                ExpiresIn=3600
            )

            return render(request, "notices/upload.html", {
                "message": "✅ Download Ready",
                "zip_url": zip_url
            })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error: {str(e)}")
        print(error_details)
        return render(request, "notices/upload.html", {
            "message": f"❌ Error: {str(e)}"
        })
