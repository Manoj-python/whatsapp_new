# your_app/models.py
from django.db import models
import datetime
class Lcc(models.Model):
    mode_of_repayment = models.CharField(max_length=255, blank=True, null=True)
    company = models.CharField(max_length=255, blank=True, null=True)
    branch = models.CharField(max_length=255, blank=True, null=True)
    centre_name = models.CharField(max_length=255, blank=True, null=True)
    loan_number = models.CharField(max_length=150, unique=True, db_index=True)
    division = models.CharField(max_length=255, blank=True, null=True)
    blc_cases = models.CharField(max_length=255, blank=True, null=True)
    vehicle_no = models.CharField(max_length=255, blank=True, null=True)
    loan_date = models.CharField(max_length=100, blank=True, null=True)  # keep raw
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    cust_mobile = models.CharField(max_length=50, blank=True, null=True)
    guarantor = models.CharField(max_length=255, blank=True, null=True)
    guarantor_mobile = models.CharField(max_length=50, blank=True, null=True)
    vehicle_type = models.CharField(max_length=255, blank=True, null=True)
    vehicle_class = models.CharField(max_length=255, blank=True, null=True)  # used "class" name avoided
    first_due_date = models.CharField(max_length=100, blank=True, null=True)  # keep raw
    last_due_date = models.CharField(max_length=100, blank=True, null=True)
    installment_date = models.CharField(max_length=100, blank=True, null=True)
    month_tbc = models.CharField(max_length=100, blank=True, null=True)
    total_dues = models.CharField(max_length=100, blank=True, null=True)
    lpc_dues = models.CharField(max_length=100, blank=True, null=True)
    vas_hl = models.CharField(max_length=100, blank=True, null=True)
    emi_due = models.CharField(max_length=100, blank=True, null=True)
    emi_due_2 = models.CharField(max_length=100, blank=True, null=True)
    running_emi = models.CharField(max_length=100, blank=True, null=True)
    paid_inst = models.CharField(max_length=100, blank=True, null=True)
    balance_inst = models.CharField(max_length=100, blank=True, null=True)
    inst = models.CharField(max_length=100, blank=True, null=True)
    last_rcvd_date = models.CharField(max_length=100, blank=True, null=True)
    seize_date = models.CharField(max_length=100, blank=True, null=True)
    customer_address = models.TextField(blank=True, null=True)
    collection_executive = models.CharField(max_length=255, blank=True, null=True)
    area = models.CharField(max_length=255, blank=True, null=True)
    source = models.CharField(max_length=255, blank=True, null=True)
    source_name = models.CharField(max_length=255, blank=True, null=True)
    lead_owner = models.CharField(max_length=255, blank=True, null=True)
    latest_status = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.loan_number} - {self.customer_name}"

class UploadHistory(models.Model):
    filename = models.CharField(max_length=255)
    uploaded_by = models.CharField(max_length=150, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    rows_in_file = models.IntegerField(default=0)
    rows_inserted = models.IntegerField(default=0)
    error = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.filename} @ {self.uploaded_at:%Y-%m-%d %H:%M}"






class Feedback(models.Model):

    FEEDBACK_CHOICES = [
        ("customer", "Customer"),
        ("guarantor", "Guarantor"),
        ("co-applicant", "Co-applicant"),
        ("others", "Others"),
    ]

    DROPDOWN_CHOICES = [
        ("PTP", "PTP"),
        ("RTP", "RTP"),
        ("WAIVER", "WAIVER"),
        ("ACCIDENT", "ACCIDENT"),
        ("PS/THEFT", "PS/THEFT"),
        ("PLEDGE", "PLEDGE"),
        ("THIRD PARTY", "THIRD PARTY"),
        ("ADDRESS SHIFTED", "ADDRESS SHIFTED"),
        ("NO RESPONSE / NOT TRACED", "NO RESPONSE / NOT TRACED"),
        ("OTHERS", "OTHERS"),
        ("WRONG NUMBER", "Wrong Number"),
        ("BILLS NOT UPDATE", "Bills Not Update"),
        ("NEW NUMBER", "New Number"),
        ("REGISTRATION COMMITMENT", "Registration Commitment"),
        ("TR SET ISSUE", "Tr Set Issue"),
        ("SVT / HANDLOAN", "SVT / Handloan"),
        ("REGISTRATION DONE", "Registration Done"),
        ("WAITING FOR NUMBER", "Waiting For Number"),
        ("PDD PENDING", "Pdd Pending"),
        ("REGISTRATION ISSUE", "Registration Issue"),

    ]

    EmpID = models.CharField(max_length=50)
    LoanNO = models.CharField(max_length=100)

    # NEW FIELDS
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    vehicle_no = models.CharField(max_length=100, null=True, blank=True)

    Date = models.DateField(default=datetime.date.today)
    Dropdown = models.CharField(max_length=100, choices=DROPDOWN_CHOICES)
    feedback_dropdwon = models.CharField(max_length=20, choices=FEEDBACK_CHOICES)
    PTPDate = models.DateField(null=True, blank=True)
    Remarks = models.TextField(blank=True, null=True)

    visiting_required = models.BooleanField(default=False)
    executive_id = models.CharField(max_length=50, null=True, blank=True)
    visit_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.LoanNO} - {self.EmpID}"









