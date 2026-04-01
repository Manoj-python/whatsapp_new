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
    ("10", "WhatsApp NOC Template (English)"),
    ("11", "Tenure Reminder to Guarantor (Telugu)"),
    ("12", "noc_address_confirmation_v2 (English)"),
    ("13", "Customer Notice (English)"),
    ("14", "Guarantor Notice (English)"),
    ("15", "Public Notice"),
    ("16", "lok_adalat (Telugu)"),
    ("17", "disposal (English)"),
    ("18", "kannada_lok (Kannada) Sree Mani Finance"),
    ("19", "lok_hr (english)"),
    ("20", "sale_loss (English)"),
    ("21", "smf_lok_doc_borrower (English)"),
    ("22", "smf_lok_doc_guarantor (English)"),
    ("23", "customer_psf_lok_doc (English)"),
    ("24", "guarantor_psf_lok_doc (English)"),
    ("25", "loss_sale_smf_borrower (English)"),
    ("26", "loss_sale_smf_guarantor (English)"),
    ("27", "loss_sale_psf_guarantor (English)"),
    ("28", "emp_lok_psf (English)"),

    

]



class UploadForm(forms.Form):
    template_choice = forms.ChoiceField(choices=TEMPLATE_CHOICES, label="Select Template")
    excel_file = forms.FileField(label="Upload Excel File")

