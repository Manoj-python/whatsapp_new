# financehub/forms.py
from django import forms
from .models import Feedback
import datetime


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = [
            "EmpID",
            "LoanNO",
            "customer_name",       # NEW
            "vehicle_no",          # NEW
            "Date",
            "Dropdown",
            "feedback_dropdwon",
            "PTPDate",
            "Remarks",
            "visiting_required",
            "executive_id",
            "visit_date",
        ]

        widgets = {
            "EmpID": forms.TextInput(attrs={"class": "form-control"}),
            "LoanNO": forms.TextInput(attrs={"class": "form-control"}),

            "customer_name": forms.TextInput(attrs={"class": "form-control"}),  # NEW
            "vehicle_no": forms.TextInput(attrs={"class": "form-control"}),     # NEW

            "Date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"},
                format="%Y-%m-%d"
            ),

            "Dropdown": forms.Select(attrs={"class": "form-select"}),

            "feedback_dropdwon": forms.Select(attrs={"class": "form-select"}),

            "PTPDate": forms.DateInput(attrs={"type": "date", "class": "form-control"}),

            "Remarks": forms.Textarea(attrs={"class": "form-control", "rows": 3}),

            "visiting_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),

            "executive_id": forms.TextInput(attrs={"class": "form-control"}),

            "visit_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["Date"].initial = datetime.date.today()
