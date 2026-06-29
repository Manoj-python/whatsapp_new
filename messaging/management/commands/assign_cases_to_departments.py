import re
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from messaging2.models import Case 
from adminpanel.models import SupportGroup

class Command(BaseCommand):
    help = 'Assign cases to departments based on keywords in description'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving')
        parser.add_argument('--all', action='store_true', help='Process all cases (not only null group)')
        parser.add_argument('--default-group', type=str, default=None,
                            help='Assign unmatched cases to this group (e.g., CUSTOMER CARE)')
        parser.add_argument('--show-skipped', action='store_true', help='Print skipped cases even without dry-run')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        process_all = options['all']
        default_group_name = options['default_group']
        show_skipped = options['show_skipped']

        # ---------- 1. Keyword → Department mapping ----------
        KEYWORD_MAP = [
    # ---------- ACCOUNTS ----------
    (r'\b(bill|bills)\s*(updation|update|not updated|not update)\b', 'ACCOUNTS'),
    (r'\b(update|updation)\s+(the\s+)?bill\b', 'ACCOUNTS'),
    (r'\bnot\s+update[d]?\b', 'ACCOUNTS'),
    (r'\bplease\s+update\b', 'ACCOUNTS'),
    (r'\bupdate\s+the\s+bill\b', 'ACCOUNTS'),
    (r'\bupdate\b', 'ACCOUNTS'),                     # generic – but lower priority
    (r'\b(statutory|gst|tds|refund|adjustment|statement|statements)\b', 'ACCOUNTS'),
    (r'\b(nach|upi)\b', 'ACCOUNTS'),
    (r'\b(closing amount|closure)\b', 'ACCOUNTS'),
    (r'\breceipt\b', 'ACCOUNTS'),
    (r'\baccount\b', 'ACCOUNTS'),
    (r'\bpaid\b', 'ACCOUNTS'),                       # ← NEW
    (r'\bemi\b', 'ACCOUNTS'),                        # ← NEW
    (r'\bphone\s*pay\b', 'ACCOUNTS'),                # optional
    (r'\bclsoing\b', 'ACCOUNTS'),                    # typo for closing
    (r'\btoken\b', 'OPERATIONS'),                # "TOKEN" → OPERATIONS
(r'\brelising\s*amount\b', 'ACCOUNTS'),      # typo: "RELISING AMOUNT" → ACCOUNTS
(r'\breleasing\s*amount\b', 'ACCOUNTS'),
    # ---------- OPERATIONS ----------
    (r'\b(noc|rc|soa|insurance|cibil issue|ckyc|hpt|thumb|pdd|documents)\b', 'OPERATIONS'),
    (r'\bnach activation\b', 'OPERATIONS'),
    (r'\breleasing\b', 'OPERATIONS'),
    (r'\brealising\b', 'OPERATIONS'),                # ← NEW (typo)
    (r'\bnocs?\b', 'OPERATIONS'),                    # ← NEW (plural)

    # ---------- COLLECTIONS ----------
    (r'\b(receipt not shared|personal account|no visit|frauds|settlements)\b', 'COLLECTIONS'),
    (r'\bpayment\b', 'COLLECTIONS'),                 # exact "payment"
    (r'\bgabbar\b', 'COLLECTIONS'),                  # if needed

    # ---------- CREDIT ----------
    (r'\b(file status|fi|tvr|kyc|cibil verification|registration)\b', 'CREDIT'),
    (r'\bcivible\b', 'CREDIT'),                      # ← NEW (typo)

    # ---------- CUSTOMER CARE ----------
    (r'\b(general queries|complaints|service delay|customer handling)\b', 'CUSTOMER CARE'),
    (r'\b(test|testing|test123|mmmm|nnn)\b', 'CUSTOMER CARE'),

    # ---------- HR ----------
    (r'\b(job application|job status|salary|incentives|full & final|attendance|leaves|background verification)\b', 'HR'),
    (r'\bfraud\b', 'HR'),

    # ---------- LEGAL ----------
    (r'\b(notices|repossession|court|lok adalat|arbitration)\b', 'LEGAL'),

    # ---------- REPO ----------
    (r'\bseizing\b', 'REPO'),
    (r'\b(parking yard|auction|status)\b', 'REPO'),
    (r'\bcode of conduct\b', 'REPO'),

    # ---------- ADMIN ----------
    (r'\b(office maintenance|utilities|stationery)\b', 'ADMIN'),
]
        PRIORITY_DEPTS = ['OPERATIONS', 'ACCOUNTS', 'COLLECTIONS', 'CREDIT', 'CUSTOMER CARE', 'HR', 'LEGAL', 'REPO', 'SALES', 'ADMIN']

        # ---------- 2. Pre‑fetch/create groups ----------
        group_cache = {}
        for _, dept in KEYWORD_MAP:
            if dept not in group_cache:
                group, created = SupportGroup.objects.get_or_create(name=dept)
                group_cache[dept] = group
                if created:
                    self.stdout.write(f"Created group: {dept}")

        if default_group_name:
            default_group, _ = SupportGroup.objects.get_or_create(name=default_group_name)
            group_cache[default_group_name] = default_group

        # ---------- 3. Build queryset ----------
        qs = Case.objects.all() if process_all else Case.objects.filter(group__isnull=True)
        total = qs.count()
        self.stdout.write(f"Processing {total} cases (dry_run={dry_run})")

        updated = 0
        skipped = 0
        dept_counts = {}

        for case in qs.iterator():
            desc = (case.issue_description or '').lower()
            matched_depts = []

            for pattern, dept in KEYWORD_MAP:
                if re.search(pattern, desc):
                    matched_depts.append(dept)

            # ---------- Show skipped cases ----------
            if not matched_depts:
                skipped += 1
                if dry_run or show_skipped:
                    # Print a snippet of the description (first 80 chars)
                    snippet = desc[:80] + '...' if len(desc) > 80 else desc
                    self.stdout.write(self.style.WARNING(
                        f"⚠️ SKIPPED: {case.case_id} | '{snippet}'"
                    ))
                continue

            # Choose department with highest priority
            chosen = None
            best_idx = 999
            for dept in set(matched_depts):
                try:
                    idx = PRIORITY_DEPTS.index(dept)
                except ValueError:
                    idx = 999
                if idx < best_idx:
                    best_idx = idx
                    chosen = dept

            if chosen:
                case.group = group_cache[chosen]
                if not dry_run:
                    case.save(update_fields=['group', 'updated_at'])
                updated += 1
                dept_counts[chosen] = dept_counts.get(chosen, 0) + 1
                self.stdout.write(f"Case {case.case_id} → {chosen} (matched: {', '.join(matched_depts)})")

        # ---------- 4. (Optional) Assign unmatched to default group ----------
        if default_group_name and not dry_run:
            remaining = Case.objects.filter(group__isnull=True)
            rem_count = remaining.count()
            if rem_count:
                remaining.update(group=default_group, updated_at=timezone.now())
                self.stdout.write(f"Assigned {rem_count} remaining unmatched cases to '{default_group_name}'")

        # ---------- 5. Summary ----------
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Done. Updated {updated} cases, skipped {skipped} cases."
        ))
        if dept_counts:
            self.stdout.write("Department distribution:")
            for dept, count in sorted(dept_counts.items()):
                self.stdout.write(f"  {dept}: {count}")
