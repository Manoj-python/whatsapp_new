from django.db import models

class Dealer_TA_Balances(models.Model):
    # sl_no = models.AutoField(primary_key=True)

    company = models.CharField(max_length=255)
    state = models.CharField(max_length=100)
    location = models.CharField(max_length=255)

    sales_manager = models.CharField(max_length=255)
    dealer = models.CharField(max_length=255)

    last_ta_paid_date = models.DateField(null=True, blank=True)
    latest_ta_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    last_file_date = models.DateField(null=True, blank=True)
    sanctioned_ta = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)


    ta_balance = models.IntegerField(null=True, blank=True)
    balance_pending_from = models.CharField(max_length=255,null=True, blank=True)

    # status = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.company} - {self.dealer}"



class Auction(models.Model):
    # Basic Info
    company = models.CharField(max_length=255, null=True, blank=True)
    branch = models.CharField(max_length=255, null=True, blank=True)
    centre = models.CharField(max_length=255, null=True, blank=True)

    loan_no = models.CharField(max_length=100, unique=True)
    veh_no = models.CharField(max_length=100, null=True, blank=True)
    cif_id = models.CharField(max_length=100, null=True, blank=True)

    # Loan Details
    loan_date = models.DateField(null=True, blank=True)
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    tenure = models.IntegerField(null=True, blank=True)

    # Customer Details
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_father_name = models.CharField(max_length=255, null=True, blank=True)
    customer_address = models.TextField(null=True, blank=True)
    customer_mobile = models.CharField(max_length=20, null=True, blank=True)

    # Guarantor Details
    guarantor_name = models.CharField(max_length=255, null=True, blank=True)
    guarantor_father_name = models.CharField(max_length=255, null=True, blank=True)
    guarantor_mobile = models.CharField(max_length=20, null=True, blank=True)
    guarantor_address = models.TextField(null=True, blank=True)

    # Co-Borrower Details
    co_borrower_name = models.CharField(max_length=255, null=True, blank=True)
    co_borrower_father_name = models.CharField(max_length=255, null=True, blank=True)
    co_borrower_mobile = models.CharField(max_length=20, null=True, blank=True)
    co_borrower_address = models.TextField(null=True, blank=True)

    # Dates
    loan_closure_date = models.DateField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)

    # Meta Info
    loan_type = models.CharField(max_length=100, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)

    # Financial Fields
    waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    loan_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    installment_received_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    loan_closure_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    difference_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_installment_received = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    irr = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # NOC Details
    noc_issued_to = models.CharField(max_length=255, null=True, blank=True)
    noc_date = models.DateField(null=True, blank=True)

    # Classification
    loan_segment = models.CharField(max_length=255, null=True, blank=True)
    scheme_name = models.CharField(max_length=255, null=True, blank=True)
    source_name = models.CharField(max_length=255, null=True, blank=True)

    # Collections
    received_installments = models.IntegerField(null=True, blank=True)
    principal_collected = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    interest_collected = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    broken_interest_collected = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    vas_charges_collected = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    vas_collect_later_received = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # Approval
    final_approval_date = models.DateField(null=True, blank=True)

    # Outstanding
    principal_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    interest_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    broken_interest_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    foreclosure_charges_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    foreclosure_tax_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    vas_charges_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    lpc_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    vas_collect_later_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # Bad Debt / Waivers
    principal_bad_debt = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    interest_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    broken_interest_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    vas_charges_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    lpc_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    foreclosure_charges_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    foreclosure_tax_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    vas_collect_later_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # Extra Fields
    fuel_type = models.CharField(max_length=50, null=True, blank=True)
    noc_issued_date = models.DateField(null=True, blank=True)
    noc_number = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.loan_no



class Write_Off(models.Model):
    # ================= BASIC INFO =================
    company = models.CharField(max_length=255, null=True, blank=True)
    branch = models.CharField(max_length=255, null=True, blank=True)
    centre = models.CharField(max_length=255, null=True, blank=True)

    loan_no = models.CharField(max_length=100, unique=True)
    vehicle_no = models.CharField(max_length=100, null=True, blank=True)
    cif_id = models.CharField(max_length=100, null=True, blank=True)

    # ================= CUSTOMER =================
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_mobile = models.CharField(max_length=20, null=True, blank=True)
    customer_father_name = models.CharField(max_length=255, null=True, blank=True)
    customer_address = models.TextField(null=True, blank=True)

    # ================= GUARANTOR =================
    guarantor_name = models.CharField(max_length=255, null=True, blank=True)
    guarantor_father_name = models.CharField(max_length=255, null=True, blank=True)
    guarantor_mobile = models.CharField(max_length=20, null=True, blank=True)
    guarantor_address = models.TextField(null=True, blank=True)

    # ================= CO-BORROWER =================
    co_borrower_name = models.CharField(max_length=255, null=True, blank=True)
    co_borrower_father_name = models.CharField(max_length=255, null=True, blank=True)
    co_borrower_mobile = models.CharField(max_length=20, null=True, blank=True)
    co_borrower_address = models.TextField(null=True, blank=True)

    # ================= VEHICLE DETAILS =================
    make = models.CharField(max_length=100, null=True, blank=True)
    vehicle_class = models.CharField(max_length=100, null=True, blank=True)
    variant = models.CharField(max_length=100, null=True, blank=True)
    vehicle_type = models.CharField(max_length=100, null=True, blank=True)

    engine_no = models.CharField(max_length=100, null=True, blank=True)
    chassis_no = models.CharField(max_length=100, null=True, blank=True)

    fuel_type = models.CharField(max_length=50, null=True, blank=True)

    # ================= LOAN DETAILS =================
    loan_date = models.DateField(null=True, blank=True)
    loan_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    tenure = models.IntegerField(null=True, blank=True)

    loan_closure_date = models.DateField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)

    loan_type = models.CharField(max_length=100, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)

    # ================= FINANCIAL =================
    waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    finance_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    installment_received_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    loan_closure_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    difference_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    total = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    irr = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # ================= NOC =================
    noc_issued_to = models.CharField(max_length=255, null=True, blank=True)
    noc_date = models.DateField(null=True, blank=True)

    # ================= CLASSIFICATION =================
    loan_segment = models.CharField(max_length=255, null=True, blank=True)
    scheme_name = models.CharField(max_length=255, null=True, blank=True)
    source_name = models.CharField(max_length=255, null=True, blank=True)

    # ================= COLLECTION =================
    received_installments = models.IntegerField(null=True, blank=True)

    principal_collected = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    interest_collected = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    broken_interest_collected = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    vas_charges_collected = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    vas_collect_later_received = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # ================= APPROVAL =================
    final_approval_date = models.DateField(null=True, blank=True)

    # ================= OUTSTANDING =================
    principal_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    interest_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    broken_interest_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    foreclosure_charges = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    foreclosure_charges_tax = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    vas_charges_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    lpc_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    vas_collect_later_outstanding = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    # ================= BAD DEBT / WAIVERS =================
    principal_bad_debt = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    interest_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    broken_interest_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    vas_charges_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    lpc_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    vas_collect_later_waiver = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.loan_no


class Ledger(models.Model):
    # Basic Info
    # serial_no = models.IntegerField(null=True, blank=True)
    company = models.CharField(max_length=255, null=True, blank=True)

    employee_id = models.CharField(max_length=100, unique=True)

    name = models.CharField(max_length=255)
    father_name = models.CharField(max_length=255, null=True, blank=True)

    # Contact Info
    mobile_no = models.CharField(max_length=20, null=True, blank=True)
    second_mobile_no = models.CharField(max_length=20, null=True, blank=True)
    emergency_no = models.CharField(max_length=20, null=True, blank=True)

    email = models.EmailField(null=True, blank=True)

    # Job Info
    designation = models.CharField(max_length=100, null=True, blank=True)
    reporting_manager = models.CharField(max_length=255, null=True, blank=True)

    # Work Info
    last_working_day = models.DateField(null=True, blank=True)

    # Financial
    ledger_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.employee_id})"


class SPLUploadHistory(models.Model):
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100, blank=True, null=True)  # NEW
    uploaded_by = models.CharField(max_length=150, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    total_rows = models.IntegerField(default=0)        # NEW
    processed_rows = models.IntegerField(default=0)    # NEW
    status = models.CharField(max_length=50, default="pending")  # NEW
    error_message = models.TextField(blank=True, null=True)       # NEW

    def progress_percentage(self):
        if self.total_rows == 0:
            return 0
        return int((self.processed_rows / self.total_rows) * 100)

    def __str__(self):
        return f"{self.filename} - {self.file_type} ({self.status})"

# Create your models here.
from django.db import models
from .utils import format_mobile

class SmsWhatsAppLog3(models.Model):
    MESSAGE_TYPE_CHOICES = (
        ("Sent", "Sent"),
        ("Received", "Received"),
    )

    CONTENT_TYPE_CHOICES = (
        ("text", "Text"),
        ("image", "Image"),
        ("audio", "Audio"),
        ("video", "Video"),
        ("document", "Document"),
        ("interactive", "Interactive"),
        ("unknown", "Unknown"),
    )
    
    job_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    customer_name = models.CharField(max_length=100, blank=True, null=True)
    mobile = models.CharField(max_length=30, db_index=True)
    template_name = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    message_id = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    sent_text_message = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default="Sent")
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default="text")
    media_file = models.FileField(upload_to="whatsapp_media3/", blank=True, null=True)
    media_url = models.TextField(null=True, blank=True)
    media_id = models.CharField(max_length=255, null=True, blank=True)

    def save(self, *args, **kwargs):
        """Normalize mobile before saving."""
        if self.mobile:
            self.mobile = format_mobile(self.mobile)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            # For contact list queries (mobile + latest message)
            models.Index(fields=['mobile', '-sent_at'], name='sc_idx_mobile_sent_at'),
            
            # For unread message counts
            models.Index(fields=['message_type', 'status'], name='sc_idx_type_status'),
            
            # For sorting by sent_at
            models.Index(fields=['-sent_at'], name='sc_idx_sent_at_desc'),
            
            # For webhook updates by message_id
            models.Index(fields=['message_id'], name='sc_idx_message_id'),
            
            # For job-related queries
            models.Index(fields=['job_id', 'status'], name='sc_idx_job_status'),
            
            # For searching messages
            models.Index(fields=['mobile', 'message_type', 'sent_at'], 
                        name='sc_idx_mobile_type_sent'),
        ]

    def __str__(self):
        return f"{self.mobile} - {self.message_type} - {self.content_type}"


class BulkJob3(models.Model):
    job_id = models.CharField(max_length=100, unique=True)
    template_name = models.CharField(max_length=50)
    total_customers = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="Pending")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    excel_file = models.FileField(upload_to="uploads3/")
    success_report = models.FileField(upload_to="reports3/", blank=True, null=True, max_length=500)
    failed_report = models.FileField(upload_to="reports3/", blank=True, null=True, max_length=500)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'started_at'], name='sc_idx_status_started'),
            models.Index(fields=['job_id'], name='sc_idx_job_id'),
        ]

    def __str__(self):
        return f"{self.template_name} ({self.job_id})"
