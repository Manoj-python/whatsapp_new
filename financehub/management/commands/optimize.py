from django.core.management.base import BaseCommand
from django.db import connection
from django.core.cache import cache

class Command(BaseCommand):
    help = 'Optimize database for faster queries'

    def handle(self, *args, **options):
        self.stdout.write("Optimizing database...")
        
        with connection.cursor() as cursor:
            # Drop old views if exist
            cursor.execute("DROP VIEW IF EXISTS v_lcc_fast;")
            cursor.execute("DROP VIEW IF EXISTS v_payment_fast;")
            cursor.execute("DROP VIEW IF EXISTS v_notice_fast;")
            
            # Create main optimized view
            self.stdout.write("Creating v_lcc_fast...")
            cursor.execute("""
                CREATE VIEW v_lcc_fast AS
                SELECT 
                    l.id,
                    l.loan_number,
                    l.customer_name,
                    l.vehicle_no,
                    l.cust_mobile,
                    l.company,
                    l.division,
                    l.branch,
                    l.centre_name,
                    l.blc_cases,
                    l.emi_due_2,
                    l.emi_due,
                    l.month_tbc,
                    l.total_dues,
                    l.installment_date,
                    l.loan_date,
                    l.customer_address,
                    ca.cm,
                    ca.tl,
                    ca.executive_name,
                    ca.employee_id,
                    evs.visit_schedule_date,
                    evs.visit_status,
                    evs.empid,
                    evs.not_visited_reason,
                    p.received_date,
                    p.received_amount,
                    dn.send_to,
                    dn.bar_number,
                    dn.notice_date,
                    dn.type_of_notice,
                    dn.notice_status,
                    CASE WHEN c.loan_number IS NOT NULL THEN 'CLOSED'
                         WHEN r.agreement_number IS NOT NULL THEN 'REPO'
                         ELSE 'ACTIVE'
                    END as loan_status
                FROM financehub_lcc l
                LEFT JOIN (
                    SELECT loan_number, 
                           MAX(cm) as cm, 
                           MAX(tl) as tl, 
                           MAX(executive_name) as executive_name,
                           MAX(employee_id) as employee_id
                    FROM `Collection_Allocations`
                    GROUP BY loan_number
                ) ca ON ca.loan_number = l.loan_number
                LEFT JOIN (
                    SELECT loanno, 
                           MAX(visit_schedule_date) as visit_schedule_date,
                           MAX(visit_status) as visit_status,
                           MAX(empid) as empid,
                           MAX(not_visited_reason) as not_visited_reason
                    FROM executive_visit_scheduling
                    GROUP BY loanno
                ) evs ON evs.loanno = l.loan_number
                LEFT JOIN (
                    SELECT loan_number, 
                           MAX(received_date) as received_date,
                           MAX(received_amount) as received_amount
                    FROM paid
                    WHERE received_date IS NOT NULL
                    GROUP BY loan_number
                ) p ON p.loan_number = l.loan_number
                LEFT JOIN (
                    SELECT loan_number, 
                           MAX(send_to) as send_to,
                           MAX(bar_number) as bar_number,
                           MAX(notice_date) as notice_date,
                           MAX(type_of_notice) as type_of_notice,
                           MAX(notice_status) as notice_status
                    FROM duenotice
                    GROUP BY loan_number
                ) dn ON dn.loan_number = l.loan_number
                LEFT JOIN closed c ON c.loan_number = l.loan_number
                LEFT JOIN repo r ON r.agreement_number = l.loan_number;
            """)
            
            # Create indexes on original tables for faster queries
            self.stdout.write("Adding indexes...")
            try:
                cursor.execute("ALTER TABLE financehub_lcc ADD INDEX idx_loan (loan_number);")
                cursor.execute("ALTER TABLE financehub_lcc ADD INDEX idx_division (division);")
                cursor.execute("ALTER TABLE financehub_lcc ADD INDEX idx_branch (branch);")
                cursor.execute("ALTER TABLE financehub_lcc ADD INDEX idx_company (company);")
                cursor.execute("ALTER TABLE financehub_lcc ADD INDEX idx_blc (blc_cases);")
                cursor.execute("ALTER TABLE `Collection_Allocations` ADD INDEX idx_loan (loan_number);")
                cursor.execute("ALTER TABLE `Collection_Allocations` ADD INDEX idx_emp (employee_id);")
                cursor.execute("ALTER TABLE executive_visit_scheduling ADD INDEX idx_loan (loanno);")
                cursor.execute("ALTER TABLE executive_visit_scheduling ADD INDEX idx_date (visit_schedule_date);")
                cursor.execute("ALTER TABLE paid ADD INDEX idx_loan (loan_number);")
                cursor.execute("ALTER TABLE paid ADD INDEX idx_date (received_date);")
                cursor.execute("ALTER TABLE duenotice ADD INDEX idx_loan (loan_number);")
            except:
                pass  # Indexes already exist
            
            self.stdout.write(self.style.SUCCESS("✓ Optimization complete!"))
            
            # Clear cache
            cache.clear()
