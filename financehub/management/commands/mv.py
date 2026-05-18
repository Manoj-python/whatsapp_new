from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Manage materialized views'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Drop if exists
            cursor.execute("DROP MATERIALIZED VIEW IF EXISTS mv_lcc_enriched CASCADE;")
            cursor.execute("DROP MATERIALIZED VIEW IF EXISTS mv_payment_summary CASCADE;")
            cursor.execute("DROP MATERIALIZED VIEW IF EXISTS mv_freshdesk_summary CASCADE;")
            cursor.execute("DROP MATERIALIZED VIEW IF EXISTS mv_dialer_summary CASCADE;")
            
            # Create main view
            self.stdout.write("Creating mv_lcc_enriched...")
            cursor.execute("""
                CREATE MATERIALIZED VIEW mv_lcc_enriched AS
                SELECT l.id, l.loan_number, l.customer_name, l.vehicle_no, l.cust_mobile,
                       l.company, l.division, l.branch, l.centre_name, l.blc_cases,
                       l.emi_due_2, l.emi_due, l.month_tbc, l.total_dues,
                       ca.cm, ca.tl, ca.executive_name, ca.employee_id,
                       evs.visit_schedule_date, evs.visit_status, evs.empid,
                       p.received_date, p.received_amount,
                       dn.send_to, dn.bar_number, dn.notice_date, dn.type_of_notice,
                       CASE WHEN c.loan_number IS NOT NULL THEN 'CLOSED'
                            WHEN r.agreement_number IS NOT NULL THEN 'REPO'
                            ELSE NULL END as quick_status
                FROM financehub_lcc l
                LEFT JOIN (SELECT DISTINCT ON (loan_number) * FROM "Collection_Allocations" ORDER BY loan_number, created_at DESC) ca ON ca.loan_number = l.loan_number
                LEFT JOIN (SELECT DISTINCT ON (loanno) * FROM executive_visit_scheduling ORDER BY loanno, visit_schedule_date DESC) evs ON evs.loanno = l.loan_number
                LEFT JOIN (SELECT DISTINCT ON (loan_number) * FROM paid WHERE received_date IS NOT NULL ORDER BY loan_number, received_date DESC) p ON p.loan_number = l.loan_number
                LEFT JOIN (SELECT DISTINCT ON (loan_number) * FROM duenotice ORDER BY loan_number, notice_date DESC) dn ON dn.loan_number = l.loan_number
                LEFT JOIN closed c ON c.loan_number = l.loan_number
                LEFT JOIN repo r ON r.agreement_number = l.loan_number;
            """)
            cursor.execute("CREATE INDEX ON mv_lcc_enriched(loan_number);")
            cursor.execute("CREATE INDEX ON mv_lcc_enriched(division);")
            cursor.execute("CREATE INDEX ON mv_lcc_enriched(branch);")
            
            # Payment summary
            self.stdout.write("Creating mv_payment_summary...")
            cursor.execute("""
                CREATE MATERIALIZED VIEW mv_payment_summary AS
                SELECT loan_number, SUM(CAST(received_amount AS DECIMAL)) as total_paid
                FROM paid WHERE received_amount ~ '^[0-9]+' GROUP BY loan_number;
            """)
            cursor.execute("CREATE INDEX ON mv_payment_summary(loan_number);")
            
            # Freshdesk summary
            self.stdout.write("Creating mv_freshdesk_summary...")
            cursor.execute("""
                CREATE MATERIALIZED VIEW mv_freshdesk_summary AS
                SELECT DISTINCT ON (loan_number) 
                       SUBSTRING(subject FROM '([0-9]+)') as loan_number,
                       description, status, "group", created_time
                FROM freshdesk WHERE subject ~ '[0-9]' ORDER BY loan_number, created_time DESC;
            """)
            cursor.execute("CREATE INDEX ON mv_freshdesk_summary(loan_number);")
            
            # Dialer summary
            self.stdout.write("Creating mv_dialer_summary...")
            cursor.execute("""
                CREATE MATERIALIZED VIEW mv_dialer_summary AS
                SELECT DISTINCT ON (l.loan_number) l.loan_number, d.ptp_date, d.disp, d.remarks
                FROM dialer d JOIN financehub_lcc l ON l.cust_mobile = d.mobile
                WHERE d.mobile IS NOT NULL ORDER BY l.loan_number, d.created_at DESC;
            """)
            cursor.execute("CREATE INDEX ON mv_dialer_summary(loan_number);")
            
            self.stdout.write(self.style.SUCCESS("✓ All views created!"))
