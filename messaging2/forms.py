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
    ("12", "NOC Address Confirmation (English)"),
    ("13", "Customer Notice (English)"),
    ("14", "Guarantor Notice (English)"),
    ("15", "Public Notice (English)"),
    ("16", "Lok Adalat (Telugu)"),
    ("17", "Disposal (English)"),
    ("18", "Kannada Lok (Kannada)"),
    ("19", "Lok HR (English)"),
    ("20", "Loss Sale PSF Borrower (English)"),
    ("21", "SMF Lok Doc Borrower (English)"),
    ("22", "SMF Lok Doc Guarantor (English)"),
    ("23", "PSF Lok Doc Borrower (English)"),
    ("24", "PSF Lok Doc Guarantor (English)"),
    ("25", "Loss Sale SMF Borrower (English)"),
    ("26", "Loss Sale SMF Guarantor (English)"),
    ("27", "Loss Sale PSF Guarantor (English)"),
    ("28", "Employee Lok PSF (English)"),
    ("29", "SMF Write Off (English)"),
    ("30", "PSF Write Off (English)"),
    ("31", "DOC NOC PSF (English)"),

    # -------- REGISTRATION (ENGLISH) --------
    ("32", "Guarantor PSF Registration Notice (English)"),
    ("33", "Guarantor SMF Registration Notice (English)"),
    ("34", "Customer PSF Registration Notice (English)"),
    ("35", "Customer SMF Registration Notice (English)"),

    # -------- REGISTRATION (TELUGU) --------
    ("36", "Customer PSF Registration Notice (Telugu)"),
    ("37", "Customer SMF Registration Notice (Telugu)"),
    ("38", "Guarantor PSF Registration Notice (Telugu)"),
    ("39", "Customer SMF Registration Notice (Telugu)"),
]


class UploadForm(forms.Form):
    template_choice = forms.ChoiceField(
        choices=TEMPLATE_CHOICES,
        label="Select Template"
    )
    excel_file = forms.FileField(label="Upload Excel File")
