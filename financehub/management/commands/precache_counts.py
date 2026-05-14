from django.core.management.base import BaseCommand
from django.db.models import Q, Count, OuterRef, Exists
from django.db import connection
from financehub.models import Lcc, LoanStatusCache, ExecutiveVisitScheduling, CollectionAllocations, DueNotice
import hashlib
import json

class Command(BaseCommand):
    help = 'Pre-cache executive visit counts for all filter combinations'

    def handle(self, *args, **kwargs):
        self.stdout.write("Pre-caching executive visit counts...")
        
        # Common filter combinations
        filter_combinations = [
            # No filters
            {},
            # Role only
            {'role': 'CM'},
            {'role': 'TL'},
            {'role': 'EXEC'},
            # Visit filter only
            {'visit_filter': 'scheduled'},
            {'visit_filter': 'not_scheduled'},
            {'visit_filter': 'visited'},
            {'visit_filter': 'not_visited'},
            # Role + Visit combinations
            {'role': 'CM', 'visit_filter': 'scheduled'},
            {'role': 'CM', 'visit_filter': 'not_scheduled'},
            {'role': 'TL', 'visit_filter': 'scheduled'},
            {'role': 'TL', 'visit_filter': 'not_scheduled'},
            {'role': 'EXEC', 'visit_filter': 'scheduled'},
            {'role': 'EXEC', 'visit_filter': 'not_scheduled'},
        ]
        
        for filters in filter_combinations:
            self.cache_counts(filters)
        
        self.stdout.write(self.style.SUCCESS("Pre-caching complete!"))

    def cache_counts(self, filters):
        self.stdout.write(f"Caching: {filters}")
        
        # Build queryset based on filters
        qs = Lcc.objects.all()
        
        role = filters.get('role')
        visit_filter = filters.get('visit_filter')
        login_empid = filters.get('login_empid', '')
        
        if role == "CM":
            qs = qs.filter(Exists(
                CollectionAllocations.objects.filter(
                    manager_employee_id__iexact=login_empid,
                    loan_number=OuterRef('loan_number')
                )
            ))
        elif role == "TL":
            qs = qs.filter(Exists(
                CollectionAllocations.objects.filter(
                    tl_employee_id__iexact=login_empid,
                    loan_number=OuterRef('loan_number')
                )
            ))
        elif role == "EXEC":
            qs = qs.filter(Exists(
                CollectionAllocations.objects.filter(
                    employee_id__iexact=login_empid,
                    loan_number=OuterRef('loan_number')
                )
            ))
        
        if visit_filter == "scheduled":
            qs = qs.filter(Exists(
                ExecutiveVisitScheduling.objects.filter(
                    loanno=OuterRef('loan_number')
                )
            ))
        elif visit_filter == "not_scheduled":
            qs = qs.exclude(Exists(
                ExecutiveVisitScheduling.objects.filter(
                    loanno=OuterRef('loan_number')
                )
            ))
        elif visit_filter == "visited":
            qs = qs.filter(Exists(
                ExecutiveVisitScheduling.objects.filter(
                    visit_status__iexact="visited",
                    loanno=OuterRef('loan_number')
                )
            ))
        elif visit_filter == "not_visited":
            qs = qs.filter(Exists(
                ExecutiveVisitScheduling.objects.filter(
                    visit_status__iexact="not_visited",
                    loanno=OuterRef('loan_number')
                )
            ))
        
        # Get total count
        total_count = qs.count()
        
        if total_count == 0:
            return
        
        # Get status counts
        loan_numbers = list(qs.values_list('loan_number', flat=True)[:10000])
        
        closed = repo = paid = partly = not_paid = 0
        
        for i in range(0, len(loan_numbers), 2000):
            chunk = loan_numbers[i:i+2000]
            counts = LoanStatusCache.objects.filter(
                loan_number__in=chunk
            ).values('status').annotate(count=Count('status'))
            
            for item in counts:
                if item['status'] == 'CLOSED':
                    closed += item['count']
                elif item['status'] == 'REPO':
                    repo += item['count']
                elif item['status'] == 'PAID':
                    paid += item['count']
                elif item['status'] == 'PARTLY PAID':
                    partly += item['count']
                else:
                    not_paid += item['count']
        
        counted = closed + repo + paid + partly + not_paid
        if counted < len(loan_numbers):
            not_paid += (len(loan_numbers) - counted)
        
        # Create cache key
        cache_key = hashlib.md5(json.dumps(filters, sort_keys=True).encode()).hexdigest()
        
        # Save to database
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO executive_count_cache 
                (cache_key, total_count, closed_count, repo_count, paid_count, partly_paid_count, not_paid_count, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                total_count = VALUES(total_count),
                closed_count = VALUES(closed_count),
                repo_count = VALUES(repo_count),
                paid_count = VALUES(paid_count),
                partly_paid_count = VALUES(partly_paid_count),
                not_paid_count = VALUES(not_paid_count),
                updated_at = NOW()
            """, [cache_key, total_count, closed, repo, paid, partly, not_paid])
        
        self.stdout.write(f"  Saved: total={total_count}, closed={closed}, repo={repo}, paid={paid}, partly={partly}, not_paid={not_paid}")
