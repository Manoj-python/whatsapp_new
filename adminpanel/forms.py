# forms.py
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

class ForgotPasswordForm(forms.Form):
    identifier = forms.CharField(
        label="Username or Email",
        max_length=150,
        help_text="Enter your username or registered email."
    )

    def clean_identifier(self):
        identifier = self.cleaned_data['identifier']
        user = None
        
        # Try to find user by username first
        try:
            user = User.objects.get(username=identifier)
        except User.DoesNotExist:
            # If not found, try by email
            try:
                user = User.objects.get(email=identifier)
            except User.DoesNotExist:
                raise ValidationError("No user found with that username or email.")
        
        # Check if user has an agent profile (optional, but good for your use case)
        # if not hasattr(user, 'agent_profile'):
        #     raise ValidationError("This user is not an agent.")
        
        self.cleaned_data['user'] = user
        return identifier


class OTPVerificationForm(forms.Form):
    otp = forms.CharField(
        label="OTP",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={'class': 'text-center', 'style': 'font-size:24px;letter-spacing:4px;'})
    )


class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput,
        min_length=8
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput
    )

    def clean(self):
        cleaned_data = super().clean()
        pwd = cleaned_data.get('new_password')
        confirm = cleaned_data.get('confirm_password')
        if pwd and confirm and pwd != confirm:
            raise ValidationError("Passwords do not match.")
        return cleaned_data
