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



from django.utils import timezone

class SmsWhatsAppLog3(models.Model):
    job_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True, default='')
    mobile = models.CharField(max_length=20, db_index=True)
    template_name = models.CharField(max_length=100, blank=True, default='')
    sent_text_message = models.TextField(blank=True, default='')
    status = models.CharField(max_length=50, blank=True, default='', db_index=True)
    message_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    message_type = models.CharField(max_length=50, blank=True, default='', db_index=True)
    content_type = models.CharField(max_length=50, blank=True, default='text')
    media_file = models.FileField(upload_to='chat_media3/', blank=True, null=True)
    sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    error_message = models.TextField(blank=True, default='')
    
    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['mobile', '-sent_at']),
            models.Index(fields=['-sent_at']),
            models.Index(fields=['message_type', 'status']),
            models.Index(fields=['job_id']),
            models.Index(fields=['message_id']),
        ]
    
    def __str__(self):
        return f"{self.mobile} - {self.message_type} - {self.sent_at}"

class ChatContact3(models.Model):
    mobile = models.CharField(max_length=20, unique=True, db_index=True)
    last_msg = models.TextField(blank=True, default='')
    last_time = models.DateTimeField(default=timezone.now, db_index=True)
    last_type = models.CharField(max_length=20, blank=True, default='')
    last_status = models.CharField(max_length=225, blank=True, default='')
    unread = models.IntegerField(default=0, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-last_time']
        indexes = [
            models.Index(fields=['-last_time', 'unread']),
            models.Index(fields=['mobile']),
        ]
    
    def to_dict(self):
        return {
            'mobile': self.mobile,
            'last_msg': self.last_msg or '',
            'last_type': self.last_type,
            'last_status': self.last_status,
            'unread': self.unread,
            'last_time': self.last_time.isoformat() if self.last_time else None,
        }
    
    def __str__(self):
        return f"{self.mobile} - {self.last_msg[:30]}"

class BulkJob3(models.Model):
    job_id = models.CharField(max_length=100, unique=True, db_index=True)
    template_name = models.CharField(max_length=100)
    total_customers = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    status = models.CharField(max_length=50, default='Pending', db_index=True)
    excel_file = models.CharField(max_length=500, blank=True, default='')
    success_report = models.FileField(upload_to="reports3/", blank=True, null=True, max_length=500)
    failed_report = models.FileField(upload_to="reports3/", blank=True, null=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True,default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
