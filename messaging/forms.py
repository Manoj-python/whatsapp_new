from django import forms

TEMPLATE_CHOICES = [
    ("1", "EMI Reminder (English)"),
    ("2", "EMI Tenure Reminder (Telugu)"),
    ("3", "CIBIL (English)"),
    ("4", "Vehicle Registration Slot Reminder (Telugu)"),
    ("5", "Nach Bounce Payment Reminder (English)"),
    ("6", "Nach Balance Reminder (English)"),
    ("7", "Vehicle Registration Reminder (English)"),
    ("8", "Welcome Message (English)"),
    ("9", "NOC Dispatch Template (English)"),
    ("11", "Tenure Reminder to Guarantor (Telugu)"),
    ("12", "customer_awareness_ (English)"),
    ("13", "customer_awareness_ (Telugu)"),
    ("14", "health_insurance (English)"),
    ("15", "books_pending (English)"),
    ("16", "multiple_reminders_books (English)"),
    ("17", "books_pending_second (English)"),
    ("18", "noc_address_confirmation_v2 (English)"),
    ("19", "legal_notice_customer (English)"),
    ("20", "Legal Notice to Guarantor (English)"),    
    ("21", "welcome_message_pdf"),
    ("22", "public_notice"),
    ("23", "lok_adalat_notice_one (English)"),
    ("24", "lok_adalat_notice_two (Telugu)"),
    ("25", "lpc_notice (English)"),
    ("26", "kannada_lok (Kannada) Sree Mani Finance"),
    ("27", "loss_sale (English)"),
    ("28", "write_off (English)"),
    ("29", "guarantor_loss_sale (English)"),
    ("30", "gur_telugu_registration_pdf"),
    ("31", "cust_telugu_registration_pdf"),
    ("32", "guarantor_registration_pdf_english"),
    ("33", "registration_notice_borrower_pdf_english"),
    ("34", "apologize english")


]

class UploadForm(forms.Form):
    template_choice = forms.ChoiceField(choices=TEMPLATE_CHOICES, label="Select Template")
    excel_file = forms.FileField(label="Upload Excel File")
