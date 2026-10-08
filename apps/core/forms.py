"""Input validation for the public design preview; no operational lookup here."""
from django import forms


class TrackingReferenceForm(forms.Form):
    reference = forms.RegexField(
        regex=r"^[A-Za-z0-9-]{8,80}$",
        min_length=8,
        max_length=80,
        strip=True,
    )
