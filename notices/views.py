from django.shortcuts import render
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os

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


def upload_excel(request):

    if request.method == "POST":

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

        excel_dir = os.path.join(settings.MEDIA_ROOT, "excel")
        os.makedirs(excel_dir, exist_ok=True)

        fs = FileSystemStorage(location=excel_dir)
        filename = fs.save(excel_file.name, excel_file)
        excel_path = fs.path(filename)

        pdf_dir = os.path.join(settings.MEDIA_ROOT, "pdfs")
        os.makedirs(pdf_dir, exist_ok=True)

        # -----------------------------
        # SM Square
        # -----------------------------
        if notice_type == "sm_borrower":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sm_borrower_notice.docx")
            generate_borrower_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "sm_guarantor":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sm_guarantor_notice.docx")
            generate_guarantor_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "sm_co_borrower":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "sm_co_borrower_notice.docx")
            generate_co_borrower_pdf(excel_path, tpl, pdf_dir)

        # -----------------------------
        # Padmasai
        # -----------------------------
        elif notice_type == "padmasai_borrower":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "padmasai_borrower_notice.docx")
            generate_borrower_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "padmasai_guarantor":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "padmasai_guarantor_notice.docx")
            generate_guarantor_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "padmasai_co_borrower":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "co_padmasai_borrower_notice.docx")
            generate_co_borrower_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "lok_adalat":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "lokadalat_template.docx")
            generate_lokadalat_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "loan_app":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "loan_app_template.docx")
            generate_loan_app_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "ledger":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "ledger_template.docx")
            generate_ledger_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "ledger_app":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "ledger_app_template.docx")
            generate_ledger_app_pdf(excel_path, tpl, pdf_dir)

        elif notice_type == "loss_notice":

            tpl = os.path.join(settings.BASE_DIR, "templates_docx", "loss_notice_template.docx")
            generate_loss_notice_pdf(excel_path, tpl, pdf_dir)

        else:

            return render(request, "notices/upload.html", {
                "message": "❌ Invalid document type"
            })

        return render(request, "notices/upload.html", {
            "message": "✅ PDFs generated successfully"
        })

    return render(request, "notices/upload.html")