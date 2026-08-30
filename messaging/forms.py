from django import forms

TEMPLATE_CHOICES = [
    ("1", "EMI Reminder (English)-[1]"),
    ("2", "EMI Tenure Reminder (Telugu)-[2]"),
    ("3", "CIBIL (English)-[3]"),
    ("4", "Vehicle Registration Slot Reminder (Telugu)-[4]"),
    ("5", "Nach Bounce Payment Reminder (English)-[5]"),
    ("6", "Nach Balance Reminder (English)-[6]"),
    ("7", "Vehicle Registration Reminder (English)-[7]"),
    ("8", "Welcome Message (English)-[8]"),
    ("9", "NOC Dispatch Template (English)-[9]"),
    ("11", "Tenure Reminder to Guarantor (Telugu)-[11]"),
    ("12", "customer_awareness_ (English)-[12]"),
    ("13", "customer_awareness_ (Telugu)-[13]"),
    ("14", "health_insurance (English)-[14]"),
    ("15", "books_pending (English)-[15]"),
    ("16", "multiple_reminders_books (English)-[16]"),
    ("17", "books_pending_second (English)-[17]"),
    ("18", "noc_address_confirmation_v2 (English)-[18]"),
    ("19", "legal_notice_customer (English)-[19]"),
    ("20", "Legal Notice to Guarantor (English)-[20]"),
    ("21", "welcome_message_pdf-[21]"),
    ("22", "public_notice-[22]"),
    ("23", "lok_adalat_notice_one (English)-[23]"),
    ("24", "lok_adalat_notice_two (Telugu)-[24]"),
    ("25", "lpc_notice (English)-[25]"),
    ("26", "kannada_lok (Kannada) Sree Mani Finance-[26]"),
    ("27", "loss_sale (English)-[27]"),
    ("28", "write_off (English)-[28]"),
    ("29", "guarantor_loss_sale (English)-[29]"),
    ("30", "gur_telugu_registration_pdf-[30]"),
    ("31", "cust_telugu_registration_pdf-[31]"),
    ("32", "guarantor_registration_pdf_english-[32]"),
    ("33", "registration_notice_borrower_pdf_english-[33]"),
    ("34", "apologize english-[34]"),
    ("35", "due_notice_borrower (English)-[35]"),
    ("36", "new_loans_te (Telugu)-[36]"),
    ("37", "presale_notices_borrower (English)-[37]"),
    ("38", "Pay Now Link (English)-[38]"),
    ("39", "RC/NOC Dispatched (English)-[39]"),
    ("40", "HPT Completed (English)-[40]"),
    ("41", "HPT Pending (English)-[41]"),
    ("42", "RC/NOC Returned (English)-[42]"),
    ("43", "SMSquare portal (English)-[43]"),
    ("44", "One Bucket (English)-[44]"),
    ("45", "Two Buckets (English)-[45]"),
    ("46", "Three Buckets and Above Customer (English)-[46]"),
    ("47", "Three Buckets and Above Guarantor (English)-[47]"),
    ("48", "doc_sms_portal (English)-[48]"),
    ("49", "Guarantor Login & Payment Link (English)-[49]"),
    

 
]

class UploadForm(forms.Form):
    template_choice = forms.ChoiceField(choices=TEMPLATE_CHOICES, label="Select Template")
    excel_file = forms.FileField(label="Upload Excel File")
