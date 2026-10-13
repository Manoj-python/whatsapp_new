from django import forms
from .models import *

class SmsTemplateForm(forms.ModelForm):
    class Meta:
        model=SMSTemplate
        fields='__all__'
