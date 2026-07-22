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
    ("10", "WhatsApp NOC Template (English)-[10]"),
    ("11", "Tenure Reminder to Guarantor (Telugu)-[11]"),
    ("12", "NOC Address Confirmation (English)-[12]"),
    ("13", "Customer Notice (English)-[13]"),
    ("14", "Guarantor Notice (English)-[14]"),
    ("15", "Public Notice (English)-[15]"),
    ("16", "Lok Adalat (Telugu)-[16]"),
    ("17", "Disposal (English)-[17]"),
    ("18", "Kannada Lok (Kannada)-[18]"),
    ("19", "Lok HR (English)-[19]"),
    ("20", "Loss Sale PSF Borrower (English)-[20]"),
    ("21", "SMF Lok Doc Borrower (English)-[21]"),
    ("22", "SMF Lok Doc Guarantor (English)-[22]"),
    ("23", "PSF Lok Doc Borrower (English)-[23]"),
    ("24", "PSF Lok Doc Guarantor (English)-[24]"),
    ("25", "Loss Sale SMF Borrower (English)-[25]"),
    ("26", "Loss Sale SMF Guarantor (English)-[26]"),
    ("27", "Loss Sale PSF Guarantor (English)-[27]"),
    ("28", "Employee Lok PSF (English)-[28]"),
    ("29", "SMF Write Off (English)-[29]"),
    ("30", "PSF Write Off Notice (English)-[30]"),
    ("31", "DOC NOC PSF (English)-[31]"),

    # -------- REGISTRATION (ENGLISH) --------
    ("32", "Guarantor PSF Registration Notice (English)-[32]"),
    ("33", "Guarantor SMF Registration Notice (English)-[33]"),
    ("34", "Customer PSF Registration Notice (English)-[34]"),
    ("35", "Customer SMF Registration Notice (English)-[35]"),

    # -------- REGISTRATION (TELUGU) --------
    ("36", "Customer PSF Registration Notice (Telugu)-[36]"),
    ("37", "Customer SMF Registration Notice (Telugu)-[37]"),
    ("38", "Guarantor PSF Registration Notice (Telugu)-[38]"),
    ("39", "Customer SMF Registration Notice (Telugu)-[39]"),
    ("40", "Guarantor PSF Write Off Notice (English)-[40]"),
    ("41", "psf_due_notice_borrower (English)"),
    ("42", "smf_due_notice_borrower (English)"),
    ("43", "new loans template (telugu)-[43]"),
    ("44", "Presale Notices PSF Borrower (English)-[44]"),
    ("45", "Presale Notices SMF Borrower (English)-[45]"),
    ("46", "Pay Now Link (English)-[46]"),
    ("47", "RC/NOC Dispatched (English)-[47]"),
    ("48", "HPT Completed (English)-[48]"),
    ("49", "HPT Pending (English)-[49]"),
    ("50", "RC/NOC Returned (English)-[50]"),
  

]


class UploadForm2(forms.Form):
    template_choice = forms.ChoiceField(
        choices=TEMPLATE_CHOICES,
        label="Select Template"
    )
    excel_file = forms.FileField(label="Upload Excel File")
