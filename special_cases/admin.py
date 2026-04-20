from django.contrib import admin

# Register your models here.
from .models import *



@admin.register(Write_Off)
class WriteOffAdmin(admin.ModelAdmin):

    # 🔍 SEARCH
    search_fields = (
        "loan_no",
        "customer_name",
        "vehicle_no",
        "cif_id",
        "guarantor_name",
    )

    # 📊 LIST VIEW
    list_display = (
        "loan_no",
        "customer_name",
        "vehicle_no",
        "loan_amount",
        "loan_date",
        "loan_closure_date",
        "loan_type",
        "branch",
        "created_at",
    )

    # 🎯 FILTERS
    list_filter = (
        "company",
        "branch",
        "loan_type",
        "loan_segment",
        "scheme_name",
        "source_name",
        "fuel_type",
        "loan_date",
        "created_at",
    )

    # 📄 PAGINATION
    list_per_page = 50

    # ⏱ DATE HIERARCHY
    date_hierarchy = "loan_date"

    # 🔒 READONLY
    readonly_fields = ("created_at",)

    # 🧾 ORGANIZED FORM
    fieldsets = (

        ("Basic Info", {
            "fields": ("company", "branch", "centre", "loan_no", "vehicle_no", "cif_id")
        }),

        ("Customer", {
            "fields": ("customer_name", "customer_mobile", "customer_father_name", "customer_address")
        }),

        ("Guarantor", {
            "fields": ("guarantor_name", "guarantor_father_name", "guarantor_mobile", "guarantor_address")
        }),

        ("Co Borrower", {
            "fields": ("co_borrower_name", "co_borrower_father_name", "co_borrower_mobile", "co_borrower_address")
        }),

        ("Vehicle Details", {
            "fields": ("make", "vehicle_class", "variant", "vehicle_type", "engine_no", "chassis_no", "fuel_type")
        }),

        ("Loan Details", {
            "fields": (
                "loan_date", "loan_amount", "tenure",
                "loan_closure_date", "maturity_date",
                "loan_type", "reason", "remarks"
            )
        }),

        ("Financial", {
            "fields": (
                "waiver", "finance_amount",
                "installment_received_amount",
                "loan_closure_amount", "difference_amount",
                "total", "irr", "amount"
            )
        }),

        ("NOC", {
            "fields": ("noc_issued_to", "noc_date")
        }),

        ("Classification", {
            "fields": ("loan_segment", "scheme_name", "source_name")
        }),

        ("Collection", {
            "fields": (
                "received_installments",
                "principal_collected", "interest_collected",
                "broken_interest_collected",
                "vas_charges_collected",
                "vas_collect_later_received"
            )
        }),

        ("Outstanding", {
            "fields": (
                "principal_outstanding", "interest_outstanding",
                "broken_interest_outstanding",
                "foreclosure_charges", "foreclosure_charges_tax",
                "vas_charges_outstanding", "lpc_outstanding",
                "vas_collect_later_outstanding"
            )
        }),

        ("Waivers / Bad Debt", {
            "fields": (
                "principal_bad_debt",
                "interest_waiver", "broken_interest_waiver",
                "vas_charges_waiver", "lpc_waiver",
                "vas_collect_later_waiver"
            )
        }),

        ("Approval", {
            "fields": ("final_approval_date",)
        }),

        ("System", {
            "fields": ("created_at",)
        }),
    )


@admin.register(Ledger)
class LedgerAdmin(admin.ModelAdmin):
    search_fields=(
        'name',
    )

@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    search_fields=(
        'centre',
        'loan_no',
        'branch',
    )

@admin.register(Dealer_TA_Balances)
class DealerAdmin(admin.ModelAdmin):
    search_fields=(
        'company',
        'dealer',
    )

# Register your models here.
@admin.register(SmsWhatsAppLog3)
class SmsWhatsAppLogAdmin3(admin.ModelAdmin):
    list_display = ("mobile", "message_type", "status", "sent_at")
    search_fields = ("mobile", "sent_text_message")

@admin.register(BulkJob3)
class BulkJobAdmin3(admin.ModelAdmin):
    list_display = ("job_id", "template_name", "status", "total_customers", "sent_count", "success_count", "failed_count")
    search_fields = ("job_id", "template_name")
