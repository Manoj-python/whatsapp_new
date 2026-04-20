from django import forms

TEMPLATE_CHOICES = [
    
    ("1", "Welcome Message (English)"),
    

]

class UploadForm3(forms.Form):
    template_choice = forms.ChoiceField(choices=TEMPLATE_CHOICES, label="Select Template")
    excel_file = forms.FileField(label="Upload Excel File")
