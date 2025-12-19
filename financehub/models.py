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




# financehub/models.py

# financehub/models.py

class CollectionAllocations(models.Model):
    company = models.CharField(max_length=255, null=True, blank=True)

    # Core
    loan_number = models.CharField(max_length=150, db_index=True)

    # Location
    branch = models.CharField(max_length=255, null=True, blank=True)

    # =============================
    # DISPLAY FIELDS (NAMES)
    # =============================
    cm = models.CharField(max_length=255, null=True, blank=True)              # Manager Name
    tl = models.CharField(max_length=255, null=True, blank=True)              # TL Name
    executive_name = models.CharField(max_length=255, null=True, blank=True)  # Executive Name

    # =============================
    # LOGIC FIELDS (EMPLOYEE IDs)
    # =============================
    manager_employee_id = models.CharField(
        max_length=150, null=True, blank=True, db_index=True
    )

    tl_employee_id = models.CharField(
        max_length=150, null=True, blank=True, db_index=True
    )

    # 👉 THIS IS THE EXECUTIVE LOGIN ID
    employee_id = models.CharField(
        max_length=150, null=True, blank=True, db_index=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "Collection_Allocations"   # DO NOT CHANGE

    def __str__(self):
        return f"{self.loan_number}"




# financehub/models.py

class Clu(models.Model):
    employee_id = models.CharField(max_length=100, null=True, blank=True)
    employee_name = models.CharField(max_length=255, null=True, blank=True)
    employee_status = models.CharField(max_length=255, null=True, blank=True)
    designation = models.CharField(max_length=255, null=True, blank=True)
    area = models.CharField(max_length=255, null=True, blank=True)
    branch_name = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    visit_under_manager = models.CharField(max_length=255, null=True, blank=True)
    employee_mobile_number = models.CharField(max_length=50, null=True, blank=True)

    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_contact_number = models.CharField(max_length=50, null=True, blank=True)

    address_type = models.CharField(max_length=255, null=True, blank=True)
    visit_address = models.TextField(null=True, blank=True)
    is_cust_address_changed = models.CharField(max_length=50, null=True, blank=True)
    new_address = models.TextField(null=True, blank=True)

    reason_for_visit = models.TextField(null=True, blank=True)
    time_spent_in_visit_location_in_mins = models.CharField(max_length=50, null=True, blank=True)
    jointly_visited_emps = models.CharField(max_length=255, null=True, blank=True)

    loan_number = models.CharField(max_length=150, null=True, blank=True, db_index=True)

    type_of_visit = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=255, null=True, blank=True)
    sub_status = models.CharField(max_length=255, null=True, blank=True)

    payment_mode = models.CharField(max_length=100, null=True, blank=True)
    payment_towards = models.CharField(max_length=255, null=True, blank=True)
    amount_paid = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.CharField(max_length=100, null=True, blank=True)
    transaction_id = models.CharField(max_length=255, null=True, blank=True)

    promised_payment_date = models.CharField(max_length=100, null=True, blank=True)
    promised_time_slot = models.CharField(max_length=255, null=True, blank=True)
    ptp_amount = models.CharField(max_length=100, null=True, blank=True)

    is_vehicle_released = models.CharField(max_length=50, null=True, blank=True)
    amount_paid_for_vehicle_release = models.CharField(max_length=100, null=True, blank=True)
    vehicle_released_date_time = models.CharField(max_length=100, null=True, blank=True)
    reason_for_vehicle_release = models.TextField(null=True, blank=True)
    days_bw_repossessed_and_released = models.CharField(max_length=50, null=True, blank=True)

    product_name = models.CharField(max_length=255, null=True, blank=True)
    application_no = models.CharField(max_length=255, null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    loan_date = models.CharField(max_length=100, null=True, blank=True)
    loan_type = models.CharField(max_length=255, null=True, blank=True)

    fi_address = models.TextField(null=True, blank=True)
    visited_on = models.CharField(max_length=100, null=True, blank=True)
    is_visit_done_at_customer_address = models.CharField(max_length=50, null=True, blank=True)
    dist_bw_cust_addr_visit_addr = models.CharField(max_length=50, null=True, blank=True)

    last_paid = models.CharField(max_length=100, null=True, blank=True)
    cp_name = models.CharField(max_length=255, null=True, blank=True)
    ag_date = models.CharField(max_length=100, null=True, blank=True)

    vehicle_no = models.CharField(max_length=100, null=True, blank=True)
    due_date = models.CharField(max_length=100, null=True, blank=True)

    new_mobile_no = models.CharField(max_length=50, null=True, blank=True)
    visit_allocated = models.CharField(max_length=50, null=True, blank=True)

    visit_latitude_longitude = models.CharField(max_length=255, null=True, blank=True)
    customer_latitude_longitude = models.CharField(max_length=255, null=True, blank=True)

    time_difference_bw_prev_visit = models.CharField(max_length=100, null=True, blank=True)

    remarks = models.TextField(null=True, blank=True)

    l2_manager_emp_id = models.CharField(max_length=100, null=True, blank=True)
    l2_manager_emp_name = models.CharField(max_length=255, null=True, blank=True)
    l3_manager_emp_id = models.CharField(max_length=100, null=True, blank=True)
    l3_manager_emp_name = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clu"

    def __str__(self):
        return f"{self.loan_number} - {self.employee_id}"



class Repo(models.Model):
    agreement_number = models.CharField(max_length=150, db_index=True)
    registration_number = models.CharField(max_length=150, null=True, blank=True)

    company = models.CharField(max_length=255, null=True, blank=True)
    branch = models.CharField(max_length=255, null=True, blank=True)
    centre = models.CharField(max_length=255, null=True, blank=True)

    fuel_type = models.CharField(max_length=100, null=True, blank=True)
    manufacture_year = models.CharField(max_length=50, null=True, blank=True)
    chassis_number = models.CharField(max_length=255, null=True, blank=True)

    customer_name = models.CharField(max_length=255, null=True, blank=True)
    mobile_number = models.CharField(max_length=50, null=True, blank=True)
    customer_address = models.TextField(null=True, blank=True)
    guarantor_address = models.TextField(null=True, blank=True)

    make = models.CharField(max_length=255, null=True, blank=True)
    vehicle_class = models.CharField(max_length=255, null=True, blank=True)   # "Class" cannot be used
    variant = models.CharField(max_length=255, null=True, blank=True)

    seize_history = models.TextField(null=True, blank=True)
    garage_name = models.CharField(max_length=255, null=True, blank=True)
    seizer_name = models.CharField(max_length=255, null=True, blank=True)

    retry_count = models.CharField(max_length=50, null=True, blank=True)
    due_count = models.CharField(max_length=50, null=True, blank=True)
    total_due = models.CharField(max_length=100, null=True, blank=True)
    arrears = models.CharField(max_length=100, null=True, blank=True)

    consultant = models.CharField(max_length=255, null=True, blank=True)
    collection_executive = models.CharField(max_length=255, null=True, blank=True)

    status = models.CharField(max_length=255, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)

    principal_os = models.CharField(max_length=100, null=True, blank=True)
    emi_paid_count = models.CharField(max_length=50, null=True, blank=True)
    rc_details = models.TextField(null=True, blank=True)

    seize_initiated = models.CharField(max_length=50, null=True, blank=True)
    seized_date = models.CharField(max_length=100, null=True, blank=True)
    asset_in_date = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "repo"

    def __str__(self):
        return f"{self.agreement_number} - {self.customer_name}"



class Paid(models.Model):
    loan_number = models.CharField(max_length=150, db_index=True)
    vehicle_no = models.CharField(max_length=100, null=True, blank=True)

    company = models.CharField(max_length=255, null=True, blank=True)
    branch = models.CharField(max_length=255, null=True, blank=True)
    centre_name = models.CharField(max_length=255, null=True, blank=True)

    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_mobile = models.CharField(max_length=50, null=True, blank=True)

    receipt_type = models.CharField(max_length=100, null=True, blank=True)
    received_amount = models.CharField(max_length=100, null=True, blank=True)
    voucher_no = models.CharField(max_length=255, null=True, blank=True)
    received_date = models.CharField(max_length=100, null=True, blank=True)

    ledger_name = models.CharField(max_length=255, null=True, blank=True)
    instrument_no = models.CharField(max_length=255, null=True, blank=True)

    comments = models.TextField(null=True, blank=True)

    collection_executive = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.CharField(max_length=255, null=True, blank=True)

    created_date = models.CharField(max_length=100, null=True, blank=True)
    created_time = models.CharField(max_length=100, null=True, blank=True)

    loan_segment = models.CharField(max_length=255, null=True, blank=True)
    scheme_name = models.CharField(max_length=255, null=True, blank=True)

    is_loan_closure_receipt = models.CharField(max_length=20, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "paid"

    def __str__(self):
        return f"{self.loan_number} - {self.received_amount}"






class Closed(models.Model):
    branch = models.CharField(max_length=255, null=True, blank=True)
    centre = models.CharField(max_length=255, null=True, blank=True)

    loan_number = models.CharField(max_length=150, db_index=True)
    cif_id = models.CharField(max_length=150, null=True, blank=True)

    loan_date = models.CharField(max_length=100, null=True, blank=True)
    loan_amount = models.CharField(max_length=100, null=True, blank=True)
    tenure = models.CharField(max_length=50, null=True, blank=True)

    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_number = models.CharField(max_length=50, null=True, blank=True)

    loan_closure_date = models.CharField(max_length=100, null=True, blank=True)
    maturity_date = models.CharField(max_length=100, null=True, blank=True)

    type = models.CharField(max_length=255, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)

    waiver = models.CharField(max_length=100, null=True, blank=True)
    loan_value = models.CharField(max_length=100, null=True, blank=True)

    installment_received_amount = models.CharField(max_length=100, null=True, blank=True)
    loan_closure_amount = models.CharField(max_length=100, null=True, blank=True)
    difference_amount = models.CharField(max_length=100, null=True, blank=True)

    total = models.CharField(max_length=100, null=True, blank=True)
    irr = models.CharField(max_length=100, null=True, blank=True)
    amount = models.CharField(max_length=100, null=True, blank=True)

    noc_issued_to = models.CharField(max_length=255, null=True, blank=True)
    noc_date = models.CharField(max_length=100, null=True, blank=True)

    loan_segment = models.CharField(max_length=255, null=True, blank=True)
    scheme_name = models.CharField(max_length=255, null=True, blank=True)
    source_name = models.CharField(max_length=255, null=True, blank=True)

    received_installments = models.CharField(max_length=50, null=True, blank=True)

    principal_portion_collected = models.CharField(max_length=100, null=True, blank=True)
    interest_portion_collected = models.CharField(max_length=100, null=True, blank=True)
    broken_interest_collected = models.CharField(max_length=100, null=True, blank=True)
    vas_charges_collected = models.CharField(max_length=100, null=True, blank=True)

    final_approval_date = models.CharField(max_length=100, null=True, blank=True)

    principal_outstanding = models.CharField(max_length=100, null=True, blank=True)
    interest_outstanding = models.CharField(max_length=100, null=True, blank=True)
    broken_interest_outstanding = models.CharField(max_length=100, null=True, blank=True)
    foreclosure_charges_outstanding = models.CharField(max_length=100, null=True, blank=True)
    foreclosure_charges_tax_outstanding = models.CharField(max_length=100, null=True, blank=True)
    vas_charges_outstanding = models.CharField(max_length=100, null=True, blank=True)
    lpc_outstanding = models.CharField(max_length=100, null=True, blank=True)
    vas_collect_later_outstanding = models.CharField(max_length=100, null=True, blank=True)

    principal_bad_debt = models.CharField(max_length=100, null=True, blank=True)
    interest_waiver = models.CharField(max_length=100, null=True, blank=True)
    broken_interest_waiver = models.CharField(max_length=100, null=True, blank=True)
    vas_charges_waiver = models.CharField(max_length=100, null=True, blank=True)
    lpc_waiver = models.CharField(max_length=100, null=True, blank=True)
    foreclosure_charges_waiver = models.CharField(max_length=100, null=True, blank=True)
    foreclosure_charges_tax_waiver = models.CharField(max_length=100, null=True, blank=True)

    vas_collect_later_received = models.CharField(max_length=100, null=True, blank=True)
    vas_collect_later_waiver = models.CharField(max_length=100, null=True, blank=True)

    final_approval_date2 = models.CharField(max_length=100, null=True, blank=True)

    fuel_type = models.CharField(max_length=100, null=True, blank=True)
    noc_issued_date = models.CharField(max_length=100, null=True, blank=True)
    noc_number = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "closed"

    def __str__(self):
        return f"{self.loan_number} - {self.customer_name}"





class Dialer(models.Model):
    call_number = models.CharField(max_length=100, null=True, blank=True)
    call_start_time = models.CharField(max_length=100, null=True, blank=True)
    call_end_time = models.CharField(max_length=100, null=True, blank=True)

    service_name = models.CharField(max_length=255, null=True, blank=True)
    agent_name = models.CharField(max_length=255, null=True, blank=True)

    agreement_number = models.CharField(max_length=150, db_index=True)
    registration_number = models.CharField(max_length=150, null=True, blank=True)

    branch = models.CharField(max_length=255, null=True, blank=True)
    region = models.CharField(max_length=255, null=True, blank=True)

    customer_name = models.CharField(max_length=255, null=True, blank=True)
    mobile = models.CharField(max_length=50, null=True, blank=True)

    vehicle_class = models.CharField(max_length=255, null=True, blank=True)

    installment_due_date = models.CharField(max_length=100, null=True, blank=True)
    total_dues = models.CharField(max_length=100, null=True, blank=True)
    lpc_dues = models.CharField(max_length=100, null=True, blank=True)
    running_emi_count = models.CharField(max_length=50, null=True, blank=True)

    last_received_date = models.CharField(max_length=100, null=True, blank=True)
    seize_date = models.CharField(max_length=100, null=True, blank=True)

    customer_address = models.TextField(null=True, blank=True)
    executive = models.CharField(max_length=255, null=True, blank=True)

    agreement_date = models.CharField(max_length=100, null=True, blank=True)

    guarrantor_name = models.CharField(max_length=255, null=True, blank=True)
    guarrantor_contact = models.CharField(max_length=50, null=True, blank=True)

    current_month_tbc = models.CharField(max_length=100, null=True, blank=True)
    vas_due_amount = models.CharField(max_length=100, null=True, blank=True)
    handloan_due_amount = models.CharField(max_length=100, null=True, blank=True)
    emi_due_count = models.CharField(max_length=50, null=True, blank=True)

    disp = models.CharField(max_length=255, null=True, blank=True)
    ptp_date = models.CharField(max_length=100, null=True, blank=True)

    remarks = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dialer"

    def __str__(self):
        return f"{self.agreement_number} - {self.customer_name}"




class DueNotice(models.Model):
    sno = models.CharField(max_length=50, null=True, blank=True)
    company = models.CharField(max_length=255, null=True, blank=True)
    branch = models.CharField(max_length=255, null=True, blank=True)

    loan_number = models.CharField(max_length=150, db_index=True)
    vehicle_no = models.CharField(max_length=100, null=True, blank=True)

    customer_name = models.CharField(max_length=255, null=True, blank=True)
    bar_number = models.CharField(max_length=100, null=True, blank=True)

    notice_date = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "duenotice"

    def __str__(self):
        return f"{self.loan_number} - {self.customer_name}"





class Visiter(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=50, null=True, blank=True)
    host = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)

    purpose = models.CharField(max_length=255, null=True, blank=True)
    loan_number = models.CharField(max_length=150, null=True, blank=True)
    vehicle_number = models.CharField(max_length=100, null=True, blank=True)
    company_name = models.CharField(max_length=255, null=True, blank=True)

    remarks = models.TextField(null=True, blank=True)

    check_in = models.CharField(max_length=100, null=True, blank=True)
    check_out = models.CharField(max_length=100, null=True, blank=True)

    profile_picture = models.CharField(max_length=255, null=True, blank=True)
    rating = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "visiter"   # Exact table name you asked for

    def __str__(self):
        return f"{self.name} - {self.phone_number}"






class EmployeeMaster(models.Model):
    employee_number = models.CharField(max_length=100, db_index=True)
    employee_name = models.CharField(max_length=255, null=True, blank=True)

    joined_on = models.CharField(max_length=100, null=True, blank=True)
    dob = models.CharField(max_length=100, null=True, blank=True)

    curr_designation = models.CharField(max_length=255, null=True, blank=True)
    curr_department = models.CharField(max_length=255, null=True, blank=True)
    curr_location = models.CharField(max_length=255, null=True, blank=True)

    father_name = models.CharField(max_length=255, null=True, blank=True)

    phone = models.CharField(max_length=50, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)

    present_address = models.TextField(null=True, blank=True)

    reporting_to_collections = models.CharField(max_length=255, null=True, blank=True)
    reporting_to_sales = models.CharField(max_length=255, null=True, blank=True)

    official_mobile_nos = models.CharField(max_length=255, null=True, blank=True)
    official_email_ids = models.CharField(max_length=255, null=True, blank=True)

    aadhaar_number = models.CharField(max_length=100, null=True, blank=True)
    curr_organisation = models.CharField(max_length=255, null=True, blank=True)

    gross = models.CharField(max_length=100, null=True, blank=True)
    ta = models.CharField(max_length=100, null=True, blank=True)
    erepf = models.CharField(max_length=100, null=True, blank=True)
    eresi = models.CharField(max_length=100, null=True, blank=True)
    ctc = models.CharField(max_length=100, null=True, blank=True)

    status = models.CharField(max_length=100, null=True, blank=True)
    lwd = models.CharField(max_length=100, null=True, blank=True)

    tenth_memo = models.CharField(max_length=255, null=True, blank=True)
    inter_memo = models.CharField(max_length=255, null=True, blank=True)

    cheque = models.CharField(max_length=255, null=True, blank=True)
    bond = models.CharField(max_length=255, null=True, blank=True)

    notice_period = models.TextField(null=True, blank=True)
    date = models.CharField(max_length=100, null=True, blank=True)
    notice_status = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "employee_master"

    def __str__(self):
        return f"{self.employee_number} - {self.employee_name}"




class Freshdesk(models.Model):
    ticket_id = models.CharField(max_length=100, db_index=True)
    subject = models.CharField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    
    status = models.CharField(max_length=100, null=True, blank=True)
    group = models.CharField(max_length=255, null=True, blank=True)

    created_time = models.CharField(max_length=100, null=True, blank=True)
    due_by_time = models.CharField(max_length=100, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "freshdesk"

    def __str__(self):
        return f"{self.ticket_id} - {self.subject}"





class EseBuzz(models.Model):
    loanno = models.CharField(max_length=150, db_index=True, null=True, blank=True)
    loantype = models.CharField(max_length=255, null=True, blank=True)
    umrnno = models.CharField(max_length=255, null=True, blank=True)
    amount = models.CharField(max_length=100, null=True, blank=True)
    postingdate = models.CharField(max_length=100, null=True, blank=True)
    initiateddate = models.CharField(max_length=100, null=True, blank=True)
    customername = models.CharField(max_length=255, null=True, blank=True)
    bankaccountno = models.CharField(max_length=255, null=True, blank=True)
    ifsccode = models.CharField(max_length=100, null=True, blank=True)
    mobileno = models.CharField(max_length=100, null=True, blank=True)
    achtype = models.CharField(max_length=100, null=True, blank=True)
    achagent = models.CharField(max_length=255, null=True, blank=True)
    bankformat = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "esebuzz"

    def __str__(self):
        return f"{self.loanno} - {self.customername}"




class Hero(models.Model):
    sno = models.CharField(max_length=100, null=True, blank=True)
    umrn = models.CharField(max_length=255, null=True, blank=True)
    amount = models.CharField(max_length=100, null=True, blank=True)
    heroagreementno = models.CharField(max_length=255, null=True, blank=True)
    referencenumber = models.CharField(max_length=255, null=True, blank=True)
    customername = models.CharField(max_length=255, null=True, blank=True)
    date = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=255, null=True, blank=True)
    branchcode = models.CharField(max_length=100, null=True, blank=True)
    branchname = models.CharField(max_length=255, null=True, blank=True)
    createdbyusername = models.CharField(max_length=255, null=True, blank=True)
    createdbyemailid = models.CharField(max_length=255, null=True, blank=True)
    encrypttransheaderid = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "hero"

    def __str__(self):
        return f"{self.sno} - {self.customername}"



class KotakECS(models.Model):
    loannumber = models.CharField(max_length=150, db_index=True, null=True, blank=True)
    customername = models.CharField(max_length=255, null=True, blank=True)
    vehicleno = models.CharField(max_length=100, null=True, blank=True)
    company = models.CharField(max_length=255, null=True, blank=True)
    amount = models.CharField(max_length=100, null=True, blank=True)
    ecsdate = models.CharField(max_length=100, null=True, blank=True)
    ecsstatus = models.CharField(max_length=255, null=True, blank=True)
    releasestatus = models.CharField(max_length=255, null=True, blank=True)
    released = models.TextField(null=True, blank=True)


    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "kotakecs"

    def __str__(self):
        return f"{self.loannumber} - {self.customername}"




class Smsquare(models.Model):
    uniqueregistrationnumber = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    transactionid = models.CharField(max_length=255, null=True, blank=True)
    presentmentmode = models.CharField(max_length=255, null=True, blank=True)
    customername = models.CharField(max_length=255, null=True, blank=True)
    amount = models.CharField(max_length=100, null=True, blank=True)
    date = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=255, null=True, blank=True)
    reasoncode = models.CharField(max_length=100, null=True, blank=True)
    reasondescription = models.CharField(max_length=500, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "smsquare"

    def __str__(self):
        return f"{self.uniqueregistrationnumber} - {self.customername}"



class Upi(models.Model):
    loannoreference = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    customername = models.CharField(max_length=255, null=True, blank=True)
    mobileno = models.CharField(max_length=100, null=True, blank=True)
    transactionamount = models.CharField(max_length=100, null=True, blank=True)
    frequency = models.CharField(max_length=100, null=True, blank=True)
    utrno = models.CharField(max_length=255, null=True, blank=True)
    dateofdeduction = models.CharField(max_length=100, null=True, blank=True)
    amounttobededucted = models.CharField(max_length=100, null=True, blank=True)
    initiateddatetime = models.CharField(max_length=100, null=True, blank=True)
    paymentdatetime = models.CharField(max_length=100, null=True, blank=True)
    paymentdescription = models.CharField(max_length=500, null=True, blank=True)
    paymentstatus = models.CharField(max_length=255, null=True, blank=True)
    notificationstatus = models.CharField(max_length=255, null=True, blank=True)
    payresponsecode = models.CharField(max_length=100, null=True, blank=True)
    transactionid = models.CharField(max_length=255, null=True, blank=True)
    accountno = models.CharField(max_length=255, null=True, blank=True)
    ifsccode = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "upi"

    def __str__(self):
        return f"{self.loannoreference} - {self.customername}"




class ExecutiveVisitScheduling(models.Model):
    loanno = models.CharField(max_length=150, db_index=True)
    visit_schedule_date = models.DateField()
    empid = models.CharField(max_length=50, db_index=True)

    VISIT_STATUS_CHOICES = [
        ("visited", "Visited"),
        ("not_visited", "Not Visited"),
    ]

    visit_status = models.CharField(
        max_length=20,
        choices=VISIT_STATUS_CHOICES,
        null=True,
        blank=True
    )

    not_visited_reason = models.TextField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "executive_visit_scheduling"

    def __str__(self):
        return f"{self.loanno} - {self.empid}"





class UploadHistory(models.Model):
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









