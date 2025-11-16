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
]

class UploadForm(forms.Form):
    template_choice = forms.ChoiceField(choices=TEMPLATE_CHOICES, label="Select Template")
    excel_file = forms.FileField(label="Upload Excel File")
