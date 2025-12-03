from django import forms
from django.core.exceptions import ValidationError

DATE_FORMAT = '%d/%m/%Y'

class InvoiceForm(forms.Form):
    company_name = forms.CharField(
        label="Company Name",
        max_length=100,
        initial="Konoz United Surabaya",
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    customer_name = forms.CharField(
        label="Customer Name",
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    invoice_number = forms.CharField(
        label="Invoice Number",
        max_length=50,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )

    issued_date = forms.DateField(
        label="Issued Date",
        input_formats=[DATE_FORMAT],
        widget=forms.TextInput(attrs={
            "placeholder": "dd/mm/yyyy",
            "class": "form-control date-field"
        })
    )

    due_date = forms.DateField(
        label="Due Date",
        input_formats=[DATE_FORMAT],
        widget=forms.TextInput(attrs={
            "placeholder": "dd/mm/yyyy",
            "class": "form-control date-field"
        })
    )

    # Data Reservasi / Hotel
    hotel = forms.CharField(
        label="Hotel",
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    check_in = forms.DateField(
        label="Check In",
        input_formats=[DATE_FORMAT],
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "dd/mm/yyyy", "class":"form-control date-field"})
    )
    check_out = forms.DateField(
        label="Check Out",
        input_formats=[DATE_FORMAT],
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "dd/mm/yyyy", "class":"form-control date-field"})
    )
    reservation_number = forms.CharField(
        label="Reservation Number",
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    reservation_total = forms.DecimalField(
        label="Reservation Total",
        max_digits=12,
        decimal_places=2,
        required=True,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )

    # Validasi tanggal
    def clean(self):
        cleaned = super().clean()
        issued = cleaned.get("issued_date")
        due = cleaned.get("due_date")
        check_in = cleaned.get("check_in")
        check_out = cleaned.get("check_out")

        if issued and due and issued > due:
            raise ValidationError("Due Date must be after or equal to Issued Date.")

        if check_in and check_out and check_in >= check_out:
            raise ValidationError("Check Out must be after Check In.")

        return cleaned
