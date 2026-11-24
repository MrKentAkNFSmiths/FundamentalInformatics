"""Forms for share password unlocking and reporting."""

from django import forms

from shares.models import Report


class SharePasswordForm(forms.Form):
    """Form to enter password for a protected share."""

    password = forms.CharField(
        label="",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Введите пароль доступа",
                "class": "input-field",
                "autofocus": "autofocus",
            }
        ),
    )


class ReportForm(forms.ModelForm):
    """Form to validate share abuse/copyright report."""

    class Meta:
        model = Report
        fields = ["reason", "comment"]
